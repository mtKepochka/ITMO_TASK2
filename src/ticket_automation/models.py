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


@dataclass(frozen=True)
class ProcessingResult:
    classification: ClassificationResult
    risk: RiskAssessment
    retrieval: RetrievalResult
    decision: Decision
    audit_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.classification.category,
            "confidence": self.classification.confidence,
            "classification_signals": list(self.classification.signals),
            "risk_level": self.risk.risk_level,
            "contains_pii": self.risk.contains_pii,
            "risk_reasons": list(self.risk.reasons),
            "retrieval": {
                "article_id": self.retrieval.article_id,
                "title": self.retrieval.title,
                "score": self.retrieval.score,
            },
            **self.decision.to_dict(),
            "audit_path": self.audit_path,
        }
