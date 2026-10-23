"""Контракты сообщений между backend и ML-воркером.

Тип задачи задаёт ИМЯ СТРИМА, а не поле в payload. Поэтому в этих dataclass'ах
нет поля `type` ни во входящих, ни в исходящих сообщениях — по трём парам стримов
backend однозначно понимает, что прислал ML, и наоборот.

ВХОД (backend → ML), поле `payload` = JSON:
    ml:tasks:ingest         → IngestTask
    ml:tasks:create-test    → CreateTestTask
    ml:tasks:grade-attempt  → GradeAttemptTask

ВЫХОД (ML → backend), поле `payload` = JSON:
    ml:results:ingest         → IngestResult
    ml:results:create-test    → CreateTestResult
    ml:results:grade-attempt  → GradeAttemptResult

Полная спецификация: docs/superpowers/specs/2026-10-22-ml-backend-contract-design.md

ML пишет в БД только material_chunks. Всё остальное — test_questions,
student_attempts, attempt_answers, статусы — пишет backend, беря значения
отсюда. Поэтому в исходящих сообщениях нет дублирующих полей вроде
`is_correct` или `correct_index` в grade_attempt: backend их уже знает из своих
же таблиц.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal["ok", "error"]
Difficulty = Literal["easy", "medium", "hard"]


class ContractError(ValueError):
    """Payload не соответствует контракту. Backend должен увидеть status=error."""


# ============================================================================
#  ВХОДЯЩИЕ ЗАДАЧИ
# ============================================================================


@dataclass
class IngestTask:
    """Скачать файл из S3, нарезать и записать чанки в material_chunks."""

    task_id: str
    material_id: str
    storage_key: str

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IngestTask":
        _require(d, "task_id", "material_id", "storage_key")
        return cls(
            task_id=str(d["task_id"]),
            material_id=str(d["material_id"]),
            storage_key=str(d["storage_key"]),
        )


@dataclass
class CreateTestTask:
    """Сгенерировать вопросы по материалам, уже нарезанным в material_chunks."""

    task_id: str
    test_id: str
    material_ids: list[str]
    title: str
    num_questions: int = 10
    difficulty: Difficulty = "medium"
    course_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "task_id": self.task_id,
            "test_id": self.test_id,
            "material_ids": list(self.material_ids),
            "title": self.title,
            "num_questions": self.num_questions,
            "difficulty": self.difficulty,
        }
        if self.course_id is not None:
            out["course_id"] = self.course_id
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CreateTestTask":
        _require(d, "task_id", "test_id", "title")
        material_ids = [str(x) for x in (d.get("material_ids") or [])]
        if not material_ids:
            raise ContractError("create_test: material_ids must be a non-empty list")
        difficulty = d.get("difficulty", "medium")
        if difficulty not in ("easy", "medium", "hard"):
            raise ContractError(f"create_test: unknown difficulty {difficulty!r}")
        return cls(
            task_id=str(d["task_id"]),
            test_id=str(d["test_id"]),
            material_ids=material_ids,
            title=str(d["title"]),
            num_questions=_positive_int(d.get("num_questions", 10), "num_questions"),
            difficulty=difficulty,
            course_id=None if d.get("course_id") is None else str(d["course_id"]),
        )


@dataclass
class StudentAnswer:
    """Ответ студента на один вопрос. ML генерирует только single_choice,
    поэтому ответ — это индекс выбранного варианта."""

    question_id: str
    student_answer_index: int | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StudentAnswer":
        if "question_id" not in d:
            raise ContractError("answer: question_id is required")
        idx = d.get("student_answer_index")
        return cls(
            question_id=str(d["question_id"]),
            student_answer_index=None if idx is None else int(idx),
        )


@dataclass
class GradeAttemptTask:
    """Проверить попытку. Backend к этому моменту уже создал строку в
    student_attempts и сохранил ответы через автосохранение.

    ML читает test_questions, чтобы знать правильные индексы, и возвращает
    score по каждому вопросу + один overall_feedback на всю попытку.
    """

    task_id: str
    attempt_id: str
    test_id: str
    answers: list[StudentAnswer] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GradeAttemptTask":
        _require(d, "task_id", "attempt_id", "test_id")
        raw = d.get("answers") or []
        if not isinstance(raw, list):
            raise ContractError("grade_attempt: answers must be a list")
        return cls(
            task_id=str(d["task_id"]),
            attempt_id=str(d["attempt_id"]),
            test_id=str(d["test_id"]),
            answers=[StudentAnswer.from_dict(a) for a in raw],
        )


# ============================================================================
#  РЕЗУЛЬТАТЫ
# ============================================================================


@dataclass
class IngestResult:
    """Backend сам знает material_id по своему же маппингу task_id → material_id,
    поэтому в ответе его нет — только подтверждение."""

    task_id: str
    status: TaskStatus = "ok"
    error: str | None = None

    def _as_dict(self) -> dict[str, Any]:
        if self.status == "ok":
            return {"task_id": self.task_id, "status": "ok"}
        return {
            "task_id": self.task_id,
            "status": "error",
            "error": self.error or "unknown error",
        }

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    @classmethod
    def ok(cls, task_id: str) -> "IngestResult":
        return cls(task_id=task_id, status="ok")

    @classmethod
    def err(cls, task_id: str, error: str) -> "IngestResult":
        return cls(task_id=task_id, status="error", error=error)


@dataclass
class TestQuestion:
    """Вопрос в том виде, в каком его запишет backend в test_questions."""

    __test__ = False  # pytest не должен пытаться собрать dataclass'ы как тесты

    id: int
    text: str
    options: list[str]
    correct_index: int
    source_chunk_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "options": list(self.options),
            "correct_index": self.correct_index,
        }
        if self.source_chunk_id is not None:
            out["source_chunk_id"] = self.source_chunk_id
        return out


@dataclass
class Test:
    __test__ = False  # pytest не должен пытаться собрать dataclass'ы как тесты

    title: str
    questions: list[TestQuestion]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "questions": [q.to_dict() for q in self.questions]}


@dataclass
class CreateTestResult:
    task_id: str
    status: TaskStatus = "ok"
    test_id: str | None = None
    test: Test | None = None
    error: str | None = None

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task_id": self.task_id, "status": self.status}
        if self.test_id is not None:
            out["test_id"] = self.test_id
        if self.status == "ok":
            if self.test is None:
                raise ContractError("create_test result: status=ok requires test")
            out["test"] = self.test.to_dict()
        else:
            out["error"] = self.error or "unknown error"
        return out

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    @classmethod
    def ok(cls, task_id: str, test_id: str, test: Test) -> "CreateTestResult":
        return cls(task_id=task_id, status="ok", test_id=test_id, test=test)

    @classmethod
    def err(cls, task_id: str, error: str, test_id: str | None = None) -> "CreateTestResult":
        return cls(task_id=task_id, status="error", error=error, test_id=test_id)


@dataclass
class GradedItem:
    """Результат по одному вопросу. is_correct backend выводит из score,
    student_answer_index и correct_index у него уже есть в своих таблицах."""

    question_id: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"question_id": self.question_id, "score": self.score}


@dataclass
class GradeAttemptResult:
    task_id: str
    status: TaskStatus = "ok"
    attempt_id: str | None = None
    test_id: str | None = None
    score_pct: float | None = None
    grade: int | None = None
    overall_feedback: str | None = None
    items: list[GradedItem] = field(default_factory=list)
    error: str | None = None

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task_id": self.task_id, "status": self.status}
        if self.attempt_id is not None:
            out["attempt_id"] = self.attempt_id
        if self.test_id is not None:
            out["test_id"] = self.test_id
        if self.status == "ok":
            out["score_pct"] = self.score_pct
            out["grade"] = self.grade
            out["overall_feedback"] = self.overall_feedback or ""
            out["items"] = [i.to_dict() for i in self.items]
        else:
            out["error"] = self.error or "unknown error"
        return out

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    @classmethod
    def ok(
        cls,
        task_id: str,
        attempt_id: str,
        test_id: str,
        score_pct: float,
        grade: int,
        overall_feedback: str,
        items: list[GradedItem],
    ) -> "GradeAttemptResult":
        return cls(
            task_id=task_id,
            status="ok",
            attempt_id=attempt_id,
            test_id=test_id,
            score_pct=score_pct,
            grade=grade,
            overall_feedback=overall_feedback,
            items=items,
        )

    @classmethod
    def err(
        cls, task_id: str, error: str, attempt_id: str | None = None, test_id: str | None = None
    ) -> "GradeAttemptResult":
        return cls(
            task_id=task_id, status="error", error=error, attempt_id=attempt_id, test_id=test_id
        )


# ============================================================================
#  DISPATCH
# ============================================================================

# Имя стрима → класс задачи. Ключ — имя входящего стрима, а не поле в payload.
TASK_TYPES: dict[str, type] = {
    "ingest": IngestTask,
    "create_test": CreateTestTask,
    "grade_attempt": GradeAttemptTask,
}


def parse_task(channel: str, payload: str | dict[str, Any]) -> IngestTask | CreateTestTask | GradeAttemptTask:
    """Разобрать payload входящего сообщения.

    Args:
        channel: имя входящего стрима, определяет тип задачи.
        payload: JSON-строка или уже распарсенный dict.

    Raises:
        ContractError: неизвестный канал, невалидный JSON, нет обязательных полей.
    """
    cls = TASK_TYPES.get(channel)
    if cls is None:
        raise ContractError(f"unknown task channel: {channel!r}")

    if isinstance(payload, str):
        try:
            d = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ContractError(f"payload is not valid JSON: {e}") from e
    else:
        d = payload

    if not isinstance(d, dict):
        raise ContractError(f"payload must be a JSON object, got {type(d).__name__}")
    return cls.from_dict(d)  # type: ignore[return-value]


def grade_from_pct(score_pct: float) -> int:
    """Шкала оценок: ≥90 → 5, ≥70 → 4, ≥50 → 3, иначе 2."""
    if score_pct >= 90:
        return 5
    if score_pct >= 70:
        return 4
    if score_pct >= 50:
        return 3
    return 2


def _require(d: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if d.get(k) in (None, "")]
    if missing:
        raise ContractError(f"missing required fields: {', '.join(missing)}")


def _positive_int(value: Any, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as e:
        raise ContractError(f"{name} must be an integer, got {value!r}") from e
    if n < 1:
        raise ContractError(f"{name} must be >= 1, got {n}")
    return n