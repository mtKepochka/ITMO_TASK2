import json
from pathlib import Path

import pytest

from ticket_automation.rollout import RolloutConfig


def test_rollout_bucket_is_stable() -> None:
    rollout = RolloutConfig(
        version="canary-v1",
        mode="auto_reply",
        kill_switch=False,
        traffic_percentage=50,
        allowed_categories=frozenset({"service_outage"}),
    )

    assert rollout.allows_auto_reply(
        "same-ticket", "service_outage"
    ) == rollout.allows_auto_reply("same-ticket", "service_outage")


def test_kill_switch_prevents_auto_reply() -> None:
    rollout = RolloutConfig(
        version="stopped-v1",
        mode="auto_reply",
        kill_switch=True,
        traffic_percentage=100,
        allowed_categories=frozenset({"service_outage"}),
    )

    assert not rollout.allows_auto_reply("ticket", "service_outage")


def test_invalid_rollout_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "rollout.json"
    path.write_text(
        json.dumps(
            {
                "version": "broken",
                "mode": "auto_reply",
                "kill_switch": False,
                "traffic_percentage": 101,
                "allowed_categories": ["service_outage"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="traffic_percentage"):
        RolloutConfig.load(path)
