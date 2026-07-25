from __future__ import annotations

from .models import (
    ClassificationResult,
    Decision,
    RetrievalResult,
    RiskAssessment,
)
from .risk import DENYLIST_CATEGORIES

MIN_CLASSIFICATION_CONFIDENCE = 0.7
MIN_RETRIEVAL_SCORE = 0.35
AUTO_REPLY_CATEGORIES = frozenset({"service_outage"})

ROUTES = {
    "payment_issue": "billing-specialists",
    "refund_request": "billing-specialists",
    "account_security": "security-specialists",
    "access_issue": "account-support",
    "service_outage": "incident-support",
    "general_question": "general-support",
    "unknown": "triage",
}


def decide(
    classification: ClassificationResult,
    risk: RiskAssessment,
    retrieval: RetrievalResult,
    *,
    draft_response: str | None = None,
    fallback_used: bool = False,
) -> Decision:
    category = classification.category
    route = ROUTES[category]

    if risk.risk_level == "high" or risk.contains_pii:
        action = "escalate"
        reason = "high_risk_or_pii"
    elif category in DENYLIST_CATEGORIES:
        action = "escalate"
        reason = "category_not_allowed_for_automation"
    elif classification.confidence < MIN_CLASSIFICATION_CONFIDENCE:
        action = "escalate"
        reason = "low_classification_confidence"
    elif retrieval.score < MIN_RETRIEVAL_SCORE:
        action = "suggest_to_agent"
        reason = "weak_knowledge_match"
    elif category in AUTO_REPLY_CATEGORIES:
        action = "auto_reply"
        reason = "safe_allowlist_with_strong_evidence"
    else:
        action = "suggest_to_agent"
        reason = "human_review_required"

    return Decision(
        action=action,
        reason=reason,
        category=category,
        confidence=classification.confidence,
        risk_level=risk.risk_level,
        draft_response=draft_response,
        route=route,
        fallback_used=fallback_used,
    )
