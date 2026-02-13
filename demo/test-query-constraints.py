#!/usr/bin/env python3
"""
Test script for Cedar TPE query-constraints endpoint.

Sends TPE queries to discover what operations are permitted.
"""
import json
import sys
import requests

PDP_URL = "http://localhost:8180/query-constraints"

# Test scenarios - query what's allowed without providing specific context values
TESTS = [
    {
        "name": "Query: What file paths can I write to?",
        "request": {
            "principal": 'OpenClaw::Agent::"main"',
            "action": 'OpenClaw::Action::"ToolExec::Write"',
            "resource": 'OpenClaw::Tool::"write"',
            # Note: no context.filePath - that's what we're querying about
        },
        "expected_residuals": True,  # Should return policy residuals
        "should_contain": "filePath"  # Residuals should mention filePath constraints
    },
    {
        "name": "Query: What bash commands can I execute?",
        "request": {
            "principal": 'OpenClaw::Agent::"main"',
            "action": 'OpenClaw::Action::"ToolExec::Bash"',
            "resource": 'OpenClaw::Tool::"bash"',
            # Note: no context.command - that's what we're querying about
        },
        "expected_residuals": True,
        "should_contain": "command"  # Residuals should mention command constraints
    },
    {
        "name": "Query: What files can I read?",
        "request": {
            "principal": 'OpenClaw::Agent::"main"',
            "action": 'OpenClaw::Action::"ToolExec::Read"',
            "resource": 'OpenClaw::Tool::"read"',
            # Note: no context.filePath - that's what we're querying about
        },
        "expected_residuals": True,
        "should_contain": "filePath"
    },
]

def run_test(test):
    """Run a single TPE query test."""
    print("\nTest: {}".format(test["name"]))
    print("  Query: {}".format(test["request"]["action"].split("::")[-1].strip('"')))

    try:
        response = requests.post(PDP_URL, json=test["request"], timeout=5)

        if response.status_code != 200:
            print("  ✗ FAIL - HTTP {}".format(response.status_code))
            print("  Response: {}".format(response.text))
            return False

        result = response.json()

        # Check decision
        if result.get("decision") != "UNKNOWN":
            print("  ✗ FAIL - Expected UNKNOWN decision, got {}".format(result.get("decision")))
            return False

        # Check residuals exist
        residuals = result.get("residuals", [])
        if test["expected_residuals"] and not residuals:
            print("  ✗ FAIL - No residuals returned")
            return False

        # Check residuals contain expected constraints
        residuals_text = "\n".join(residuals)
        if test["should_contain"] not in residuals_text:
            print("  ✗ FAIL - Residuals don't mention '{}'".format(test["should_contain"]))
            print("  Residuals: {}".format(residuals_text[:200]))
            return False

        # Success
        print("  Decision: {}".format(result["decision"]))
        print("  Residuals: {} policies".format(len(residuals)))

        # Show first residual as example
        if residuals:
            print("  Example constraint:")
            # Extract just the when clause for readability
            first_residual = residuals[0]
            for line in first_residual.split('\n'):
                if 'when' in line or 'like' in line or 'context' in line:
                    print("    {}".format(line.strip()))

        print("  ✓ PASS")
        return True

    except requests.exceptions.ConnectionError:
        print("  ✗ FAIL - Cannot connect to PDP server")
        print("  Make sure PDP server is running: python3 demo/cedar-pdp-server.py")
        return False
    except Exception as e:
        print("  ✗ FAIL - {}".format(str(e)))
        return False

def main():
    """Run all TPE query tests."""
    print("=" * 70)
    print("Cedar TPE Query Constraints Tests")
    print("=" * 70)

    passed = 0
    failed = 0

    for test in TESTS:
        if run_test(test):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 70)
    print("Results: {} passed, {} failed".format(passed, failed))
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
