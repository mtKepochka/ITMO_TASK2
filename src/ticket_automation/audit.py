from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from . import __version__
from .models import (
    ClassificationResult,
    Decision,
    RetrievalResult,
    RiskAssessment,
)

PIPELINE_VERSION = __version__


class JsonlAudit:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def write(
        self,
        *,
        ticket_id: str,
        classification: ClassificationResult,
        risk: RiskAssessment,
        retrieval: RetrievalResult,
        decision: Decision,
        latency_ms: float,
        classifier_version: str,
        knowledge_base_version: str,
        retriever_version: str,
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
            "retrieval_source": retrieval.source,
            "retrieval_fallback_used": retrieval.fallback_used,
            "action": decision.action,
            "reason": decision.reason,
            "route": decision.route,
            "fallback_used": decision.fallback_used,
            "auto_reply_eligible": decision.auto_reply_eligible,
            "rollout_version": decision.rollout_version,
            "latency_ms": round(latency_ms, 2),
            "pipeline_version": PIPELINE_VERSION,
            "classifier_version": classifier_version,
            "knowledge_base_version": knowledge_base_version,
            "retriever_version": retriever_version,
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as destination:
                destination.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
