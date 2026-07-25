from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from .models import Category, RetrievalResult

DEFAULT_E5_MODEL = "intfloat/multilingual-e5-small"
DEFAULT_E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
DEFAULT_SEMANTIC_MIN_SIMILARITY = 0.70
DEFAULT_SEMANTIC_MIN_MARGIN = 0.01

STOP_WORDS = {
    "а",
    "в",
    "вы",
    "где",
    "для",
    "и",
    "из",
    "как",
    "ли",
    "мой",
    "на",
    "не",
    "но",
    "по",
    "с",
    "у",
    "это",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zа-яё0-9]+", text.lower())
        if len(token) > 1 and token not in STOP_WORDS
    }


@dataclass(frozen=True)
class KnowledgeArticle:
    id: str
    title: str
    content: str
    categories: tuple[Category, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> KnowledgeArticle:
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            content=str(value["content"]),
            categories=tuple(value.get("categories", ())),
        )


def load_articles(path: str | Path) -> tuple[list[KnowledgeArticle], str]:
    raw = Path(path).read_bytes()
    values = json.loads(raw)
    if not isinstance(values, list) or not values:
        raise ValueError("knowledge base must contain a non-empty list")
    return (
        [KnowledgeArticle.from_dict(value) for value in values],
        f"sha256:{sha256(raw).hexdigest()[:12]}",
    )


class LexicalRetriever:
    def __init__(
        self,
        articles: list[KnowledgeArticle],
        *,
        version: str = "in-memory",
    ) -> None:
        self._articles = articles
        self.version = version
        self.knowledge_base_version = version

    @classmethod
    def from_file(cls, path: str | Path) -> LexicalRetriever:
        articles, version = load_articles(path)
        return cls(articles, version=version)

    def search(self, query: str, category: Category) -> RetrievalResult:
        query_tokens = _tokens(query)
        best: tuple[float, KnowledgeArticle] | None = None
        for article in self._articles:
            article_tokens = _tokens(f"{article.title} {article.content}")
            overlap = len(query_tokens & article_tokens)
            lexical_score = overlap / max(1, len(query_tokens))
            category_bonus = 0.15 if category in article.categories else 0.0
            score = min(1.0, lexical_score + category_bonus)
            if best is None or score > best[0]:
                best = (score, article)

        if best is None or best[0] == 0:
            return RetrievalResult(None, "", "", 0.0)
        score, article = best
        return RetrievalResult(
            article_id=article.id,
            title=article.title,
            content=article.content,
            score=round(score, 2),
            source="lexical",
        )


class SentenceEncoder(Protocol):
    def encode(
        self,
        sentences: str | list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> Any: ...


class KnowledgeRetriever(Protocol):
    version: str
    knowledge_base_version: str

    def search(
        self,
        query: str,
        category: Category,
    ) -> RetrievalResult: ...


class SemanticRetrieverUnavailable(RuntimeError):
    """The optional semantic retriever could not be initialized."""


def _as_vectors(value: Any) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list):
        raise TypeError("encoder returned an invalid vector payload")
    if value and isinstance(value[0], (int, float)):
        value = [value]
    if not all(
        isinstance(vector, list)
        and vector
        and all(isinstance(item, (int, float)) for item in vector)
        for vector in value
    ):
        raise ValueError("encoder returned invalid vectors")
    dimensions = {len(vector) for vector in value}
    if len(dimensions) != 1:
        raise ValueError("encoder returned vectors with inconsistent dimensions")
    return [[float(item) for item in vector] for vector in value]


