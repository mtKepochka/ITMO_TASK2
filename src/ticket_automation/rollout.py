from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import Category

RolloutMode = Literal["suggest", "auto_reply"]
VALID_CATEGORIES = {
    "service_outage",
    "access_issue",
    "payment_issue",
    "refund_request",
    "account_security",
    "general_question",
    "unknown",
}


@dataclass(frozen=True)
class RolloutConfig:
    version: str
    mode: RolloutMode
    kill_switch: bool
    traffic_percentage: int
    allowed_categories: frozenset[Category]

    @classmethod
    def load(cls, path: str | Path) -> RolloutConfig:
        source = Path(path)
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
            version = value["version"]
            mode = value["mode"]
            kill_switch = value["kill_switch"]
            traffic = value["traffic_percentage"]
            categories = value["allowed_categories"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid rollout configuration: {source}") from error
        if not isinstance(version, str) or not version:
            raise ValueError("rollout version must be a non-empty string")
        if mode not in {"suggest", "auto_reply"}:
            raise ValueError("rollout mode must be suggest or auto_reply")
        if not isinstance(kill_switch, bool):
            raise ValueError("rollout kill_switch must be boolean")
        if (
            not isinstance(traffic, int)
            or isinstance(traffic, bool)
            or not 0 <= traffic <= 100
        ):
            raise ValueError("rollout traffic_percentage must be between 0 and 100")
        if not isinstance(categories, list) or not all(
            isinstance(category, str) for category in categories
        ):
            raise ValueError("rollout allowed_categories must be a string list")
        unknown_categories = set(categories) - VALID_CATEGORIES
        if unknown_categories:
            raise ValueError(
                "rollout contains unknown categories: "
                + ", ".join(sorted(unknown_categories))
            )
        return cls(
            version=version,
            mode=mode,
            kill_switch=kill_switch,
            traffic_percentage=traffic,
            allowed_categories=frozenset(categories),  # type: ignore[arg-type]
        )

    def allows_auto_reply(self, ticket_id: str, category: Category) -> bool:
        if (
            self.kill_switch
            or self.mode != "auto_reply"
            or category not in self.allowed_categories
            or self.traffic_percentage == 0
        ):
            return False
        if self.traffic_percentage == 100:
            return True
        digest = hashlib.blake2b(ticket_id.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % 100
        return bucket < self.traffic_percentage
