from __future__ import annotations

from typing import Protocol

from .models import RetrievalResult, Ticket


class ResponseGenerator(Protocol):
    def generate(
        self, ticket: Ticket, sanitized_text: str, retrieval: RetrievalResult
    ) -> str: ...


class DeterministicGenerator:
    def __init__(self, *, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure

    def generate(
        self, ticket: Ticket, sanitized_text: str, retrieval: RetrievalResult
    ) -> str:
        if self.simulate_failure:
            raise RuntimeError("simulated generator failure")
        if not retrieval.article_id:
            raise ValueError("generation requires a knowledge article")
        return (
            "Здравствуйте! По вашему обращению подходит проверенная инструкция: "
            f"{retrieval.content}"
        )


FALLBACK_TEMPLATES = {
    "service_outage": (
        "Здравствуйте! Мы проверяем состояние сервиса. "
        "Пожалуйста, повторите попытку позднее."
    )
}
