"""Тесты чтения вопросов из БД (`services/test_store.py`).

Мы мокаем asyncpg: настоящая БД в тестах не нужна — проверяем поведение
`fetch_questions` при разных ответах Postgres'а.

Что защищаем
============
Контракт v4.1: в `test_questions` есть колонка `answer_key` — эталон
правильного ответа, который backend пишет из ответа ML. Но колонка появится
у backend'а только с его миграцией: на старых схемах (в т.ч. на живой
стендовой БД `ml_live`) её нет.

Поэтому `fetch_questions` обязан:
  - читать `answer_key`, когда колонка есть;
  - при `UndefinedColumnError` / `UndefinedTableError` повторить запрос без
    колонки и подставить пустой эталон, а НЕ упасть — иначе проверка любой
    попытки на старой схеме падала бы целиком;
  - проверять форму данных: json/jsonb приходят с codec'ом как `dict`/`list`,
    а строка вместо объекта — ошибка формы (`ValidationError`), а не тихая
    подстановка (именно из-за неё `key_points` превращался в список символов).

Тест детерминированный: ни сети, ни БД.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.models import AnswerKey, QuestionRow
from app.services.test_store import TestStore


# ---------------------------------------------------------------------------
# Моки
# ---------------------------------------------------------------------------

class FakeRow(dict):
    """Строка результата fetch — словарь с доступом по ключу."""


class FakeConn:
    """Соединение asyncpg: отдаёт заранее подготовленные строки.

    `raises` — исключение, которое нужно кинуть на ПЕРВОМ запросе (имитация
    отсутствующей колонки). Второй запрос (без колонки) отдаёт `rows`.
    """

    def __init__(self, rows: list[dict], raises: Exception | None = None) -> None:
        self._rows = rows
        self._raises = raises
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[FakeRow]:
        self.queries.append(" ".join(query.split()))
        if self._raises is not None:
            error, self._raises = self._raises, None
            raise error
        return [FakeRow(r) for r in self._rows]


class FakePool:
    """Пул asyncpg: отдаёт одно и то же соединение."""

    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _Acquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _store_with(conn: FakeConn) -> TestStore:
    """TestStore с подменённым пулом (connect() не трогает сеть)."""
    store = TestStore(dsn="postgresql://ml:ml@localhost:5432/ml")
    store._pool = FakePool(conn)
    return store


def _undefined_column() -> Exception:
    """Исключение asyncpg про отсутствующую колонку."""
    import asyncpg
    return asyncpg.exceptions.UndefinedColumnError(
        'column "answer_key" does not exist'
    )


def _undefined_table() -> Exception:
    import asyncpg
    return asyncpg.exceptions.UndefinedTableError(
        'relation "test_questions" does not exist'
    )


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

class TestFetchQuestions:
    @pytest.mark.asyncio
    async def test_reads_answer_key_when_column_exists(self):
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "single_choice",
                "text_question": "Вопрос?",
                "options": ["A", "B"],
                "key_points": [],
                "answer_key": {"correct_index": 1, "explanation": "потому что B"},
            },
        ])
        rows = await _store_with(conn).fetch_questions("T1")
        assert len(rows) == 1
        assert rows[0].answer_key.correct_index == 1
        assert rows[0].answer_key.explanation == "потому что B"
        assert "answer_key" in conn.queries[0]

    @pytest.mark.asyncio
    async def test_answer_key_json_string_is_rejected(self):
        """JSONB приходит строкой — это битая строка в БД, а не «эталон».

        Раньше такая строка молча превращалась в эталон (или в пустой), и
        прикладной код получал `str` вместо `dict`. Теперь форма проверяется:
        `ValidationError` вместо тихой подстановки."""
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "open_answer",
                "text_question": "Открытый вопрос?",
                "options": [],
                "key_points": ["пункт 1"],
                "answer_key": '{"reference_answer": "Эталон"}',
            },
        ])
        with pytest.raises(ValidationError):
            await _store_with(conn).fetch_questions("T1")

    @pytest.mark.asyncio
    async def test_answer_key_list_is_rejected(self):
        """Список вместо объекта — тоже ошибка формы, а не «пустой эталон»."""
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "single_choice",
                "text_question": "Вопрос?",
                "options": ["A", "B"],
                "key_points": [],
                "answer_key": ["мусор"],
            },
        ])
        with pytest.raises(ValidationError):
            await _store_with(conn).fetch_questions("T1")

    @pytest.mark.asyncio
    async def test_missing_answer_key_gives_empty_reference(self):
        """`answer_key` отсутствует (NULL) — эталона нет, пустой эталон."""
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "single_choice",
                "text_question": "Вопрос?",
                "options": ["A", "B"],
                "key_points": [],
                "answer_key": None,
            },
        ])
        rows = await _store_with(conn).fetch_questions("T1")
        assert rows[0].answer_key == AnswerKey()
        assert rows[0].answer_key.correct_index is None

    @pytest.mark.asyncio
    async def test_fallback_when_answer_key_column_missing(self):
        """Колонки `answer_key` нет — запрос повторяется без неё, эталон пуст.

        Падать нельзя: иначе проверка любой попытки на старой схеме упала бы
        целиком, а не деградировала до Redis/LLM-страховки."""
        conn = FakeConn(
            [
                {
                    "question_id": "q1",
                    "type_question": "single_choice",
                    "text_question": "Вопрос?",
                    "options": ["A", "B"],
                    "key_points": [],
                },
            ],
            raises=_undefined_column(),
        )
        rows = await _store_with(conn).fetch_questions("T1")
        assert len(rows) == 1
        assert rows[0].answer_key == AnswerKey()
        assert rows[0].question_id == "q1"
        # Два запроса: первый с колонкой, второй — без.
        assert len(conn.queries) == 2
        assert "answer_key" in conn.queries[0]
        assert "answer_key" not in conn.queries[1]

    @pytest.mark.asyncio
    async def test_fallback_when_table_missing(self):
        """Нет самой таблицы — тот же фолбэк, без падения."""
        conn = FakeConn(
            [],
            raises=_undefined_table(),
        )
        rows = await _store_with(conn).fetch_questions("T1")
        assert rows == []
        assert len(conn.queries) == 2

    @pytest.mark.asyncio
    async def test_other_errors_are_not_swallowed(self):
        """Сбой БД, не связанный с отсутствующей колонкой, — пробрасывается.

        Иначе реальные поломки БД выглядели бы как «просто нет эталона»."""
        conn = FakeConn([], raises=RuntimeError("connection lost"))
        with pytest.raises(RuntimeError, match="connection lost"):
            await _store_with(conn).fetch_questions("T1")

    @pytest.mark.asyncio
    async def test_key_points_normalised(self):
        """key_points приводятся к канону (плоский список критериев)."""
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "open_answer",
                "text_question": "Открытый вопрос?",
                "options": [],
                "key_points": {"points": 2, "criteria": ["пункт 1", "пункт 2"]},
                "answer_key": {},
            },
        ])
        rows = await _store_with(conn).fetch_questions("T1")
        assert rows[0].key_points == ["пункт 1", "пункт 2"]
        assert rows[0].criteria() == ["пункт 1", "пункт 2"]

    @pytest.mark.asyncio
    async def test_key_points_string_is_rejected(self):
        """Строковый key_points — битая строка в БД: ошибка формы.

        Именно этот случай давал студенту ответ «[» вместо первого критерия:
        `kp[0]` у строки `'["пункт 1"]'` — это «[»."""
        conn = FakeConn([
            {
                "question_id": "q1",
                "type_question": "open_answer",
                "text_question": "Открытый вопрос?",
                "options": [],
                "key_points": '["пункт 1"]',
                "answer_key": {},
            },
        ])
        with pytest.raises(ValidationError):
            await _store_with(conn).fetch_questions("T1")


class TestQuestionRow:
    def test_answer_key_defaults_to_empty(self):
        row = QuestionRow(
            question_id="q1", type_question="single_choice",
            text_question="Вопрос?", options=["A"], key_points=[],
        )
        assert row.answer_key == AnswerKey()

    def test_answer_key_is_not_shared_between_instances(self):
        """default_factory, а не общий объект — иначе эталоны вопросов
        перетирали бы друг друга."""
        a = QuestionRow(
            question_id="q1", type_question="single_choice",
            text_question="?", options=[], key_points=[],
        )
        b = QuestionRow(
            question_id="q2", type_question="single_choice",
            text_question="?", options=[], key_points=[],
        )
        a.answer_key.correct_index = 0
        assert b.answer_key.correct_index is None
