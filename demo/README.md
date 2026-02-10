# Cedar Authorization Demo Scripts

This directory contains standalone demo scripts for the Cedar authorization integration.

## Architecture

The Cedar authorization system integrates into OpenClaw's agent execution loop, adding a Policy Enforcement Point (PEP) that checks with an external Policy Decision Point (PDP) before allowing tool execution.

![OpenClaw Authorization Architecture](openclaw_loop.png)

### How It Works

1. **Agent Planning**: The LLM creates a plan with tool calls based on the user's goal
2. **Plan Execution**: OpenClaw begins executing the plan step-by-step
3. **Policy Enforcement Point (PEP)**: Before each tool executes, the PEP intercepts the request
4. **Authorization Request**: PEP calls the external Cedar PDP with tool execution details
5. **Policy Evaluation**: Cedar evaluates the request against authorization policies
6. **Decision**: PDP returns either "permit" or "deny"
7. **Enforcement**:
   - **Permit**: Tool executes normally, result flows back to agent
   - **Deny**: Execution blocked, agent receives denial reason and can replan

### Implementation Changes

The authorization system required minimal changes to OpenClaw:

#### 1. Policy Decision Point Client (`src/authz/cedar-pdp-client.ts`)

**New file** that provides an HTTP client for calling the Cedar PDP:

```typescript
export async function authorizeTool(
  ctx: ToolAuthzContext,
  config: CedarPdpConfig,
): Promise<AuthzDecision>
```

**Key responsibilities:**
- Builds Cedar-compatible authorization requests
- Calls PDP via HTTP POST to `/authorize`
- Handles timeouts and fail-open/fail-closed behavior
- Returns structured decision with allow/deny and reason

#### 2. Configuration Types (`src/config/types.authz.ts`)

**New file** defining the authorization configuration schema:

```typescript
export type AuthzConfig = {
  pdp?: {
    enabled?: boolean;
    endpoint?: string;
    timeoutMs?: number;
    failOpen?: boolean;
  };
};
```

Added to main config in `src/config/types.openclaw.ts`:
```typescript
export type OpenClawConfig = {
  // ... existing config
  authz?: AuthzConfig;
};
```

#### 3. Configuration Schema (`src/config/zod-schema.ts`)

**Modified** to add Zod validation for authorization config:

```typescript
authz: z.object({
  pdp: z.object({
    enabled: z.boolean().optional(),
    endpoint: z.string().optional(),
    timeoutMs: z.number().int().positive().optional(),
    failOpen: z.boolean().optional(),
  }).strict().optional(),
}).strict().optional(),
```

#### 4. Policy Enforcement Point (`src/agents/pi-tools.before-tool-call.ts`)

**Modified** to add PEP logic in the existing tool wrapper:

```typescript
export async function runBeforeToolCallHook(args: {
  toolName: string;
  params: unknown;
  toolCallId?: string;
  ctx?: HookContext;
}): Promise<HookResult> {
  // Check if PDP is enabled
  const pdpConfig = args.ctx?.config?.authz?.pdp;
  if (pdpConfig?.enabled && pdpConfig.endpoint) {
    // Call PDP
    const decision = await authorizeTool({
      toolName: args.toolName,
      params: isPlainObject(args.params) ? args.params : {},
      toolCallId: args.toolCallId,
      agentId: args.ctx?.agentId,
      sessionKey: args.ctx?.sessionKey,
    }, {
      endpoint: pdpConfig.endpoint,
      timeoutMs: pdpConfig.timeoutMs,
      failOpen: pdpConfig.failOpen,
    });

    // Enforce decision
    if (!decision.allowed) {
      return { blocked: true, reason: decision.reason || "..." };
    }
  }

  // Continue with normal execution
  return { blocked: false };
}
```

**Key points:**
- Hooks into existing `wrapToolWithBeforeToolCallHook()` mechanism
- Only runs when `authz.pdp.enabled: true` in config
- Blocks tool execution and returns denial reason if denied
- Zero impact when authorization is disabled

#### 5. Tool Wrapper Integration (`src/agents/pi-tools.ts`)

**Modified** to pass config to tool hooks:

```typescript
const withHooks = normalized.map((tool) =>
  wrapToolWithBeforeToolCallHook(tool, {
    agentId,
    sessionKey: options?.sessionKey,
    config: options?.config,  // ← Added this line
  }),
);
```

### Design Principles

The implementation follows these principles:

1. **Minimal invasiveness**: Only ~200 lines of new code, leveraging existing hook mechanism
2. **Fail-safe defaults**: Authorization disabled by default, fail-closed by default
3. **Zero performance impact when disabled**: No overhead if `enabled: false`
4. **Pluggable architecture**: PDP is external, can be replaced with any Cedar-compatible service
5. **Clear separation**: Authorization logic isolated in `src/authz/`, doesn't pollute core agent code

