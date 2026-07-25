from ticket_automation.models import Ticket
from ticket_automation.preprocessing import normalize_text, prepare_ticket


def test_normalizes_html_unicode_controls_and_spacing() -> None:
    value = "<p>Сбой&nbsp;сервиса</p>\x00<p>Повторите   позже</p>"

    assert normalize_text(value) == "Сбой сервиса Повторите позже"


def test_masks_pii_before_safe_ticket_reaches_classifier() -> None:
    prepared = prepare_ticket(
        Ticket(
            "prepared",
            "web",
            "",
            "Почта user@example.com, телефон +7 999 123-45-67",
            "",
        )
    )

    assert "user@example.com" in prepared.normalized_ticket.text
    assert "user@example.com" not in prepared.safe_ticket.text
    assert "[EMAIL]" in prepared.safe_ticket.text
    assert "[PHONE]" in prepared.safe_ticket.text
