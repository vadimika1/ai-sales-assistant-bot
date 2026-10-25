from __future__ import annotations

import json

from app.rag.retriever import SimpleRAGRetriever
from app.schemas import AISuggestionRequest


def test_rag_retriever_returns_top_k_relevant_items(tmp_path) -> None:
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(
        json.dumps(
            [
                {
                    "id": "pricing",
                    "title": "Цена и бюджет",
                    "text": "Стоимость обсуждаем после короткой квалификации.",
                    "tags": ["цена", "стоимость", "бюджет"],
                },
                {
                    "id": "timeline",
                    "title": "Сроки запуска",
                    "text": "Срок запуска оценивается после уточнения объема работ.",
                    "tags": ["срок", "дедлайн", "запуск"],
                },
                {
                    "id": "other",
                    "title": "Нерелевантный материал",
                    "text": "Встреча команды и внутренний ретро-статус.",
                    "tags": ["команда"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    retriever = SimpleRAGRetriever.from_json_file(kb_path)

    payload = AISuggestionRequest(
        manager_message="Клиент спрашивает цену и сроки запуска",
        conversation=[],
        lead_context={},
    )
    results = retriever.retrieve(payload=payload, top_k=2, min_score=0.5)

    ids = [item.id for item in results]
    assert len(results) == 2
    assert "pricing" in ids
    assert "timeline" in ids


def test_rag_retriever_returns_empty_for_missing_file(tmp_path) -> None:
    missing_path = tmp_path / "missing.json"
    retriever = SimpleRAGRetriever.from_json_file(missing_path)
    payload = AISuggestionRequest(manager_message="Тест", conversation=[], lead_context={})

    assert retriever.retrieve(payload=payload, top_k=3, min_score=1.0) == []
