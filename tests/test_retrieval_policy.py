from pathlib import Path

from ticket_automation.models import (
    ClassificationResult,
    RetrievalResult,
    RiskAssessment,
)
from ticket_automation.policy import decide
from ticket_automation.retrieval import (
    E5SemanticRetriever,
    FallbackRetriever,
    LexicalRetriever,
    SemanticRetrieverUnavailable,
    create_retriever,
)

KB_PATH = Path(__file__).parents[1] / "data" / "knowledge_base.json"


class FakeEncoder:
    def __init__(self) -> None:
        self.calls: list[str | list[str]] = []

    def encode(
        self,
        sentences: str | list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        self.calls.append(sentences)
        values = [sentences] if isinstance(sentences, str) else sentences
        vectors = []
        for value in values:
            if value.startswith("passage:"):
                if "общем сбое" in value:
                    vectors.append([1.0, 0.0, 0.0, 0.0])
                elif "Восстановление доступа" in value:
                    vectors.append([0.0, 1.0, 0.0, 0.0])
                elif "Проверка списания" in value:
                    vectors.append([0.0, 0.0, 1.0, 0.0])
                else:
                    vectors.append([0.0, 0.0, 0.0, 1.0])
            elif "авторизации отвергает" in value.lower():
                vectors.append([0.0, 0.99, 0.01, 0.0])
            else:
                vectors.append([0.99, 0.01, 0.0, 0.0])
        return vectors


def test_retrieves_relevant_outage_article() -> None:
    retriever = LexicalRetriever.from_file(KB_PATH)

    result = retriever.search(
        "Приложение не открывается. Это общий сбой?", "service_outage"
    )

    assert result.article_id == "kb-outage-01"
    assert result.score >= 0.35


def test_semantic_retriever_finds_paraphrase_and_records_source(
    tmp_path: Path,
) -> None:
    retriever = E5SemanticRetriever.from_file(
        KB_PATH,
        cache_directory=tmp_path,
        encoder=FakeEncoder(),
    )

    result = retriever.search(
        "Экран авторизации отвергает мои данные",
        "access_issue",
    )

    assert result.article_id == "kb-access-01"
    assert result.source == "e5"
    assert result.fallback_used is False


def test_semantic_retriever_reuses_cached_kb_embeddings(
    tmp_path: Path,
) -> None:
    E5SemanticRetriever.from_file(
        KB_PATH,
        cache_directory=tmp_path,
        encoder=FakeEncoder(),
    )
    second_encoder = FakeEncoder()

    E5SemanticRetriever.from_file(
        KB_PATH,
        cache_directory=tmp_path,
        encoder=second_encoder,
    )

    assert second_encoder.calls == []


def test_semantic_category_mismatch_abstains(tmp_path: Path) -> None:
    retriever = E5SemanticRetriever.from_file(
        KB_PATH,
        cache_directory=tmp_path,
        encoder=FakeEncoder(),
    )

    result = retriever.search(
        "Экран авторизации отвергает мои данные",
        "service_outage",
    )

    assert result.article_id is None
    assert result.source == "e5"


def test_missing_semantic_model_uses_lexical_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def unavailable(**kwargs):
        raise SemanticRetrieverUnavailable("not cached")

    monkeypatch.setattr(
        "ticket_automation.retrieval.load_sentence_transformer",
        unavailable,
    )

    retriever, warning = create_retriever(
        "e5",
        knowledge_base_path=KB_PATH,
        cache_directory=tmp_path,
        local_files_only=True,
    )
    result = retriever.search(
        "Приложение не открывается. Общий сбой.",
        "service_outage",
    )

    assert warning is not None
    assert result.article_id == "kb-outage-01"
    assert result.source == "lexical"
    assert result.fallback_used is True


def test_runtime_semantic_error_uses_lexical_fallback() -> None:
    class BrokenSemanticRetriever:
        version = "broken"

        def search(self, query: str, category: str):
            raise RuntimeError("encoder crashed")

    fallback = FallbackRetriever(
        BrokenSemanticRetriever(),  # type: ignore[arg-type]
        LexicalRetriever.from_file(KB_PATH),
        primary_version="broken",
    )

    result = fallback.search(
        "Приложение не открывается. Общий сбой.",
        "service_outage",
    )

    assert result.article_id == "kb-outage-01"
    assert result.fallback_used is True


def test_policy_allows_only_safe_strong_case() -> None:
    decision = decide(
        ClassificationResult("service_outage", 0.95, ("общий сбой",)),
        RiskAssessment("low", False, ()),
        RetrievalResult("kb-outage-01", "Сбой", "Инструкция", 0.8),
    )

    assert decision.action == "auto_reply"


def test_policy_escalates_payment_even_with_strong_retrieval() -> None:
    decision = decide(
        ClassificationResult("payment_issue", 0.95, ("списали",)),
        RiskAssessment("high", False, ("denylist_category:payment_issue",)),
        RetrievalResult("kb-billing-01", "Списание", "Инструкция", 0.9),
    )

    assert decision.action == "escalate"
    assert decision.route == "billing-specialists"


def test_policy_abstains_on_low_confidence() -> None:
    decision = decide(
        ClassificationResult("service_outage", 0.37, ("не работает",)),
        RiskAssessment("low", False, ()),
        RetrievalResult("kb-outage-01", "Сбой", "Инструкция", 0.8),
    )

    assert decision.action == "escalate"
    assert decision.reason == "low_classification_confidence"


def test_policy_sends_weak_retrieval_to_agent() -> None:
    decision = decide(
        ClassificationResult("service_outage", 0.9, ("сбой",)),
        RiskAssessment("low", False, ()),
        RetrievalResult(None, "", "", 0.0),
    )

    assert decision.action == "suggest_to_agent"
