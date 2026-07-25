#!/bin/sh
set -eu

output_file="$(mktemp)"
failure_file="$(mktemp)"
audit_file="$(mktemp)"
trap 'rm -f "$output_file" "$failure_file" "$audit_file"' EXIT

python -m ticket_automation.cli demo --audit "$audit_file" >"$output_file"
grep -q '"ticket_id": "demo-happy"' "$output_file"
grep -q '"action": "auto_reply"' "$output_file"
grep -q '"ticket_id": "demo-risky"' "$output_file"
grep -q '"reason": "high_risk_or_pii"' "$output_file"
grep -q '"ticket_id": "demo-low-confidence"' "$output_file"
grep -q '"reason": "low_classification_confidence"' "$output_file"
if grep -q '4111 1111' "$output_file" || grep -q '4111 1111' "$audit_file"; then
    echo "card number leaked into output or audit" >&2
    exit 1
fi

python -m ticket_automation.cli demo \
    --simulate-generator-failure \
    --audit "$audit_file" >"$failure_file"
grep -q '"fallback_used": true' "$failure_file"

echo "smoke test passed"
