from __future__ import annotations

import re
from collections import defaultdict

from .models import Category, ClassificationResult, Ticket

# Weights encode transparent domain evidence, not learned probabilities.
INTENT_SIGNALS: dict[Category, dict[str, int]] = {
    "service_outage": {
        "общий сбой": 4,
        "массовый сбой": 4,
        "не открывается": 2,
        "недоступен": 2,
        "сбой": 2,
        "лежит": 2,
        "не работает": 1,
    },
    "access_issue": {
        "не могу войти": 4,
        "не приходит код": 4,
        "сбросить пароль": 4,
        "войти": 2,
        "логин": 2,
        "пароль": 2,
        "код подтверждения": 2,
    },
    "payment_issue": {
        "двойное списание": 4,
        "дважды списали": 4,
        "списали": 3,
        "платёж": 2,
        "оплата": 2,
        "карта": 1,
    },
    "refund_request": {
        "верните деньги": 5,
        "верните платёж": 5,
        "хочу возврат": 4,
        "возврат": 3,
        "вернуть": 2,
    },
    "account_security": {
        "аккаунт взломали": 5,
        "чужой вход": 5,
        "утечка данных": 5,
        "мошенничество": 4,
        "взлом": 4,
        "заблокирован": 3,
    },
    "general_question": {
        "как изменить": 3,
        "где найти": 3,
        "подскажите": 2,
        "тариф": 2,
        "комиссия": 2,
    },
    "unknown": {},
}


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-zа-яё0-9]+", text.lower()))


def classify(ticket: Ticket) -> ClassificationResult:
    text = _normalize(f"{ticket.subject} {ticket.text}")
    scores: dict[Category, int] = defaultdict(int)
    matched: dict[Category, list[str]] = defaultdict(list)

    for category, signals in INTENT_SIGNALS.items():
        for signal, weight in signals.items():
            if signal in text:
                scores[category] += weight
                matched[category].append(signal)

    ranked = sorted(
        ((score, category) for category, score in scores.items()),
        reverse=True,
    )
    if not ranked or ranked[0][0] == 0:
        return ClassificationResult("unknown", 0.0, ())

    best_score, best_category = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0
    evidence = min(0.99, 0.25 + 0.12 * best_score)
    ambiguity_penalty = min(0.3, 0.08 * runner_up)
    confidence = round(max(0.0, evidence - ambiguity_penalty), 2)
    return ClassificationResult(
        category=best_category,
        confidence=confidence,
        signals=tuple(sorted(matched[best_category])),
    )
