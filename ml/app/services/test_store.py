"""Read-only доступ к `test_questions` для Grader.

ML хранит chunks в своём vector_store, но `test_questions` — это backendовская
таблица, она живёт в Postgres, и при grading'е нам нужно достать оттуда
text_question / options / key_points / answer_key для каждого question_id из
attempt'а.

⚠️ Порядок вопросов задаёт backend миграцией 006: колонка `question_order`
(1..N). Без неё сортировка по `question_id` (случайный UUID) даёт произвольный
порядок. Колонки `question_order` и `answer_key` в СТАРЫХ схемах отсутствуют
(на живой стендовой БД `ml_live` их нет, на боевой появятся после миграции
backend'а). Поэтому запрос идёт списком кандидатов: пробуем самый полный,
при `UndefinedColumnError` / `UndefinedTableError` переходим к следующему.

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


# Кандидаты запроса — от самого полного к самому простому.
#
# 1) Есть и `question_order`, и `answer_key` — новая схема (миграция backend'а 006).
# 2) Есть `answer_key`, но нет `question_order` — порядок вопросов тогда
#    произвольный (сортировка по UUID), но эталон доступен.
# 3) Нет ни `question_order`, ни `answer_key` — старая схема: эталон пустой,
#    сработает Redis/LLM-страховка.
#
# Колонку `question_order` в SELECT НЕ выбираем: `QuestionRow` её не знает,
# а модель на границе БД должна остаться неизменной.
_QUERY_CANDIDATES: tuple[tuple[str, str], ...] = (
    (
        "question_order, answer_key",
        """
        SELECT question_id, type_question, text_question,
               options, key_points, answer_key
        FROM test_questions
        WHERE test_id = $1
        ORDER BY question_order, question_id
        """,
    ),
    (
        "answer_key",
        """
        SELECT question_id, type_question, text_question,
               options, key_points, answer_key
        FROM test_questions
        WHERE test_id = $1
        ORDER BY question_id
        """,
    ),
    (
        "ни question_order, ни answer_key",
        """
        SELECT question_id, type_question, text_question,
               options, key_points
        FROM test_questions
        WHERE test_id = $1
        ORDER BY question_id
        """,
    ),
)


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
        """Достать ВСЕ вопросы теста в порядке вопросов теста.

        Порядок — по `question_order` (есть в новой схеме), иначе по
        `question_id`. Эталон `answer_key` — когда колонка есть, иначе пустой
        (тогда включится Redis/LLM-страховка).
        """
        await self.connect()
        async with self._pool.acquire() as conn:
            rows = None
            last_error: BaseException | None = None
            for missing, query in _QUERY_CANDIDATES:
                try:
                    rows = await conn.fetch(query, test_id)
                    break
                except _undefined_column_errors() as e:
                    last_error = e
                    logger.warning(
                        f"TestStore: нет колонки {missing} "
                        f"({type(e).__name__}: {e}) — пробуем следующий вариант запроса"
                    )
            if rows is None:
                # Все кандидаты отпали: таблицы нет вовсе (или схема совсем
                # чужая). Это настоящая поломка БД, а не «нет эталона» —
                # пробрасываем последнюю ошибку наружу.
                raise last_error  # type: ignore[misc]
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
