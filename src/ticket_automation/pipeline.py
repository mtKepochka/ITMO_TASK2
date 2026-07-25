from __future__ import annotations

import os
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import Self

from .audit import JsonlAudit
from .classifier import classify
from .generator import (
    FALLBACK_TEMPLATES,
    DeterministicGenerator,
    ResponseGenerator,
)
from .models import (
    ClassificationResult,
    Decision,
    ProcessingResult,
    RetrievalResult,
    RiskAssessment,
    Ticket,
)
from .policy import ROUTES, decide
from .preprocessing import prepare_ticket
from .retrieval import LexicalRetriever
from .risk import apply_category_risk, assess_risk
from .rollout import RolloutConfig

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
DEFAULT_ROLLOUT_PATH = Path(
    os.getenv(
        "TICKET_ROLLOUT_CONFIG",
        PROJECT_ROOT / "config" / "rollout.json",
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
        rollout: RolloutConfig | None = None,
        rollout_path: str | Path | None = None,
        fast_path_deadline_ms: int = 500,
        scorer_workers: int = 8,
    ) -> None:
        if fast_path_deadline_ms <= 0:
            raise ValueError("fast_path_deadline_ms must be positive")
        if scorer_workers < 2:
            raise ValueError("scorer_workers must be at least 2")
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
        self.classification_threshold = float(
            getattr(self.classifier, "confidence_threshold", 0.7)
        )
        self.rollout = rollout or RolloutConfig.load(
            rollout_path or DEFAULT_ROLLOUT_PATH
        )
        self.fast_path_deadline_seconds = fast_path_deadline_ms / 1_000
        self._scorers = ThreadPoolExecutor(
            max_workers=scorer_workers,
            thread_name_prefix="ticket-scorer",
        )
        self._processed: dict[str, ProcessingResult] = {}
        self._inflight: dict[str, Future[ProcessingResult]] = {}
        self._state_lock = Lock()

    def process(
        self,
        ticket: Ticket,
        *,
        simulate_component_failure: str | None = None,
        simulate_component_timeout: str | None = None,
    ) -> ProcessingResult:
        owner = False
        with self._state_lock:
            cached = self._processed.get(ticket.id)
            if cached is not None:
                return cached
            inflight = self._inflight.get(ticket.id)
            if inflight is None:
                inflight = Future()
                self._inflight[ticket.id] = inflight
                owner = True
        if not owner:
            return inflight.result()

        try:
            result = self._process_once(
                ticket,
                simulate_component_failure=simulate_component_failure,
                simulate_component_timeout=simulate_component_timeout,
            )
        except BaseException as error:
            with self._state_lock:
                self._inflight.pop(ticket.id, None)
            inflight.set_exception(error)
            raise
        with self._state_lock:
            self._processed[ticket.id] = result
            self._inflight.pop(ticket.id, None)
        inflight.set_result(result)
        return result

    def _process_once(
        self,
        ticket: Ticket,
        *,
        simulate_component_failure: str | None,
        simulate_component_timeout: str | None,
    ) -> ProcessingResult:
        started = time.perf_counter()
        prepared = prepare_ticket(ticket)

        def classification_call() -> ClassificationResult:
            if simulate_component_failure == "classification":
                raise RuntimeError("simulated classification failure")
            if simulate_component_timeout == "classification":
                time.sleep(self.fast_path_deadline_seconds + 0.05)
            return self.classifier(prepared.safe_ticket)

        def risk_call() -> RiskAssessment:
            if simulate_component_failure == "risk":
                raise RuntimeError("simulated risk failure")
            if simulate_component_timeout == "risk":
                time.sleep(self.fast_path_deadline_seconds + 0.05)
            return assess_risk(prepared.normalized_ticket)

        calls = {
            "classification": self._scorers.submit(classification_call),
            "risk": self._scorers.submit(risk_call),
        }
        remaining = max(
            0.0,
            self.fast_path_deadline_seconds - (time.perf_counter() - started),
        )
        done, not_done = wait(calls.values(), timeout=remaining)
        technical_errors: list[str] = []
        values: dict[str, object] = {}
        for name, future in calls.items():
            if future in not_done:
                future.cancel()
                technical_errors.append(f"{name.upper()}:TIMEOUT")
                continue
            if future in done:
                try:
                    values[name] = future.result()
                except Exception as error:  # noqa: BLE001 - scorer boundary
                    technical_errors.append(
                        f"{name.upper()}:{type(error).__name__}"
                    )
        fast_path_ms = round((time.perf_counter() - started) * 1_000, 3)

        classification = values.get("classification")
        risk = values.get("risk")
        if not isinstance(classification, ClassificationResult):
            classification = ClassificationResult("unknown", 0.0, ())
        if not isinstance(risk, RiskAssessment):
            risk = RiskAssessment(
                "high",
                False,
                ("risk:technical_failure",),
            )
        risk = apply_category_risk(risk, classification.category)

        retrieval = RetrievalResult(None, "", "", 0.0)
        if technical_errors:
            decision = Decision(
                action="escalate",
                reason="technical_fallback",
                category=classification.category,
                confidence=classification.confidence,
                risk_level=risk.risk_level,
                draft_response=None,
                route=ROUTES[classification.category],
                fallback_used=False,
                rollout_version=self.rollout.version,
            )
        else:
            decision = decide(
                classification,
                risk,
                retrieval,
                min_classification_confidence=self.classification_threshold,
            )

        if decision.action != "escalate":
            retrieval = self.retriever.search(
                prepared.sanitized_text,
                classification.category,
            )
            decision = decide(
                classification,
                risk,
                retrieval,
                min_classification_confidence=self.classification_threshold,
            )

        if decision.action != "escalate" and retrieval.article_id:
            fallback_used = False
            try:
                draft = self.generator.generate(
                    prepared.safe_ticket,
                    prepared.sanitized_text,
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
                min_classification_confidence=self.classification_threshold,
            )
            if fallback_used and draft is None:
                decision = replace(
                    decision,
                    action="escalate",
                    reason="generator_failed_without_safe_fallback",
                    draft_response=None,
                    fallback_used=True,
                    auto_reply_eligible=False,
                )

        decision = self._apply_rollout(ticket.id, decision)
        result = ProcessingResult(
            classification=classification,
            risk=risk,
            retrieval=retrieval,
            decision=decision,
            audit_path=str(self.audit.path),
            fast_path_ms=fast_path_ms,
            technical_errors=tuple(technical_errors),
        )
        self.audit.write(
            ticket_id=ticket.id,
            classification=classification,
            risk=risk,
            retrieval=retrieval,
            decision=decision,
            latency_ms=(time.perf_counter() - started) * 1_000,
            classifier_version=self.classifier_version,
            knowledge_base_version=getattr(
                self.retriever,
                "version",
                "in-memory",
            ),
        )
        return result

    def _apply_rollout(self, ticket_id: str, decision: Decision) -> Decision:
        if not decision.auto_reply_eligible:
            return replace(decision, rollout_version=self.rollout.version)
        if self.rollout.allows_auto_reply(ticket_id, decision.category):
            return replace(decision, rollout_version=self.rollout.version)
        return replace(
            decision,
            action="suggest_to_agent",
            reason="rollout_suggest_mode",
            rollout_version=self.rollout.version,
        )

    def get_result(self, ticket_id: str) -> ProcessingResult | None:
        with self._state_lock:
            return self._processed.get(ticket_id)

    def close(self) -> None:
        self._scorers.shutdown(wait=True, cancel_futures=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
