"""Задача grade_attempt: проверка ответов + один общий фидбэк на попытку.

Баллы считаются детерминированно (grader), текст фидбэка пишет LLM.
Если LLM с фидбэком не справился — попытка всё равно засчитывается:
ошибку фидбэка ловим отдельно и отдаём пустую строку, потому что потерять
оценку из-за текста хуже, чем отдать оценку без текста.
"""

from __future__ import annotations

from loguru import logger

from app.contracts import GradeAttemptResult, GradeAttemptTask
from app.db.questions import fetch_questions
from app.services import feedback as feedback_service
from app.services.grader import grade
from app.services.llm import LLMClient


async def process_grade_attempt(
    task: GradeAttemptTask,
    *,
    llm: LLMClient | None = None,
) -> GradeAttemptResult:
    try:
        questions = await fetch_questions(task.test_id)
        graded = grade(task, questions)
    except Exception as e:  # noqa: BLE001 — без баллов попытку засчитать нельзя
        logger.exception(f"Grading failed for attempt {task.attempt_id}: {e}")
        return GradeAttemptResult.err(
            task.task_id, f"{type(e).__name__}: {e}", task.attempt_id, task.test_id
        )

    try:
        client = llm or LLMClient()
        overall = await feedback_service.overall_feedback(
            client, graded.mistakes, len(questions)
        )
    except Exception as e:  # noqa: BLE001 — фидбэк не критичен, оценка уже посчитана
        logger.exception(f"Feedback failed for attempt {task.attempt_id}: {e}")
        overall = ""

    return GradeAttemptResult.ok(
        task_id=task.task_id,
        attempt_id=task.attempt_id,
        test_id=task.test_id,
        score_pct=graded.score_pct,
        grade=graded.grade,
        overall_feedback=overall,
        items=graded.items,
    )