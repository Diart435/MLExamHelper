"""Обёртка над OpenRouter-совместимым chat API.

Один клиент на всё: генерация теста и общий фидбэк. Системный промпт
передаёт вызывающий код — здесь нет промпта «по умолчанию», потому что
задачи разные и общий промпт только мешал бы.

Backend никогда не видит сырой вывод LLM: наружу уходит либо разобранный
dict, либо текст. Если модель ответила мусором — клиент сам повторяет попытку
и только затем поднимает LLMError.
"""

from __future__ import annotations

import asyncio
import json

from loguru import logger
from openai import AsyncOpenAI

from app.core.config import get_settings

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 2.0


class LLMError(RuntimeError):
    """Модель не ответила или ответила непригодным для разбора текстом."""


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(api_key=s.openrouter_api_key, base_url=s.base_url)
        self._model = s.llm_model

    async def _complete(
        self, system: str, user: str, json_mode: bool
    ) -> str | None:
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            **kwargs,
        )
        return resp.choices[0].message.content

    async def chat(self, system: str, user: str) -> str:
        """Обычный текстовый ответ с повторами на сетевых сбоях."""
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                answer = await self._complete(system, user, json_mode=False)
            except Exception as e:  # noqa: BLE001 — сеть и провайдер любят кидать что угодно
                last = e
                logger.warning(f"LLM attempt {attempt}/{MAX_ATTEMPTS} failed: {type(e).__name__}: {e}")
            else:
                if answer and answer.strip():
                    logger.info(f"LLM responded ({len(answer)} chars)")
                    return answer
                last = LLMError("empty response")
                logger.warning(f"LLM attempt {attempt}/{MAX_ATTEMPTS} returned empty content")

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE_S * attempt)

        raise LLMError(f"LLM failed after {MAX_ATTEMPTS} attempts: {last}") from last

    async def chat_json(self, system: str, user: str) -> dict:
        """Ответ строго JSON-объектом. Модели, которые оборачивают JSON в
        ```-блок, разворачиваем — иначе такая модель молча ломает разбор."""
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # JSON-режим просим только с первой попытки: модель, которая его
            # не поддерживает, со второй попытки получит обычный текст.
            try:
                raw = await self._complete(system, user, json_mode=attempt == 1)
                if not raw or not raw.strip():
                    raise LLMError("empty response")
                parsed = json.loads(_strip_fences(raw))
                if not isinstance(parsed, dict):
                    raise LLMError(f"expected JSON object, got {type(parsed).__name__}")
                logger.info(f"LLM returned JSON ({len(parsed)} keys)")
                return parsed
            except Exception as e:  # noqa: BLE001 — сюда приходит и LLMError, и ошибки провайдера
                last = e
                logger.warning(
                    f"LLM JSON attempt {attempt}/{MAX_ATTEMPTS} failed: {type(e).__name__}: {e}"
                )
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(BACKOFF_BASE_S * attempt)

        raise LLMError(f"LLM returned unusable JSON after {MAX_ATTEMPTS} attempts: {last}") from last


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()