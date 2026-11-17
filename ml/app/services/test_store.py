"""Read-only доступ к `test_questions` для Grader.

ML хранит chunks в своём vector_store, но `test_questions` — это backendовская
таблица, она живёт в Postgres, и при grading'е нам нужно достать оттуда
text_question / options / answer_key / key_points для каждого question_id
из attempt'а.

Подключаемся тем же пулом asyncpg, что и PgVectorStore. Singleton-обёртка
с lazy connect — `Grader` и `TestStore` создаются на каждый task, поэтому
проверяем, что пул уже жив, иначе делаем новый.

Зачем выделено в отдельный файл (а не запихнуто в Grader): чтобы потом
не дублировать логику fetch_questions для answer-key / grading-history.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class QuestionRow:
    question_id: str
    type_question: str
    text_question: str
    options: list[str]
    answer_key: dict[str, Any]
    key_points: list[str]

    def correct_index(self) -> int | None:
        """Достать правильный индекс варианта из answer_key. None, если не single_choice."""
        if "correct_index" not in self.answer_key:
            return None
        try:
            return int(self.answer_key["correct_index"])
        except (TypeError, ValueError):
            return None

    def correct_indexes(self) -> list[int]:
        """Правильные индексы вариантов для multi_choice. Пусто у других типов."""
        raw = self.answer_key.get("correct_indexes") or []
        if not isinstance(raw, list):
            return []
        try:
            return sorted({int(i) for i in raw})
        except (TypeError, ValueError):
            return []

    def explanation(self) -> str:
        """Короткое объяснение правильного ответа (answer_key.explanation)."""
        v = self.answer_key.get("explanation")
        return str(v).strip() if v else ""

    def criteria(self) -> list[str]:
        """Опорные пункты для open_answer (key_points)."""
        return list(self.key_points)


class TestStore:
    """Читает вопросы теста из Postgres. Без состояния, без кэша — task короткоживущий."""

    __test__ = False  # не pytest-класс

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        import asyncpg  # локальный импорт — pytest с pg-выключенным не тащил драйвер
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=2)
        logger.info("TestStore connected")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "TestStore":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def fetch_questions(self, test_id: str) -> list[QuestionRow]:
        """Достать ВСЕ вопросы теста в порядке question_id (≈ порядок генерации)."""
        await self.connect()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT question_id, type_question, text_question,
                       options, answer_key, key_points
                FROM test_questions
                WHERE test_id = $1
                ORDER BY question_id
                """,
                test_id,
            )
        result: list[QuestionRow] = []
        for r in rows:
            opts = r["options"]
            if isinstance(opts, str):
                opts = json.loads(opts)
            ak = r["answer_key"]
            if isinstance(ak, str):
                ak = json.loads(ak)
            kp = r["key_points"]
            if isinstance(kp, str):
                kp = json.loads(kp)
            ak = ak or {}
            # Каноническая форма: key_points — список критериев, объяснение —
            # в answer_key. Legacy-объект ({points, explanation, criteria})
            # разворачиваем здесь, чтобы grader знал только одну форму.
            criteria, legacy_explanation = _split_key_points(kp)
            if legacy_explanation and not ak.get("explanation"):
                ak["explanation"] = legacy_explanation
            result.append(QuestionRow(
                question_id=str(r["question_id"]),
                type_question=str(r["type_question"]),
                text_question=str(r["text_question"]),
                options=list(opts) if opts else [],
                answer_key=ak,
                key_points=criteria,
            ))
        return result


def _split_key_points(raw: Any) -> tuple[list[str], str]:
    """key_points из БД → (критерии, объяснение из legacy-формы).

    Новая форма — массив строк (критерии). Старая — объект
    {points, explanation, criteria}: объяснение оттуда переносится в
    answer_key, чтобы grader читал объяснение из одного места.
    """
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()], ""
    if isinstance(raw, dict):
        crit = raw.get("criteria")
        criteria = (
            [str(c).strip() for c in crit if str(c).strip()]
            if isinstance(crit, list) else []
        )
        expl = raw.get("explanation")
        return criteria, str(expl).strip() if expl else ""
    return [], ""