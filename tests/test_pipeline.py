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
