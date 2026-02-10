#!/bin/bash
# Test all Cedar authorization requests
# Requires: cedar CLI installed (brew install cedar)

set -e

SCHEMA="schema.cedarschema"
POLICIES="policies.cedar"
ENTITIES="entities.json"
TEST_DIR="test-requests"

echo "=================================="
echo "Cedar Authorization Policy Tests"
echo "=================================="
echo ""

# Check if cedar is installed
if ! command -v cedar &> /dev/null; then
    echo "ERROR: cedar CLI not found"
    echo "Install with: brew install cedar"
    exit 1
fi

# Validate schema and policies first
echo "Validating schema and policies..."
if cedar validate --schema "$SCHEMA" --policies "$POLICIES"; then
    echo "✓ Schema and policies are valid"
    echo ""
else
    echo "✗ Schema or policies validation failed"
    exit 1
fi

# Run each test
test_count=0
pass_count=0
fail_count=0

run_test() {
    local test_file=$1
    local expected=$2
    local description=$3

    test_count=$((test_count + 1))

    echo "Test $test_count: $description"
    echo "  Request: $test_file"
    echo -n "  Expected: $expected ... "

    # Run cedar authorize
    result=$(cedar authorize \
        --schema "$SCHEMA" \
        --policies "$POLICIES" \
        --entities "$ENTITIES" \
        --request-json "$TEST_DIR/$test_file" \
        2>&1 || true)

    # Check result
    if echo "$result" | grep -q "ALLOW" && [ "$expected" = "ALLOW" ]; then
        echo "✓ PASS"
        pass_count=$((pass_count + 1))
    elif echo "$result" | grep -q "DENY" && [ "$expected" = "DENY" ]; then
        echo "✓ PASS"
        pass_count=$((pass_count + 1))
    else
        echo "✗ FAIL"
        echo "  Actual result: $result"
        fail_count=$((fail_count + 1))
    fi
    echo ""
}

# Run all tests
echo "Running authorization tests..."
echo ""

run_test "01-allow-read.json" "ALLOW" \
    "Allow reading user files (policy-1-allow-readonly)"

run_test "02-deny-system-write.json" "DENY" \
    "Deny writing to /etc/passwd (policy-3-deny-system-writes)"

run_test "03-allow-tmp-write.json" "ALLOW" \
    "Allow writing to /tmp directory (policy-2-allow-tmp-writes)"

run_test "04-deny-dangerous-bash.json" "DENY" \
    "Deny dangerous rm -rf command (policy-5-deny-dangerous-bash)"

run_test "05-allow-git-status.json" "ALLOW" \
    "Allow safe git status command (policy-4-allow-safe-bash)"

run_test "06-deny-credential-read.json" "DENY" \
    "Deny reading SSH private key (policy-7-deny-credential-files)"

# Summary
echo "=================================="
echo "Test Summary"
echo "=================================="
echo "Total:  $test_count"
echo "Passed: $pass_count"
echo "Failed: $fail_count"
echo ""

if [ $fail_count -eq 0 ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Some tests failed"
    exit 1
fi