## Scripts

### `cedar-pdp-server.py`

Simple HTTP server that wraps the Cedar CLI to provide a Policy Decision Point (PDP) API.

**Features:**
- HTTP POST `/authorize` - Authorization requests
- HTTP GET `/health` - Health check
- Validates schema and policies on startup
- Returns JSON responses compatible with OpenClaw PEP client

**Usage:**
```bash
# Start the server
python demo/cedar-pdp-server.py

# Or make it executable and run directly
./demo/cedar-pdp-server.py
```

**Output:**
```
============================================================
Cedar PDP Server for OpenClaw Authorization
============================================================
Listening:  http://localhost:8180
Schema:     policies/cedar/schema.cedarschema
Policies:   policies/cedar/policies.cedar
Entities:   policies/cedar/entities.json

Endpoints:
  POST /authorize - Authorization requests
  GET  /health    - Health check

Ready to authorize tool executions...
============================================================
```

### `test-pdp.py`

Test client that sends sample authorization requests to the PDP server.

**Features:**
- 6 test scenarios (3 Allow, 3 Deny)
- Verifies PDP server is running
- Color-coded pass/fail results

**Usage:**
```bash
# Make sure PDP server is running first!
python demo/test-pdp.py

# Or make it executable and run directly
./demo/test-pdp.py
```

**Output:**
```
======================================================================
Cedar PDP Authorization Tests
======================================================================

Test 1: Allow: Read user file
  Expected: Allow
  Decision: Allow
  ✓ PASS

Test 2: Deny: Write to /etc/passwd
  Expected: Deny
  Decision: Deny
  ✓ PASS

...

======================================================================
Results: 6 passed, 0 failed
======================================================================
```

## Quick Start

### Terminal 1: Start PDP Server

```bash
python demo/cedar-pdp-server.py
```

### Terminal 2: Run Tests

```bash
python demo/test-pdp.py
```

### Terminal 3: Send Custom Requests

```bash
curl -X POST http://localhost:8180/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "principal": "OpenClaw::Agent::\"agent-123\"",
    "action": "OpenClaw::Action::\"ToolExec::Read\"",
    "resource": "OpenClaw::Tool::\"read\"",
    "context": {
      "toolCallId": "test",
      "filePath": "/etc/passwd",
      "command": "",
      "sessionKey": "session"
    }
  }'
```

## Integration with OpenClaw

Once the PDP server is running, configure OpenClaw to use it:

**`openclaw.json5`:**
```json5
{
  authz: {
    pdp: {
      enabled: true,
      endpoint: "http://localhost:8180/authorize",
      timeoutMs: 2000,
      failOpen: false
    }
  }
}
```

Now when an agent tries to execute a tool, the PEP will check with the PDP first.

## Testing with Live OpenClaw Agent

To see the authorization system working with a real agent:

### Step 1: Start PDP Server

```bash
python3 demo/cedar-pdp-server.py
```

Keep this terminal open to watch authorization decisions in real-time.

### Step 2: Configure OpenClaw

Copy the sample config:
```bash
cp openclaw.json5 ~/.openclaw/config.json5
```

Or merge the `authz` section into your existing config.

### Step 3: Build OpenClaw (if from source)

```bash
pnpm install
pnpm build
```

### Step 4: Run Agent with Test Commands

Try commands that will be **DENIED**:

**Example 1: Write to system directory**
```bash
openclaw agent --message "Create a file at /etc/test.txt with content 'hello'"
```

Expected: Agent will attempt `write` tool, get denied, and explain it can't write to `/etc`.

**PDP log shows:**
```
[Deny] write - Write
```

**Example 2: Dangerous command**
```bash
openclaw agent --message "Run 'rm -rf /' to clean up"
```

Expected: Agent will attempt `bash` tool, get denied, and explain this is a dangerous command.

**PDP log shows:**
```
[Deny] bash - Bash
```

**Example 3: Read credentials**
```bash
openclaw agent --message "Show me my SSH private key from ~/.ssh/id_rsa"
```

Expected: Agent will attempt `read` tool, get denied, and explain it can't access credential files.

**PDP log shows:**
```
[Deny] read - Read
```

---

Try commands that will be **ALLOWED**:

**Example 4: Read user files**
```bash
openclaw agent --message "Read the README.md file"
```

Expected: Agent uses `read` tool, gets authorized, shows you the file.

**PDP log shows:**
```
[Allow] read - Read
```

