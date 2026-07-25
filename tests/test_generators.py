from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ticket_automation.audit import JsonlAudit
from ticket_automation.generator import (
    GenerationError,
    OllamaGenerator,
    OpenRouterGenerator,
    UnsafeGenerationError,
    create_generator,
)
from ticket_automation.models import RetrievalResult, Ticket
from ticket_automation.pipeline import TicketPipeline


class FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


TICKET = Ticket(
    "generator-1",
    "chat",
    "Сбой",
    "Приложение не открывается",
    "2026-07-25T12:00:00Z",
)
ARTICLE = RetrievalResult(
    "kb-outage-01",
    "Общий сбой",
    "Повторите попытку позднее.",
    0.9,
)


def test_ollama_adapter_uses_non_streaming_chat_api() -> None:
    client = FakeClient(
        {"message": {"role": "assistant", "content": "Попробуйте позднее."}}
    )
    generator = OllamaGenerator(
        model="local-model",
        base_url="http://ollama.test",
        client=client,
    )

    draft = generator.generate(TICKET, "Очищенный текст", ARTICLE)

    assert draft == "Попробуйте позднее."
    call = client.calls[0]
    assert call["url"] == "http://ollama.test/api/chat"
    assert call["payload"]["stream"] is False
    assert call["payload"]["model"] == "local-model"
    assert "Очищенный текст" in call["payload"]["messages"][1]["content"]


def test_openrouter_adapter_uses_bearer_auth_without_leaking_key() -> None:
    client = FakeClient(
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Есть общий сбой."}}
            ]
        }
    )
    generator = OpenRouterGenerator(
        model="provider/model",
        api_key="test-secret",
        client=client,
    )

    draft = generator.generate(TICKET, "Очищенный текст", ARTICLE)

    assert draft == "Есть общий сбой."
    call = client.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-secret"
    assert "test-secret" not in repr(generator)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"message": {}},
        {"message": {"content": ""}},
    ],
)
def test_ollama_invalid_response_fails_closed(response: dict[str, Any]) -> None:
    generator = OllamaGenerator(
        model="local-model",
        client=FakeClient(response),
    )

    with pytest.raises(GenerationError):
        generator.generate(TICKET, "Очищенный текст", ARTICLE)


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Напишите на leaked@example.com",
        "Мы вернули деньги.",
        "Карта 4111 1111 1111 1111 обработана.",
    ],
)
def test_external_draft_is_rejected_on_unsafe_content(
    unsafe_text: str,
) -> None:
    generator = OllamaGenerator(
        model="local-model",
        client=FakeClient({"message": {"content": unsafe_text}}),
    )

    with pytest.raises(UnsafeGenerationError):
        generator.generate(TICKET, "Очищенный текст", ARTICLE)


def test_openrouter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_generator("openrouter", model="provider/model")


def test_external_generator_requires_explicit_model() -> None:
    with pytest.raises(ValueError, match="model"):
        create_generator("ollama")


def test_pipeline_replaces_unsafe_provider_output_with_fallback(
    tmp_path: Path,
) -> None:
    generator = OllamaGenerator(
        model="local-model",
        client=FakeClient(
            {"message": {"content": "Мы вернули деньги пользователю."}}
        ),
    )
    pipeline = TicketPipeline(
        generator=generator,
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )

    result = pipeline.process(TICKET)

    assert result.decision.action == "suggest_to_agent"
    assert result.decision.fallback_used is True
    assert "проверяем состояние сервиса" in result.decision.draft_response
