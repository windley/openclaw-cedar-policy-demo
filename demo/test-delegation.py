#!/usr/bin/env python3
"""
Test script for Cedar delegation-as-data authorization.

Tests that SubAgents with delegations are properly authorized/denied,
and that main Agents remain unaffected.

Prerequisites:
  - Cedar PDP server running: python3 demo/cedar-pdp-server.py
  - pip install requests
"""
import json
import sys
import requests

PDP_URL = "http://localhost:8180/authorize"

# Shared helpers
def subagent_principal(eid="agent:main:subagent:demo-reader"):
    return f'OpenClaw::SubAgent::"{eid}"'

def agent_principal(eid="agent-abc123"):
    return f'OpenClaw::Agent::"{eid}"'

def action(tool):
    return f'OpenClaw::Action::"ToolExec::{tool}"'

def resource(tool):
    return f'OpenClaw::Tool::"{tool.lower()}"'


TESTS = [
    # ── SubAgent with valid delegation ────────────────────────────────
    {
        "name": "SubAgent delegated read: allow Read /tmp/data.txt",
        "request": {
            "principal": subagent_principal(),
            "action": action("Read"),
            "resource": resource("read"),
            "context": {
                "toolCallId": "deleg_001",
                "filePath": "/tmp/data.txt",
                "command": "",
                "isDelegated": True,
                "delegatedActions": ["read", "glob"],
                "delegatedPathPattern": "/tmp/*",
            },
        },
        "expected": "Allow",
    },
    {
        "name": "SubAgent delegated read: allow Glob (in delegatedActions)",
        "request": {
            "principal": subagent_principal(),
            "action": action("Glob"),
            "resource": resource("glob"),
            "context": {
                "toolCallId": "deleg_002",
                "filePath": "/tmp/data",
                "command": "",
                "isDelegated": True,
                "delegatedActions": ["read", "glob"],
                "delegatedPathPattern": "/tmp/*",
            },
        },
        "expected": "Allow",
    },

    # ── SubAgent delegation scope enforcement ─────────────────────────
    {
        "name": "SubAgent delegated read: deny Write (not in delegatedActions)",
        "request": {
            "principal": subagent_principal("agent:main:subagent:demo-writer"),
            "action": action("Write"),
            "resource": resource("write"),
            "context": {
                "toolCallId": "deleg_003",
                "filePath": "/tmp/out.txt",
                "command": "",
                "isDelegated": True,
                "delegatedActions": ["read"],  # write not included
            },
        },
        "expected": "Deny",
    },
    {
        "name": "SubAgent delegated to /tmp: deny Read /etc/passwd (path constraint)",
        "request": {
            "principal": subagent_principal(),
            "action": action("Read"),
            "resource": resource("read"),
            "context": {
                "toolCallId": "deleg_004",
                "filePath": "/etc/passwd",
                "command": "",
                "isDelegated": True,
                "delegatedActions": ["read"],
                "delegatedPathPattern": "/tmp/*",
            },
        },
        "expected": "Deny",
    },
    {
        "name": "SubAgent delegated git-only: deny Bash 'rm -rf /' (command constraint)",
        "request": {
            "principal": subagent_principal("agent:main:subagent:demo-writer"),
            "action": action("Bash"),
            "resource": resource("bash"),
            "context": {
                "toolCallId": "deleg_005",
                "filePath": "",
                "command": "rm -rf /",
                "isDelegated": True,
                "delegatedActions": ["bash"],
                "delegatedCommandPattern": "git *",
            },
        },
        "expected": "Deny",
    },
    {
        "name": "SubAgent delegated git-only: allow Bash 'git status' (command matches)",
        "request": {
            "principal": subagent_principal("agent:main:subagent:demo-writer"),
            "action": action("Bash"),
            "resource": resource("bash"),
            "context": {
                "toolCallId": "deleg_006",
                "filePath": "",
                "command": "git status",
                "isDelegated": True,
                "delegatedActions": ["bash"],
                "delegatedCommandPattern": "git *",
            },
        },
        "expected": "Allow",
    },

    # ── SubAgent without delegation ───────────────────────────────────
    {
        "name": "SubAgent without delegation: deny Read",
        "request": {
            "principal": subagent_principal(),
            "action": action("Read"),
            "resource": resource("read"),
            "context": {
                "toolCallId": "deleg_007",
                "filePath": "/tmp/data.txt",
                "command": "",
                # isDelegated is false / missing
            },
        },
        "expected": "Deny",
    },
    {
        "name": "SubAgent with isDelegated=false: deny Read",
        "request": {
            "principal": subagent_principal(),
            "action": action("Read"),
            "resource": resource("read"),
            "context": {
                "toolCallId": "deleg_008",
                "filePath": "/tmp/data.txt",
                "command": "",
                "isDelegated": False,
            },
        },
        "expected": "Deny",
    },

    # ── Main Agent unaffected ─────────────────────────────────────────
    {
        "name": "Main Agent: allow Read (unaffected by delegation policies)",
        "request": {
            "principal": agent_principal(),
            "action": action("Read"),
            "resource": resource("read"),
            "context": {
                "toolCallId": "deleg_009",
                "filePath": "/home/user/code/main.py",
                "command": "",
                "sessionKey": "test-session",
            },
        },
        "expected": "Allow",
    },
    {
        "name": "Main Agent: allow Write /tmp (unaffected by delegation policies)",
        "request": {
            "principal": agent_principal(),
            "action": action("Write"),
            "resource": resource("write"),
            "context": {
                "toolCallId": "deleg_010",
                "filePath": "/tmp/output.txt",
                "command": "",
                "sessionKey": "test-session",
            },
        },
        "expected": "Allow",
    },
]


def run_tests():
    passed = 0
    failed = 0

    print("=" * 70)
    print("Cedar Delegation-as-Data Authorization Tests")
    print("=" * 70)
    print()

    for test in TESTS:
        name = test["name"]
        expected = test["expected"]
        try:
            resp = requests.post(PDP_URL, json=test["request"], timeout=5)
            resp.raise_for_status()
            result = resp.json()
            decision = result["decision"]
            policies = result.get("diagnostics", {}).get("reason", [])

            status = "PASS" if decision == expected else "FAIL"
            symbol = "\u2713" if status == "PASS" else "\u2717"

            print(f"Test: {name}")
            print(f"  Decision: {decision} (expected {expected})")
            if policies:
                print(f"  Policies: {', '.join(policies)}")
            print(f"  {symbol} {status}")
            print()

            if status == "PASS":
                passed += 1
            else:
                failed += 1
        except requests.ConnectionError:
            print(f"Test: {name}")
            print("  ERROR: Cannot connect to PDP server at {}".format(PDP_URL))
            print("  Start it with: python3 demo/cedar-pdp-server.py")
            print()
            failed += 1
        except Exception as e:
            print(f"Test: {name}")
            print(f"  ERROR: {e}")
            print()
            failed += 1

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
