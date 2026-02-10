#!/bin/bash
# Test to show agent receiving denial and replanning

echo "================================================================"
echo "Test: Agent Replanning After Authorization Denial"
echo "================================================================"
echo ""
echo "This test shows the agent:"
echo "1. Attempting a denied operation"
echo "2. Receiving the denial message from Cedar"
echo "3. Replanning with an alternative approach"
echo ""
echo "================================================================"
echo ""

cd "$(dirname "$0")/.."

# Enable verbose output to see the full agent reasoning
export DEBUG="openclaw:authz*"

echo "Running: Agent attempts to write to /etc (DENIED)"
echo "Then should suggest writing to /tmp instead (ALLOWED)"
echo ""
echo "================================================================"
echo ""

pnpm openclaw agent --agent main --message "I'm testing authorization. Please create a test file at /etc/demo-test.txt. If that doesn't work, try /tmp instead."

echo ""
echo "================================================================"
echo "Expected behavior:"
echo "1. Agent tries to write to /etc/demo-test.txt"
echo "2. Receives: 'Tool execution denied by policy: policy-3-deny-system-writes'"
echo "3. Agent explains why it was denied"
echo "4. Agent suggests and executes write to /tmp/demo-test.txt instead"
echo "================================================================"
