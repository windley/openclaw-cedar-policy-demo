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
ENTITIES = CEDAR_DIR / "entities.json"

class CedarPDPHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cedar authorization requests."""

    def do_POST(self):
        """Handle POST requests to /authorize."""
        if self.path != "/authorize":
            self.send_error(404, "Not Found - use POST /authorize")
            return

        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            authz_request = json.loads(body)

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
                # Call cedar CLI
                result = subprocess.run(
                    [
                        'cedar', 'authorize',
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

                # Build response
                response = {
                    "decision": decision,
                    "diagnostics": {
                        "reason": [],
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
            error_msg = str(e)
            sys.stderr.write("ERROR: {}\n".format(error_msg))
            self.send_error(500, "Internal Server Error: {}".format(error_msg))

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

    # Start server
    server = HTTPServer(('localhost', port), CedarPDPHandler)

    print("=" * 60)
    print("Cedar PDP Server for OpenClaw Authorization")
    print("=" * 60)
    print("Listening:  http://localhost:{}".format(port))
    print("Schema:     {}".format(SCHEMA.relative_to(REPO_ROOT)))
    print("Policies:   {}".format(POLICIES.relative_to(REPO_ROOT)))
    print("Entities:   {}".format(ENTITIES.relative_to(REPO_ROOT)))
    print()
    print("Endpoints:")
    print("  POST /authorize - Authorization requests")
    print("  GET  /health    - Health check")
    print()
    print("Ready to authorize tool executions...")
    print("=" * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()
