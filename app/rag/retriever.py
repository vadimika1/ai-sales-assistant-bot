from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas import AISuggestionRequest

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]{2,}")


@dataclass(frozen=True)
class RetrievedKnowledge:
    id: str
    title: str
    text: str
    score: float

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "score": round(self.score, 3),
        }


@dataclass(frozen=True)
class _KnowledgeItem:
    id: str
    title: str
    text: str
    tags: tuple[str, ...]
    tokens: frozenset[str]
    roots: frozenset[str]
    tag_tokens: frozenset[str]
    tag_roots: frozenset[str]


class SimpleRAGRetriever:
    def __init__(self, items: list[_KnowledgeItem]):
        self._items = items

    @classmethod
    def from_json_file(cls, kb_path: str | Path) -> "SimpleRAGRetriever":
        path = Path(kb_path)
        if not path.exists():
            logger.warning("RAG KB file does not exist: %s", path)
            return cls(items=[])

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read RAG KB file: %s", path)
            return cls(items=[])

        if not isinstance(raw, list):
            logger.warning("RAG KB format is invalid (expected JSON array): %s", path)
            return cls(items=[])

        items: list[_KnowledgeItem] = []
        for index, row in enumerate(raw):
            if not isinstance(row, dict):
                continue

            item_id = str(row.get("id", f"item_{index + 1}")).strip()
            title = str(row.get("title", "")).strip()
            text = str(row.get("text", "")).strip()
            raw_tags = row.get("tags", [])
            tags = tuple(tag.strip() for tag in raw_tags if isinstance(tag, str) and tag.strip())

            if not title and not text:
                continue

            token_base = " ".join([title, text, *tags]).strip()
            tokens = frozenset(_tokenize(token_base))
            roots = frozenset(_to_roots(tokens))
            tag_tokens = frozenset(_tokenize(" ".join(tags)))
            tag_roots = frozenset(_to_roots(tag_tokens))
            items.append(
                _KnowledgeItem(
                    id=item_id or f"item_{index + 1}",
                    title=title or f"Материал {index + 1}",
                    text=text,
                    tags=tags,
                    tokens=tokens,
                    roots=roots,
                    tag_tokens=tag_tokens,
                    tag_roots=tag_roots,
                )
            )

        logger.info("RAG KB loaded", extra={"items_count": len(items), "kb_path": str(path)})
        return cls(items=items)

    def retrieve(
        self,
        payload: AISuggestionRequest,
        top_k: int = 3,
        min_score: float = 1.0,
    ) -> list[RetrievedKnowledge]:
        if not self._items:
            return []

        limited_top_k = max(1, min(int(top_k), 10))
        score_threshold = max(0.1, float(min_score))
        query_tokens = set(_tokenize(_build_query(payload)))
        query_roots = set(_to_roots(query_tokens))
        if not query_tokens:
            return []

        ranked: list[RetrievedKnowledge] = []
        for item in self._items:
            overlap = query_tokens.intersection(item.tokens)
            root_overlap = query_roots.intersection(item.roots)
            if not overlap and not root_overlap:
                continue

            tag_hits = query_tokens.intersection(item.tag_tokens)
            tag_root_hits = query_roots.intersection(item.tag_roots)
            score = (
                float(len(overlap))
                + float(len(tag_hits)) * 0.5
                + float(len(root_overlap)) * 0.35
                + float(len(tag_root_hits)) * 0.2
            )
            if score < score_threshold:
                continue

            ranked.append(
                RetrievedKnowledge(
                    id=item.id,
                    title=item.title,
                    text=item.text,
                    score=score,
                )
            )

        ranked.sort(key=lambda row: (-row.score, row.id))
        return ranked[:limited_top_k]


def _build_query(payload: AISuggestionRequest) -> str:
    parts = [payload.manager_message]
    parts.extend(item.text for item in payload.conversation)
    return " ".join(parts)


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _to_roots(tokens: set[str] | frozenset[str]) -> list[str]:
    roots: list[str] = []
    for token in tokens:
        if len(token) <= 3:
            roots.append(token)
            continue
        roots.append(token[:3])
    return roots
