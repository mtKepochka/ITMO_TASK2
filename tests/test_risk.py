import pytest

from ticket_automation.models import Ticket
from ticket_automation.risk import assess_risk, redact_pii


def ticket(text: str) -> Ticket:
    return Ticket("risk-1", "email", "", text, "2026-07-25T12:00:00Z")


@pytest.mark.parametrize(
    ("text", "expected_reason"),
    [
        ("Пишите на user@example.com", "pii:email"),
        ("Мой телефон +7 (999) 123-45-67", "pii:phone"),
        ("Карта 4111 1111 1111 1111", "pii:payment_card"),
        ("Аккаунт взломали", "risk:account_compromise"),
        ("Подам в суд", "risk:legal_threat"),
    ],
)
def test_detects_sensitive_and_high_risk_signals(
    text: str, expected_reason: str
) -> None:
    result = assess_risk(ticket(text), "general_question")

    assert result.risk_level == "high"
    assert expected_reason in result.reasons


def test_payment_category_is_high_risk_without_explicit_phrase() -> None:
    result = assess_risk(ticket("Не вижу операцию"), "payment_issue")

    assert result.risk_level == "high"
    assert "denylist_category:payment_issue" in result.reasons


def test_redacts_all_supported_pii() -> None:
    source = "user@example.com, +7 999 123-45-67, 4111-1111-1111-1111"

    redacted = redact_pii(source)

    assert "user@example.com" not in redacted
    assert "999 123" not in redacted
    assert "4111" not in redacted
    assert redacted == "[EMAIL], [PHONE], [PAYMENT_CARD]"
