# Cedar Human-in-the-Loop Demo for OpenClaw

**Advanced Feature:** This demo adds a **hard human-in-the-loop** for simulated email send. Policy allows `send_email` only after a Yubikey (WebAuthn) attestation bound to that exact message. Timeout is a hard deny with no retry of the wait.

> Complete the [reactive authorization demo](README.md) first.

## What This Demo Adds

Previous demos answer “may the agent do this?” This one answers “may the agent send *this* email now that a human has cryptographically attested it?”

- **Gather and draft** stay ungated (read, write a scratch file, etc.)
- **`send_email`** parks until you approve it on the approver page with a Yubikey
- Delivery is simulated: one JSON file per send under `demo/mailbox/sent/`, named with a UTC datetime
- There is **no notification**. Open [http://localhost:8180/approver](http://localhost:8180/approver) when a send is waiting
- If nobody taps before timeout, the tool call is denied and the PEP does not wait again

```
Agent → send_email → Cedar deny (no approval) → park
Human opens /approver → Yubikey tap bound to this request hash
PEP retries Cedar with injected humanApproval → permit → mailbox file
```

## Prerequisites

1. Completed the [basic Cedar demo](README.md)
2. Python packages (use a venv; macOS Python is PEP 668 managed):

```bash
python3 -m venv demo/.venv
demo/.venv/bin/pip install -r demo/requirements.txt
```
3. A FIDO2 authenticator for the live agent walkthrough. Policy tests do not need one. For a *physical* human gate, register the passkey on a Yubikey (see [Passkeys and Yubikeys](#passkeys-and-yubikeys)).

## Passkeys and Yubikeys

The approver does not talk to Yubico’s proprietary APIs. Approval is ordinary **WebAuthn / passkeys**: the browser creates or asserts a credential, and the PDP verifies the signature against a challenge bound to this send.

That means the “human” in HITL is only as strong as where the passkey lives:

- **On a Yubikey (or other roaming hardware key):** the credential is stored on the device. Approval requires a person to present that key and touch it. Software agents cannot do that.
- **In a software authenticator** (iCloud Keychain, a password manager, the browser’s platform store): the same WebAuthn ceremony succeeds, but there is no hardware presence. Anything that can unlock that store can approve.

Registration asks for a **cross-platform (roaming)** authenticator so the browser should offer a security key rather than Touch ID / a cloud passkey. Still choose the Yubikey in the prompt. If you previously registered a software passkey, click **Register Yubikey** again with the key inserted so the stored credential is the hardware one.

For a while at least, we do not expect software agents to physically insert and use Yubikeys. That is the point of this demo.

## Quick Start

### Step 1: Start the PDP (also serves the approver)

```bash
demo/.venv/bin/python demo/cedar-pdp-server.py
```

You should see:

```
HITL:       policies/cedar/policies-hitl.cedar
  GET  /approver           - Human-in-the-loop Yubikey page
```

Open [http://localhost:8180/approver](http://localhost:8180/approver) (must be `localhost`, not `127.0.0.1`, so WebAuthn origin matches) and register the Yubikey once. The page stays empty until a send is attempted.

### Step 2: Policy tests (no Yubikey)

```bash
demo/.venv/bin/python demo/test-hitl.py
```

Expected: send without approval is denied; send with a matching WebAuthn approval is allowed; reads still pass.

### Step 3: Live agent send

If you already have OpenClaw configured from an earlier demo, add `hitlEndpoint` and `hitlTimeoutMs` under `authz.pdp` in `~/.openclaw/openclaw.json` (or recopy `openclaw.json5`). The PEP also falls back to the PDP origin when `hitlEndpoint` is omitted.

```bash
pnpm openclaw agent --agent main --message \
  "Send a simulated email to alex@example.com with subject 'Weekly summary' and a short body. Use the send_email tool."
```

Then, on the approver page, review To/Subject/Body and tap the Yubikey. A file appears in `demo/mailbox/sent/`, for example `2026-09-21T195312.441Z.json`.

If you do not tap before `hitlTimeoutMs` (default 180 seconds), the agent receives a hard deny and no mailbox file is written.

### Step 4: Verify previous demos still work

```bash
python3 demo/test-pdp.py
python3 demo/test-query-constraints.py
python3 demo/test-delegation.py
```

## Cedar Policies

| Policy ID | Type | Purpose |
|-----------|------|---------|
| `hitl-1-allow-send-with-approval` | permit | Allow `SendEmail` when injected approval is verified WebAuthn and `requestHash` matches |
| `hitl-2-forbid-send-without-approval` | forbid | Deny `SendEmail` unless that approval is present |

The PEP injects `humanApproval`. The agent cannot supply it. Timeout lives in the PEP because Cedar has no `now()`.

## Mailbox sink

Approved sends write JSON to `demo/mailbox/sent/`:

```json
{
  "to": "alex@example.com",
  "subject": "Weekly summary",
  "body": "Here is the draft summary.",
  "sentAt": "2026-09-21T19:53:12.441Z",
  "filename": "2026-09-21T195312.441Z.json"
}
```

Colons are stripped from the filename so successive sends stay distinct and easy to inspect.

## Implementation

- Approver UI: `demo/hitl/static/` served at `/approver`
- Pending store + WebAuthn: `demo/hitl/`
- Tool: `src/agents/tools/send-email-tool.ts`
- PEP park/wait: `src/agents/pi-tools.before-tool-call.ts`
- Policies: `policies/cedar/policies-hitl.cedar`
