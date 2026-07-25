from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Category, RetrievalResult

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


class LexicalRetriever:
    def __init__(self, articles: list[KnowledgeArticle]) -> None:
        self._articles = articles

    @classmethod
    def from_file(cls, path: str | Path) -> LexicalRetriever:
        with Path(path).open(encoding="utf-8") as source:
            values = json.load(source)
        return cls([KnowledgeArticle.from_dict(value) for value in values])

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
        )
