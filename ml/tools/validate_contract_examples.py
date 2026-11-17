"""Проверяет JSON-схемы и примеры контрактов Redis Streams.

Запуск из корня ml/:
    python tools/validate_contract_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator

from app.contracts import (
    CreateTestTask,
    GradeAttemptTask,
    IngestTask,
    StudentAnswer,
)


CONTRACTS = ROOT / "docs" / "contracts"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_be_to_ml(channel: str) -> dict[str, Any]:
    if channel == "ingest-be-to-ml":
        return json.loads(
            IngestTask(
                material_id="5a2c9f10-1c4d-4f7b-9a2e-7d3f6b8c1e04",
                storage_key="materials/5a2c9f10-1c4d-4f7b-9a2e-7d3f6b8c1e04/lecture.pdf",
                task_id="2b8e4c31-6d7a-4f19-a503-9e8c1b4d6f27",
                course_id="f7b2d48c-3a91-4f62-8d15-6e9c4a2b7d30",
            ).to_json()
        )
    if channel == "create-test-be-to-ml":
        return json.loads(
            CreateTestTask(
                task_id="2b8e4c31-6d7a-4f19-a503-9e8c1b4d6f27",
                test_id="9e3a6d52-8c14-47b0-a2f6-1d8e5c3b4a90",
                material_ids=["5a2c9f10-1c4d-4f7b-9a2e-7d3f6b8c1e04"],
                title="Контрольная работа по базам данных",
                num_questions=3,
                difficulty="medium",
                course_id="f7b2d48c-3a91-4f62-8d15-6e9c4a2b7d30",
            ).to_json()
        )
    if channel == "grade-test-be-to-ml":
        return json.loads(
            GradeAttemptTask(
                task_id="2b8e4c31-6d7a-4f19-a503-9e8c1b4d6f27",
                attempt_id="4d8f2b76-1e35-4c9a-b027-8f6a3d1e5b42",
                test_id="9e3a6d52-8c14-47b0-a2f6-1d8e5c3b4a90",
                user_id="8c1d4a29-6e73-4b85-9f02-3a7e5c9d1b68",
                answers=[
                    StudentAnswer(question_id="18c5e91a-2d74-4f60-b839-7e1a5c0d6b42", student_answer_index=1),
                    StudentAnswer(question_id="7a0d3e91-c642-4f88-b125-6d9e2a4c8f31", student_answer_indexes=[0, 1, 2]),
                    StudentAnswer(question_id="c30e8f2a-4b19-4d77-a810-6f3b9c2e5d04", student_answer_text="Транзакция обеспечивает атомарность операций."),
                ],
            ).to_json()
        )
    raise ValueError(channel)


def main() -> None:
    channels = [
        "ingest-be-to-ml",
        "ingest-ml-to-be",
        "create-test-be-to-ml",
        "create-test-ml-to-be",
        "grade-test-be-to-ml",
        "grade-test-ml-to-be",
    ]
    for channel in channels:
        schema_path = CONTRACTS / f"{channel}.schema.json"
        example_path = CONTRACTS / "examples" / f"{channel}.json"
        schema = load(schema_path)
        example = load(example_path)

        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(example)
        assert schema["examples"][0] == example, f"{channel}: schema example differs from file"

        if channel.endswith("-be-to-ml"):
            expected = expected_be_to_ml(channel)
            assert example == expected, f"{channel}: differs from dataclass serialization"
        else:
            assert example["input_msg_id"] == "1766000000000-0", f"{channel}: missing input_msg_id"

        print(f"OK {channel}")

    print(f"Validated {len(channels)} schemas and examples")


if __name__ == "__main__":
    main()
