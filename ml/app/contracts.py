"""Контракт сообщений между backend и ML-воркером.

=== ГДЕ ЖИВЁТ ===
Один тип задачи — один канал. Имя канала: `<prefix>:<type>`, где prefix —
`ml-tasks` (backend → ml) или `ml-results` (ml → backend).

    ml-tasks:ingest          ml-results:ingest
    ml-tasks:rag_question    ml-results:rag_question
    ml-tasks:create_test     ml-results:create_test
    ml-tasks:grade_attempt   ml-results:grade_attempt

Тип задачи определяется ИМЕНЕМ КАНАЛА, а не полем в payload: payload не несёт
`type`. Обработчик выбирается по каналу, поэтому сообщение нельзя прочитать не
тем обработчиком.

=== КАК ПОЛЬЗОВАТЬСЯ ===
Сборка:
    task = IngestTask(material_id="uuid-material", storage_key="uploads/lec.pdf")
    await redis.xadd(stream_channel("ml-tasks", "ingest"), {"payload": task.to_json()})

Парсинг входящего сообщения (тип известен из канала):
    payload = fields["payload"]
    task = parse_task(payload, "ingest")   # сам выберет нужный dataclass по типу
    if isinstance(task, UnknownTask):
        ...                            # отдать ошибку в ml-results:ingest

Сборка ответа:
    result = IngestResult.ok(task_id="", material_id="uuid-material", chunks_indexed=29)
    await redis.xadd(stream_channel("ml-results", "ingest"), {"payload": result.to_json()})

=== BEST PRACTICE ===
- ML отдаёт ВАЛИДНЫЙ структурированный JSON, не сырой текст LLM. Если LLM вернул
  кривой JSON — ML сам делает retry и только потом error. Backend никогда не
  парсит LLM-output напрямую.
- Поле `task_id` обязательно в каждом сообщении, кроме ingest: там корреляция
  идёт по material_id (одна индексация — один материал). Backend использует
  task_id, чтобы сопоставить результат с запросом. Канал задаёт ТИП задачи,
  task_id — КАКУЮ именно: в одном канале может висеть несколько задач.
- `status` в результатах: "ok" | "error", для ingest — "ready" | "error".
  При error — поле `error` обязательно.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal


TaskStatus = Literal["ok", "error"]
IngestStatus = Literal["ready", "error"]
Difficulty = Literal["easy", "medium", "hard"]

# Ограничения заказчика на количество вопросов в тесте.
# Минимум 1, а не 5: мы не знаем, какие материалы прилетят — на записке с тремя
# тезисами разбирается один вопрос, и требовать пять — значит выдумывать.
MIN_QUESTIONS = 1
MAX_QUESTIONS = 30

# Типы вопросов, которые ML умеет генерировать и проверять.
QUESTION_TYPES = ("single_choice", "multi_choice", "open_answer")
DIFFICULTIES = ("easy", "medium", "hard")

# Префиксы каналов: задачи (backend → ml) и результаты (ml → backend).
TASKS_STREAM_PREFIX = "ml-tasks"
RESULTS_STREAM_PREFIX = "ml-results"


def stream_channel(prefix: str, task_type: str) -> str:
    """Имя канала для типа задачи: '<prefix>:<type>'.

    Один тип задачи — один канал. Тип определяется именем канала, а не полем
    в payload, поэтому сообщение нельзя положить не туда.
    """
    return f"{prefix}:{task_type}"


def channel_task_type(channel: str) -> str:
    """Обратное преобразование: 'ml-tasks:create_test' → 'create_test'."""
    head, sep, tail = channel.rpartition(":")
    return tail if sep else ""


# ============================================================================
#  ВХОДЯЩИЕ ЗАДАЧИ
# ============================================================================

@dataclass
class IngestTask:
    """Скачать файл из MinIO и проиндексировать в vector store.

    Backend заливает файл в MinIO (bucket=MINIO_BUCKET), затем шлёт эту задачу.
    В контракте у задачи нет `task_id`: корреляция идёт по material_id —
    одна индексация соответствует одному материалу.
    """
    material_id: str                       # UUID-строка от backend; int-иды больше не используются
    storage_key: str                       # путь внутри MinIO bucket, например "uploads/lec.pdf"
    task_id: str = ""                      # необязателен: корреляция по material_id
    course_id: str | None = None           # опц., ml не использует; для логов/tracing
    TYPE: ClassVar[str] = "ingest"

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        return {
            **({"task_id": self.task_id} if self.task_id else {}),
            "material_id": self.material_id,
            "storage_key": self.storage_key,
            **({"course_id": self.course_id} if self.course_id is not None else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "IngestTask":
        return cls(
            task_id=str(d.get("task_id") or ""),
            material_id=str(d["material_id"]),         # было int() — бек шлёт UUID-строку
            storage_key=str(d["storage_key"]),
            course_id=d.get("course_id"),
        )


@dataclass
class RAGQuestionTask:
    """Ответить на вопрос по уже проиндексированному материалу."""
    task_id: str
    material_id: int
    question: str
    top_k: int = 4
    retrieve_n: int | None = None          # None → равен top_k
    rerank: bool = False
    TYPE: ClassVar[str] = "rag_question"

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "material_id": self.material_id,
            "question": self.question,
            "top_k": self.top_k,
            **({"retrieve_n": self.retrieve_n} if self.retrieve_n is not None else {}),
            "rerank": self.rerank,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RAGQuestionTask":
        rn = d.get("retrieve_n")
        return cls(
            task_id=str(d["task_id"]),
            material_id=int(d["material_id"]),
            question=str(d["question"]),
            top_k=int(d.get("top_k", 4)),
            retrieve_n=int(rn) if rn is not None else None,
            rerank=bool(d.get("rerank", False)),
        )


@dataclass
class CreateTestTask:
    """Сгенерировать тест (вопросы с вариантами) по нескольким материалам.

    Backend присылает список уже проиндексированных material_ids; ML собирает
    контекст из всех, отдаёт в LLM с JSON-output, парсит, валидирует, возвращает
    структурированный Test.

    num_questions = None → число вопросов определяет ML сам (планировщик смотрит
    на материал и решает, сколько фактов в нём разбирается). Заданное число →
    ровно столько, как просил backend (нужно старым клиентам, которые число
    ещё присылают).
    """
    task_id: str
    test_id: str                           # uuid теста, который хранит backend
    material_ids: list[str]                # uuid-строки от backend (раньше было int)
    title: str
    num_questions: int | None = None
    difficulty: Difficulty = "medium"
    course_id: str | None = None           # uuid-строка (раньше было int)
    TYPE: ClassVar[str] = "create_test"

    def __post_init__(self) -> None:
        # Лимиты заказчика: 1..30. None = «определи сам», тогда проверять нечего.
        if self.num_questions is not None and not (
            MIN_QUESTIONS <= self.num_questions <= MAX_QUESTIONS
        ):
            raise ValueError(
                f"num_questions must be in [{MIN_QUESTIONS}, {MAX_QUESTIONS}], "
                f"got {self.num_questions}"
            )
        if self.difficulty not in DIFFICULTIES:
            raise ValueError(
                f"difficulty must be one of {DIFFICULTIES}, got {self.difficulty!r}"
            )

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "test_id": self.test_id,
            "material_ids": list(self.material_ids),
            "title": self.title,
            # Явное число — «ровно столько вопросов». "min" — размер выбирает
            # ML сам по материалу (планировщик).
            "amountQuestions": self.num_questions if self.num_questions is not None else "min",
            "difficulty": self.difficulty,
            **({"course_id": self.course_id} if self.course_id is not None else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CreateTestTask":
        mids = d.get("material_ids") or []
        if not isinstance(mids, list) or not mids:
            raise ValueError("material_ids must be a non-empty list")
        # Число вопросов необязательно: каноническое имя — amountQuestions,
        # num_questions принимаем как legacy (в Redis Streams остались payload'ы
        # прежнего формата). "min"/"auto"/None — «ML выбирает размер сам».
        raw_n = d.get("amountQuestions")
        if raw_n is None:
            raw_n = d.get("num_questions")
        if isinstance(raw_n, str) and raw_n.strip().lower() in ("min", "auto", ""):
            raw_n = None
        # Лимиты num_questions и difficulty проверяет __post_init__
        return cls(
            task_id=str(d["task_id"]),
            test_id=str(d["test_id"]),
            material_ids=[str(x) for x in mids],
            title=str(d["title"]),
            num_questions=None if raw_n is None else int(raw_n),
            difficulty=str(d.get("difficulty", "medium")),  # type: ignore[arg-type]
            course_id=d.get("course_id"),
        )


# ============================================================================
#  РЕЗУЛЬТАТЫ
# ============================================================================

@dataclass
class IngestResult:
    """Результат индексации материала.

    В контракте статус успеха — "ready" (материал проиндексирован), а не "ok":
    это тот же смысл, что у `materials.status_material` в БД. Ошибка — "error"
    с обязательным полем `error`.
    """
    task_id: str
    status: IngestStatus
    material_id: str | None = None         # UUID-строка от backend; в err-ветке включается,
                                            # если известен — чтобы backend мог обновить status_material
    chunks_indexed: int | None = None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.task_id:
            out["task_id"] = self.task_id
        if self.material_id is not None:
            out["material_id"] = self.material_id
        out["status"] = self.status
        if self.status == "ready":
            out["chunks_indexed"] = self.chunks_indexed
        else:
            out["error"] = self.error or "unknown error"
        return out

    @classmethod
    def ok(cls, task_id: str, material_id: str, chunks_indexed: int) -> "IngestResult":
        return cls(task_id=task_id, status="ready", material_id=material_id, chunks_indexed=chunks_indexed)

    @classmethod
    def err(cls, task_id: str, error: str, material_id: str | None = None) -> "IngestResult":
        return cls(task_id=task_id, status="error", error=error, material_id=material_id)


@dataclass
class RAGQuestionResult:
    task_id: str
    status: TaskStatus
    answer: str | None = None
    sources: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task_id": self.task_id, "status": self.status}
        if self.status == "ok":
            out["answer"] = self.answer or ""
            out["sources"] = list(self.sources)
        else:
            out["error"] = self.error or "unknown error"
        return out

    @classmethod
    def ok(cls, task_id: str, answer: str, sources: list[str]) -> "RAGQuestionResult":
        return cls(task_id=task_id, status="ok", answer=answer, sources=sources)

    @classmethod
    def err(cls, task_id: str, error: str) -> "RAGQuestionResult":
        return cls(task_id=task_id, status="error", error=error)


@dataclass
class TestQuestion:
    """Один вопрос теста. Backend кладёт в свою таблицу test_questions.

    Три типа вопросов:
      - `single_choice` — есть варианты, в `answer_key` лежит `{"correct_index": N}`;
      - `multi_choice`  — есть варианты, в `answer_key` лежит
        `{"correct_indexes": [N, M]}` (2 или 3 правильных);
      - `open_answer`    — вариантов нет, в `answer_key` лежит
        `{"reference_answer": "<эталон>"}`, а в `key_points` — опорные пункты.

    `answer_key.explanation` — короткое объяснение правильного ответа (есть у всех
    типов вопросов). `key_points` — список опорных пунктов; у закрытых вопросов
    список пустой.

    `source_chunk_id` — UUID чанка, из которого взят вопрос (nullable). LLM
    возвращает короткий алиас в `source_chunk_ref`, генератор разворачивает его
    в UUID — модель не выдумывает UUID'ы, а выбирает из списка реальных.

    На входе принимаются и плоские legacy-поля (`correct_index`, `explanation`),
    и старая форма `key_points` (объект с `criteria`) — в Redis Streams остались
    payload'ы прежнего формата. На выходе — только канонический вид.
    """
    __test__ = False  # не pytest-класс
    id: int
    text: str
    type_question: str = "single_choice"
    options: list[str] = field(default_factory=list)
    answer_key: dict[str, Any] = field(default_factory=dict)
    key_points: list[str] = field(default_factory=list)
    source_chunk_id: str | None = None
    source_chunk_ref: str | None = None      # внутренний алиас чанка от LLM

    def to_dict(self) -> dict[str, Any]:
        # Имя поля типа в контракте — `type`. `answer_key` обязателен: backend
        # кладёт его в test_questions.answer_key, а грейдер берёт оттуда
        # эталон при проверке попытки — без него тест нечем оценивать.
        return {
            "id": self.id,
            "type": self.type_question,
            "text": self.text,
            "options": list(self.options),
            "answer_key": dict(self.answer_key),
            "key_points": list(self.key_points),
            "source_chunk_id": self.source_chunk_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TestQuestion":
        qid = d.get("id")
        # `type` — каноническое имя поля типа, type_question принимаем как legacy.
        qtype = str(d.get("type") or d.get("type_question") or "single_choice")
        if qtype not in QUESTION_TYPES:
            raise ValueError(f"question {qid}: unknown type_question {qtype!r}")

        opts = d.get("options") or []
        if not isinstance(opts, list):
            raise ValueError(f"question {qid}: options must be a list")
        opts = [str(o) for o in opts]

        answer_key = dict(d.get("answer_key") or {})
        raw_kp = d.get("key_points")
        key_points = _key_points_list(raw_kp)
        if isinstance(raw_kp, dict) and raw_kp.get("explanation") and "explanation" not in answer_key:
            answer_key["explanation"] = str(raw_kp["explanation"])

        # legacy: плоские поля → вложенные
        if "correct_index" in d and "correct_index" not in answer_key:
            answer_key["correct_index"] = int(d["correct_index"])
        if "correct_indexes" in d and "correct_indexes" not in answer_key:
            answer_key["correct_indexes"] = list(d["correct_indexes"])
        if "explanation" in d and "explanation" not in answer_key:
            answer_key["explanation"] = str(d["explanation"])

        if qtype == "single_choice":
            if len(opts) < 2:
                raise ValueError(f"question {qid}: single_choice needs >= 2 options")
            if "correct_index" not in answer_key:
                raise ValueError(f"question {qid}: single_choice needs answer_key.correct_index")
            ci = int(answer_key["correct_index"])
            if not (0 <= ci < len(opts)):
                raise ValueError(f"question {qid}: correct_index {ci} out of range")
            answer_key["correct_index"] = ci
        elif qtype == "multi_choice":
            if len(opts) < 2:
                raise ValueError(f"question {qid}: multi_choice needs >= 2 options")
            raw = answer_key.get("correct_indexes")
            if raw is None:
                raise ValueError(f"question {qid}: multi_choice needs answer_key.correct_indexes")
            if not isinstance(raw, list) or not raw:
                raise ValueError(f"question {qid}: correct_indexes must be a non-empty list")
            indexes = [int(i) for i in raw]
            if len(set(indexes)) != len(indexes):
                raise ValueError(f"question {qid}: correct_indexes has duplicates")
            if len(indexes) < 2:
                raise ValueError(f"question {qid}: multi_choice needs >= 2 correct indexes")
            if any(not (0 <= i < len(opts)) for i in indexes):
                raise ValueError(f"question {qid}: correct_indexes out of range")
            answer_key["correct_indexes"] = sorted(indexes)
        else:
            reference = str(answer_key.get("reference_answer") or "").strip()
            if not reference:
                raise ValueError(f"question {qid}: open_answer needs answer_key.reference_answer")
            answer_key["reference_answer"] = reference
            # LLM нередко кладёт `criteria` в answer_key, а не в key_points.
            # Нормализуем на границе: дальше судья читает key_points, а в
            # answer_key остаётся только эталон.
            if "criteria" in answer_key and not key_points:
                key_points = _key_points_list(answer_key.pop("criteria"))

        chunk_id = d.get("source_chunk_id")
        chunk_ref = d.get("source_chunk_ref")

        return cls(
            id=int(d["id"]),
            text=str(d["text"]).strip(),
            type_question=qtype,
            options=opts,
            answer_key=answer_key,
            key_points=key_points,
            source_chunk_id=str(chunk_id) if chunk_id else None,
            source_chunk_ref=str(chunk_ref) if chunk_ref else None,
        )

    def reference_answer(self) -> str:
        """Эталонный ответ для open_answer (пустая строка у single_choice)."""
        return str(self.answer_key.get("reference_answer") or "").strip()

    def explanation(self) -> str:
        """Короткое объяснение правильного ответа (answer_key.explanation)."""
        return str(self.answer_key.get("explanation") or "").strip()

    def criteria(self) -> list[str]:
        """Опорные пункты для open_answer."""
        return list(self.key_points)

    def correct_indexes(self) -> list[int]:
        """Правильные индексы вариантов для multi_choice (пусто у других типов)."""
        raw = self.answer_key.get("correct_indexes") or []
        if not isinstance(raw, list):
            return []
        try:
            return sorted({int(i) for i in raw})
        except (TypeError, ValueError):
            return []


def _key_points_list(raw: Any) -> list[str]:
    """key_points в канонической форме — список строк.

    Принимаем новую форму (список критериев) и старую (объект с `criteria`) —
    в Redis Streams остались payload'ы прежнего формата.
    """
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, dict):
        crit = raw.get("criteria")
        if isinstance(crit, list):
            return [str(x).strip() for x in crit if str(x).strip()]
    return []


@dataclass
class Test:
    """Сгенерированный тест: title + список вопросов."""
    __test__ = False  # не pytest-класс
    title: str
    questions: list[TestQuestion]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "questions": [q.to_dict() for q in self.questions]}

    @classmethod
    def from_dict(cls, d: dict) -> "Test":
        qs_raw = d.get("questions") or []
        if not isinstance(qs_raw, list) or not qs_raw:
            raise ValueError("test.questions must be a non-empty list")
        return cls(
            title=str(d.get("title", "")).strip(),
            questions=[TestQuestion.from_dict(q) for q in qs_raw],
        )


@dataclass
class CreateTestResult:
    task_id: str
    status: TaskStatus
    test: Test | None = None
    # test_id из задачи — чтобы backend знал, какую запись в tests апдейтить,
    # не заводя task_id → test_id маппинг и лишнюю колонку.
    test_id: str | None = None
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task_id": self.task_id, "status": self.status}
        if self.test_id is not None:
            out["test_id"] = self.test_id
        if self.status == "ok":
            assert self.test is not None
            out["test"] = self.test.to_dict()
        else:
            out["error"] = self.error or "unknown error"
        return out

    @classmethod
    def ok(
        cls,
        task_id: str,
        test: Test,
        test_id: str | None = None,
    ) -> "CreateTestResult":
        return cls(task_id=task_id, status="ok", test=test, test_id=test_id)

    @classmethod
    def err(cls, task_id: str, error: str, test_id: str | None = None) -> "CreateTestResult":
        return cls(task_id=task_id, status="error", error=error, test_id=test_id)


# ============================================================================
#  GRADE ATTEMPT
# ============================================================================

@dataclass
class StudentAnswer:
    """Один ответ студента в attempt'е. Хранится как dict в payload.

    Принимаем три формата:
      - новый  — `{"question_id": ..., "student_answer": {"index": 2}}`,
                 `{"question_id": ..., "student_answer": {"indexes": [0, 2]}}` или
                 `{"question_id": ..., "student_answer": {"text": "..."}}`;
      - legacy — плоские `student_answer_index` / `student_answer_text`.
    """
    question_id: str
    student_answer_index: int | None = None    # для single_choice (0..N-1)
    student_answer_indexes: list[int] | None = None  # для multi_choice (2-3 индекса)
    student_answer_text: str | None = None      # для open_answer

    @classmethod
    def from_dict(cls, d: dict) -> "StudentAnswer":
        idx = d.get("student_answer_index")
        idxs = d.get("student_answer_indexes")
        txt = d.get("student_answer_text")

        raw = d.get("student_answer")
        if isinstance(raw, dict):
            if raw.get("index") is not None:
                idx = raw["index"]
            if raw.get("indexes") is not None:
                idxs = raw["indexes"]
            if raw.get("text") is not None:
                txt = raw["text"]

        parsed_idxs: list[int] | None = None
        if idxs is not None:
            if not isinstance(idxs, list) or not idxs:
                raise ValueError(
                    f"answer for question {d.get('question_id')}: indexes must be a non-empty list"
                )
            parsed_idxs = [int(i) for i in idxs]

        if idx is None and parsed_idxs is None and (txt is None or not str(txt).strip()):
            raise ValueError(f"answer for question {d.get('question_id')}: empty")
        return cls(
            question_id=str(d["question_id"]),
            student_answer_index=int(idx) if idx is not None else None,
            student_answer_indexes=parsed_idxs,
            student_answer_text=str(txt) if txt is not None else None,
        )


def _student_answer_payload(a: StudentAnswer) -> dict[str, Any]:
    """Канонический вид ответа студента в payload задачи.

    Ровно одно из трёх: `index` (single_choice), `indexes` (multi_choice),
    `text` (open_answer). Backend шлёт именно так — см. MlTaskPublisherImpl.
    """
    if a.student_answer_indexes is not None:
        return {"indexes": list(a.student_answer_indexes)}
    if a.student_answer_index is not None:
        return {"index": a.student_answer_index}
    return {"text": a.student_answer_text or ""}


@dataclass
class GradeAttemptTask:
    """Оценить attempt: backend присылает test_id + ответы студента, ML достаёт
    вопросы из БД, проверяет, возвращает per-question score + feedback + total.

    Backend при отправке этой задачи уже создал запись в student_attempts
    (started_at = NOW()). Наш результат запишет finished_at + score + grade.
    """
    task_id: str
    attempt_id: str                        # uuid попытки
    test_id: str                           # uuid теста
    user_id: str                           # uuid студента (для логов/идемпотентности)
    answers: list[StudentAnswer]
    TYPE: ClassVar[str] = "grade_attempt"

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "test_id": self.test_id,
            "user_id": self.user_id,
            "answers": [
                {"question_id": a.question_id, "student_answer": _student_answer_payload(a)}
                for a in self.answers
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GradeAttemptTask":
        raw = d.get("answers") or []
        if not isinstance(raw, list) or not raw:
            raise ValueError("answers must be a non-empty list")
        return cls(
            task_id=str(d["task_id"]),
            attempt_id=str(d["attempt_id"]),
            test_id=str(d["test_id"]),
            user_id=str(d["user_id"]),
            answers=[StudentAnswer.from_dict(a) for a in raw],
        )


@dataclass
class GradedItem:
    """Per-question результат проверки.

    В контракте ответы плоские, строками: `correct_answer` — текст правильного
    варианта (для открытого вопроса — эталон), `student_answer` — что ответил
    студент (текст отмеченных вариантов или его собственный ответ).
    """
    question_id: str
    is_correct: bool
    score: float                           # 0.0..1.0 — доля баллов за вопрос
    feedback: str = ""
    correct_answer: str = ""
    student_answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "is_correct": self.is_correct,
            "score": self.score,
            "feedback": self.feedback,
            "correct_answer": self.correct_answer,
            "student_answer": self.student_answer,
        }


@dataclass
class GradeAttemptResult:
    task_id: str
    status: TaskStatus
    attempt_id: str | None = None          # чтобы backend нашёл строку в student_attempts
    test_id: str | None = None
    score_pct: float | None = None         # 0..100
    grade: int | None = None               # 2..5
    items: list[GradedItem] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), ensure_ascii=False)

    def _as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"task_id": self.task_id, "status": self.status}
        if self.attempt_id is not None:
            out["attempt_id"] = self.attempt_id
        if self.test_id is not None:
            out["test_id"] = self.test_id
        if self.status == "ok":
            out["score_pct"] = self.score_pct
            out["grade"] = self.grade
            out["items"] = [i.to_dict() for i in self.items]
        else:
            out["error"] = self.error or "unknown error"
        return out

    @classmethod
    def ok(
        cls, task_id: str, attempt_id: str, test_id: str,
        score_pct: float, grade: int, items: list[GradedItem],
    ) -> "GradeAttemptResult":
        return cls(
            task_id=task_id, status="ok",
            attempt_id=attempt_id, test_id=test_id,
            score_pct=score_pct, grade=grade, items=items,
        )

    @classmethod
    def err(
        cls, task_id: str, error: str,
        attempt_id: str | None = None, test_id: str | None = None,
    ) -> "GradeAttemptResult":
        return cls(
            task_id=task_id, status="error", error=error,
            attempt_id=attempt_id, test_id=test_id,
        )


# ============================================================================
#  DISPATCH
# ============================================================================

@dataclass
class UnknownTask:
    """Заглушка для нераспознанного типа канала. Не падаем — отдаём ошибку."""
    task_id: str
    raw_type: str
    payload: dict

    def to_error(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "status": "error",
                "error": f"unknown task type: {self.raw_type!r}"}


TASK_CLASSES: dict[str, type] = {
    "ingest": IngestTask,
    "rag_question": RAGQuestionTask,
    "create_test": CreateTestTask,
    "grade_attempt": GradeAttemptTask,
}

# Типы задач — по одному каналу на каждый.
TASK_TYPES: tuple[str, ...] = tuple(TASK_CLASSES)


def parse_task(
    payload: str | dict,
    task_type: str,
) -> IngestTask | RAGQuestionTask | CreateTestTask | GradeAttemptTask | UnknownTask:
    """Разобрать payload из Redis Stream в dataclass по типу задачи.

    Тип приходит из ИМЕНИ КАНАЛА, а не из payload: один тип задачи — один
    канал, поэтому «положить не туда» невозможно.

    Raises:
        ValueError: если payload не JSON или нет обязательного поля task_id
            (для ingest task_id не требуется — там корреляция по material_id).
    """
    if isinstance(payload, str):
        try:
            d = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ValueError(f"payload is not valid JSON: {e}") from e
    else:
        d = payload

    if not isinstance(d, dict):
        raise ValueError(f"payload must be a JSON object, got {type(d).__name__}")

    task_id = str(d.get("task_id") or "")
    if not task_id and task_type != "ingest":
        raise ValueError("payload.task_id is required")

    cls = TASK_CLASSES.get(task_type)
    if cls is None:
        return UnknownTask(task_id=task_id, raw_type=str(task_type), payload=d)
    return cls.from_dict(d)


def all_task_types() -> list[str]:
    """Список поддерживаемых типов задач (для документации/Swagger)."""
    return sorted(TASK_CLASSES)
