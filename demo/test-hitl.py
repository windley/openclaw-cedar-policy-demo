#!/usr/bin/env python3
"""Cedar HITL authorization tests for simulated email send."""
import sys
import requests

PDP_URL = "http://localhost:8180/authorize"
HASH = "a" * 64

def ctx(**extra):
    base = {
        "toolCallId": "hitl_test",
        "filePath": "",
        "command": "",
        "emailTo": "alex@example.com",
        "emailSubject": "Weekly summary",
        "emailBody": "Here is the draft summary.",
        "requestHash": HASH,
    }
    base.update(extra)
    return base

def send_request(**context_extra):
    return {
        "principal": 'OpenClaw::Agent::"agent-abc123"',
        "action": 'OpenClaw::Action::"ToolExec::SendEmail"',
        "resource": 'OpenClaw::Tool::"send_email"',
        "context": ctx(**context_extra),
    }

TESTS = [
    {
        "name": "Deny: SendEmail without human approval",
        "request": send_request(),
        "expected": "Deny",
    },
    {
        "name": "Allow: SendEmail with matching WebAuthn approval",
        "request": send_request(
            humanApproval={
                "verified": True,
                "method": "webauthn",
                "requestHash": HASH,
            }
        ),
        "expected": "Allow",
    },
    {
        "name": "Deny: SendEmail with mismatched requestHash",
        "request": send_request(
            humanApproval={
                "verified": True,
                "method": "webauthn",
                "requestHash": "b" * 64,
            }
        ),
        "expected": "Deny",
    },
    {
        "name": "Deny: SendEmail with unverified approval",
        "request": send_request(
            humanApproval={
                "verified": False,
                "method": "webauthn",
                "requestHash": HASH,
            }
        ),
        "expected": "Deny",
    },
    {
        "name": "Allow: Read still ungated",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Read"',
            "resource": 'OpenClaw::Tool::"read"',
            "context": {
                "toolCallId": "hitl_read",
                "filePath": "/tmp/notes.txt",
                "command": "",
            },
        },
        "expected": "Allow",
    },
]


def main():
    print("=" * 70)
    print("Cedar HITL Email Authorization Tests")
    print("=" * 70)
    print()

    try:
        health = requests.get("http://localhost:8180/health", timeout=2)
        if health.status_code != 200:
            print("ERROR: PDP server is not healthy")
            sys.exit(1)
    except requests.RequestException:
        print("ERROR: PDP server is not running at http://localhost:8180")
        print("Start it with: python3 demo/cedar-pdp-server.py")
        sys.exit(1)

    passed = 0
    failed = 0
    for test in TESTS:
        response = requests.post(PDP_URL, json=test["request"], timeout=10)
        response.raise_for_status()
        payload = response.json()
        decision = payload.get("decision")
        ok = decision == test["expected"]
        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"Test: {test['name']}")
        print(f"  Decision: {decision} (expected {test['expected']})")
        print(f"  Policies: {', '.join(payload.get('diagnostics', {}).get('reason') or []) or 'none'}")
        print(f"  ✓ {mark}" if ok else f"  ✗ {mark}")
        print()

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
