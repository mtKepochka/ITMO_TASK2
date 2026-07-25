from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Callable

from .audit import JsonlAudit
from .classifier import classify
from .generator import (
    FALLBACK_TEMPLATES,
    DeterministicGenerator,
    ResponseGenerator,
)
from .models import (
    ClassificationResult,
    ProcessingResult,
    RetrievalResult,
    Ticket,
)
from .policy import decide
from .retrieval import LexicalRetriever
from .risk import assess_risk, redact_pii

PROJECT_ROOT = Path(
    os.getenv("TICKET_PROJECT_ROOT", Path(__file__).parents[2])
).resolve()
DEFAULT_KB_PATH = Path(
    os.getenv("TICKET_KB_PATH", PROJECT_ROOT / "data" / "knowledge_base.json")
)
DEFAULT_AUDIT_PATH = Path(
    os.getenv(
        "TICKET_AUDIT_PATH",
        PROJECT_ROOT / "audit" / "decisions.jsonl",
    )
)


class TicketPipeline:
    def __init__(
        self,
        *,
        retriever: LexicalRetriever | None = None,
        generator: ResponseGenerator | None = None,
        audit: JsonlAudit | None = None,
        classifier: Callable[[Ticket], ClassificationResult] | None = None,
    ) -> None:
        self.retriever = retriever or LexicalRetriever.from_file(DEFAULT_KB_PATH)
        self.generator = generator or DeterministicGenerator()
        self.audit = audit or JsonlAudit(DEFAULT_AUDIT_PATH)
        self.classifier = classifier or classify
        self.classifier_version = getattr(
            self.classifier,
            "version",
            (
                "rules-v1"
                if self.classifier is classify
                else type(self.classifier).__name__
            ),
        )
        self._processed: dict[str, ProcessingResult] = {}

    def process(self, ticket: Ticket) -> ProcessingResult:
        if ticket.id in self._processed:
            return self._processed[ticket.id]

        started = perf_counter()
        classification = self.classifier(ticket)
        risk = assess_risk(ticket, classification.category)
        sanitized_text = redact_pii(
            f"{ticket.subject} {ticket.text}"
        )
        retrieval = RetrievalResult(None, "", "", 0.0)
        decision = decide(classification, risk, retrieval)

        if decision.action != "escalate":
            retrieval = self.retriever.search(
                sanitized_text,
                classification.category,
            )
            decision = decide(classification, risk, retrieval)

        if decision.action != "escalate" and retrieval.article_id:
            fallback_used = False
            try:
                draft = self.generator.generate(
                    ticket,
                    sanitized_text,
                    retrieval,
                )
            except (RuntimeError, TimeoutError, ValueError):
                fallback_used = True
                draft = FALLBACK_TEMPLATES.get(classification.category)
            decision = decide(
                classification,
                risk,
                retrieval,
                draft_response=draft,
                fallback_used=fallback_used,
            )
            if fallback_used and draft is None:
                decision = decision.__class__(
                    action="escalate",
                    reason="generator_failed_without_safe_fallback",
                    category=decision.category,
                    confidence=decision.confidence,
                    risk_level=decision.risk_level,
                    draft_response=None,
                    route=decision.route,
                    fallback_used=True,
                )

        result = ProcessingResult(
            classification=classification,
            risk=risk,
            retrieval=retrieval,
            decision=decision,
            audit_path=str(self.audit.path),
        )
        self.audit.write(
            ticket_id=ticket.id,
            classification=classification,
            risk=risk,
            retrieval=retrieval,
            decision=decision,
            latency_ms=(perf_counter() - started) * 1000,
            classifier_version=self.classifier_version,
            knowledge_base_version=getattr(
                self.retriever,
                "version",
                "in-memory",
            ),
        )
        self._processed[ticket.id] = result
        return result
