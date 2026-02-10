# Cedar Authorization Demo for OpenClaw

This repository demonstrates how to add fine-grained authorization controls to OpenClaw agent tool executions using [Cedar Policy Language](https://www.cedarpolicy.com/).

## What This Demo Shows

When authorization is enabled, every tool execution request is intercepted and evaluated against Cedar policies **before** the tool runs:

- ✅ **Allow** safe operations (read user files, write to `/tmp`, run `git status`)
- ❌ **Deny** dangerous operations (write to `/etc`, run `rm -rf`, read SSH keys)
- 🤖 **Agent replans** when denied, explaining limitations and suggesting alternatives

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ OpenClaw Agent                                          │
│  "Can you create /etc/test.txt?"                        │
└────────────┬────────────────────────────────────────────┘
             │ Tool: write, path: /etc/test.txt
             ▼
┌─────────────────────────────────────────────────────────┐
│ Policy Enforcement Point (PEP)                          │
│  src/agents/pi-tools.before-tool-call.ts                │
│  Intercepts tool call → builds authz request            │
└────────────┬────────────────────────────────────────────┘
             │ HTTP POST /authorize
             ▼
┌─────────────────────────────────────────────────────────┐
│ Policy Decision Point (PDP)                             │
│  demo/cedar-pdp-server.py (port 8180)                   │
│  Evaluates request against Cedar policies               │
└────────────┬────────────────────────────────────────────┘
             │ Decision: Deny (policy-3-deny-system-writes)
             ▼
┌─────────────────────────────────────────────────────────┐
│ Agent Response                                          │
│  "I cannot write to /etc - it's a system directory.     │
│   I can create the file in /tmp instead if you'd like." │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start PDP Server

```bash
python3 demo/cedar-pdp-server.py
```

Or from within demo directory:
```bash
cd demo
python3 cedar-pdp-server.py
```

### 2. Configure OpenClaw

```bash
cp openclaw.json5 ~/.openclaw/config.json5
```

### 3. Test with Agent

Try a restricted operation:
```bash
openclaw agent --message "Create a file at /etc/test.txt"
```

The agent will be denied and explain why!

## Demo Materials

### 📖 Documentation

- **[README.md](README.md)** - Scripts, testing with live agent, examples
- **[TESTING.md](TESTING.md)** - Comprehensive end-to-end testing guide
- **[../policies/cedar/README.md](../policies/cedar/README.md)** - Policy documentation

### 🐍 Python Scripts

- **[cedar-pdp-server.py](cedar-pdp-server.py)** - HTTP server wrapping Cedar CLI
- **[test-pdp.py](test-pdp.py)** - Test client with 6 scenarios

### 📓 Jupyter Notebook

- **[cedar-authorization-demo.ipynb](cedar-authorization-demo.ipynb)** - Interactive demo

### 🦀 Cedar Policies

- **[../policies/cedar/schema.cedarschema](../policies/cedar/schema.cedarschema)** - Entity types and actions
- **[../policies/cedar/policies.cedar](../policies/cedar/policies.cedar)** - Authorization policies
- **[../policies/cedar/entities.json](../policies/cedar/entities.json)** - Agent and tool entities

### 💻 TypeScript Implementation

- **[../src/authz/cedar-pdp-client.ts](../src/authz/cedar-pdp-client.ts)** - PDP HTTP client
- **[../src/agents/pi-tools.before-tool-call.ts](../src/agents/pi-tools.before-tool-call.ts)** - PEP integration
- **[../src/config/types.authz.ts](../src/config/types.authz.ts)** - Configuration types

## Example Policies

### Policy 1: Allow Read-Only Tools

```cedar
@id("policy-1-allow-readonly")
permit(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Read",
    OpenClaw::Action::"ToolExec::Glob",
    OpenClaw::Action::"ToolExec::Grep"
  ],
  resource
);
```

### Policy 3: Deny System Writes

```cedar
@id("policy-3-deny-system-writes")
forbid(
  principal,
  action in [
    OpenClaw::Action::"ToolExec::Write",
    OpenClaw::Action::"ToolExec::Edit"
  ],
  resource
)
when {
  context.filePath like "/etc/*" ||
  context.filePath like "/usr/*" ||
  context.filePath like "/bin/*" ||
  context.filePath like "/sbin/*"
};
```

### Policy 5: Deny Dangerous Commands

```cedar
@id("policy-5-deny-dangerous-bash")
forbid(
  principal,
  action == OpenClaw::Action::"ToolExec::Bash",
  resource
)
when {
  context.command like "*rm -rf*" ||
  context.command like "*shutdown*" ||
  context.command like "*reboot*" ||
  context.command like "*mkfs*" ||
  context.command like "*dd if=*"
};
```

## Testing Scenarios

| Scenario | Tool | Input | Expected | Policy |
|----------|------|-------|----------|--------|
| Read user file | read | `/home/user/code/main.py` | ✅ Allow | policy-1 |
| Write to /etc | write | `/etc/passwd` | ❌ Deny | policy-3 |
| Write to /tmp | write | `/tmp/output.txt` | ✅ Allow | policy-2 |
| Dangerous rm -rf | bash | `rm -rf /` | ❌ Deny | policy-5 |
| Safe git command | bash | `git status` | ✅ Allow | policy-4 |
| Read SSH key | read | `~/.ssh/id_rsa` | ❌ Deny | policy-7 |

See [demo/test-pdp.py](demo/test-pdp.py) for automated tests.

## Configuration

Add to `~/.openclaw/config.json5`:

```json5
{
  authz: {
    pdp: {
      // Enable authorization checks
      enabled: true,

      // PDP endpoint (cedar-pdp-server.py)
      endpoint: "http://localhost:8180/authorize",

      // Request timeout in milliseconds
      timeoutMs: 2000,

      // Fail-open vs fail-closed
      // false = fail-closed (deny on PDP errors) - RECOMMENDED
      // true = fail-open (allow on PDP errors) - testing only
      failOpen: false
    }
  }
}
```

## How It Works

### Authorization Flow

1. **Agent requests tool execution**
   - Example: `tool="write"`, `params={path: "/etc/test.txt"}`

2. **PEP intercepts** (before tool runs)
   - Builds Cedar request with principal, action, resource, context
   - Calls PDP via HTTP: `POST http://localhost:8180/authorize`

3. **PDP evaluates policies**
   - Loads schema, policies, and entities
   - Calls Cedar CLI: `cedar authorize`
   - Returns decision: `Allow` or `Deny`

4. **PEP enforces decision**
   - **Allow**: Tool executes normally
   - **Deny**: Tool blocked, agent receives error with reason

5. **Agent handles result**
   - On success: Shows tool output
   - On denial: Explains limitation, suggests alternatives, or asks for guidance

### What Agent Sees on Denial

```json
{
  "blocked": true,
  "reason": "Tool execution denied by policy: policy-3-deny-system-writes"
}
```

The agent interprets this as a failed tool execution and includes it in conversation history. The agent can then explain the limitation and replan.

## Requirements

- **Cedar CLI:** `brew install cedar`
- **Python 3.7+:** For PDP server
- **Python requests:** `pip3 install --break-system-packages requests`
- **Node.js 22+:** For OpenClaw
- **pnpm:** For building OpenClaw

## Running the Demo

### Option 1: Standalone Scripts (No Agent)

Test the PDP server without OpenClaw:

```bash
# Terminal 1: Start PDP
python3 demo/cedar-pdp-server.py

# Terminal 2: Run tests
python3 demo/test-pdp.py
```

### Option 2: Jupyter Notebook

Interactive demo with code examples:

```bash
jupyter notebook cedar-authorization-demo.ipynb
```

### Option 3: Live Agent Testing

Test with a real OpenClaw agent:

```bash
# Terminal 1: Start PDP
python3 demo/cedar-pdp-server.py

# Terminal 2: Configure and run agent
cp openclaw.json5 ~/.openclaw/config.json5
pnpm build
openclaw agent --message "Create /etc/test.txt"
```

See [TESTING.md](TESTING.md) for detailed testing scenarios.

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

3. **Test changes:**
   ```bash
   ./test-all.sh
   ```

4. **Restart PDP server** (loads policies on startup)

5. **Test with agent** - no need to restart OpenClaw

## Policy Summary

| Policy ID | Effect | Description |
|-----------|--------|-------------|
| policy-1-allow-readonly | Allow | Read-only tools always safe |
| policy-2-allow-tmp-writes | Allow | Writes to `/tmp/*` only |
| policy-3-deny-system-writes | Deny | No writes to system directories |
| policy-4-allow-safe-bash | Allow | Safe commands: `ls`, `cat`, `git status` |
| policy-5-deny-dangerous-bash | Deny | Dangerous: `rm -rf`, `shutdown` |
| policy-6-allow-git-ops | Allow | All git operations |
| policy-7-deny-credential-files | Deny | No access to SSH keys, AWS credentials |
| policy-8-deny-network-tools | Deny | No network operations |
| policy-9-deny-process-tools | Deny | No process management |
| policy-10-workspace-scoped | Allow | Workspace-based permissions (example) |

## Troubleshooting

### PDP server won't start

```bash
# Check Cedar CLI installed
cedar --version

# Check policy files exist
ls -la policies/cedar/

# Check Python version
python3 --version
```

### Agent not checking authorization

```bash
# Verify config loaded
cat ~/.openclaw/config.json5

# Verify PDP server running
curl http://localhost:8180/health

# Rebuild OpenClaw
pnpm build
```

### All requests denied/allowed

```bash
# Validate policies
cd policies/cedar
cedar validate --schema schema.cedarschema --policies policies.cedar

# Test individual requests
cd policies/cedar
cedar authorize \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --request-json test-requests/01-allow-read.json
```

## Resources

- **[Cedar Documentation](https://www.cedarpolicy.com/)** - Cedar policy language reference
- **[Cedar Playground](https://www.cedarpolicy.com/playground)** - Try Cedar policies online
- **[Cedar SDK](https://github.com/cedar-policy/cedar)** - Cedar Rust SDK
- **[OpenClaw Docs](https://docs.openclaw.ai/)** - OpenClaw documentation

## Next Steps

1. **Explore the policies** - Review [policies/cedar/policies.cedar](policies/cedar/policies.cedar)
2. **Run the tests** - Execute `python3 demo/test-pdp.py`
3. **Test with agent** - Follow [TESTING.md](TESTING.md)
4. **Modify policies** - Add your own authorization rules
5. **Integrate with your workflow** - Deploy PDP server and enable in OpenClaw config

## License

MIT - See [LICENSE](LICENSE) file for details.
