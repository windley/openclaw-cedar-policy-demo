#!/usr/bin/env python3
"""
Simple Cedar PDP HTTP server for OpenClaw authorization demo.

This server wraps the Cedar CLI and provides an HTTP API for authorization requests.
"""
import json
import mimetypes
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hitl.store import ApprovalStore

try:
    from hitl.webauthn_flow import WebAuthnManager
except ImportError:
    WebAuthnManager = None

# Paths
REPO_ROOT = Path(__file__).parent.parent
CEDAR_DIR = REPO_ROOT / "policies" / "cedar"
SCHEMA = CEDAR_DIR / "schema.cedarschema"
POLICIES = CEDAR_DIR / "policies.cedar"
POLICIES_TPE = CEDAR_DIR / "policies-tpe.cedar"
POLICIES_DELEGATION = CEDAR_DIR / "policies-delegation.cedar"
POLICIES_HITL = CEDAR_DIR / "policies-hitl.cedar"
ENTITIES = CEDAR_DIR / "entities.json"
HITL_DIR = Path(__file__).parent / "hitl"
STATIC_DIR = HITL_DIR / "static"
MAILBOX_DIR = Path(__file__).parent / "mailbox" / "sent"
CREDENTIALS_PATH = HITL_DIR / ".webauthn-credentials.json"

APPROVALS = ApprovalStore()
WEBAUTHN = WebAuthnManager(CREDENTIALS_PATH) if WebAuthnManager else None

def build_combined_policies():
    """Combine base policies with optional demo policy files into a temp file."""
    content = POLICIES.read_text()
    if POLICIES_DELEGATION.exists():
        content += "\n\n" + POLICIES_DELEGATION.read_text()
    if POLICIES_HITL.exists():
        content += "\n\n" + POLICIES_HITL.read_text()
    return content

# Build combined policies once at startup
_combined_policies_content = build_combined_policies()

