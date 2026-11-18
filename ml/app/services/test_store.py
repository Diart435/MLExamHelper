"""Read-only доступ к `test_questions` для Grader.

ML хранит chunks в своём vector_store, но `test_questions` — это backendовская
таблица, она живёт в Postgres, и при grading'е нам нужно достать оттуда
text_question / options / key_points / answer_key для каждого question_id из
attempt'а.

⚠️ Колонка `answer_key` в `test_questions` есть (контракт v4.1: backend пишет
туда эталон, который ML отдал в `create-test:ml-to-be`), но в СТАРЫХ схемах её
может не быть — на живой стендовой БД `ml_live` колонки ещё нет, а на боевой
она появится после миграции backend'а. Поэтому запрос идёт с фолбэком: если
Postgres не знает колонку, повторяем запрос без неё и подставляем пустой
эталон (тогда включится Redis/LLM-страховка).

Подключаемся тем же пулом asyncpg, что и PgVectorStore. Singleton-обёртка
с lazy connect — `Grader` и `TestStore` создаются на каждый task, поэтому
проверяем, что пул уже жив, иначе делаем новый.

Форма данных проверяется Pydantic-моделями из `app/models.py`: с codec'ом
json/jsonb asyncpg отдаёт `dict`/`list`, а строка вместо объекта — ошибка
формы (`ValidationError`), а не тихая подстановка.

Зачем выделено в отдельный файл (а не запихнуто в Grader): чтобы потом
не дублировать логику fetch_questions для answer-key / grading-history.
"""
from __future__ import annotations

from loguru import logger

from app.core.db import install_json_codecs
from app.models import QuestionRow


class TestStore:
    """Читает вопросы теста из Postgres. Без состояния, без кэша — task короткоживущий."""

    __test__ = False  # не pytest-класс

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        import asyncpg  # локальный импорт — pytest с pg-выключенным не тащил драйвер
        self._pool = await asyncpg.create_pool(
            self._dsn, min_size=1, max_size=2, init=install_json_codecs,
        )
        logger.info("TestStore connected")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "TestStore":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def fetch_questions(self, test_id: str) -> list[QuestionRow]:
        """Достать ВСЕ вопросы теста в порядке question_id (≈ порядок генерации).

        Колонка `answer_key` может отсутствовать в схеме (старые БД) — тогда
        повторяем запрос без неё и оставляем эталон пустым.
        """
        await self.connect()
        async with self._pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT question_id, type_question, text_question,
                           options, key_points, answer_key
                    FROM test_questions
                    WHERE test_id = $1
                    ORDER BY question_id
                    """,
                    test_id,
                )
            except _undefined_column_errors() as e:
                logger.warning(
                    f"TestStore: колонка answer_key недоступна ({type(e).__name__}: {e}) — "
                    f"читаем вопросы без эталона, сработает Redis/LLM-страховка"
                )
                rows = await conn.fetch(
                    """
                    SELECT question_id, type_question, text_question,
                           options, key_points
                    FROM test_questions
                    WHERE test_id = $1
                    ORDER BY question_id
                    """,
                    test_id,
                )
        return [QuestionRow.model_validate(dict(r)) for r in rows]


def _undefined_column_errors() -> tuple[type[BaseException], ...]:
    """Исключения asyncpg про отсутствующую колонку/таблицу.

    asyncpg в тестах может быть не установлен — тогда ловить нечего, но и
    падать не надо: возвращаем пустой кортеж, и except просто не сработает.
    """
    try:
        import asyncpg
    except ImportError:  # pragma: no cover — asyncpg ставится в прод-образ
        return ()
    return (
        asyncpg.exceptions.UndefinedColumnError,
        asyncpg.exceptions.UndefinedTableError,
    )
