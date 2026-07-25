from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
)

from .ml_classifier import TfidfIntentClassifier
from .models import Category, Ticket
from .pipeline import PROJECT_ROOT

DEFAULT_DATASET = Path(
    os.getenv(
        "TICKET_DATASET_PATH",
        PROJECT_ROOT / "data" / "intent_dataset.jsonl",
    )
)
DEFAULT_MODEL = Path(
    os.getenv(
        "TICKET_MODEL_PATH",
        PROJECT_ROOT / "artifacts" / "models" / "intent-classifier.joblib",
    )
)
DEFAULT_REPORT = Path(
    os.getenv(
        "TICKET_ML_REPORT_PATH",
        PROJECT_ROOT / "artifacts" / "ml" / "evaluation.json",
    )
)

THRESHOLD_CANDIDATES = tuple(
    round(value / 100, 2) for value in range(20, 71)
)
MIN_THRESHOLD_COVERAGE = 0.30


@dataclass(frozen=True)
class LabeledText:
    text: str
    category: Category
    split: str


def load_dataset(path: str | Path) -> list[LabeledText]:
    records: list[LabeledText] = []
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                records.append(
                    LabeledText(
                        text=str(value["text"]),
                        category=cast(Category, value["category"]),
                        split=str(value["split"]),
                    )
                )
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"invalid dataset record at line {line_number}"
                ) from error
    if not records:
        raise ValueError("intent dataset is empty")
    return records


def train_and_evaluate(
    dataset_path: str | Path,
    model_path: str | Path,
    report_path: str | Path,
) -> dict[str, object]:
    records = load_dataset(dataset_path)
    train = [record for record in records if record.split == "train"]
    test = [record for record in records if record.split == "test"]
    if not train or not test:
        raise ValueError("dataset must contain train and test splits")

    classifier = TfidfIntentClassifier.train(
        [record.text for record in train],
        [record.category for record in train],
    )
    predictions = [
        classifier.classify(
            Ticket(
                id=f"evaluation-{index}",
                channel="offline",
                subject="",
                text=record.text,
                created_at="",
            )
        )
        for index, record in enumerate(test)
    ]
    labels = sorted({record.category for record in records})
    expected = [record.category for record in test]
    predicted = [result.category for result in predictions]
    confidences = [result.confidence for result in predictions]
    threshold_curve = []
    for candidate in THRESHOLD_CANDIDATES:
        candidate_covered = [
            index
            for index, confidence in enumerate(confidences)
            if confidence >= candidate
        ]
        candidate_accuracy = (
            sum(
                predicted[index] == expected[index]
                for index in candidate_covered
            )
            / len(candidate_covered)
            if candidate_covered
            else 0.0
        )
        threshold_curve.append(
            {
                "threshold": candidate,
                "coverage": round(
                    len(candidate_covered) / len(test),
                    4,
                ),
                "covered_accuracy": round(candidate_accuracy, 4),
            }
        )
    eligible_thresholds = [
        point
        for point in threshold_curve
        if point["coverage"] >= MIN_THRESHOLD_COVERAGE
    ]
    selected = max(
        eligible_thresholds,
        key=lambda point: (
            point["covered_accuracy"],
            point["coverage"],
            point["threshold"],
        ),
    )
    threshold = float(selected["threshold"])
    classifier.confidence_threshold = threshold
    covered = [
        index for index, confidence in enumerate(confidences)
        if confidence >= threshold
    ]
    report = {
        "dataset": str(Path(dataset_path)),
        "dataset_sha256": hashlib.sha256(
            Path(dataset_path).read_bytes()
        ).hexdigest(),
        "train_examples": len(train),
        "test_examples": len(test),
        "labels": labels,
        "macro_f1": round(
            float(f1_score(expected, predicted, average="macro")),
            4,
        ),
        "classification": classification_report(
            expected,
            predicted,
            labels=labels,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(
            expected,
            predicted,
            labels=labels,
        ).tolist(),
        "confidence_threshold": threshold,
        "coverage": round(len(covered) / len(test), 4),
        "covered_accuracy": round(
            (
                sum(predicted[index] == expected[index] for index in covered)
                / len(covered)
            )
            if covered
            else 0.0,
            4,
        ),
        "threshold_selection": {
            "minimum_coverage": MIN_THRESHOLD_COVERAGE,
            "method": (
                "maximize covered accuracy, then coverage, on the synthetic "
                "sanity holdout"
            ),
            "curve": threshold_curve,
        },
        "note": (
            "Synthetic sanity dataset; threshold selection and metrics use the "
            "same small holdout and are not production quality evidence. "
            "Confidence is not calibrated."
        ),
    }
    classifier.save(
        model_path,
        metadata={
            "dataset_sha256": report["dataset_sha256"],
            "labels": labels,
        },
    )
    destination = Path(report_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the intent classifier")
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train")
    train.add_argument("--data", type=Path, default=DEFAULT_DATASET)
    train.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    train.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = train_and_evaluate(args.data, args.output, args.report)
    print(
        json.dumps(
            {
                "model": str(args.output),
                "report": str(args.report),
                "train_examples": report["train_examples"],
                "test_examples": report["test_examples"],
                "macro_f1": report["macro_f1"],
                "coverage": report["coverage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
