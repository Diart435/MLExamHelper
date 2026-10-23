"""Чтение test_questions — единственная таблица кроме material_chunks,
в которую ML ходит. Записывает её backend, читает grader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.pool import get_pool


@dataclass
class QuestionRow:
    question_id: str
    text: str
    type_question: str
    options: list[str] = field(default_factory=list)
    answer_key: dict[str, Any] = field(default_factory=dict)

    @property
    def correct_index(self) -> int | None:
        """Индекс верного варианта. None, если вопрос не single_choice
        или в answer_key его нет — тогда автопроверка невозможна."""
        if "correct_index" not in self.answer_key:
            return None
        return int(self.answer_key["correct_index"])

    def correct_text(self) -> str | None:
        ci = self.correct_index
        if ci is None or not (0 <= ci < len(self.options)):
            return None
        return self.options[ci]


async def fetch_questions(test_id: str) -> list[QuestionRow]:
    """Все вопросы теста в порядке создания."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT question_id, text_question, type_question, options, answer_key "
        "FROM test_questions WHERE test_id = $1::uuid ORDER BY created_at, question_id",
        test_id,
    )
    return [
        QuestionRow(
            question_id=str(r["question_id"]),
            text=r["text_question"],
            type_question=r["type_question"],
            options=list(r["options"] or []),
            answer_key=dict(r["answer_key"] or {}),
        )
        for r in rows
    ]