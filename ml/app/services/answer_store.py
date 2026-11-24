"""Хранилище эталонов ответов в Redis.

Зачем оно нужно
===============
Эталон правильного ответа нужен при проверке попытки: ML должен знать, какой
вариант правильный, и какой эталонный текст у открытого вопроса.

⚠️ Контракт v4.1: эталон — прежде всего в БД (`test_questions.answer_key`),
его пишет backend из ответа `create-test:ml-to-be`. Redis — **резервная
копия**: он переживает старые тесты, у которых эталон в БД не заполнен, и
служит страховкой, пока в БД не появилась колонка.

⚠️ Redis-эталон живёт 30 суток (TTL) — это ненадёжное хранилище, поэтому он
и не основной. Источники эталона в порядке приоритета: **БД → Redis →
LLM-судья** (см. `services/grader.py`).

Ключ и формат
=============
    ключ:  ml:answers:{canonical_test_id}
    значение: JSON-объект, где ключ — порядковый номер вопроса в тесте
              (1-based), значение — эталон вопроса:

    {"1": {"type": "single_choice", "text": "...",
           "options": ["...", "..."], "answer_key": {...}},
     "2": {...}}

Внутри эталона `answer_key` — тот же словарь, что генератор отдаёт LLM:
`correct_index` / `correct_indexes` / `reference_answer` + `explanation`.

Почему test_id канонизируется
==============================
Java-backend присылает `UUID.toString()` С дефисами, а другие клиенты могут
прислать тот же UUID в hex-форме. Без канонизации запись эталона и поиск при
проверке попадали бы в разные ключи Redis: эталон молча не находился, и
проверка незаметно деградировала до LLM-судьи — уже по другой «истине», чем
та, которую сгенерировал ML. Поэтому UUID приводится к hex без дефисов, а
остальные идентификаторы используются как есть.

Почему ключ сопоставления — нормализованный текст вопроса
===========================================================
`question_id` в БД генерирует backend, и на момент генерации теста ML его не
знает. Поэтому при проверке эталон ищется по тексту вопроса: strip + схлопнуть
пробелы + lower. Это же объясняет, почему в эталоне лежит `text`.

Сопоставление по тексту — не эталон точности: опечатка в БД или правка
формулировки приводят к тому, что эталон не найден. Тогда срабатывает
страховка — LLM-судья (`services/choice_judge.py`,
`services/open_answer_judge.py`): она определяет правильный вариант сама.

TTL
===
Эталоны нужны, пока тест живёт. По умолчанию — 30 суток; если тест создают
заново (тот же `test_id`), эталоны перезаписываются.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Protocol

from loguru import logger


# Префикс ключа: `ml:answers:{test_id}`.
KEY_PREFIX = "ml:answers:"

# TTL по умолчанию: 30 суток. Тест, созданный раньше, эталон уже не нужен.
DEFAULT_TTL_SECONDS = 30 * 24 * 3600

# Разные пробелы (в т.ч. неразрывные) — в один пробел, чтобы «Вопрос ?» и
# «Вопрос?» сошлись при сопоставлении.
_WS_RE = re.compile(r"\s+")


def _canonical_id(value: str) -> str:
    """Каноническая форма id: UUID без дефисов, остальное — как есть."""
    raw = (value or "").strip()
    try:
        return uuid.UUID(raw).hex
    except (ValueError, AttributeError, TypeError):
        return raw


def answer_key_for(test_id: str) -> str:
    """Ключ Redis с эталонами теста."""
    return f"{KEY_PREFIX}{_canonical_id(test_id)}"


def normalize_question_text(text: str) -> str:
    """Нормализовать текст вопроса для сопоставления эталонов.

    strip + схлопнуть пробелы + lower. Регистр и лишние пробелы в формулировке
    не должны ломать сопоставление с эталоном.
    """
    return _WS_RE.sub(" ", (text or "").strip()).lower()


class RedisLike(Protocol):
    """Минимальный интерфейс Redis, который нужен хранилищу.

    Описан протоколом, а не конкретным классом redis.asyncio.Redis: так
    тесты подставляют заглушку без настоящего сервера.
    """

    async def set(self, name: str, value: str, ex: int | None = None) -> Any: ...

    async def get(self, name: str) -> Any: ...


class AnswerStore:
    """Эталоны ответов тестов в Redis.

    Создаётся один раз на воркер и переиспользуется: подключение к Redis уже
    есть, второй клиент не нужен.
    """

    __test__ = False  # не pytest-класс

    def __init__(self, redis: RedisLike, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def save(self, test_id: str, questions: list[Any]) -> int:
        """Сохранить эталоны вопросов теста. Возвращает число сохранённых вопросов.

        `questions` — список `app.contracts.TestQuestion`. В эталон уходит всё,
        что нужно для проверки: тип, текст вопроса (по нему ищем эталон),
        варианты и `answer_key`.
        """
        payload: dict[str, Any] = {}
        for i, q in enumerate(questions, start=1):
            payload[str(i)] = {
                "type": getattr(q, "type_question", None),
                "text": getattr(q, "text", ""),
                "options": list(getattr(q, "options", []) or []),
                "answer_key": dict(getattr(q, "answer_key", {}) or {}),
            }
        if not payload:
            logger.warning(f"AnswerStore: test {test_id} без вопросов — эталон не сохранён")
            return 0
        await self._redis.set(
            answer_key_for(test_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._ttl,
        )
        logger.info(f"AnswerStore: сохранено {len(payload)} эталонов для теста {test_id}")
        return len(payload)

    async def load(self, test_id: str) -> dict[str, Any]:
        """Прочитать эталоны теста. Пустой словарь — эталонов нет.

        Пусто бывает в двух случаях: тест сгенерирован до появления хранилища
        либо Redis очистился. Оба — повод включить LLM-судью как страховку.
        """
        raw = await self._redis.get(answer_key_for(test_id))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(f"AnswerStore: эталон теста {test_id} — не JSON, игнорируем")
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    async def find_by_text(self, test_id: str, question_text: str) -> dict[str, Any] | None:
        """Найти эталон вопроса по нормализованному тексту.

        None — эталон не найден (нужен LLM-судья).
        """
        target = normalize_question_text(question_text)
        if not target:
            return None
        for ref in (await self.load(test_id)).values():
            if not isinstance(ref, dict):
                continue
            if normalize_question_text(str(ref.get("text") or "")) == target:
                return ref
        return None
