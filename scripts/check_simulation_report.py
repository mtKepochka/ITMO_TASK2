from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

DENYLIST = ("payment_issue", "refund_request", "account_security")
PROBABILITY_FIELDS = (
    "automation_rate",
    "escalation_rate",
    "fallback_rate",
    "automation_rejection_probability",
    "system_loss_probability",
)


def check_numbers(value: Any, location: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            check_numbers(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            check_numbers(child, f"{location}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or value < 0:
            raise AssertionError(f"invalid numeric value at {location}: {value}")


def check_report(report: dict[str, Any], location: str) -> None:
    check_numbers(report, location)
    assert report["arrived"] == (
        report["completed"] + report["lost"] + report["unfinished"]
    ), f"ticket balance failed in {location}"
    assert report["completed"] == (
        report["auto_replied"]
        + report["fallback_completed"]
        + report["sent_to_operator"]
    ), f"terminal outcome balance failed in {location}"

    for field in PROBABILITY_FIELDS:
        assert 0 <= report[field] <= 1, f"{field} out of range in {location}"
    for name, node in report["nodes"].items():
        assert 0 <= node["utilization"] <= 1, (
            f"utilization out of range for {name} in {location}"
        )
    for category in DENYLIST:
        outcomes = report["outcomes_by_category"].get(category, {})
        assert outcomes.get("auto_reply", 0) == 0, (
            f"unsafe auto-reply for {category} in {location}"
        )


def main(paths: list[str]) -> int:
    if not paths:
        raise SystemExit("usage: check_simulation_report.py REPORT.json [...]")
    checked = 0
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports = payload if isinstance(payload, list) else [payload]
        for index, report in enumerate(reports):
            check_report(report, f"{path}[{index}]")
            checked += 1
    print(f"simulation reports valid: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
