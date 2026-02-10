# Testing Cedar Authorization with OpenClaw

This guide shows how to test the Cedar authorization integration with a live OpenClaw agent.

## Overview

When authorization is enabled, the agent's tool executions are intercepted by a Policy Enforcement Point (PEP) that calls the Cedar Policy Decision Point (PDP) before allowing the tool to run.

**What happens when a tool is denied:**
- The PEP blocks the tool execution
- The agent receives a structured error message explaining the denial
- The agent can replan with an alternative approach or ask for guidance

## Prerequisites

1. **Cedar CLI installed:**
   ```bash
   brew install cedar
   ```

2. **Node.js and dependencies:**
   ```bash
   pnpm install
   pnpm build
   ```

3. **Python requests library:**
   ```bash
   pip3 install --break-system-packages requests
   ```

## Step 1: Start the Cedar PDP Server

In a dedicated terminal, start the PDP server:

```bash
python3 demo/cedar-pdp-server.py
```

You should see:
```
============================================================
Cedar PDP Server for OpenClaw Authorization
============================================================
Listening:  http://localhost:8180
...
Ready to authorize tool executions...
============================================================
```

Keep this terminal open - you'll see authorization decisions logged here.

## Step 2: Configure OpenClaw

The repository includes a sample configuration in `openclaw.json5`:

```json5
{
  authz: {
    pdp: {
      enabled: true,
      endpoint: "http://localhost:8180/authorize",
      timeoutMs: 2000,
      failOpen: false  // fail-closed for security
    }
  }
}
```

To use this configuration with OpenClaw, either:

**Option A: Copy to OpenClaw config directory**
```bash
mkdir -p ~/.openclaw
cp openclaw.json5 ~/.openclaw/config.json5
```

**Option B: Merge into existing config**
Add the `authz` section to your existing `~/.openclaw/config.json5`

## Step 3: Run OpenClaw Agent

Start an OpenClaw agent session:

```bash
pnpm openclaw agent --message "Hello, I'm testing authorization" --config openclaw.json5
```

Or if you copied the config:
```bash
openclaw agent
```

## Step 4: Test Denied Operations

Try asking the agent to perform operations that should be **DENIED** by policy:

### Test 1: Write to system directory
```
Can you create a file at /etc/test.txt?
```

**Expected behavior:**
- The agent will attempt to use the `write` tool
- The PEP will call the PDP
- The PDP will return `Deny` (policy-3-deny-system-writes)
- The agent will receive an error
- The agent should explain it can't write to /etc and suggest alternatives

**PDP server log:**
```
[Deny] write - Write
```

### Test 2: Dangerous bash command
```
Can you run 'rm -rf /' to clean up?
```

**Expected behavior:**
- The agent will attempt to use the `bash` tool
- The PDP will return `Deny` (policy-5-deny-dangerous-bash)
- The agent will explain this command is dangerous and can't be executed

**PDP server log:**
```
[Deny] bash - Bash
```

### Test 3: Read SSH private key
```
Can you read my SSH private key at ~/.ssh/id_rsa?
```

**Expected behavior:**
- The agent will attempt to use the `read` tool
- The PDP will return `Deny` (policy-7-deny-credential-files)
- The agent will explain it can't access credential files

**PDP server log:**
```
[Deny] read - Read
```

## Step 5: Test Allowed Operations

Try asking the agent to perform operations that should be **ALLOWED** by policy:

### Test 4: Read user files
```
Can you read the README.md file?
```

**Expected behavior:**
- The agent uses the `read` tool
- The PDP returns `Allow` (policy-1-allow-readonly)
- The tool executes successfully
- The agent shows you the file contents

**PDP server log:**
```
[Allow] read - Read
```

### Test 5: Write to /tmp
```
Can you create a test file at /tmp/test.txt?
```

**Expected behavior:**
- The agent uses the `write` tool
- The PDP returns `Allow` (policy-2-allow-tmp-writes)
- The tool executes successfully
- The file is created

**PDP server log:**
```
[Allow] write - Write
```

