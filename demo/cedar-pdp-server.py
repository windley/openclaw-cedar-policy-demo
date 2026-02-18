#!/usr/bin/env python3
"""
Simple Cedar PDP HTTP server for OpenClaw authorization demo.

This server wraps the Cedar CLI and provides an HTTP API for authorization requests.
"""
import json
import subprocess
import sys
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).parent.parent
CEDAR_DIR = REPO_ROOT / "policies" / "cedar"
SCHEMA = CEDAR_DIR / "schema.cedarschema"
POLICIES = CEDAR_DIR / "policies.cedar"
POLICIES_TPE = CEDAR_DIR / "policies-tpe.cedar"
ENTITIES = CEDAR_DIR / "entities.json"

class CedarPDPHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cedar authorization requests."""

    def do_POST(self):
        """Handle POST requests to /authorize or /query-constraints."""
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            request_data = json.loads(body)

            if self.path == "/authorize":
                self._handle_authorize(request_data)
            elif self.path == "/query-constraints":
                self._handle_query_constraints(request_data)
            else:
                self.send_error(404, "Not Found - use POST /authorize or /query-constraints")

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

            try:
                # Call cedar CLI with --verbose to get policy IDs
                result = subprocess.run(
                    [
                        'cedar', 'authorize',
                        '--verbose',
                        '--schema', str(SCHEMA),
                        '--policies', str(POLICIES),
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
                # Verbose output includes lines like "policy-1-allow-readonly" or "policy-3-deny-system-writes"
                policy_ids = []
                for line in result.stdout.split('\n'):
                    # Look for lines containing policy IDs (format: policy-N-...)
                    if 'policy-' in line.lower():
                        # Extract policy ID from the line
                        import re
                        matches = re.findall(r'policy-[\w-]+', line, re.IGNORECASE)
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
                print("[{}] {} - {}".format(decision, tool, action))

            finally:
                Path(request_file).unlink(missing_ok=True)

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
                '-s', str(SCHEMA),
                '-p', str(POLICIES_TPE),
                '--entities', str(ENTITIES),
                '--principal-type', principal_type,
                '--principal-eid', principal_eid,
                '-a', action,
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
        """Handle GET requests (health check)."""
        if self.path == "/health":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found - use POST /authorize or GET /health")

    def log_message(self, format, *args):
        """Suppress default HTTP logging (we have custom logging)."""
        pass

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

    # Start server
    server = HTTPServer(('localhost', port), CedarPDPHandler)

    print("=" * 70)
    print("Cedar PDP Server for OpenClaw Authorization")
    print("=" * 70)
    print("Listening:  http://localhost:{}".format(port))
    print("Schema:     {}".format(SCHEMA.relative_to(REPO_ROOT)))
    print("Policies:   {}".format(POLICIES.relative_to(REPO_ROOT)))
    if POLICIES_TPE.exists():
        print("TPE Policies: {}".format(POLICIES_TPE.relative_to(REPO_ROOT)))
    print("Entities:   {}".format(ENTITIES.relative_to(REPO_ROOT)))
    print()
    print("Endpoints:")
    print("  POST /authorize          - Authorization requests (reactive)")
    print("  POST /query-constraints  - TPE constraint queries (proactive)")
    print("  GET  /health             - Health check")
    print()
    print("Ready to authorize tool executions...")
    print("=" * 70)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()
