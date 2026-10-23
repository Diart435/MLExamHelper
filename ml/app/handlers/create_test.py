"""Задача create_test: релевантные чанки → LLM → вопросы.

Backend получает готовый тест и сам пишет его в tests/test_questions.
ML ничего не сохраняет: правильные индексы и source_chunk_id уезжают
в payload, чтобы backend мог заполнить answer_key и внешний ключ.
"""

from __future__ import annotations

from loguru import logger

from app.contracts import CreateTestResult, CreateTestTask
from app.db.chunks import PgChunkStore
from app.services.embeddings import EmbeddingsClient
from app.services.test_generator import TestGenerator


async def process_create_test(
    task: CreateTestTask,
    *,
    generator: TestGenerator | None = None,
    embeddings: EmbeddingsClient | None = None,
    chunks: PgChunkStore | None = None,
) -> CreateTestResult:
    try:
        test_generator = generator or TestGenerator(
            embeddings=embeddings, chunks=chunks
        )
        test = await test_generator.generate(
            material_ids=task.material_ids,
            title=task.title,
            num_questions=task.num_questions,
            difficulty=task.difficulty,
        )
        logger.info(
            f"Generated test {task.test_id}: {len(test.questions)} question(s), "
            f"{sum(1 for q in test.questions if q.source_chunk_id)} with source chunk"
        )
        return CreateTestResult.ok(task.task_id, task.test_id, test)

    except Exception as e:  # noqa: BLE001 — наружу уходит результат, а не исключение
        logger.exception(f"Create test failed for test {task.test_id}: {e}")
        return CreateTestResult.err(task.task_id, f"{type(e).__name__}: {e}", task.test_id)