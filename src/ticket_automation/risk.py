from __future__ import annotations

import re

from .models import Category, RiskAssessment, Ticket

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"
)

HIGH_RISK_SIGNALS: dict[str, tuple[str, ...]] = {
    "account_compromise": ("взлом", "взломали", "чужой вход", "украли аккаунт"),
    "fraud": ("мошенничество", "мошенник", "не совершал"),
    "data_leak": ("утечка данных", "слили данные"),
    "disputed_charge": ("спорное списание", "дважды списали", "двойное списание"),
    "refund": ("верните деньги", "верните платёж", "возврат денег"),
    "account_block": ("аккаунт заблокирован", "заблокировали аккаунт"),
    "legal_threat": ("подам в суд", "обращусь в суд", "жалоба в прокуратуру"),
}

DENYLIST_CATEGORIES: frozenset[Category] = frozenset(
    {"payment_issue", "refund_request", "account_security"}
)


def _ticket_text(ticket: Ticket) -> str:
    return f"{ticket.subject} {ticket.text}".lower()


def assess_risk(ticket: Ticket, category: Category) -> RiskAssessment:
    text = _ticket_text(ticket)
    pii_types = []
    if EMAIL_RE.search(text):
        pii_types.append("email")
    if PHONE_RE.search(text):
        pii_types.append("phone")
    if CARD_RE.search(text):
        pii_types.append("payment_card")

    reasons = [f"pii:{kind}" for kind in pii_types]
    reasons.extend(
        f"risk:{name}"
        for name, phrases in HIGH_RISK_SIGNALS.items()
        if any(phrase in text for phrase in phrases)
    )
    if category in DENYLIST_CATEGORIES:
        reasons.append(f"denylist_category:{category}")

    if reasons:
        level = "high"
    elif category == "unknown":
        level = "medium"
    else:
        level = "low"
    return RiskAssessment(level, bool(pii_types), tuple(sorted(set(reasons))))


def redact_pii(text: str) -> str:
    redacted = CARD_RE.sub("[PAYMENT_CARD]", text)
    redacted = EMAIL_RE.sub("[EMAIL]", redacted)
    return PHONE_RE.sub("[PHONE]", redacted)
