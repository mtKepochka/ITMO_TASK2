from pathlib import Path

from ticket_automation.models import (
    ClassificationResult,
    RetrievalResult,
    RiskAssessment,
)
from ticket_automation.policy import decide
from ticket_automation.retrieval import LexicalRetriever

KB_PATH = Path(__file__).parents[1] / "data" / "knowledge_base.json"


def test_retrieves_relevant_outage_article() -> None:
    retriever = LexicalRetriever.from_file(KB_PATH)

    result = retriever.search(
        "Приложение не открывается. Это общий сбой?", "service_outage"
    )

    assert result.article_id == "kb-outage-01"
    assert result.score >= 0.35


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