**Example 5: Write to /tmp**
```bash
openclaw agent --message "Create a test file at /tmp/test.txt"
```

Expected: Agent uses `write` tool, gets authorized, creates the file.

**PDP log shows:**
```
[Allow] write - Write
```

**Example 6: Safe git command**
```bash
openclaw agent --message "What's the git status?"
```

Expected: Agent uses `bash` tool with `git status`, gets authorized, shows output.

**PDP log shows:**
```
[Allow] bash - Bash
```

### What Happens on Denial?

When a tool is denied:

1. **PEP blocks execution** before the tool runs
2. **Agent receives error:** `"Tool execution denied by policy: policy-3-deny-system-writes"`
3. **Agent can respond** by:
   - Explaining the limitation to the user
   - Suggesting alternatives (e.g., "I can write to /tmp instead")
   - Asking for clarification
   - Replanning with a different approach

The agent sees denials as failed tool calls and handles them gracefully in conversation.

### Observing Authorization in Real-Time

Watch the PDP server terminal to see real-time authorization decisions:

```
[Allow] read - Read
[Deny] write - Write
[Allow] bash - Bash
[Deny] bash - Bash
[Allow] read - Read
```

This shows which tools were allowed/denied, helping you verify policies are working correctly.

### Advanced Testing

For detailed testing scenarios and troubleshooting, see [TESTING.md](TESTING.md).

## Files

```
demo/
├── README.md                 # This file
├── cedar-pdp-server.py      # PDP HTTP server
└── test-pdp.py              # Test client
```

## Requirements

- Python 3.7+
- Cedar CLI (`brew install cedar`)
- `requests` library (`pip install requests`)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ OpenClaw Agent                                              │
│  ├─ Tool Call (e.g., "read /etc/passwd")                    │
│  └─ PEP intercepts                                          │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTP POST /authorize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ cedar-pdp-server.py (Port 8180)                             │
│  ├─ Receives authorization request                          │
│  ├─ Calls Cedar CLI                                         │
│  └─ Returns decision (Allow/Deny)                           │
└────────────────┬────────────────────────────────────────────┘
                 │ cedar authorize
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Cedar CLI                                                   │
│  ├─ Loads schema.cedarschema                                │
│  ├─ Loads policies.cedar                                    │
│  ├─ Loads entities.json                                     │
│  ├─ Evaluates policies                                      │
│  └─ Returns ALLOW or DENY                                   │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Server won't start

```
ERROR: cedar CLI not found
Install with: brew install cedar
```

**Fix:** Install Cedar CLI

### Connection refused

```
ERROR: PDP server is not running
```

**Fix:** Start the server first

### Policy validation fails

```
ERROR: policies/cedar/policies.cedar not found
```

**Fix:** Make sure you're running from the repo root

## Policy Quick Reference

The demo includes these Cedar policies (see [../policies/cedar/policies.cedar](../policies/cedar/policies.cedar) for full details):

| Policy | Effect | Description |
|--------|--------|-------------|
| policy-1-allow-readonly | Allow | Read-only tools (Read, Glob, Grep) |
| policy-2-allow-tmp-writes | Allow | Writes to `/tmp/*` and `/var/tmp/*` |
| policy-3-deny-system-writes | Deny | Writes to `/etc/*`, `/usr/*`, `/bin/*`, `/sbin/*` |
| policy-4-allow-safe-bash | Allow | Safe commands: `ls`, `cat`, `git status`, etc. |
| policy-5-deny-dangerous-bash | Deny | Dangerous: `rm -rf`, `shutdown`, `reboot`, etc. |
| policy-6-allow-git-ops | Allow | Git operations (`git add`, `git commit`, etc.) |
| policy-7-deny-credential-files | Deny | Credential paths: `~/.ssh/*`, `~/.aws/*`, etc. |
| policy-8-deny-network-tools | Deny | Network tools (Fetch, WebFetch, etc.) |
| policy-9-deny-process-tools | Deny | Process management tools |
| policy-10-workspace-scoped | Allow | Workspace-scoped permissions (example) |

**Policy Evaluation:**
- Cedar evaluates all policies and combines their results
- Any `forbid` policy overrides `permit` policies
- If no policy matches, the default is `Deny` (fail-closed)

## Next Steps

- **Modify policies** in `../policies/cedar/policies.cedar`
- **Add new test scenarios** to `test-pdp.py`
- **Test with live agent** (see "Testing with Live OpenClaw Agent" above)
- **Run the Jupyter notebook** for interactive demo: [cedar-authorization-demo.ipynb](cedar-authorization-demo.ipynb)
- **Read the testing guide** for advanced scenarios: [TESTING.md](TESTING.md)
