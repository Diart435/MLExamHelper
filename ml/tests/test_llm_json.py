"""Тесты LLMClient: json_schema, деградация формата, терпимый парсинг.

Зачем эти тесты: на свободном json_object модель отдаёт `{}`, дублирует ключи
в одном объекте и обрывает ответ по лимиту токенов. Схема (`json_schema`)
убирает эти поломки, но провайдер может её не поддержать — тогда клиент обязан
ослабить требования (json_schema → json_object → свободный текст), а не упасть.
"""

from __future__ import annotations

import json

import httpx
import pytest
from openai import BadRequestError

from app.services.llm import (
    LLMClient,
    _loads_lenient,
    _merge_pairs,
)


def _bad_request() -> BadRequestError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError("response_format is not supported", response=response, body=None)


def _make_llm(responses) -> LLMClient:
    """LLMClient без сети: `_chat_once_raw` отдаёт заранее заданные ответы.

    responses — список: строка (контент) либо исключение (которое нужно бросить).
    """
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    llm._client = None
    llm.requests = []  # type: ignore[attr-defined]
    it = iter(responses)

    async def fake_raw(system_prompt, user_message, *, fmt="plain", schema=None):
        llm.requests.append({"fmt": fmt, "schema": schema, "system": system_prompt})
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    llm._chat_once_raw = fake_raw  # type: ignore[method-assign]
    return llm


# ============================================================================
# Терпимый парсинг
# ============================================================================

class TestLenientParse:
    def test_plain_json(self):
        assert _loads_lenient('{"a": 1}') == {"a": 1}

    def test_duplicate_key_last_wins(self):
        # Обычное переопределение: второе вхождение побеждает.
        assert _loads_lenient('{"a": 1, "a": 2}') == {"a": 2}

    def test_duplicate_object_key_merges_without_data_loss(self):
        # Наблюдалось на реальном ответе LLM: key_points с criteria и без.
        raw = (
            '{"key_points": {"points": 1, "explanation": "пояснение", "criteria": ["a", "b"]},'
            ' "key_points": {"points": 1, "explanation": "пояснение"}}'
        )
        data = _loads_lenient(raw)
        assert data["key_points"]["criteria"] == ["a", "b"]
        assert data["key_points"]["points"] == 1

    def test_merge_pairs_keeps_unique_keys(self):
        merged = _merge_pairs([("a", {"x": 1}), ("a", {"y": 2})])
        assert merged == {"a": {"x": 1, "y": 2}}

    def test_merge_pairs_non_dict_overrides(self):
        merged = _merge_pairs([("a", {"x": 1}), ("a", 5)])
        assert merged == {"a": 5}


# ============================================================================
# Формат ответа
# ============================================================================

class TestChatJsonFormat:
    @pytest.mark.asyncio
    async def test_schema_is_used_as_json_schema_response_format(self):
        llm = _make_llm([json.dumps({"ok": True})])
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        await llm.chat_json("вопрос", validator=lambda d: d, schema=schema)
        assert llm.requests[0]["fmt"] == "json_schema"
        assert llm.requests[0]["schema"] == schema

    @pytest.mark.asyncio
    async def test_without_schema_uses_json_object(self):
        llm = _make_llm([json.dumps({"ok": True})])
        await llm.chat_json("вопрос", validator=lambda d: d)
        assert llm.requests[0]["fmt"] == "json_object"

    @pytest.mark.asyncio
    async def test_degrades_to_json_object_when_schema_unsupported(self):
        from app.services.llm import _UnsupportedResponseFormat

        llm = _make_llm([_UnsupportedResponseFormat("400"), json.dumps({"ok": True})])
        result = await llm.chat_json("вопрос", validator=lambda d: d, schema={"type": "object"})
        assert result == {"ok": True}
        assert [r["fmt"] for r in llm.requests] == ["json_schema", "json_object"]

    @pytest.mark.asyncio
    async def test_degrades_down_to_plain_text(self):
        from app.services.llm import _UnsupportedResponseFormat

        llm = _make_llm([
            _UnsupportedResponseFormat("400"),
            _UnsupportedResponseFormat("400"),
            json.dumps({"ok": True}),
        ])
        result = await llm.chat_json(
            "вопрос", validator=lambda d: d, schema={"type": "object"}, max_retries=3
        )
        assert result == {"ok": True}
        assert [r["fmt"] for r in llm.requests] == ["json_schema", "json_object", "plain"]

    @pytest.mark.asyncio
    async def test_duplicate_keys_do_not_break_the_call(self):
        # Ответ LLM с дублем key_points обязан распарситься, а не отброситься.
        raw = (
            '{"title": "t", "questions": [],'
            ' "key_points": {"points": 1, "criteria": ["x"]},'
            ' "key_points": {"points": 1}}'
        )
        llm = _make_llm([raw])
        result = await llm.chat_json("вопрос", validator=lambda d: d)
        assert result["key_points"]["criteria"] == ["x"]

    @pytest.mark.asyncio
    async def test_retry_after_parse_failure(self):
        llm = _make_llm(["не json", json.dumps({"ok": True})])
        result = await llm.chat_json("вопрос", validator=lambda d: d, max_retries=2)
        assert result == {"ok": True}
        assert len(llm.requests) == 2


# ============================================================================
# Ошибки провайдера
# ============================================================================

class TestBadRequestMapping:
    @pytest.mark.asyncio
    async def test_bad_request_is_not_transient(self):
        from app.services.llm import _UnsupportedResponseFormat

        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"

        async def raising(**kwargs):
            raise _bad_request()

        llm._client = type("C", (), {})()
        llm._client.chat = type("Ch", (), {})()
        llm._client.chat.completions = type("Comp", (), {"create": staticmethod(raising)})()

        with pytest.raises(_UnsupportedResponseFormat):
            await llm._chat_once_raw("sys", "user", fmt="json_schema", schema={"type": "object"})

    @pytest.mark.asyncio
    async def test_network_error_is_transient(self):
        from app.services.llm import _TransientLLMError

        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"

        async def raising(**kwargs):
            raise RuntimeError("connection reset")

        llm._client = type("C", (), {})()
        llm._client.chat = type("Ch", (), {})()
        llm._client.chat.completions = type("Comp", (), {"create": staticmethod(raising)})()

        with pytest.raises(_TransientLLMError):
            await llm._chat_once_raw("sys", "user", fmt="plain")
