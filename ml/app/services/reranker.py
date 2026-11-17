"""Two-stage retrieval: vector store → LLM-as-judge reranker.

Зачем нужен reranker поверх cosine-similarity:
- Эмбеддинги ловят семантику, но промахиваются по точным терминам
  (фамилии, формулы, конкретные даты), по разным формулировкам одного и того же,
  и смешивают «вроде про то же» с «прямо про то».
- LLM-reranker использует всю мощь модели, чтобы понять «про что вопрос»
  и оценно отранжировать каждый чанк.

Минусы: +1 API-вызов и дополнительные токены. На маленьких материалах (4 чанка
как в нашем ломоносовском PPTX) выигрыша нет — поэтому rerank здесь только
опционален и включается отдельно.

Fallback: если LLM-вызов упал или вернул нераспарсиваемый JSON, оставляем
косинус-порядок и предупреждаем в логе.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from loguru import logger

from app.services.llm import LLMClient
from app.services.vector_store import Hit

_RERANK_PROMPT = """Ты — ассистент для оценки релевантности текстовых фрагментов вопросу.

Вопрос: {question}

Ниже дано {n} фрагментов (нумерация [0]..[{last_i}]). Оцени каждый фрагмент
по шкале 0-10: насколько он помогает ответить на вопрос (0 = бесполезен,
10 = содержит прямой ответ).

Верни ТОЛЬКО JSON-массив из {n} чисел (по одному на фрагмент, в том же порядке),
без пояснений и комментариев. Пример ответа: [7, 3, 9, 1, 5]

Фрагменты:

{chunks}
"""


@dataclass
class Reranker:
    """LLM-as-judge reranker. Stateless; takes LLM via DI."""
    llm: LLMClient | None = None

    async def rerank(
        self,
        question: str,
        candidates: list[Hit],
        top_k: int,
        *,
        max_chars_per_chunk: int = 700,
    ) -> list[Hit]:
        if not candidates:
            return []
        if len(candidates) <= top_k:
            return candidates

        llm = self.llm or LLMClient()
        brief = [
            h.text if len(h.text) <= max_chars_per_chunk
            else h.text[:max_chars_per_chunk] + "…"
            for h in candidates
        ]
        prompt = _RERANK_PROMPT.format(
            question=question,
            n=len(candidates),
            last_i=len(candidates) - 1,
            chunks="\n\n".join(f"[{i}]\n{t}" for i, t in enumerate(brief)),
        )

        try:
            raw = await llm.chat(prompt)
        except Exception as e:
            logger.warning(f"Reranker LLM call failed ({type(e).__name__}: {e}); "
                           f"falling back to cosine order")
            return candidates[:top_k]

        scores = _parse_score_array(raw, expected_n=len(candidates))
        if scores is None:
            logger.warning("Reranker returned unparseable response; "
                           "falling back to cosine order")
            return candidates[:top_k]

        scored = sorted(
            zip(candidates, scores),
            key=lambda cs: cs[1] if cs[1] is not None else -1.0,
            reverse=True,
        )
        top = scored[:top_k]
        logger.info(
            f"Reranked {len(candidates)} → {len(top)} "
            f"(top scores: {[round(s, 2) if s is not None else None for _, s in top]})"
        )
        return [c for c, _ in top]


def _parse_score_array(text: str, expected_n: int) -> list[float | None] | None:
    """Достаём JSON-массив чисел из ответа LLM. Терпимы к markdown и мусору."""
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()

    # 1) Попытка распарсить весь ответ как JSON
    arr = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            arr = parsed
    except Exception:
        pass

    # 2) Фоллбек: первый подмассив [...] в тексте (терпимы к нечисловым токенам — они станут None)
    if arr is None:
        m = re.search(r"\[[^\[\]]*\]", cleaned)
        if m:
            inner = m.group(0)
            # Пытаемся строгий парсинг. Если фейлится — идём поштучно.
            try:
                arr = json.loads(inner)
            except Exception:
                # Разделяем по запятой, чистим каждый токен, пробуем float
                raw_tokens = inner.strip().lstrip("[").rstrip("]").split(",")
                arr = []
                for tok in raw_tokens:
                    t = tok.strip().strip("\"'")
                    try:
                        arr.append(float(t))
                    except ValueError:
                        arr.append(t)  # type: ignore[arg-type]
                if not any(isinstance(x, (int, float)) for x in arr):
                    return None

    if not isinstance(arr, list):
        return None

    out: list[float | None] = []
    for x in arr[:expected_n]:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            out.append(None)
    while len(out) < expected_n:
        out.append(None)
    return out
