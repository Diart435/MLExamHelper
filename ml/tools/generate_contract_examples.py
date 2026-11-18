"""Генерирует канонические примеры JSON-контрактов из app.contracts.

Запуск из корня ml/:
    python tools/generate_contract_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.contracts import (
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    GradedItem,
    IngestResult,
    IngestTask,
    StudentAnswer,
    Test,
    TestQuestion,
)


OUT = ROOT / "docs" / "contracts" / "examples"

MATERIAL_ID = "5a2c9f10-1c4d-4f7b-9a2e-7d3f6b8c1e04"
TASK_ID = "2b8e4c31-6d7a-4f19-a503-9e8c1b4d6f27"
TEST_ID = "9e3a6d52-8c14-47b0-a2f6-1d8e5c3b4a90"
ATTEMPT_ID = "4d8f2b76-1e35-4c9a-b027-8f6a3d1e5b42"


def _dump(name: str, payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


def main() -> None:
    ingest_task = IngestTask(
        material_id=MATERIAL_ID,
        storage_key="materials/5a2c9f10-1c4d-4f7b-9a2e-7d3f6b8c1e04/lecture.pdf",
    )
    _dump("ingest-be-to-ml.json", ingest_task._as_dict())

    ingest_result = IngestResult.ok(material_id=MATERIAL_ID)
    _dump("ingest-ml-to-be.json", ingest_result._as_dict())

    create_task = CreateTestTask(
        task_id=TASK_ID,
        test_id=TEST_ID,
        material_ids=[MATERIAL_ID],
        title="Контрольная работа по базам данных",
        difficulty="medium",
    )
    _dump("create-test-be-to-ml.json", create_task._as_dict())

    questions = [
        TestQuestion(
            id=1,
            text="Какой уровень изоляции транзакций допускает чтение неподтверждённых изменений?",
            type_question="single_choice",
            options=["READ COMMITTED", "READ UNCOMMITTED", "REPEATABLE READ", "SERIALIZABLE"],
            answer_key={"correct_index": 1, "explanation": "READ UNCOMMITTED допускает грязные чтения."},
            key_points=[],
            source_chunk_id="18c5e91a-2d74-4f60-b839-7e1a5c0d6b42",
        ),
        TestQuestion(
            id=2,
            text="Какие ограничения целостности поддерживает реляционная СУБД?",
            type_question="multi_choice",
            options=["Первичный ключ", "Уникальность", "Ссылочная целостность", "Каскадное удаление", "Шифрование"],
            answer_key={
                "correct_indexes": [0, 1, 2],
                "explanation": "Первичный ключ, уникальность и ссылочная целостность являются стандартными ограничениями.",
            },
            key_points=[],
            source_chunk_id="7a0d3e91-c642-4f88-b125-6d9e2a4c8f31",
        ),
        TestQuestion(
            id=3,
            text="Объясните назначение транзакции и принцип атомарности.",
            type_question="open_answer",
            options=[],
            answer_key={
                "reference_answer": "Транзакция объединяет операции в единую логическую единицу работы; атомарность гарантирует выполнение всех операций либо откат всех изменений.",
                "explanation": "Ответ должен называть единицу работы и гарантию all-or-nothing.",
            },
            key_points=[
                "Транзакция — единая логическая единица работы.",
                "При ошибке изменения откатываются целиком.",
            ],
            source_chunk_id=None,
        ),
    ]
    create_result = CreateTestResult.ok(
        task_id=TASK_ID,
        test=Test(title="Контрольная работа по базам данных", questions=questions),
        test_id=TEST_ID,
    )
    _dump("create-test-ml-to-be.json", create_result._as_dict())

    grade_task = GradeAttemptTask(
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        test_id=TEST_ID,
        answers=[
            StudentAnswer(question_id="18c5e91a-2d74-4f60-b839-7e1a5c0d6b42", student_answer_index=1),
            StudentAnswer(question_id="7a0d3e91-c642-4f88-b125-6d9e2a4c8f31", student_answer_indexes=[0, 1, 2]),
            StudentAnswer(question_id="c30e8f2a-4b19-4d77-a810-6f3b9c2e5d04", student_answer_text="Транзакция обеспечивает атомарность операций."),
        ],
    )
    _dump("grade-test-be-to-ml.json", grade_task._as_dict())

    grade_result = GradeAttemptResult.ok(
        task_id=TASK_ID,
        attempt_id=ATTEMPT_ID,
        test_id=TEST_ID,
        score_pct=83.33,
        grade=4,
        items=[
            GradedItem(
                question_id="18c5e91a-2d74-4f60-b839-7e1a5c0d6b42",
                is_correct=True,
                score=1.0,
                feedback="Верно: READ UNCOMMITTED допускает грязные чтения.",
                correct_answer="READ UNCOMMITTED",
                student_answer="READ UNCOMMITTED",
            ),
            GradedItem(
                question_id="7a0d3e91-c642-4f88-b125-6d9e2a4c8f31",
                is_correct=True,
                score=1.0,
                feedback="Верно, выбраны все три поддерживаемых ограничения.",
                correct_answer="Первичный ключ; Уникальность; Ссылочная целостность",
                student_answer="Первичный ключ; Уникальность; Ссылочная целостность",
            ),
            GradedItem(
                question_id="c30e8f2a-4b19-4d77-a810-6f3b9c2e5d04",
                is_correct=False,
                score=0.33,
                feedback="Верно названа атомарность, но не раскрыто назначение транзакции как единой логической единицы работы.",
                correct_answer="Транзакция объединяет операции в единую логическую единицу работы; атомарность гарантирует выполнение всех операций либо откат всех изменений.",
                student_answer="Транзакция обеспечивает атомарность операций.",
            ),
        ],
    )
    _dump("grade-test-ml-to-be.json", grade_result._as_dict())


if __name__ == "__main__":
    main()
