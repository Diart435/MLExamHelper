"""Tests for the LLM reranker — `_parse_score_array` is pure, full rerank uses mocks."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.reranker import Reranker, _parse_score_array
from app.services.vector_store import Hit


# === _parse_score_array — pure JSON / text parsing ===

def test_parse_clean_json_array():
    out = _parse_score_array("[7, 3, 9, 1]", expected_n=4)
    assert out == [7.0, 3.0, 9.0, 1.0]


def test_parse_with_markdown_fences():
    out = _parse_score_array("```json\n[7, 3, 9]\n```", expected_n=3)
    assert out == [7.0, 3.0, 9.0]


def test_parse_with_surrounding_text():
    out = _parse_score_array("Я думаю, ответ — [8, 5, 2].", expected_n=3)
    assert out == [8.0, 5.0, 2.0]


def test_parse_unparseable_returns_none():
    assert _parse_score_array("не знаю", expected_n=3) is None


def test_parse_pads_short_array_with_none():
    out = _parse_score_array("[5]", expected_n=4)
    assert out == [5.0, None, None, None]


def test_parse_truncates_long_array():
    out = _parse_score_array("[1, 2, 3, 4, 5]", expected_n=3)
    assert out == [1.0, 2.0, 3.0]


def test_parse_skips_non_numeric_tokens():
    out = _parse_score_array("[7, abc, 9]", expected_n=3)
    assert out == [7.0, None, 9.0]


def test_parse_floats():
    out = _parse_score_array("[0.5, 9.0, 7]", expected_n=3)
    assert out == [0.5, 9.0, 7.0]


# === Reranker.rerank — async, mocks LLM ===

def _make_hits(n: int) -> list[Hit]:
    # Скоринг cosine-заглушка: hits[0] самый релевантный, дальше хуже.
    return [
        Hit(f"c{i}", f"фрагмент номер {i}: текст про тему {i}", 0.95 - 0.05 * i)
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_rerank_returns_top_k_by_score():
    fake_llm = AsyncMock()
    # Highest scores — для index 5, 3, 0, 7 (т.е. ranks 5-й, 3-й, 0-й, 7-й чанки).
    fake_llm.chat = AsyncMock(return_value="[1, 1, 1, 8, 1, 9, 1, 7, 1, 1, 1]")
    r = Reranker(llm=fake_llm)
    hits = _make_hits(11)
    top = await r.rerank("вопрос", hits, top_k=4)

    assert len(top) == 4
    assert top[0].chunk_id == "c5"  # score 9
    assert top[1].chunk_id == "c3"  # score 8
    assert top[2].chunk_id == "c7"  # score 7
    assert top[3].chunk_id == "c0"  # score 1 (tied w/ others, first by python sort stable)


@pytest.mark.asyncio
async def test_rerank_skips_when_candidates_lt_top_k():
    fake_llm = AsyncMock()
    fake_llm.chat = AsyncMock(return_value="[]")  # Если вызвали — тест фейлится
    r = Reranker(llm=fake_llm)
    hits = _make_hits(3)
    top = await r.rerank("вопрос", hits, top_k=10)

    assert fake_llm.chat.await_count == 0  # Не дёргали LLM
    assert top == hits


@pytest.mark.asyncio
async def test_rerank_falls_back_on_llm_error():
    fake_llm = AsyncMock()
    fake_llm.chat = AsyncMock(side_effect=RuntimeError("rate-limited"))
    r = Reranker(llm=fake_llm)
    hits = _make_hits(10)
    top = await r.rerank("вопрос", hits, top_k=4)

    # На фоллбеке — первые top_k по cosine-порядку (c0..c3).
    assert [h.chunk_id for h in top] == ["c0", "c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_rerank_falls_back_on_unparseable_response():
    fake_llm = AsyncMock()
    fake_llm.chat = AsyncMock(return_value="это не json, sorry")
    r = Reranker(llm=fake_llm)
    hits = _make_hits(8)
    top = await r.rerank("вопрос", hits, top_k=3)

    assert [h.chunk_id for h in top] == ["c0", "c1", "c2"]
