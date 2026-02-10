#!/bin/bash
# Test script to see Cedar CLI output format
cd "$(dirname "$0")/../policies/cedar"

echo "=== Test 1: DENY - Write to /etc/passwd ==="
cat > /tmp/test-deny.json << 'EOF'
{
  "principal": "OpenClaw::Agent::\"main\"",
  "action": "OpenClaw::Action::\"ToolExec::Write\"",
  "resource": "OpenClaw::Tool::\"write\"",
  "context": {
    "toolCallId": "test",
    "filePath": "/etc/passwd",
    "command": "",
    "sessionKey": "test"
  }
}
EOF

cedar authorize \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --request-json /tmp/test-deny.json

echo ""
echo "=== Test 2: ALLOW - Write to /tmp ==="
cat > /tmp/test-allow.json << 'EOF'
{
  "principal": "OpenClaw::Agent::\"main\"",
  "action": "OpenClaw::Action::\"ToolExec::Write\"",
  "resource": "OpenClaw::Tool::\"write\"",
  "context": {
    "toolCallId": "test",
    "filePath": "/tmp/test.txt",
    "command": "",
    "sessionKey": "test"
  }
}
EOF

cedar authorize \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --request-json /tmp/test-allow.json

rm /tmp/test-deny.json /tmp/test-allow.json
