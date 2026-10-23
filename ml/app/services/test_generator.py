"""Генерация теста: релевантные чанки из material_chunks → LLM → Test.

Наружу отдаём ровно то, что ждёт backend: title и вопросы с correct_index и
source_chunk_id. Поля explanation и source нужны только внутри — explanation
заставляет модель перепроверить правильный вариант, а source — это ссылка на
чанк, из которого выведен вопрос.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.contracts import Difficulty, Test, TestQuestion
from app.db.chunks import ChunkHit, PgChunkStore
from app.services.embeddings import EmbeddingsClient
from app.services.llm import LLMClient

SYSTEM_PROMPT = (
    "Ты — методист, который составляет контрольные тесты по материалам лекций. "
    "Все вопросы и варианты ответа пиши на русском языке.\n"
    "\n"
    "Правила работы с материалом:\n"
    "1. Используй ТОЛЬКО факты из блока <context>...</context>.\n"
    "2. Не придумывай термины, формулы и определения, которых нет в контексте.\n"
    "3. Каждый вопрос должен опираться на конкретный фрагмент, а не на общие знания.\n"
    "\n"
    "Формат ответа — строго один JSON-объект без пояснений вокруг:\n"
    "{\n"
    '  "title": "название теста, до 80 символов",\n'
    '  "questions": [\n'
    "    {\n"
    '      "id": 1,\n'
    '      "text": "текст вопроса",\n'
    '      "options": ["вариант A", "вариант B", "вариант C", "вариант D"],\n'
    '      "correct_index": 0,\n'
    '      "explanation": "краткое объяснение, почему верен именно этот вариант",\n'
    '      "source": 1\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "\n"
    "Требования к вопросам:\n"
    "- ровно столько вопросов, сколько указано в задании;\n"
    "- ровно 4 варианта ответа, ровно один из них верный;\n"
    "- correct_index — индекс верного варианта с нуля, диапазон 0..3;\n"
    "- варианты ответа не должны повторять друг друга или вопрос;\n"
    "- не задавай двух вопросов про одно и то же, темы не повторяются;\n"
    "- explanation обязателен, одно-два предложения;\n"
    "- source — число в квадратных скобках у блока контекста, из которого взят вопрос;\n"
    "- не добавляй полей сверх перечисленных."
)

DIFFICULTY_HINTS: dict[Difficulty, str] = {
    "easy": "вопросы на прямое перечисление фактов и определений из текста",
    "medium": "вопросы на понимание смысла, различий между понятиями и применение правила к конкретному случаю",
    "hard": "вопросы, требующие рассуждения: сравнения, вывода следствий, разбора неочевидной формулировки",
}


class TestGenerator:
    def __init__(
        self,
        llm: LLMClient | None = None,
        embeddings: EmbeddingsClient | None = None,
        chunks: PgChunkStore | None = None,
    ) -> None:
        self._llm = llm or LLMClient()
        self._embeddings = embeddings or EmbeddingsClient()
        self._chunks = chunks or PgChunkStore()

    async def generate(
        self,
        material_ids: list[str],
        title: str,
        num_questions: int,
        difficulty: Difficulty = "medium",
        context_limit: int = 12,
    ) -> Test:
        hits = await self._retrieve(material_ids, title, context_limit)
        if not hits:
            raise ValueError("no indexed chunks for the requested materials")

        numbered = build_context(hits)
        parsed = await self._llm.chat_json(SYSTEM_PROMPT, build_task(title, num_questions, difficulty, numbered))
        return _to_test(parsed, hits)

    async def _retrieve(self, material_ids: list[str], title: str, top_k: int) -> list[ChunkHit]:
        query = await self._embeddings.embed(title)
        hits = await self._chunks.search(material_ids, query, top_k)
        logger.info(f"Retrieved {len(hits)} chunks for test generation")
        return hits


def build_context(hits: list[ChunkHit]) -> str:
    """Чанки с номерами в квадратных скобках — по этим номерам LLM ссылается
    на источник вопроса, а мы потом подставляем настоящий chunk_id."""
    blocks = [f"[{i}] {hit.text}" for i, hit in enumerate(hits, start=1)]
    return "<context>\n" + "\n\n---\n\n".join(blocks) + "\n</context>"


def build_task(title: str, num_questions: int, difficulty: Difficulty, context: str) -> str:
    return (
        f"Составь тест по названию «{title}».\n"
        f"Количество вопросов: {num_questions}.\n"
        f"Сложность: {difficulty} — {DIFFICULTY_HINTS[difficulty]}.\n"
        f"\n{context}\n"
    )


def _to_test(parsed: dict[str, Any], hits: list[ChunkHit]) -> Test:
    raw_questions = parsed.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("LLM returned no questions")

    questions: list[TestQuestion] = []
    for position, raw in enumerate(raw_questions, start=1):
        question = _to_question(raw, position, hits)
        if question is None:
            continue
        questions.append(question)

    if not questions:
        raise ValueError("LLM returned no usable questions")

    dropped = len(raw_questions) - len(questions)
    if dropped:
        logger.warning(f"Dropped {dropped} malformed question(s) from LLM output")

    title = str(parsed.get("title") or "").strip() or "Тест"
    return Test(title=title, questions=questions)


def _to_question(raw: Any, position: int, hits: list[ChunkHit]) -> TestQuestion | None:
    if not isinstance(raw, dict):
        return None

    text = str(raw.get("text") or "").strip()
    options = [str(o).strip() for o in (raw.get("options") or []) if str(o).strip()]
    if not text or len(options) < 2:
        return None

    try:
        correct_index = int(raw.get("correct_index"))
    except (TypeError, ValueError):
        logger.warning(f"Question {position}: correct_index is not an integer, dropping")
        return None
    if not (0 <= correct_index < len(options)):
        logger.warning(
            f"Question {position}: correct_index {correct_index} out of range 0..{len(options) - 1}, dropping"
        )
        return None

    return TestQuestion(
        id=int(raw.get("id") or position),
        text=text,
        options=options,
        correct_index=correct_index,
        source_chunk_id=_resolve_source(raw.get("source"), hits),
    )


def _resolve_source(source: Any, hits: list[ChunkHit]) -> str | None:
    """Номер блока контекста (1-based) → настоящий chunk_id из material_chunks."""
    try:
        index = int(source)
    except (TypeError, ValueError):
        return None
    if not (1 <= index <= len(hits)):
        return None
    return hits[index - 1].chunk_id