"""Сгенерировать реальные JSON-payload'ы проверки попытки (grade_attempt).

Запуск: python -m tools.gen_grade_json

Всё печатается из боевого кода (app/contracts.py, app/services/grader.py),
поэтому формат в примере совпадает с тем, что реально уходит в Redis Streams.
"""

from __future__ import annotations

import asyncio
import json

from app.contracts import GradeAttemptResult, GradeAttemptTask
from app.services.grader import Grader
from app.services.open_answer_judge import Verdict
from app.services.test_store import QuestionRow


TEST_ID = "b7f3c1a2-5d84-4e19-9c07-2a6f8b41d3e5"
ATTEMPT_ID = "e91d7c48-6b02-4a73-8f51-6d0c9e2b7a44"
USER_ID = "3c8e5f17-9b40-4d26-a1e9-72f4b8c05d13"

Q_SINGLE = "d1a4f6b2-8e3c-4a17-95d0-2b6c9f8e4a01"
Q_MULTI = "a7b3c9d5-1f68-4e02-b3a7-5d8c2f9e6b12"
Q_OPEN = "5f9d2e8b-3a47-4c16-b8e5-0d7c4a1f9b23"


def hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


async def main() -> None:
    # ── 1. Задача: backend → ML (канал grade-test:be-to-ml) ────────────────
    hr("1. ЗАДАЧА  backend → ML   XADD grade-test:be-to-ml * payload '<json>'")

    backend_payload = {
        "task_id": "8f2a1c73-5d90-4b62-8e14-3c7f6a2b9d50",
        "attempt_id": ATTEMPT_ID,
        "test_id": TEST_ID,
        "user_id": USER_ID,
        "answers": [
            {"question_id": Q_SINGLE, "student_answer": {"index": 2}},
            {"question_id": Q_MULTI, "student_answer": {"indexes": [0, 2, 3]}},
            {"question_id": Q_OPEN, "student_answer": {"text": "Поток управляет памятью."}},
        ],
    }
    print(json.dumps(backend_payload, ensure_ascii=False, indent=2))

    # Тот же payload, но собранный ML-ом из своего dataclass'а — должен совпасть.
    task = GradeAttemptTask.from_dict(backend_payload)
    print("\n--- ровно то же, собранное ML-ом (GradeAttemptTask.to_json) ---")
    print(json.dumps(json.loads(task.to_json()), ensure_ascii=False, indent=2))

    # ── 2. Что ML делает с задачей ─────────────────────────────────────────
    hr("2. ПРОВЕРКА  внутри ML  (grader.py)")

    questions = [
        QuestionRow(
            question_id=Q_SINGLE,
            type_question="single_choice",
            text_question="Что такое кэш-память?",
            options=["Энергонезависимое хранилище", "Быстрая оперативная память",
                     "Постоянное хранилище на диске", "Регистр процессора"],
            answer_key={"correct_index": 1, "explanation": "Кэш-память — это SRAM между CPU и RAM."},
            key_points=[],
        ),
        QuestionRow(
            question_id=Q_MULTI,
            type_question="multi_choice",
            text_question="Какие задачи решает кэш-память?",
            options=["Ускорение доступа к данным", "Увеличение объёма RAM",
                     "Снижение задержки обращения к памяти", "Хранение состояния ОС"],
            answer_key={"correct_indexes": [0, 2],
                        "explanation": "Кэш ускоряет доступ и снижает задержку, но не увеличивает RAM."},
            key_points=[],
        ),
        QuestionRow(
            question_id=Q_OPEN,
            type_question="open_answer",
            text_question="Объясните принцип работы кэш-памяти.",
            options=[],
            answer_key={"reference_answer": "Кэш-память — это небольшая быстрая память (SRAM) "
                                           "между процессором и оперативной памятью. Она хранит "
                                           "копии часто используемых данных, чтобы процессор "
                                           "не обращался к медленной RAM.",
                        "explanation": "Оценивается по совпадению с эталоном."},
            key_points=["SRAM между CPU и RAM", "хранит копии часто используемых данных",
                        "снижает время доступа"],
        ),
    ]

    judge_verdict = Verdict(score=0.7, feedback="Верно в целом, но не названо, что это SRAM.")

    class FakeJudge:
        async def judge(self, question, reference_answer, criteria, student_answer):
            return judge_verdict

    grader = Grader(store=object(), judge=FakeJudge())
    items = []
    for ans, q in zip(task.answers, questions):
        items.append(await grader._grade_one(q, ans))

    print("open_answer → LLM-судья вернул такой JSON (это и есть VERDICT_SCHEMA):")
    print(json.dumps({"score": judge_verdict.score, "feedback": judge_verdict.feedback},
                     ensure_ascii=False, indent=2))

    # ── 3. Результат: ML → backend ─────────────────────────────────────────
    hr("3. РЕЗУЛЬТАТ  ML → backend   XADD grade-test:ml-to-be * payload '<json>'")

    outcome = None  # grade() ходит в БД; ниже считаем на тех же items
    from app.services.grader import _aggregate
    score_pct, grade = _aggregate(items, total_questions=len(questions))

    result = GradeAttemptResult.ok(
        task_id=backend_payload["task_id"],
        attempt_id=ATTEMPT_ID,
        test_id=TEST_ID,
        score_pct=score_pct,
        grade=grade,
        items=items,
    )
    print(json.dumps(json.loads(result.to_json()), ensure_ascii=False, indent=2))

    # ── 4. Ошибка ───────────────────────────────────────────────────────────
    hr("4. ОШИБКА  ML → backend   (status=error)")

    err = GradeAttemptResult.err(
        task_id=backend_payload["task_id"],
        error="no questions found for test_id=" + TEST_ID,
        attempt_id=ATTEMPT_ID,
        test_id=TEST_ID,
    )
    print(json.dumps(json.loads(err.to_json()), ensure_ascii=False, indent=2))

    # ── 5. Что backend пишет в БД ───────────────────────────────────────────
    hr("5. ЧТО BACKEND ПИШЕТ В БД")

    print("UPDATE student_attempts SET finished_at = NOW(), score_pct = " + str(score_pct)
          + ", grade = " + str(grade))
    print("  WHERE attempt_id = '" + ATTEMPT_ID + "';")
    print("UPDATE attempt_answers SET score = ..., feedback = ... -- по строке на вопрос;")
    print("(сами строки attempt_answers backend создаёт при сдаче попытки —")
    print(" student_answer пишется тогда, score/feedback — приходит из ML);")


if __name__ == "__main__":
    asyncio.run(main())
