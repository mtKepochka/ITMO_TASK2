import json
from pathlib import Path

from ticket_automation.audit import JsonlAudit
from ticket_automation.generator import DeterministicGenerator
from ticket_automation.models import Ticket
from ticket_automation.pipeline import TicketPipeline


def ticket(ticket_id: str, text: str, subject: str = "") -> Ticket:
    return Ticket(ticket_id, "chat", subject, text, "2026-07-25T12:00:00Z")


def pipeline(tmp_path: Path, *, generator=None) -> TicketPipeline:
    return TicketPipeline(
        generator=generator,
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )


def test_happy_path_creates_grounded_auto_reply(tmp_path: Path) -> None:
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
    assert result.decision.action == "auto_reply"
    assert result.decision.draft_response


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


def test_same_ticket_id_returns_same_decision_and_one_audit_record(
    tmp_path: Path,
) -> None:
    app = pipeline(tmp_path)
    first = app.process(ticket("same-id", "Опять не работает."))
    second = app.process(ticket("same-id", "Подскажите, где тариф?"))

    assert first is second
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
    assert record["pipeline_version"] == "0.2.0"
    assert record["classifier_version"] == "rules-v1"
    assert record["knowledge_base_version"].startswith("sha256:")
    assert "4111" not in raw_audit
    assert "С карты" not in raw_audit


def test_generator_failure_uses_safe_fallback(tmp_path: Path) -> None:
    app = pipeline(
        tmp_path, generator=DeterministicGenerator(simulate_failure=True)
    )

    result = app.process(
        ticket("fallback", "Приложение не открывается. Это общий сбой?")
    )

    assert result.decision.action == "auto_reply"
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
