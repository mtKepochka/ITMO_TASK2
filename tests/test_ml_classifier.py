from __future__ import annotations

from pathlib import Path

import pytest

from ticket_automation.audit import JsonlAudit
from ticket_automation.ml_classifier import TfidfIntentClassifier
from ticket_automation.models import Ticket
from ticket_automation.pipeline import TicketPipeline
from ticket_automation.training import load_dataset, train_and_evaluate

DATASET = Path(__file__).parents[1] / "data" / "intent_dataset.jsonl"


@pytest.fixture(scope="module")
def classifier() -> TfidfIntentClassifier:
    records = load_dataset(DATASET)
    train = [record for record in records if record.split == "train"]
    return TfidfIntentClassifier.train(
        [record.text for record in train],
        [record.category for record in train],
    )


def ticket(text: str) -> Ticket:
    return Ticket("ml-1", "chat", "", text, "2026-07-25T12:00:00Z")


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Приложение не открывается, это общий сбой", "service_outage"),
        ("Не могу войти, забыл пароль", "access_issue"),
        ("С карты дважды списали оплату", "payment_issue"),
        ("Хочу оформить возврат денег", "refund_request"),
        ("Кажется, аккаунт взломали", "account_security"),
        ("Подскажите условия тарифа", "general_question"),
        ("Что-то странное происходит", "unknown"),
    ],
)
def test_ml_classifier_handles_representative_intents(
    classifier: TfidfIntentClassifier,
    text: str,
    category: str,
) -> None:
    assert classifier.classify(ticket(text)).category == category


def test_ml_classifier_returns_feature_contributions(
    classifier: TfidfIntentClassifier,
) -> None:
    result = classifier.classify(
        ticket("Приложение не открывается, это общий сбой")
    )

    assert result.signals
    assert any("сбой" in signal for signal in result.signals)


def test_model_round_trip_is_deterministic(
    classifier: TfidfIntentClassifier,
    tmp_path: Path,
) -> None:
    path = tmp_path / "classifier.joblib"
    classifier.save(path, metadata={"test": True})

    restored = TfidfIntentClassifier.load_trusted(path)

    assert restored.classify(ticket("Не могу войти")) == classifier.classify(
        ticket("Не могу войти")
    )


def test_ml_payment_prediction_still_obeys_safety_policy(
    classifier: TfidfIntentClassifier,
    tmp_path: Path,
) -> None:
    pipeline = TicketPipeline(
        classifier=classifier,
        audit=JsonlAudit(tmp_path / "audit.jsonl"),
    )

    result = pipeline.process(
        ticket("С карты дважды списали оплату, верните деньги")
    )

    assert result.classification.category in {
        "payment_issue",
        "refund_request",
    }
    assert result.decision.action == "escalate"


def test_training_writes_reproducible_model_report(tmp_path: Path) -> None:
    first = train_and_evaluate(
        DATASET,
        tmp_path / "first.joblib",
        tmp_path / "first.json",
    )
    second = train_and_evaluate(
        DATASET,
        tmp_path / "second.joblib",
        tmp_path / "second.json",
    )

    assert first == second
    assert first["train_examples"] == 56
    assert first["test_examples"] == 21
    assert 0.0 <= first["macro_f1"] <= 1.0
    assert (tmp_path / "first.joblib").is_file()
