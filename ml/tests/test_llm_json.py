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
from openai import APIStatusError
from openai import BadRequestError

from app.services.llm import (
    MAX_TOKENS,
    MAX_TOKENS_JSON,
    MAX_TOKENS_SMALL_JSON,
    LLMClient,
    _loads_lenient,
    _merge_pairs,
)


def _bad_request() -> BadRequestError:
    request = httpx.Request("POST", "https://llm.test/api/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError("response_format is not supported", response=response, body=None)


def _payment_required() -> APIStatusError:
    """HTTP 402 от провайдера: не хватило кредита на запрос."""
    request = httpx.Request("POST", "https://llm.test/api/v1/chat/completions")
    response = httpx.Response(402, request=request)
    return APIStatusError(
        "This request requires more credits, or fewer max_tokens.",
        response=response,
        body=None,
    )


def _make_llm(responses) -> LLMClient:
    """LLMClient без сети: `_chat_once_raw` отдаёт заранее заданные ответы.

    responses — список: строка (контент) либо исключение (которое нужно бросить).
    """
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    llm._client = None
    llm.requests = []  # type: ignore[attr-defined]
    it = iter(responses)

    async def fake_raw(system_prompt, user_message, *, fmt="plain", schema=None, max_tokens=None, attempt=""):
        llm.requests.append({
            "fmt": fmt, "schema": schema, "system": system_prompt,
            "max_tokens": max_tokens,
        })
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


# ============================================================================
# Бюджет токенов
# ============================================================================

class TestMaxTokensBudget:
    """Бюджет ответа — по измерению, а не «всем одинаково».

    Провайдер (RouterAI) для free-моделей сверяет запрошенный max_tokens с
    остатком кредита: при 16384 приходил HTTP 402 («can only afford 4415»),
    а 1024 проходит. Поэтому судьи просят маленький бюджет явно."""

    @pytest.mark.asyncio
    async def test_explicit_max_tokens_is_passed_through(self):
        llm = _make_llm([json.dumps({"ok": True})])
        await llm.chat_json(
            "вопрос", validator=lambda d: d, schema={"type": "object"},
            max_tokens=MAX_TOKENS_SMALL_JSON,
        )
        assert llm.requests[0]["max_tokens"] == MAX_TOKENS_SMALL_JSON

    @pytest.mark.asyncio
    async def test_default_budget_for_json_format(self):
        """Без явного max_tokens поведение прежнее: json-формат — большой бюджет."""
        llm = _make_llm([json.dumps({"ok": True})])
        await llm.chat_json("вопрос", validator=lambda d: d)
        assert llm.requests[0]["max_tokens"] is None

        # Дефолт по формату считается в _chat_once_raw — проверяем там.
        sent = await _capture_kwargs(fmt="json_object")
        assert sent["max_tokens"] == MAX_TOKENS_JSON

    @pytest.mark.asyncio
    async def test_default_budget_for_plain_format(self):
        sent = await _capture_kwargs(fmt="plain")
        assert sent["max_tokens"] == MAX_TOKENS

    @pytest.mark.asyncio
    async def test_explicit_max_tokens_overrides_format_default(self):
        sent = await _capture_kwargs(fmt="json_object", max_tokens=MAX_TOKENS_SMALL_JSON)
        assert sent["max_tokens"] == MAX_TOKENS_SMALL_JSON


async def _capture_kwargs(*, fmt: str, max_tokens: int | None = None) -> dict:
    """Что реально уходит в провайдера: kwargs вызова completions.create."""
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    captured: dict = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    llm._client = type("C", (), {})()
    llm._client.chat = type("Ch", (), {})()
    llm._client.chat.completions = type("Comp", (), {"create": staticmethod(create)})()

    await llm._chat_once_raw("sys", "user", fmt=fmt, max_tokens=max_tokens)
    return captured


def _fake_response():
    """Минимальный ответ провайдера: одно сообщение с непустым content."""
    class _Msg:
        content = '{"ok": true}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    return _Resp()


# ============================================================================
# 402 — нет кредита: не ретраится
# ============================================================================

class TestPaymentRequired:
    """HTTP 402 (Payment Required) — не транзиентная ошибка.

    Раньше 402 уезжал в _TransientLLMError: цикл ретраил его три раза, тратил
    время и писал в лог «transient», хотя это «нет кредитов», а не сетевой
    сбой. Теперь ошибка вылетает сразу."""

    @pytest.mark.asyncio
    async def test_402_is_mapped_to_credit_error(self):
        from app.services.llm import _LLMCreditError

        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"

        async def raising(**kwargs):
            raise _payment_required()

        llm._client = type("C", (), {})()
        llm._client.chat = type("Ch", (), {})()
        llm._client.chat.completions = type("Comp", (), {"create": staticmethod(raising)})()

        with pytest.raises(_LLMCreditError):
            await llm._chat_once_raw("sys", "user", fmt="json_object")

    @pytest.mark.asyncio
    async def test_402_is_not_retried_by_chat_json(self):
        """Ровно один вызов: исключение вылетает наружу, ретрая нет."""
        from app.services.llm import _LLMCreditError

        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"
        calls: list[dict] = []

        async def create(**kwargs):
            calls.append(kwargs)
            raise _payment_required()

        llm._client = type("C", (), {})()
        llm._client.chat = type("Ch", (), {})()
        llm._client.chat.completions = type("Comp", (), {"create": staticmethod(create)})()

        with pytest.raises(_LLMCreditError):
            await llm.chat_json(
                "вопрос", validator=lambda d: d, schema={"type": "object"}, max_retries=3,
            )
        assert len(calls) == 1, "402 не должен ретраиться"

    @pytest.mark.asyncio
    async def test_other_api_status_error_is_still_transient(self):
        """Остальные APIStatusError (500 и т.п.) — по-прежнему транзиентные."""
        from app.services.llm import _TransientLLMError

        request = httpx.Request("POST", "https://llm.test/api/v1/chat/completions")
        response = httpx.Response(500, request=request)
        err = APIStatusError("upstream boom", response=response, body=None)

        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"

        async def raising(**kwargs):
            raise err

        llm._client = type("C", (), {})()
        llm._client.chat = type("Ch", (), {})()
        llm._client.chat.completions = type("Comp", (), {"create": staticmethod(raising)})()

        with pytest.raises(_TransientLLMError):
            await llm._chat_once_raw("sys", "user", fmt="plain")


# ============================================================================
# Судьи просят маленький бюджет
# ============================================================================

class TestJudgesSmallBudget:
    """Судьи отдают 100–200 токенов — большой бюджет им не нужен, а на
    free-моделях он упирается в HTTP 402."""

    @pytest.mark.asyncio
    async def test_open_answer_judge_uses_small_budget(self):
        from app.services.open_answer_judge import OpenAnswerJudge

        class FakeLLM:
            def __init__(self):
                self.calls: list[dict] = []

            async def chat_json(self, user_message, *, validator, system_prompt=None,
                                max_retries=3, schema=None, max_tokens=None):
                self.calls.append({"max_tokens": max_tokens})
                return validator({"score": 1.0, "feedback": "верно"})

        llm = FakeLLM()
        judge = OpenAnswerJudge(llm=llm)
        await judge.judge(
            question="q", reference_answer="r", criteria=["пункт"], student_answer="a",
        )
        assert llm.calls[0]["max_tokens"] == MAX_TOKENS_SMALL_JSON

    @pytest.mark.asyncio
    async def test_choice_judge_uses_small_budget(self):
        from app.services.choice_judge import ChoiceJudge

        class FakeLLM:
            def __init__(self):
                self.calls: list[dict] = []

            async def chat_json(self, user_message, *, validator, system_prompt=None,
                                max_retries=3, schema=None, max_tokens=None):
                self.calls.append({"max_tokens": max_tokens})
                return validator({"correct_indexes": [0], "explanation": "потому что A"})

        llm = FakeLLM()
        judge = ChoiceJudge(llm=llm)
        await judge.judge(question="q", options=["A", "B"])
        assert llm.calls[0]["max_tokens"] == MAX_TOKENS_SMALL_JSON
