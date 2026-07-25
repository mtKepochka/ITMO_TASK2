from __future__ import annotations

from pathlib import Path
from typing import Sequence, cast

import joblib
import sklearn
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion

from .models import Category, ClassificationResult, Ticket

MODEL_FORMAT_VERSION = 1


def _build_vectorizer() -> FeatureUnion:
    return FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    lowercase=True,
                    ngram_range=(3, 5),
                    sublinear_tf=True,
                ),
            ),
        ],
        transformer_weights={"word": 1.0, "char": 0.6},
    )


class TfidfIntentClassifier:
    """A trainable sparse baseline with local feature explanations."""

    def __init__(
        self,
        vectorizer: FeatureUnion,
        estimator: LogisticRegression,
        *,
        training_examples: int,
    ) -> None:
        self.vectorizer = vectorizer
        self.estimator = estimator
        self.training_examples = training_examples

    @classmethod
    def train(
        cls,
        texts: Sequence[str],
        labels: Sequence[Category],
    ) -> TfidfIntentClassifier:
        if len(texts) != len(labels) or not texts:
            raise ValueError("training texts and labels must be non-empty and aligned")
        vectorizer = _build_vectorizer()
        features = vectorizer.fit_transform(texts)
        estimator = LogisticRegression(
            C=6.0,
            class_weight="balanced",
            max_iter=2_000,
            solver="lbfgs",
        )
        estimator.fit(features, labels)
        return cls(
            vectorizer,
            estimator,
            training_examples=len(texts),
        )

    def classify(self, ticket: Ticket) -> ClassificationResult:
        text = f"{ticket.subject} {ticket.text}".strip()
        features = cast(csr_matrix, self.vectorizer.transform([text]))
        probabilities = self.estimator.predict_proba(features)[0]
        best_index = int(probabilities.argmax())
        category = cast(Category, self.estimator.classes_[best_index])
        confidence = round(float(probabilities[best_index]), 4)
        return ClassificationResult(
            category=category,
            confidence=confidence,
            signals=self._top_signals(features, best_index),
        )

    def __call__(self, ticket: Ticket) -> ClassificationResult:
        return self.classify(ticket)

    def _top_signals(
        self,
        features: csr_matrix,
        class_index: int,
        limit: int = 5,
    ) -> tuple[str, ...]:
        names = self.vectorizer.get_feature_names_out()
        row = features.getrow(0)
        coefficients = self.estimator.coef_[class_index]
        contributions = sorted(
            (
                (float(coefficients[index] * value), int(index))
                for index, value in zip(row.indices, row.data, strict=True)
                if coefficients[index] * value > 0
            ),
            reverse=True,
        )
        return tuple(str(names[index]) for _, index in contributions[:limit])

    def save(self, path: str | Path, *, metadata: dict[str, object]) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "format_version": MODEL_FORMAT_VERSION,
                "sklearn_version": sklearn.__version__,
                "training_examples": self.training_examples,
                "metadata": metadata,
                "vectorizer": self.vectorizer,
                "estimator": self.estimator,
            },
            destination,
        )

    @classmethod
    def load_trusted(cls, path: str | Path) -> TfidfIntentClassifier:
        """Load only an artifact produced locally by this project."""
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"classifier artifact not found: {source}")
        payload = joblib.load(source)
        if (
            not isinstance(payload, dict)
            or payload.get("format_version") != MODEL_FORMAT_VERSION
            or not isinstance(payload.get("vectorizer"), FeatureUnion)
            or not isinstance(payload.get("estimator"), LogisticRegression)
        ):
            raise ValueError("unsupported classifier artifact")
        if payload.get("sklearn_version") != sklearn.__version__:
            raise ValueError(
                "classifier artifact was built with another scikit-learn version"
            )
        return cls(
            payload["vectorizer"],
            payload["estimator"],
            training_examples=int(payload["training_examples"]),
        )