### Test 6: Safe git command
```
Can you run 'git status'?
```

**Expected behavior:**
- The agent uses the `bash` tool
- The PDP returns `Allow` (policy-4-allow-safe-bash or policy-6-allow-git-ops)
- The command executes successfully
- The agent shows you the git status

**PDP server log:**
```
[Allow] bash - Bash
```

## Step 6: Observe Agent Behavior

### What the Agent Sees on Denial

When a tool is denied, the agent receives a structured error:

```typescript
{
  blocked: true,
  reason: "Tool execution denied by policy: policy-3-deny-system-writes"
}
```

The agent's framework interprets this as a failed tool execution and includes it in the conversation history. The agent can then:

1. **Explain the limitation** to the user
2. **Suggest alternatives** (e.g., write to /tmp instead of /etc)
3. **Replan** with a different approach
4. **Ask for clarification** or user guidance

### Watch the PDP Server Logs

In the PDP server terminal, you'll see real-time authorization decisions:

```
[Allow] read - Read
[Deny] write - Write
[Allow] bash - Bash
[Deny] bash - Bash
...
```

This shows which tools were allowed/denied and helps you verify the policies are working correctly.

## Troubleshooting

### Agent doesn't seem to be checking authorization

**Check:**
1. PDP server is running: `curl http://localhost:8180/health`
2. Config is loaded: Verify `authz.pdp.enabled: true` in config
3. OpenClaw was built: `pnpm build`
4. No config errors: Check OpenClaw startup logs

### All tools are being denied

**Check:**
1. Cedar policies are valid: `cd policies/cedar && cedar validate --schema schema.cedarschema --policies policies.cedar`
2. Entities file exists: `ls -la policies/cedar/entities.json`
3. PDP server is using the right policy files (check server startup output)

### Authorization is timing out

**Check:**
1. PDP server is reachable: `curl http://localhost:8180/health`
2. Timeout is reasonable: Default is 2000ms (2 seconds)
3. Increase timeout in config: `timeoutMs: 5000`

### Want to disable authorization temporarily

**Option 1: Fail-open mode (allows on errors)**
```json5
{
  authz: {
    pdp: {
      enabled: true,
      failOpen: true  // ← Change to true
    }
  }
}
```

**Option 2: Disable entirely**
```json5
{
  authz: {
    pdp: {
      enabled: false  // ← Change to false
    }
  }
}
```

## Understanding the Policies

See [policies/cedar/README.md](policies/cedar/README.md) for detailed policy documentation.

**Quick reference:**
- **Policy 1**: Allow read-only tools (Read, Glob, Grep) - always safe
- **Policy 2**: Allow writes to `/tmp/*` only
- **Policy 3**: Deny writes to system directories (`/etc/*`, `/usr/*`, etc.)
- **Policy 4**: Allow safe bash commands (`ls`, `cat`, `git status`, etc.)
- **Policy 5**: Deny dangerous commands (`rm -rf`, `shutdown`, etc.)
- **Policy 6**: Allow git operations
- **Policy 7**: Deny credential files (`~/.ssh/*`, `~/.aws/*`, etc.)
- **Policy 8**: Deny network tools
- **Policy 9**: Deny process management tools
- **Policy 10**: Workspace-scoped permissions (example for advanced use)

## Modifying Policies

1. **Edit policies:**
   ```bash
   vim policies/cedar/policies.cedar
   ```

2. **Validate changes:**
   ```bash
   cd policies/cedar
   cedar validate --schema schema.cedarschema --policies policies.cedar
   ```

3. **Test with Cedar CLI:**
   ```bash
   ./test-all.sh
   ```

4. **Restart PDP server** (it loads policies on startup)

5. **Test with agent** - no need to restart OpenClaw, just send new commands

## Next Steps

- **Add custom policies** for your specific use cases
- **Modify entity attributes** to add roles, security levels, etc.
- **Integrate with external policy store** instead of file-based policies
- **Add audit logging** to track all authorization decisions
- **Create policy tests** for your custom policies
