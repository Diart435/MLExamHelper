"""Генератор теста. LLM заменяем фейком — проверяем нашу логику:
разбор ответа, привязку вопроса к чанку-источнику, чистку мусора."""

import pytest

from app.db.chunks import ChunkHit
from app.services.test_generator import _to_test, build_context, build_task

HITS = [
    ChunkHit("chunk-a", "m1", "Текст про индексы и поиск.", 0.1),
    ChunkHit("chunk-b", "m1", "Текст про транзакции.", 0.2),
    ChunkHit("chunk-c", "m2", "Текст про нормализацию.", 0.3),
]


def test_context_is_numbered_from_one():
    context = build_context(HITS)
    assert context.startswith("<context>")
    assert context.endswith("</context>")
    assert "[1] Текст про индексы и поиск." in context
    assert "[3] Текст про нормализацию." in context


def test_task_carries_the_requested_difficulty():
    task = build_task("Основы СУБД", 5, "hard", "<context/>")
    assert "Основы СУБД" in task
    assert "5" in task
    assert "hard" in task


def test_source_number_is_mapped_back_to_a_real_chunk_id():
    """LLM отвечает номером блока контекста — наружу уходит настоящий chunk_id,
    иначе backend не сможет заполнить внешний ключ source_chunk_id."""
    parsed = {
        "title": "Основы СУБД",
        "questions": [
            {
                "id": 1,
                "text": "Что делает индекс?",
                "options": ["ускоряет поиск", "уменьшает объём", "не делает ничего", "ломает БД"],
                "correct_index": 0,
                "explanation": "Индекс ускоряет поиск.",
                "source": 1,
            },
            {
                "id": 2,
                "text": "Что гарантирует транзакция?",
                "options": ["атомарность", "целостность", "избыточность", "читаемость"],
                "correct_index": 0,
                "explanation": "Транзакция атомарна.",
                "source": 2,
            },
        ],
    }

    test = _to_test(parsed, HITS)

    assert [q.source_chunk_id for q in test.questions] == ["chunk-a", "chunk-b"]
    assert test.title == "Основы СУБД"
    # explanation наружу не отдаём — в test_questions такой колонки нет
    assert "explanation" not in test.to_dict()["questions"][0]


def test_out_of_range_source_becomes_null():
    parsed = {
        "title": "T",
        "questions": [
            {"text": "Вопрос", "options": ["a", "b"], "correct_index": 0, "source": 99},
            {"text": "Вопрос", "options": ["a", "b"], "correct_index": 0, "source": "abc"},
        ],
    }
    assert all(q.source_chunk_id is None for q in _to_test(parsed, HITS).questions)


@pytest.mark.parametrize(
    "raw",
    [
        {"text": "", "options": ["a", "b"], "correct_index": 0},  # пустой текст
        {"text": "Вопрос", "options": ["a"], "correct_index": 0},  # один вариант
        {"text": "Вопрос", "options": ["a", "b"], "correct_index": "не число"},
        {"text": "Вопрос", "options": ["a", "b"], "correct_index": 5},  # вне диапазона
        {"text": "Вопрос", "options": ["a", "b"], "correct_index": -1},
    ],
)
def test_malformed_questions_are_dropped_not_fatal(raw):
    parsed = {"title": "T", "questions": [raw, {"text": "Норм", "options": ["a", "b"], "correct_index": 1}]}
    test = _to_test(parsed, HITS)
    assert [q.text for q in test.questions] == ["Норм"]


def test_all_questions_malformed_raises():
    parsed = {"title": "T", "questions": [{"text": "", "options": [], "correct_index": 0}]}
    with pytest.raises(ValueError):
        _to_test(parsed, HITS)


def test_empty_questions_list_raises():
    with pytest.raises(ValueError):
        _to_test({"title": "T", "questions": []}, HITS)


def test_question_ids_are_reindexed_when_the_llm_forgets_them():
    parsed = {
        "title": "T",
        "questions": [
            {"text": "Первый", "options": ["a", "b"], "correct_index": 0},
            {"text": "Второй", "options": ["a", "b"], "correct_index": 0},
        ],
    }
    assert [q.id for q in _to_test(parsed, HITS).questions] == [1, 2]