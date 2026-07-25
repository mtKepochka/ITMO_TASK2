import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from ticket_automation.audit import JsonlAudit
from ticket_automation.generator import DeterministicGenerator
from ticket_automation.models import RetrievalResult, Ticket
from ticket_automation.pipeline import TicketPipeline
from ticket_automation.rollout import RolloutConfig


def ticket(ticket_id: str, text: str, subject: str = "") -> Ticket:
    return Ticket(ticket_id, "chat", subject, text, "2026-07-25T12:00:00Z")


def pipeline(tmp_path: Path, *, generator=None) -> TicketPipeline:
    return TicketPipeline(
        generator=generator,
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )


def test_happy_path_creates_grounded_operator_suggestion(tmp_path: Path) -> None:
    result = pipeline(tmp_path).process(
        ticket(
            "happy",
            "Приложение не открывается. Это общий сбой?",
            "Приложение недоступно",
        )
    )

    assert result.classification.category == "service_outage"
    assert result.risk.risk_level == "low"
    assert result.retrieval.article_id == "kb-outage-01"
    assert result.decision.action == "suggest_to_agent"
    assert result.decision.auto_reply_eligible is True
    assert result.decision.reason == "rollout_suggest_mode"
    assert result.decision.draft_response


def test_explicit_auto_rollout_allows_auto_reply(tmp_path: Path) -> None:
    app = TicketPipeline(
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
        rollout=RolloutConfig(
            version="test-auto-v1",
            mode="auto_reply",
            kill_switch=False,
            traffic_percentage=100,
            allowed_categories=frozenset({"service_outage"}),
        ),
    )

    result = app.process(
        ticket("auto", "Приложение не открывается. Это общий сбой?")
    )

    assert result.decision.action == "auto_reply"
    assert result.decision.rollout_version == "test-auto-v1"


def test_risky_payment_is_escalated_without_calling_generator(
    tmp_path: Path,
) -> None:
    class ForbiddenGenerator:
        def generate(self, *args: object) -> str:
            raise AssertionError("generator must not be called")

    result = pipeline(tmp_path, generator=ForbiddenGenerator()).process(
        ticket(
            "risky",
            "С карты дважды списали деньги. 4111 1111 1111 1111. "
            "Верните платёж.",
        )
    )

    assert result.decision.action == "escalate"
    assert result.decision.route == "billing-specialists"
    assert result.decision.draft_response is None


def test_risky_payment_is_escalated_without_calling_retrieval(
    tmp_path: Path,
) -> None:
    class ForbiddenRetriever:
        def search(self, *args: object):
            raise AssertionError("retrieval must not be called")

    app = TicketPipeline(
        retriever=ForbiddenRetriever(),  # type: ignore[arg-type]
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )

    result = app.process(
        ticket("risky-before-retrieval", "Верните деньги на карту")
    )

    assert result.decision.action == "escalate"
    assert result.retrieval.article_id is None


def test_pii_is_escalated_before_retrieval(tmp_path: Path) -> None:
    class ForbiddenRetriever:
        def search(self, *args: object):
            raise AssertionError("retrieval must not be called")

    app = TicketPipeline(
        retriever=ForbiddenRetriever(),  # type: ignore[arg-type]
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )

    result = app.process(
        ticket(
            "pii-before-retrieval",
            "Общий сбой, приложение не открывается. user@example.com",
        )
    )

    assert result.decision.action == "escalate"
    assert result.risk.contains_pii is True


def test_safe_retriever_receives_only_sanitized_text(tmp_path: Path) -> None:
    class RecordingRetriever:
        version = "recording-v1"

        def __init__(self) -> None:
            self.query = ""

        def search(self, query: str, category: str) -> RetrievalResult:
            self.query = query
            return RetrievalResult(
                "kb-outage-01",
                "Сбой",
                "Повторите попытку позднее.",
                0.9,
            )

    retriever = RecordingRetriever()
    app = TicketPipeline(
        retriever=retriever,  # type: ignore[arg-type]
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )
    result = app.process(
        ticket(
            "semantic-pii",
            "Приложение не открывается. Общий сбой. user@example.com",
        )
    )

    assert result.decision.action == "escalate"
    assert retriever.query == ""


def test_same_ticket_id_returns_same_decision_and_one_audit_record(
    tmp_path: Path,
) -> None:
    app = pipeline(tmp_path)
    first = app.process(ticket("same-id", "Опять не работает."))
    second = app.process(ticket("same-id", "Подскажите, где тариф?"))

    assert first is second
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 1


def test_concurrent_duplicate_is_processed_once(tmp_path: Path) -> None:
    app = pipeline(tmp_path)
    barrier = Barrier(20)

    def process_duplicate(_: int):
        barrier.wait()
        return app.process(
            ticket("concurrent-id", "Приложение не открывается. Общий сбой?")
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(process_duplicate, range(20)))

    assert len({id(result) for result in results}) == 1
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 1


def test_audit_has_decision_but_not_ticket_text_or_card(tmp_path: Path) -> None:
    app = pipeline(tmp_path)
    app.process(
        ticket("audit-risk", "С карты 4111 1111 1111 1111 дважды списали.")
    )

    raw_audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    record = json.loads(raw_audit)
    assert record["ticket_id"] == "audit-risk"
    assert record["action"] == "escalate"
    assert record["pipeline_version"] == "0.4.0"
    assert record["classifier_version"] == "rules-v1"
    assert record["knowledge_base_version"].startswith("sha256:")
    assert record["retriever_version"].startswith("sha256:")
    assert "4111" not in raw_audit
    assert "С карты" not in raw_audit


def test_generator_failure_uses_safe_fallback(tmp_path: Path) -> None:
    app = pipeline(
        tmp_path, generator=DeterministicGenerator(simulate_failure=True)
    )

    result = app.process(
        ticket("fallback", "Приложение не открывается. Это общий сбой?")
    )

    assert result.decision.action == "suggest_to_agent"
    assert result.decision.fallback_used is True
    assert "проверяем состояние сервиса" in result.decision.draft_response


def test_generator_failure_without_approved_template_escalates(
    tmp_path: Path,
) -> None:
    app = pipeline(
        tmp_path, generator=DeterministicGenerator(simulate_failure=True)
    )

    result = app.process(
        ticket("fallback-general", "Подскажите, где найти мой тариф?")
    )

    assert result.decision.action == "escalate"
    assert result.decision.fallback_used is True
    assert result.decision.draft_response is None
    assert result.decision.reason == "generator_failed_without_safe_fallback"


def test_fast_path_component_failure_fails_safe(tmp_path: Path) -> None:
    result = pipeline(tmp_path).process(
        ticket("failed-risk", "Приложение не открывается. Общий сбой?"),
        simulate_component_failure="risk",
    )

    assert result.decision.action == "escalate"
    assert result.decision.reason == "technical_fallback"
    assert result.technical_errors == ("RISK:RuntimeError",)


def test_fast_path_timeout_respects_shared_deadline(tmp_path: Path) -> None:
    app = TicketPipeline(
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
        fast_path_deadline_ms=20,
    )

    result = app.process(
        ticket("timeout-risk", "Приложение не открывается. Общий сбой?"),
        simulate_component_timeout="risk",
    )

    assert result.decision.action == "escalate"
    assert "RISK:TIMEOUT" in result.technical_errors
    assert result.fast_path_ms < 100
