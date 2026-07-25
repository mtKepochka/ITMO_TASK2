import pytest

from ticket_automation.classifier import classify
from ticket_automation.models import Ticket


def ticket(text: str, subject: str = "") -> Ticket:
    return Ticket("test-1", "chat", subject, text, "2026-07-25T12:00:00Z")


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Приложение не открывается. Это общий сбой?", "service_outage"),
        ("Не могу войти, забыл пароль", "access_issue"),
        ("С карты дважды списали оплату", "payment_issue"),
        ("Хочу возврат, верните деньги", "refund_request"),
        ("Кажется, аккаунт взломали", "account_security"),
        ("Подскажите, где найти мой тариф", "general_question"),
    ],
)
def test_classifies_supported_intents(text: str, category: str) -> None:
    assert classify(ticket(text)).category == category


def test_returns_explainable_signals() -> None:
    result = classify(ticket("Приложение не открывается. Это общий сбой?"))

    assert result.confidence >= 0.8
    assert "общий сбой" in result.signals


def test_abstains_from_inventing_category_without_evidence() -> None:
    result = classify(ticket("Что-то странное происходит"))

    assert result.category == "unknown"
    assert result.confidence == 0.0
