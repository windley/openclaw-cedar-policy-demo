#!/usr/bin/env python3
"""
Test script for Cedar PDP server.

Sends sample authorization requests and displays results.
"""
import json
import sys
import requests
from pathlib import Path

PDP_URL = "http://localhost:8180/authorize"

# Test scenarios
TESTS = [
    {
        "name": "Allow: Read user file",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Read"',
            "resource": 'OpenClaw::Tool::"read"',
            "context": {
                "toolCallId": "test_001",
                "filePath": "/home/user/code/main.py",
                "command": "",
                "sessionKey": "test-session"
            }
        },
        "expected": "Allow"
    },
    {
        "name": "Deny: Write to /etc/passwd",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Write"',
            "resource": 'OpenClaw::Tool::"write"',
            "context": {
                "toolCallId": "test_002",
                "filePath": "/etc/passwd",
                "command": "",
                "sessionKey": "test-session"
            }
        },
        "expected": "Deny"
    },
    {
        "name": "Allow: Write to /tmp",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Write"',
            "resource": 'OpenClaw::Tool::"write"',
            "context": {
                "toolCallId": "test_003",
                "filePath": "/tmp/output.txt",
                "command": "",
                "sessionKey": "test-session"
            }
        },
        "expected": "Allow"
    },
    {
        "name": "Deny: Dangerous rm -rf",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Bash"',
            "resource": 'OpenClaw::Tool::"bash"',
            "context": {
                "toolCallId": "test_004",
                "filePath": "",
                "command": "rm -rf /",
                "sessionKey": "test-session"
            }
        },
        "expected": "Deny"
    },
    {
        "name": "Allow: Safe git command",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Bash"',
            "resource": 'OpenClaw::Tool::"bash"',
            "context": {
                "toolCallId": "test_005",
                "filePath": "",
                "command": "git status",
                "sessionKey": "test-session"
            }
        },
        "expected": "Allow"
    },
    {
        "name": "Deny: Read SSH key",
        "request": {
            "principal": 'OpenClaw::Agent::"agent-abc123"',
            "action": 'OpenClaw::Action::"ToolExec::Read"',
            "resource": 'OpenClaw::Tool::"read"',
            "context": {
                "toolCallId": "test_006",
                "filePath": "/home/user/.ssh/id_rsa",
                "command": "",
                "sessionKey": "test-session"
            }
        },
        "expected": "Deny"
    },
]

def test_pdp():
    """Run all test scenarios."""
    print("=" * 70)
    print("Cedar PDP Authorization Tests")
    print("=" * 70)
    print()

    # Check if server is running
    try:
        response = requests.get("http://localhost:8180/health", timeout=2)
        if response.status_code != 200:
            print("ERROR: PDP server is not healthy")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("ERROR: PDP server is not running")
        print("Start it with: python demo/cedar-pdp-server.py")
        sys.exit(1)

    passed = 0
    failed = 0

    for i, test in enumerate(TESTS, 1):
        print(f"Test {i}: {test['name']}")
        print(f"  Expected: {test['expected']}")

        try:
            response = requests.post(
                PDP_URL,
                json=test['request'],
                headers={'Content-Type': 'application/json'},
                timeout=5
            )

            if response.status_code == 200:
                result = response.json()
                decision = result['decision']
                print(f"  Decision: {decision}")

                if decision == test['expected']:
                    print("  ✓ PASS")
                    passed += 1
                else:
                    print("  ✗ FAIL")
                    failed += 1
            else:
                print(f"  ✗ HTTP {response.status_code}: {response.text}")
                failed += 1

        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

        print()

    # Summary
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    test_pdp()