def _cosine_from_normalized(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    return sum(a * b for a, b in zip(left, right, strict=True))


def load_sentence_transformer(
    *,
    model_name: str,
    revision: str,
    cache_directory: Path,
    local_files_only: bool,
) -> SentenceEncoder:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise SemanticRetrieverUnavailable(
            "semantic extra is not installed; run "
            "`python -m pip install -e '.[semantic]'`"
        ) from error
    try:
        return SentenceTransformer(
            model_name,
            revision=revision,
            cache_folder=str(cache_directory / "models"),
            local_files_only=local_files_only,
            trust_remote_code=False,
        )
    except Exception as error:
        raise SemanticRetrieverUnavailable(
            f"cannot load pinned semantic model {model_name}@{revision}"
        ) from error


class E5SemanticRetriever:
    def __init__(
        self,
        articles: list[KnowledgeArticle],
        encoder: SentenceEncoder,
        *,
        knowledge_base_version: str,
        model_name: str = DEFAULT_E5_MODEL,
        revision: str = DEFAULT_E5_REVISION,
        cache_directory: str | Path,
        min_similarity: float = DEFAULT_SEMANTIC_MIN_SIMILARITY,
        min_margin: float = DEFAULT_SEMANTIC_MIN_MARGIN,
    ) -> None:
        if not 0 <= min_similarity <= 1 or not 0 <= min_margin <= 1:
            raise ValueError("semantic thresholds must be between 0 and 1")
        self._articles = articles
        self._encoder = encoder
        self.model_name = model_name
        self.revision = revision
        self.min_similarity = min_similarity
        self.min_margin = min_margin
        self.version = (
            f"e5:{model_name}@{revision[:12]}|kb:{knowledge_base_version}"
        )
        self.knowledge_base_version = knowledge_base_version
        self._cache_directory = Path(cache_directory)
        self._passage_vectors = self._load_or_encode_passages(
            knowledge_base_version
        )

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        cache_directory: str | Path,
        model_name: str = DEFAULT_E5_MODEL,
        revision: str = DEFAULT_E5_REVISION,
        local_files_only: bool = False,
        min_similarity: float = DEFAULT_SEMANTIC_MIN_SIMILARITY,
        min_margin: float = DEFAULT_SEMANTIC_MIN_MARGIN,
        encoder: SentenceEncoder | None = None,
    ) -> E5SemanticRetriever:
        articles, knowledge_base_version = load_articles(path)
        cache_path = Path(cache_directory)
        effective_encoder = encoder or load_sentence_transformer(
            model_name=model_name,
            revision=revision,
            cache_directory=cache_path,
            local_files_only=local_files_only,
        )
        return cls(
            articles,
            effective_encoder,
            knowledge_base_version=knowledge_base_version,
            model_name=model_name,
            revision=revision,
            cache_directory=cache_path,
            min_similarity=min_similarity,
            min_margin=min_margin,
        )

    def _load_or_encode_passages(
        self,
        knowledge_base_version: str,
    ) -> list[list[float]]:
        identity = (
            f"{self.model_name}\n{self.revision}\n{knowledge_base_version}"
        )
        cache_key = sha256(identity.encode("utf-8")).hexdigest()[:20]
        cache_path = self._cache_directory / f"kb-embeddings-{cache_key}.json"
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            vectors = _as_vectors(cached["vectors"])
            if (
                cached.get("identity") == identity
                and len(vectors) == len(self._articles)
            ):
                return vectors
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

        passages = [
            f"passage: {article.title}. {article.content}"
            for article in self._articles
        ]
        vectors = _as_vectors(
            self._encoder.encode(
                passages,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        if len(vectors) != len(self._articles):
            raise ValueError("encoder returned an unexpected passage count")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"identity": identity, "vectors": vectors},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, cache_path)
        return vectors

    def search(self, query: str, category: Category) -> RetrievalResult:
        query_vectors = _as_vectors(
            self._encoder.encode(
                [f"query: {query}"],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        if len(query_vectors) != 1:
            raise ValueError("encoder returned an unexpected query count")
        scores = [
            _cosine_from_normalized(vector, query_vectors[0])
            for vector in self._passage_vectors
        ]
        order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        best_index = order[0]
        second_score = scores[order[1]] if len(order) > 1 else -1.0
        score = scores[best_index]
        margin = score - second_score
        article = self._articles[best_index]
        if (
            category not in article.categories
            or score < self.min_similarity
            or margin < self.min_margin
        ):
            return RetrievalResult(
                None,
                "",
                "",
                round(max(0.0, score), 4),
                source="e5",
            )
        return RetrievalResult(
            article_id=article.id,
            title=article.title,
            content=article.content,
            score=round(max(0.0, min(1.0, score)), 4),
            source="e5",
        )


class FallbackRetriever:
    """Use lexical retrieval if the optional semantic path is unavailable."""

    def __init__(
        self,
        primary: E5SemanticRetriever | None,
        fallback: LexicalRetriever,
        *,
        primary_version: str,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.version = (
            f"primary:{primary_version}|fallback:{fallback.version}"
        )
        self.knowledge_base_version = fallback.knowledge_base_version

    def search(self, query: str, category: Category) -> RetrievalResult:
        if self.primary is not None:
            try:
                return self.primary.search(query, category)
            except Exception:  # noqa: BLE001 - optional model boundary
                return self._fallback_search(query, category)
        return self._fallback_search(query, category)

    def _fallback_search(
        self,
        query: str,
        category: Category,
    ) -> RetrievalResult:
        result = self.fallback.search(query, category)
        return RetrievalResult(
            article_id=result.article_id,
            title=result.title,
            content=result.content,
            score=result.score,
            source=result.source,
            fallback_used=True,
        )


def create_retriever(
    provider: str,
    *,
    knowledge_base_path: str | Path,
    cache_directory: str | Path,
    model_name: str = DEFAULT_E5_MODEL,
    revision: str = DEFAULT_E5_REVISION,
    local_files_only: bool = False,
) -> tuple[KnowledgeRetriever, str | None]:
    lexical = LexicalRetriever.from_file(knowledge_base_path)
    if provider == "lexical":
        return lexical, None
    if provider != "e5":
        raise ValueError("retriever must be one of: lexical, e5")
    primary = None
    warning = None
    try:
        primary = E5SemanticRetriever.from_file(
            knowledge_base_path,
            cache_directory=cache_directory,
            model_name=model_name,
            revision=revision,
            local_files_only=local_files_only,
        )
    except (OSError, SemanticRetrieverUnavailable, ValueError) as error:
        warning = (
            "semantic retriever unavailable, using lexical fallback: "
            f"{error}"
        )
    return (
        FallbackRetriever(
            primary,
            lexical,
            primary_version=f"e5:{model_name}@{revision[:12]}",
        ),
        warning,
    )
