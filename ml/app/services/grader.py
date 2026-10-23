"""Детерминированная проверка single_choice.

Оценка не зависит от LLM: индекс ответа студента сравнивается с
answer_key.correct_index, который backend записал в test_questions.
LLM здесь не нужен — он работает только над текстом общего фидбэка.

Считаются ВСЕ вопросы теста, а не только те, что есть в ответах:
пропущенный вопрос — это тоже ноль, иначе попытка без ответов
набирала бы 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from app.contracts import GradeAttemptTask, GradedItem, grade_from_pct
from app.db.questions import QuestionRow


@dataclass
class Mistake:
    """Промах для фидбэка: что спросили, что выбрал студент, что верно."""

    question_id: str
    question: str
    student_answer: str | None
    correct_answer: str | None
    reason: str | None = None


@dataclass
class Graded:
    score_pct: float
    grade: int
    items: list[GradedItem] = field(default_factory=list)
    mistakes: list[Mistake] = field(default_factory=list)


def grade(task: GradeAttemptTask, questions: list[QuestionRow]) -> Graded:
    """Проверить попытку по всем вопросам теста."""
    given = {a.question_id: a.student_answer_index for a in task.answers}
    items: list[GradedItem] = []
    mistakes: list[Mistake] = []
    correct_count = 0

    for q in questions:
        student_index = given.get(q.question_id)
        correct_index = q.correct_index

        if correct_index is None or q.type_question != "single_choice":
            reason = f"автопроверка для типа {q.type_question!r} не реализована"
            logger.info(f"Question {q.question_id}: {reason}")
            student_answer = _option_text(q, student_index)
            if student_answer is not None:
                mistakes.append(
                    Mistake(
                        question_id=q.question_id,
                        question=q.text,
                        student_answer=student_answer,
                        correct_answer=q.correct_text(),
                        reason=reason,
                    )
                )
            items.append(GradedItem(question_id=q.question_id, score=0.0))
            continue

        is_correct = student_index is not None and student_index == correct_index
        if is_correct:
            correct_count += 1
        else:
            mistakes.append(
                Mistake(
                    question_id=q.question_id,
                    question=q.text,
                    student_answer=_option_text(q, student_index),
                    correct_answer=q.correct_text(),
                )
            )
        items.append(GradedItem(question_id=q.question_id, score=1.0 if is_correct else 0.0))

    total = len(questions)
    if total == 0:
        raise ValueError(f"test {task.test_id} has no questions to grade")

    score_pct = round(100.0 * correct_count / total, 2)
    logger.info(
        f"Attempt {task.attempt_id}: {correct_count}/{total} correct "
        f"({score_pct}%, grade {grade_from_pct(score_pct)}), {len(mistakes)} mistake(s)"
    )
    return Graded(
        score_pct=score_pct,
        grade=grade_from_pct(score_pct),
        items=items,
        mistakes=mistakes,
    )


def _option_text(q: QuestionRow, index: int | None) -> str | None:
    if index is None or not (0 <= index < len(q.options)):
        return None
    return q.options[index]