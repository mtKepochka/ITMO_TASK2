from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    ClassificationResult,
    Decision,
    RetrievalResult,
    RiskAssessment,
)

PIPELINE_VERSION = "0.1.0"


class JsonlAudit:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(
        self,
        *,
        ticket_id: str,
        classification: ClassificationResult,
        risk: RiskAssessment,
        retrieval: RetrievalResult,
        decision: Decision,
        latency_ms: float,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "ticket_id": ticket_id,
            "category": classification.category,
            "confidence": classification.confidence,
            "classification_signals": list(classification.signals),
            "risk_level": risk.risk_level,
            "contains_pii": risk.contains_pii,
            "risk_reasons": list(risk.reasons),
            "retrieval_article_id": retrieval.article_id,
            "retrieval_score": retrieval.score,
            "action": decision.action,
            "reason": decision.reason,
            "route": decision.route,
            "fallback_used": decision.fallback_used,
            "latency_ms": round(latency_ms, 2),
            "pipeline_version": PIPELINE_VERSION,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