def get_combined_policies_file():
    """Write combined policies to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.cedar', delete=False)
    f.write(_combined_policies_content)
    f.close()
    return f.name

class CedarPDPHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cedar authorization requests."""

    def do_POST(self):
        """Handle POST requests to /authorize or /query-constraints."""
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            request_data = json.loads(body)

            parsed = urlparse(self.path)
            if parsed.path == "/authorize":
                self._handle_authorize(request_data)
            elif parsed.path == "/query-constraints":
                self._handle_query_constraints(request_data)
            elif parsed.path == "/approvals":
                self._handle_create_approval(request_data)
            elif parsed.path == "/webauthn/register/verify":
                self._handle_register_verify(request_data)
            elif parsed.path == "/webauthn/authenticate/verify":
                self._handle_authenticate_verify(request_data)
            else:
                self.send_error(404, "Not Found")

        except Exception as e:
            error_msg = str(e)
            sys.stderr.write("ERROR: {}\n".format(error_msg))
            self.send_error(500, "Internal Server Error: {}".format(error_msg))

    def _handle_authorize(self, authz_request):
        """Handle authorization request."""
        try:

            # Build Cedar request
            cedar_request = {
                "principal": authz_request["principal"],
                "action": authz_request["action"],
                "resource": authz_request["resource"],
                "context": authz_request.get("context", {})
            }

            # Write request to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(cedar_request, f)
                request_file = f.name

            # Use combined policies (base + delegation) for authorization
            combined_policies_file = get_combined_policies_file()
            try:
                # Call cedar CLI with --verbose to get policy IDs
                result = subprocess.run(
                    [
                        'cedar', 'authorize',
                        '--verbose',
                        '--schema', str(SCHEMA),
                        '--policies', combined_policies_file,
                        '--entities', str(ENTITIES),
                        '--request-json', request_file
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(CEDAR_DIR)
                )

                # Debug: Show Cedar CLI output
                print("\n--- Cedar Request ---")
                print(json.dumps(cedar_request, indent=2))
                print("\n--- Cedar CLI Output ---")
                print(result.stdout)
                if result.stderr:
                    print("--- Cedar CLI Errors ---")
                    print(result.stderr)
                print("--- End Cedar Output ---\n")

                # Parse Cedar output
                decision = "Allow" if "ALLOW" in result.stdout else "Deny"

                # Extract policy IDs from verbose output
                policy_ids = []
                for line in result.stdout.split('\n'):
                    if 'policy-' in line.lower() or 'delegation-' in line.lower() or 'hitl-' in line.lower():
                        import re
                        matches = re.findall(r'(?:policy|delegation|hitl)-[\w-]+', line, re.IGNORECASE)
                        policy_ids.extend(matches)

                # Remove duplicates while preserving order
                policy_ids = list(dict.fromkeys(policy_ids))

                # Build response
                response = {
                    "decision": decision,
                    "diagnostics": {
                        "reason": policy_ids,
                        "errors": []
                    }
                }

                # Send response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))

                # Log
                tool = authz_request.get("resource", "").split("::")[- 1].strip('"')
                action = authz_request.get("action", "").split("::")[- 1].strip('"')
                principal = authz_request.get("principal", "")
                is_subagent = "SubAgent" in principal
                prefix = "[{}]{}".format(decision, " [SubAgent]" if is_subagent else "")
                print("{} {} - {}".format(prefix, tool, action))

            finally:
                Path(request_file).unlink(missing_ok=True)
                Path(combined_policies_file).unlink(missing_ok=True)

        except Exception as e:
            # Re-raise to be caught by outer handler
            raise

    def _handle_query_constraints(self, query_request):
        """Handle TPE query-constraints request."""
        # Extract components from entity IDs (e.g., "OpenClaw::Agent::\"main\"")
        principal = query_request["principal"]
        action = query_request["action"]
        resource = query_request["resource"]

        # Parse entity ID format: "Namespace::Type::\"eid\""
        def parse_entity_id(full_id):
            """Parse Cedar entity ID into type and eid."""
            # Example: "OpenClaw::Agent::\"main\"" -> ("OpenClaw::Agent", "main")
            parts = full_id.split("::")
            if len(parts) >= 3:
                entity_type = "::".join(parts[:-1])
                eid = parts[-1].strip('"')
                return entity_type, eid
            return full_id, ""

        principal_type, principal_eid = parse_entity_id(principal)
        resource_type, resource_eid = parse_entity_id(resource)

        # Call cedar tpe with individual arguments (no context - that's what we're querying)
        result = subprocess.run(
            [
                'cedar', 'tpe',
                '--schema', str(SCHEMA),
                '--policies', str(POLICIES_TPE),
                '--entities', str(ENTITIES),
                '--principal-type', principal_type,
                '--principal-eid', principal_eid,
                '--action', action,
                '--resource-type', resource_type,
                '--resource-eid', resource_eid
            ],
            capture_output=True,
            text=True,
            cwd=str(CEDAR_DIR)
        )

        # Debug: Show Cedar TPE output
        print("\n--- Cedar TPE Query ---")
        print("Principal: {} ({})".format(principal_type, principal_eid))
        print("Action: {}".format(action))
        print("Resource: {} ({})".format(resource_type, resource_eid))
        print("\n--- Cedar TPE Output ---")
        print(result.stdout)
        if result.stderr:
            print("--- Cedar TPE Errors ---")
            print(result.stderr)
        print("--- End Cedar TPE Output ---\n")

        # Parse residual policies from output
        # The output contains the decision (UNKNOWN) and residual policies in Cedar syntax
        residuals = []
        current_residual = []
        in_residual = False

        for line in result.stdout.split('\n'):
            # Look for policy annotations like @id("policy-2-allow-tmp-writes")
            if line.strip().startswith('@id('):
                if current_residual:
                    residuals.append('\n'.join(current_residual))
                current_residual = [line]
                in_residual = True
            elif in_residual:
                if line.strip() and not line.strip().startswith('---'):
                    current_residual.append(line)
                elif line.strip().startswith('---') or not line.strip():
                    if current_residual and current_residual[-1].strip().endswith(';'):
                        residuals.append('\n'.join(current_residual))
                        current_residual = []
                        in_residual = False

        # Add last residual if exists
        if current_residual:
            residuals.append('\n'.join(current_residual))

        # Build response
        response = {
            "decision": "UNKNOWN",  # TPE always returns UNKNOWN with residuals
            "residuals": residuals,
            "explanation": "These are the policy constraints that must be satisfied for authorization"
        }

        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response, indent=2).encode('utf-8'))

        # Log
        print("[TPE Query] {} - returned {} residual policies".format(action, len(residuals)))

    def do_GET(self):
        """Handle GET requests (health, approver UI, HITL APIs)."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"status": "ok"})
        elif path in ("/approver", "/approver/"):
            self._serve_static("index.html")
        elif path.startswith("/approver/"):
            self._serve_static(path[len("/approver/"):])
        elif path == "/approvals":
            self._send_json({"items": APPROVALS.list_pending()})
        elif path.endswith("/wait") and path.startswith("/approvals/"):
            approval_id = path[len("/approvals/"):-len("/wait")].strip("/")
            self._send_json(APPROVALS.wait(approval_id))
        elif path == "/mailbox":
            self._send_json({"items": list_mailbox()})
        elif path == "/webauthn/status":
            if not self._require_webauthn():
                return
            self._send_json(WEBAUTHN.status())
        elif path == "/webauthn/register/options":
            if not self._require_webauthn():
                return
            self._send_json(WEBAUTHN.registration_options())
        elif path == "/webauthn/authenticate/options":
            if not self._require_webauthn():
                return
            approval_id = (query.get("approvalId") or [None])[0]
            record = APPROVALS.get(approval_id) if approval_id else None
            if record is None or record["status"] != "pending":
                self._send_json({"error": "no pending approval"}, status=404)
                return
            self._send_json(WEBAUTHN.authentication_options(record["requestHash"]))
        else:
            self.send_error(404, "Not Found")

    def _handle_create_approval(self, request_data):
        request_hash = request_data.get("requestHash")
        if not request_hash:
            self._send_json({"error": "requestHash required"}, status=400)
            return
        record = APPROVALS.create(
            email_to=request_data.get("to") or "",
            subject=request_data.get("subject") or "",
            body=request_data.get("body") or "",
            request_hash=request_hash,
            agent_id=request_data.get("agentId") or "unknown",
            tool_call_id=request_data.get("toolCallId") or "unknown",
            timeout_ms=int(request_data.get("timeoutMs") or 180000),
        )
        print("[HITL] pending send {} to={} subject={}".format(
            record["id"], record["to"], record["subject"],
        ))
        self._send_json(record, status=201)

    def _handle_register_verify(self, request_data):
        if not self._require_webauthn():
            return
        try:
            result = WEBAUTHN.verify_registration(request_data)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        print("[HITL] Yubikey registered")
        self._send_json(result)

    def _handle_authenticate_verify(self, request_data):
        if not self._require_webauthn():
            return
        approval_id = request_data.get("approvalId")
        record = APPROVALS.get(approval_id) if approval_id else None
        if record is None or record["status"] != "pending":
            self._send_json({"error": "no pending approval"}, status=404)
            return
        try:
            WEBAUTHN.verify_authentication(
                request_data.get("credential") or {},
                record["requestHash"],
            )
            approved = APPROVALS.approve(approval_id, record["requestHash"])
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        print("[HITL] approved send {} to={}".format(approved["id"], approved["to"]))
        self._send_json({"verified": True, "approval": approved})

    def _require_webauthn(self):
        if WEBAUTHN is None:
            self._send_json(
                {"error": "Python package 'webauthn' is not installed. pip3 install webauthn"},
                status=503,
            )
            return False
        return True

    def _send_json(self, payload, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _serve_static(self, relative):
        target = (STATIC_DIR / relative).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self.send_error(404, "Not Found")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """Suppress default HTTP logging (we have custom logging)."""
        pass

class ThreadingPDPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def list_mailbox():
    """List simulated sent messages for the approver page."""
    MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(MAILBOX_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        items.append({"filename": path.name, **data})
    return items


def main():
    """Start the Cedar PDP server."""
    port = 8180

    # Verify Cedar CLI is installed
    try:
        subprocess.run(['cedar', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.stderr.write("ERROR: cedar CLI not found\n")
        sys.stderr.write("Install with: brew install cedar\n")
        sys.exit(1)

    # Verify policy files exist
    for path in [SCHEMA, POLICIES, ENTITIES]:
        if not path.exists():
            sys.stderr.write("ERROR: {} not found\n".format(path))
            sys.exit(1)

    # Check for TPE policies (optional, warn if missing)
    if not POLICIES_TPE.exists():
        print("Warning: {} not found - /query-constraints endpoint will not work".format(POLICIES_TPE))
        print("TPE queries require policies with 'has' checks for optional context attributes")
        print()

    MAILBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Start server (threaded so long-poll waits do not block the approver UI)
    server = ThreadingPDPServer(('localhost', port), CedarPDPHandler)
    accept_thread = threading.Thread(target=server.serve_forever, daemon=True)
    accept_thread.start()
    sys.stderr.write("Cedar PDP listening on http://localhost:{}\n".format(port))
    sys.stderr.flush()

    print("=" * 70)
    print("Cedar PDP Server for OpenClaw Authorization")
    print("=" * 70)
    print("Listening:  http://localhost:{}".format(port))
    print("Schema:     {}".format(SCHEMA.relative_to(REPO_ROOT)))
    print("Policies:   {}".format(POLICIES.relative_to(REPO_ROOT)))
    if POLICIES_TPE.exists():
        print("TPE Policies: {}".format(POLICIES_TPE.relative_to(REPO_ROOT)))
    if POLICIES_DELEGATION.exists():
        print("Delegation: {}".format(POLICIES_DELEGATION.relative_to(REPO_ROOT)))
    if POLICIES_HITL.exists():
        print("HITL:       {}".format(POLICIES_HITL.relative_to(REPO_ROOT)))
    print("Entities:   {}".format(ENTITIES.relative_to(REPO_ROOT)))
    if WEBAUTHN is None:
        print()
        print("Note: pip3 install webauthn  (required for /approver Yubikey flows)")
    print()
    print("Endpoints:")
    print("  POST /authorize          - Authorization requests (reactive)")
    print("  POST /query-constraints  - TPE constraint queries (proactive)")
    print("  GET  /approver           - Human-in-the-loop Yubikey page")
    print("  GET  /health             - Health check")
    print()
    print("Ready to authorize tool executions...")
    print("=" * 70)
    print()

    try:
        accept_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()
