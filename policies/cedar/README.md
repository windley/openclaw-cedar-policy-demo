# Cedar Authorization Policies for OpenClaw

This directory contains Cedar schema and policies for authorizing OpenClaw agent tool executions.

## Files

- **`schema.cedarschema`** - Cedar schema defining entity types, actions, and context
- **`policies.cedar`** - Sample authorization policies demonstrating common patterns
- **`entities.json`** - Entity store (agents and tools) - see below
- **`config.json`** - Cedar-agent configuration - see below

## Quick Start

### 1. Install Cedar CLI

```bash
# Option A: Using Homebrew (macOS/Linux)
brew install cedar

# Option B: Using Cargo
cargo install cedar-policy-cli

# Option C: Download binary from GitHub releases
# https://github.com/cedar-policy/cedar/releases
```

### 2. Create Entity Store

Create `entities.json` with agent and tool entities:

```json
[
  {
    "uid": {
      "type": "OpenClaw::Agent",
      "id": "agent-abc123"
    },
    "attrs": {
      "role": "developer",
      "securityLevel": "medium"
    },
    "parents": []
  },
  {
    "uid": {
      "type": "OpenClaw::Tool",
      "id": "bash"
    },
    "attrs": {
      "category": "shell",
      "riskLevel": "high"
    },
    "parents": []
  },
  {
    "uid": {
      "type": "OpenClaw::Tool",
      "id": "read"
    },
    "attrs": {
      "category": "file_operation",
      "riskLevel": "low"
    },
    "parents": []
  },
  {
    "uid": {
      "type": "OpenClaw::Tool",
      "id": "write"
    },
    "attrs": {
      "category": "file_operation",
      "riskLevel": "medium"
    },
    "parents": []
  }
]
```

### 3. Validate Schema

```bash
cedar validate --schema schema.cedarschema --policies policies.cedar
```

### 4. Test Authorization Requests

Create a test request file `test-request.json`:

```json
{
  "principal": "OpenClaw::Agent::\"agent-abc123\"",
  "action": "OpenClaw::Action::\"ToolExec::Bash\"",
  "resource": "OpenClaw::Tool::\"bash\"",
  "context": {
    "toolCallId": "toolu_123",
    "command": "ls -la",
    "sessionKey": "session-xyz"
  }
}
```

Test with Cedar CLI:

```bash
cedar authorize \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --request test-request.json
```

## Running Cedar-Agent PDP

### Option 1: Using Cedar-Agent (Recommended)

If you have cedar-agent installed:

```bash
# Start cedar-agent on port 8180
cedar-agent \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --port 8180
```

### Option 2: Build a Simple PDP Service

Create a simple HTTP wrapper around Cedar (example in Node.js):

```javascript
// pdp-server.js
import { createServer } from 'http';
import { spawn } from 'child_process';

const server = createServer(async (req, res) => {
  if (req.method !== 'POST' || req.url !== '/authorize') {
    res.writeHead(404);
    res.end();
    return;
  }

  let body = '';
  for await (const chunk of req) {
    body += chunk;
  }

  const authzRequest = JSON.parse(body);

  // Convert to Cedar CLI format
  const cedarRequest = {
    principal: authzRequest.principal,
    action: authzRequest.action,
    resource: authzRequest.resource,
    context: authzRequest.context || {}
  };

  // Call cedar CLI
  const cedar = spawn('cedar', [
    'authorize',
    '--schema', 'schema.cedarschema',
    '--policies', 'policies.cedar',
    '--entities', 'entities.json',
    '--request-json', JSON.stringify(cedarRequest)
  ]);

  let output = '';
  cedar.stdout.on('data', (data) => output += data);

  await new Promise((resolve) => cedar.on('close', resolve));

  const decision = output.includes('ALLOW') ? 'Allow' : 'Deny';

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    decision,
    diagnostics: { reason: [], errors: [] }
  }));
});

server.listen(8180, () => {
  console.log('Cedar PDP listening on http://localhost:8180');
});
```

Run it:

```bash
node pdp-server.js
```

## Configure OpenClaw

Add to your `openclaw.json5`:

```json5
{
  authz: {
    pdp: {
      enabled: true,
      endpoint: "http://localhost:8180/authorize",
      timeoutMs: 2000,
      failOpen: false  // fail-closed: deny on PDP errors
    }
  }
}
```

## Policy Patterns Explained

### Pattern 1: Allow-List for Safe Tools

```cedar
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Glob"
  ],
  resource
);
```

Allows all agents to use read-only tools without restrictions.

### Pattern 2: Context-Based Restrictions

```cedar
permit(
  principal,
  action == OpenClaw::Action::"ToolExec::Write",
  resource
)
when {
  context.filePath.startsWith("/tmp/")
};
```

Allows write operations only to specific directories using context attributes.

### Pattern 3: Deny-List for Dangerous Operations

