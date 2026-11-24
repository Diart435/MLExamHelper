"""Pydantic-модели предметной области на границе БД.

Зачем
=====
Данные из Postgres проходят через эти модели, и **форма проверяется**. Раньше
JSONB приходил строкой, и код тихо превращал строку в мусор: `key_points` вида
`'["пункт 1"]'` давал `kp[0] == "["` — студенту уходил ответ «[» вместо
первого критерия.

Теперь строка вместо объекта/списка — `ValidationError`: ошибка формы видна
сразу, а не превращается в тихую подстановку. Единственное исключение —
legacy-форма `key_points` (объект `{points, explanation, criteria}`), она
нормализуется в плоский список критериев.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def split_key_points(raw: Any) -> tuple[list[str], str]:
    """key_points из БД → (критерии, объяснение из legacy-формы).

    Новая форма — массив строк (критерии). Старая — объект
    {points, explanation, criteria}: критерии разворачиваем в список, а
    объяснение оттуда отдаём отдельно — хранить его негде, эталон лежит в
    отдельной колонке `answer_key`.
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


class AnswerKey(BaseModel):
    """Эталон правильного ответа (контракт v4.1)."""

    # Лишние поля от нового backend'а игнорируем (обратная совместимость),
    # но неверный тип ИЗВЕСТНОГО поля — ошибка: `correct_indexes="1,2"` не молча
    # превращается в список.
    model_config = ConfigDict(extra="ignore")

    correct_index: int | None = None
    correct_indexes: list[int] = Field(default_factory=list)
    reference_answer: str | None = None
    explanation: str | None = None

    @field_validator("correct_indexes", mode="before")
    @classmethod
    def _reject_str(cls, v: Any) -> Any:
        """Строка вместо списка индексов — ошибка формы, а не «пустой эталон»."""
        if isinstance(v, str):
            raise ValueError("correct_indexes должен быть списком, а не строкой")
        return v

    @field_validator("correct_index", mode="before")
    @classmethod
    def _reject_str_index(cls, v: Any) -> Any:
        if isinstance(v, str):
            raise ValueError("correct_index должен быть числом, а не строкой")
        return v


class QuestionRow(BaseModel):
    """Вопрос теста, прочитанный из БД.

    `answer_key` — эталон правильного ответа (контракт v4.1). В новых схемах
    он приходит из колонки `test_questions.answer_key`; в старых её нет —
    тогда поле пустое, и эталон берётся из Redis (см. `services/answer_store.py`)
    либо определяется LLM-судьёй.

    Зато есть `key_points` — опорные пункты, которых хватает open_answer-судье,
    когда эталона нет.
    """

    model_config = ConfigDict(extra="ignore")

    question_id: str
    type_question: str
    text_question: str
    options: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    answer_key: AnswerKey = Field(default_factory=AnswerKey)

    @field_validator("question_id", mode="before")
    @classmethod
    def _uuid_to_str(cls, v: Any) -> Any:
        """Колонка uuid приходит из Postgres объектом UUID — домен ждёт строку.

        Pydantic не сужает `UUID` → `str` сам, а вопросы приходят из БД
        именно как UUID.
        """
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("key_points", mode="before")
    @classmethod
    def _normalise_key_points(cls, v: Any) -> Any:
        """Legacy-объект {points, explanation, criteria} → плоский список."""
        if v is None:
            return []
        if isinstance(v, (list, dict)):
            criteria, _explanation = split_key_points(v)
            return criteria
        return v

    @field_validator("answer_key", mode="before")
    @classmethod
    def _empty_when_none(cls, v: Any) -> Any:
        """`answer_key=None` — эталона нет, а не ошибка формы."""
        if v is None:
            return {}
        return v

    def criteria(self) -> list[str]:
        """Опорные пункты для open_answer (key_points)."""
        return list(self.key_points)
