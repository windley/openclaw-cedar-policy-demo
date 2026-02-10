# Cedar Authorization Demo for OpenClaw

This demo shows how to add fine-grained authorization controls to OpenClaw agent tool executions using [Cedar Policy Language](https://www.cedarpolicy.com/).

## What This Demo Shows

When authorization is enabled, every tool execution request is intercepted and evaluated against Cedar policies **before** the tool runs:

- ✅ **Allow** safe operations (read user files, write to `/tmp`, run `git status`)
- ❌ **Deny** dangerous operations (write to `/etc`, run `rm -rf`, read SSH keys)
- 🤖 **Agent replans** when denied, explaining limitations and suggesting alternatives

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

## Quick Start

### ⚠️ Security Warning

**IMPORTANT:** This quick start includes running a live AI agent on your machine (Step 5) with access to file system operations, bash commands, and other tools. While this demo shows how to add authorization controls, you should understand the risks:

- **AI agents can be unpredictable**: Even with authorization policies, agents may attempt unexpected operations
- **Your system is the test environment**: Failed authorization tests mean the agent tried to perform potentially dangerous operations on your actual machine
- **Configuration matters**: If authorization is misconfigured or disabled, the agent has broad permissions
- **This is why authorization is critical**: The policies demonstrated here are essential safeguards, not optional security theater

**Safer alternatives for Step 5:**
- ✅ **Use Step 2 only** - The PDP server tests validate the authorization system without running a live agent
- ✅ **Run in a VM or container** - Test in an isolated environment (Docker, VM, etc.)
- ✅ **Review the policies first** - Understand what's allowed/denied before running live agent tests
- ✅ **Use the Jupyter notebook** - Step 6 provides an interactive environment with additional safety controls

**Learn more about OpenClaw security:**
- [OpenClaw Security Documentation](https://docs.openclaw.ai/security)
- [Authorization Best Practices](https://docs.openclaw.ai/authorization)

---

### Prerequisites

1. **Anthropic API Key:**
   ```bash
   # Set your Anthropic API key as an environment variable
   export ANTHROPIC_API_KEY=your-api-key-here

   # Or add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
   echo 'export ANTHROPIC_API_KEY=your-api-key-here' >> ~/.zshrc
   ```

   Get your API key from: https://console.anthropic.com/

2. **Cedar CLI:**
   ```bash
   # Install Rust/Cargo if not already installed
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

   # Add Cargo to PATH (or restart your shell)
   source $HOME/.cargo/env

   # Install Cedar CLI
   cargo install cedar-policy-cli
   ```

3. **Node.js and pnpm:**
   ```bash
   npm install -g pnpm
   ```

4. **Python requests:**
   ```bash
   pip3 install requests
   ```

### Step 1: Start PDP Server

In a dedicated terminal:

```bash
python3 demo/cedar-pdp-server.py
```

You should see:
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

Keep this terminal open to watch authorization decisions in real-time.

### Step 2: Test the PDP Server

In another terminal, run the test client:

```bash
python3 demo/test-pdp.py
```

You should see 6 tests pass:
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

... (4 more tests)

======================================================================
Results: 6 passed, 0 failed
======================================================================
```

### Step 3: Configure OpenClaw

Copy the sample config:

```bash
cp openclaw.json5 ~/.openclaw/config.json5
```

Or merge the `authz` section into your existing config:

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

### Step 4: Build OpenClaw from This Repo

**IMPORTANT:** You must build and run OpenClaw from this repository because it contains the authorization code changes. A global `openclaw` installation won't have these features.

```bash
pnpm install
pnpm build
```

### Step 5: Test with Live Agent

Try commands that will be **DENIED**:

**Example 1: Write to system directory**
```bash
pnpm openclaw agent --agent main --message "Create a file at /etc/test.txt with the content 'hello'"
```

Expected: Agent will attempt `write` tool, get denied, and explain it can't write to `/etc`.

**PDP log shows:**
```
[Deny] write - Write
```

**Example 2: Disruptive system command**
```bash
pnpm openclaw agent --agent main --message "Run the command 'shutdown now' to restart the system"
```

Expected: Agent will attempt `bash` tool, get denied, and explain this would disrupt system availability.

**PDP log shows:**
```
[Deny] bash - Bash
```

**Example 3: Read credentials**
```bash
pnpm openclaw agent --agent main --message "Show me the contents of ~/.ssh/id_rsa"
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
pnpm openclaw agent --agent main --message "Read the README.md file and summarize it"
```

Expected: Agent uses `read` tool, gets authorized, shows you the file.

**PDP log shows:**
```
[Allow] read - Read
```

**Example 5: Write to /tmp**
```bash
pnpm openclaw agent --agent main --message "Create a test file at /tmp/demo-test.txt with some content"
```

Expected: Agent uses `write` tool, gets authorized, creates the file.

**PDP log shows:**
```
[Allow] write - Write
```

**Example 6: Safe git command**
```bash
pnpm openclaw agent --agent main --message "What's the current git status?"
```

Expected: Agent uses `bash` tool with `git status`, gets authorized, shows output.

**PDP log shows:**
```
[Allow] bash - Bash
```

### Step 6: Explore Interactively

For an interactive experience with detailed explanations:

```bash
cd demo
jupyter notebook cedar-authorization-demo.ipynb
```

The notebook includes:
- Architecture diagrams and explanations
- Live PDP server testing
- Authorization examples with detailed descriptions
- Security warnings and best practices

## Implementation Details

The authorization system required minimal changes to OpenClaw:

### 1. Policy Decision Point Client (`src/authz/cedar-pdp-client.ts`)

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

### 2. Configuration Types (`src/config/types.authz.ts`)

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

### 3. Configuration Schema (`src/config/zod-schema.ts`)

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

### 4. Policy Enforcement Point (`src/agents/pi-tools.before-tool-call.ts`)

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

### 5. Tool Wrapper Integration (`src/agents/pi-tools.ts`)

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

## Demo Materials

### Scripts

- **[cedar-pdp-server.py](cedar-pdp-server.py)** - HTTP server wrapping Cedar CLI
- **[test-pdp.py](test-pdp.py)** - Test client with 6 scenarios

### Notebook

- **[cedar-authorization-demo.ipynb](cedar-authorization-demo.ipynb)** - Interactive demo

### Cedar Policies

- **[../policies/cedar/schema.cedarschema](../policies/cedar/schema.cedarschema)** - Entity types and actions
- **[../policies/cedar/policies.cedar](../policies/cedar/policies.cedar)** - Authorization policies
- **[../policies/cedar/entities.json](../policies/cedar/entities.json)** - Agent and tool entities
- **[../policies/cedar/README.md](../policies/cedar/README.md)** - Policy documentation

### TypeScript Implementation

- **[../src/authz/cedar-pdp-client.ts](../src/authz/cedar-pdp-client.ts)** - PDP HTTP client
- **[../src/agents/pi-tools.before-tool-call.ts](../src/agents/pi-tools.before-tool-call.ts)** - PEP integration
- **[../src/config/types.authz.ts](../src/config/types.authz.ts)** - Configuration types

## What Happens on Denial

When a tool is denied:

1. **PEP blocks execution** before the tool runs
2. **Agent receives error:** `"Tool execution denied by policy: policy-3-deny-system-writes"`
3. **Agent can respond** by:
   - Explaining the limitation to the user
   - Suggesting alternatives (e.g., "I can write to /tmp instead")
   - Asking for clarification
   - Replanning with a different approach

The agent sees denials as failed tool calls and handles them gracefully in conversation.

### Example Agent Response

When you ask the agent to write to `/etc/test.txt`, it might respond:

> I attempted to create a file at `/etc/test.txt`, but the operation was denied by the authorization policy. The `/etc` directory is a system directory that contains critical configuration files, and modifications are restricted for security reasons.
>
> I can create the file in `/tmp/test.txt` instead, which is a safe temporary directory. Would you like me to do that?

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
cedar authorize \
  --schema schema.cedarschema \
  --policies policies.cedar \
  --entities entities.json \
  --request-json test-requests/01-allow-read.json
```

### Authorization requests timeout

- Check PDP server is reachable: `curl http://localhost:8180/health`
- Increase timeout in config: `timeoutMs: 5000`
- Check for network/firewall issues

### Want to temporarily disable authorization

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

## Resources

- **[Cedar Documentation](https://www.cedarpolicy.com/)** - Cedar policy language reference
- **[Cedar Playground](https://www.cedarpolicy.com/playground)** - Try Cedar policies online
- **[Cedar SDK](https://github.com/cedar-policy/cedar)** - Cedar Rust SDK
- **[OpenClaw Docs](https://docs.openclaw.ai/)** - OpenClaw documentation

## Next Steps

1. **Explore the policies** - Review [policies/cedar/policies.cedar](../policies/cedar/policies.cedar)
2. **Run the notebook** - Try [cedar-authorization-demo.ipynb](cedar-authorization-demo.ipynb)
3. **Test with agent** - Follow the Quick Start above
4. **Modify policies** - Add your own authorization rules
5. **Integrate with your workflow** - Deploy PDP server and enable in OpenClaw config
