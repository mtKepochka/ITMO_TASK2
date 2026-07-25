from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Category = Literal[
    "service_outage",
    "access_issue",
    "payment_issue",
    "refund_request",
    "account_security",
    "general_question",
    "unknown",
]
RiskLevel = Literal["low", "medium", "high"]
Action = Literal["auto_reply", "suggest_to_agent", "escalate"]


@dataclass(frozen=True)
class Ticket:
    id: str
    channel: str
    subject: str
    text: str
    created_at: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Ticket:
        return cls(
            id=str(value["id"]),
            channel=str(value["channel"]),
            subject=str(value.get("subject", "")),
            text=str(value["text"]),
            created_at=str(value["created_at"]),
        )


@dataclass(frozen=True)
class ClassificationResult:
    category: Category
    confidence: float
    signals: tuple[str, ...]


@dataclass(frozen=True)
class RiskAssessment:
    risk_level: RiskLevel
    contains_pii: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalResult:
    article_id: str | None
    title: str
    content: str
    score: float


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    category: Category
    confidence: float
    risk_level: RiskLevel
    draft_response: str | None
    route: str
    fallback_used: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