```cedar
forbid(
  principal,
  action == OpenClaw::Action::"ToolExec::Bash",
  resource
)
when {
  context.command.contains("rm -rf")
};
```

Blocks dangerous commands using pattern matching on context.

### Pattern 4: Content-Based Command Filtering

```cedar
permit(
  principal,
  action == OpenClaw::Action::"ToolExec::Bash",
  resource
)
when {
  context.command.startsWith("git ")
};
```

Allows only specific command patterns (e.g., git operations).

## Testing Scenarios

### Scenario 1: Allow Safe Read

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-abc123\"",
    "action": "OpenClaw::Action::\"ToolExec::Read\"",
    "resource": "OpenClaw::Tool::\"read\"",
    "context": {
      "toolCallId": "toolu_001",
      "filePath": "/home/user/code/main.py",
      "sessionKey": "session-123"
    }
  }'
```

**Expected**: `Allow` (policy-1-allow-readonly)

### Scenario 2: Deny System File Write

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-abc123\"",
    "action": "OpenClaw::Action::\"ToolExec::Write\"",
    "resource": "OpenClaw::Tool::\"write\"",
    "context": {
      "toolCallId": "toolu_002",
      "filePath": "/etc/passwd",
      "sessionKey": "session-123"
    }
  }'
```

**Expected**: `Deny` (policy-3-deny-system-writes)

### Scenario 3: Allow Temp File Write

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-abc123\"",
    "action": "OpenClaw::Action::\"ToolExec::Write\"",
    "resource": "OpenClaw::Tool::\"write\"",
    "context": {
      "toolCallId": "toolu_003",
      "filePath": "/tmp/output.txt",
      "sessionKey": "session-123"
    }
  }'
```

**Expected**: `Allow` (policy-2-allow-tmp-writes)

### Scenario 4: Deny Dangerous Bash

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-abc123\"",
    "action": "OpenClaw::Action::\"ToolExec::Bash\"",
    "resource": "OpenClaw::Tool::\"bash\"",
    "context": {
      "toolCallId": "toolu_004",
      "command": "rm -rf /",
      "sessionKey": "session-123"
    }
  }'
```

**Expected**: `Deny` (policy-5-deny-dangerous-bash)

### Scenario 5: Allow Safe Git Command

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-abc123\"",
    "action": "OpenClaw::Action::\"ToolExec::Bash\"",
    "resource": "OpenClaw::Tool::\"bash\"",
    "context": {
      "toolCallId": "toolu_005",
      "command": "git status",
      "sessionKey": "session-123"
    }
  }'
```

**Expected**: `Allow` (policy-4-allow-safe-bash OR policy-6-allow-git-ops)

## Policy Evaluation Order

Cedar evaluates policies in this order:

1. **Forbid policies** are evaluated first
2. If any forbid policy matches → **Deny**
3. **Permit policies** are evaluated
4. If any permit policy matches → **Allow**
5. If no policy matches → **Deny** (default deny)

This means `forbid` policies always win over `permit` policies.

## Extending the Policies

### Add New Actions

1. Update `schema.cedarschema` with new action:
   ```cedar
   action "ToolExec::MyNewTool" appliesTo {
     principal: [Agent],
     resource: [Tool],
     context: ToolContext
   };
   ```

2. Add policies for the new action in `policies.cedar`

### Add Entity Attributes

1. Update entity type in `schema.cedarschema`:
   ```cedar
   entity Agent = {
     "role"?: String,
     "department"?: String,  // new attribute
   };
   ```

2. Update `entities.json` with new attributes

3. Reference in policies:
   ```cedar
   permit(...) when { principal.department == "engineering" };
   ```

### Add Context Attributes

1. Update `ToolContext` in `schema.cedarschema`:
   ```cedar
   type ToolContext = {
     "toolCallId": String,
     "timestamp"?: Long,  // new attribute
   };
   ```

2. Update OpenClaw PDP client to include new context

3. Reference in policies:
   ```cedar
   permit(...) when { context.timestamp > 1234567890 };
   ```

## Troubleshooting

### Schema Validation Fails

```bash
cedar validate --schema schema.cedarschema --policies policies.cedar
```

Check for:
- Typos in entity type names
- Missing action definitions
- Invalid attribute types

### Authorization Always Denies

1. Check entity UIDs match exactly (case-sensitive)
2. Verify action name matches schema
3. Test with Cedar CLI to see which policies match
4. Add debug logging in cedar-agent

### Performance Issues

- Keep policies simple (avoid complex string operations)
- Use indexed lookups where possible
- Consider caching authorization decisions for identical requests
- Monitor PDP response times and adjust timeout

## References

- [Cedar Policy Language](https://www.cedarpolicy.com/)
- [Cedar Schema Format](https://docs.cedarpolicy.com/schema/schema.html)
- [Cedar Policy Syntax](https://docs.cedarpolicy.com/policies/syntax-policy.html)
- [Cedar CLI Documentation](https://docs.cedarpolicy.com/cli/index.html)
