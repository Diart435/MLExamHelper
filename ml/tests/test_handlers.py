"""Хендлеры — чистые функции: всё, что нужно, приходит аргументами.
Здесь их гоняем с фейками, без Redis, Postgres и OpenRouter."""

import pytest

from app.contracts import (
    CreateTestTask,
    GradeAttemptTask,
    IngestTask,
    StudentAnswer,
    Test,
    TestQuestion,
)
from app.db.questions import QuestionRow
from app.handlers import create_test as create_test_handler
from app.handlers import grade_attempt as grade_attempt_handler
from app.handlers import ingest as ingest_handler
from app.services.grader import Mistake

PDF_BYTES = b"%PDF-1.4 pretend"


class FakeChunks:
    def __init__(self) -> None:
        self.added: list[tuple[str, list[str], list[list[float]]]] = []

    async def add_chunks(self, material_id, texts, embeddings):
        self.added.append((material_id, texts, embeddings))
        return [f"chunk-{i}" for i, _ in enumerate(texts)]


class FakeEmbeddings:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    async def embed_batch(self, texts):
        self.batches.append(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeLLM:
    def __init__(self, answer: str = "Разбери транзакции.") -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    async def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.answer


class FakeGenerator:
    def __init__(self, test: Test | None = None) -> None:
        self.test = test or Test(title="Тест", questions=[TestQuestion(id=1, text="В", options=["a", "b"], correct_index=0)])

    async def generate(self, **kwargs):
        return self.test


# --------------------------------------------------------------------------
#  ingest
# --------------------------------------------------------------------------


async def _stub_download(monkeypatch, data: bytes = PDF_BYTES):
    async def fake(storage_key: str) -> bytes:
        return data

    monkeypatch.setattr(ingest_handler, "download_bytes", fake)
    monkeypatch.setattr(
        ingest_handler.registry, "parse", lambda storage_key, payload: "Первый абзац. Второй абзац."
    )


async def test_ingest_stores_chunks_and_answers_ok(monkeypatch):
    await _stub_download(monkeypatch)
    store, embedder = FakeChunks(), FakeEmbeddings()

    result = await ingest_handler.process_ingest(
        IngestTask(task_id="t1", material_id="m1", storage_key="a.pdf"),
        chunks=store,
        embeddings=embedder,
    )

    assert result.status == "ok"
    material_id, texts, _ = store.added[0]
    assert material_id == "m1"
    assert texts
    assert embedder.batches[0] == texts


async def test_ingest_on_download_failure_returns_error_not_exception(monkeypatch):
    async def boom(storage_key: str) -> bytes:
        raise FileNotFoundError("нет такого ключа")

    monkeypatch.setattr(ingest_handler, "download_bytes", boom)

    result = await ingest_handler.process_ingest(
        IngestTask(task_id="t1", material_id="m1", storage_key="missing.pdf"),
        chunks=FakeChunks(),
        embeddings=FakeEmbeddings(),
    )

    assert result.status == "error"
    assert "нет такого ключа" in (result.error or "")
    assert result.task_id == "t1"


async def test_ingest_on_empty_text_returns_error(monkeypatch):
    await _stub_download(monkeypatch)
    monkeypatch.setattr(ingest_handler.registry, "parse", lambda key, data: "   \n  ")

    result = await ingest_handler.process_ingest(
        IngestTask(task_id="t1", material_id="m1", storage_key="a.pdf"),
        chunks=FakeChunks(),
        embeddings=FakeEmbeddings(),
    )
    assert result.status == "error"
    assert "empty text" in (result.error or "")


# --------------------------------------------------------------------------
#  create_test
# --------------------------------------------------------------------------


async def test_create_test_passes_the_task_through():
    task = CreateTestTask(
        task_id="t2", test_id="te1", material_ids=["m1"], title="Основы", num_questions=7,
        difficulty="hard",
    )
    generator = FakeGenerator()

    result = await create_test_handler.process_create_test(task, generator=generator)

    assert result.status == "ok"
    assert result.test_id == "te1"
    assert result.test is not None and result.test.questions


async def test_create_test_error_names_the_test():
    class Failing:
        async def generate(self, **kwargs):
            raise ValueError("no indexed chunks for the requested materials")

    result = await create_test_handler.process_create_test(
        CreateTestTask(task_id="t2", test_id="te1", material_ids=["m1"], title="Основы"),
        generator=Failing(),
    )

    assert result.status == "error"
    assert result.test_id == "te1"  # backend должен найти строку и поставить status=failed


# --------------------------------------------------------------------------
#  grade_attempt
# --------------------------------------------------------------------------


def _questions() -> list[QuestionRow]:
    return [
        QuestionRow("q1", "Вопрос 1", "single_choice", ["верно", "неверно"], {"correct_index": 0}),
        QuestionRow("q2", "Вопрос 2", "single_choice", ["верно", "неверно"], {"correct_index": 1}),
    ]


async def test_grade_attempt_scores_and_writes_one_overall_feedback(monkeypatch):
    async def fake_fetch(test_id: str):
        return _questions()

    monkeypatch.setattr(grade_attempt_handler, "fetch_questions", fake_fetch)
    seen: list[tuple] = []

    async def fake_feedback(llm, mistakes, total):
        seen.append((mistakes, total))
        return "Ты хорошо разбираешься в основах, но путаешь транзакции."

    monkeypatch.setattr(grade_attempt_handler.feedback_service, "overall_feedback", fake_feedback)

    result = await grade_attempt_handler.process_grade_attempt(
        GradeAttemptTask(
            task_id="t3",
            attempt_id="a1",
            test_id="te1",
            answers=[StudentAnswer(question_id="q1", student_answer_index=0)],
        ),
        llm=FakeLLM(),
    )

    assert result.status == "ok"
    assert result.score_pct == 50.0
    assert result.grade == 3
    assert result.overall_feedback.startswith("Ты хорошо")

    mistakes, total = seen[0]
    assert total == 2
    assert len(mistakes) == 1
    assert mistakes[0].question_id == "q2"


async def test_grade_attempt_survives_a_broken_llm(monkeypatch):
    """Оценку нельзя потерять из-за текста фидбэка."""

    async def fake_fetch(test_id: str):
        return _questions()

    monkeypatch.setattr(grade_attempt_handler, "fetch_questions", fake_fetch)

    class BrokenLLM:
        async def chat(self, system: str, user: str) -> str:
            raise RuntimeError("провайдер умер")

    result = await grade_attempt_handler.process_grade_attempt(
        GradeAttemptTask(task_id="t3", attempt_id="a1", test_id="te1"), llm=BrokenLLM()
    )

    assert result.status == "ok"
    assert result.score_pct == 0.0
    assert result.overall_feedback == ""


async def test_grade_attempt_reports_failure_when_scoring_breaks(monkeypatch):
    async def fake_fetch(test_id: str):
        raise RuntimeError("db is down")

    monkeypatch.setattr(grade_attempt_handler, "fetch_questions", fake_fetch)

    result = await grade_attempt_handler.process_grade_attempt(
        GradeAttemptTask(task_id="t3", attempt_id="a1", test_id="te1")
    )

    assert result.status == "error"
    assert result.attempt_id == "a1"
    assert result.test_id == "te1"


# --------------------------------------------------------------------------
#  feedback
# --------------------------------------------------------------------------


async def test_feedback_skips_the_llm_when_there_are_no_mistakes():
    from app.services.feedback import NO_MISTAKES_TEXT, overall_feedback

    llm = FakeLLM()
    text = await overall_feedback(llm, [], total_questions=10)

    assert text == NO_MISTAKES_TEXT
    assert llm.calls == [], "без промахов LLM звать незачем — он начнёт выдумывать ошибки"


async def test_feedback_prompt_lists_mistakes_without_praising():
    from app.services.feedback import overall_feedback

    llm = FakeLLM(answer="Разбери изоляцию транзакций.")
    mistakes = [
        Mistake("q1", "Что такое ACID?", "Транзакция", "Атомарность", reason="перепутал понятия")
    ]

    text = await overall_feedback(llm, mistakes, total_questions=2)

    system, user = llm.calls[0]
    assert "ты" in system.lower()
    assert "Что такое ACID?" in user
    assert "Транзакция" in user and "Атомарность" in user
    assert "перепутал понятия" in user
    assert text == "Разбери изоляцию транзакций."