import asyncio
import json
import re
from typing import Any, Awaitable, Callable

from openai import APIStatusError
from openai import AsyncOpenAI
from openai import BadRequestError
from loguru import logger

from app.core.config import get_settings

SYSTEM_PROMPT = (
    "Ты — ассистент для студентов, отвечающий ТОЛЬКО на основе предоставленного контекста из лекции. "
    "Правила:\n"
    "1. Отвечай ТОЛЬКО на основе текста между <context> и </context>.\n"
    "2. Если в контексте нет ответа — напиши ровно: 'В документах не нашёл информации.'\n"
    "3. Не придумывай факты, которых нет в контексте.\n"
    "4. Не упоминай 'контекст' или 'документы' в ответе — пиши как будто знаешь материал."
)

# Жёсткий лимит на размер ответа.
# Free-модели на OpenRouter имеют per-request кредит — дефолтные 131 072 токена
# (полный max модели) превышают этот лимит. 1024 — заведомо достаточно для
# grounded RAG-ответа (≈ 4 КБ текста по-русски).
MAX_TOKENS = 1024

# Лимит побольше для генерации тестов. Замерено на deepseek/deepseek-v4.1-flash:
# 30 вопросов с открытыми ответами — ~8 900 токенов. Старые 4096 не хватало:
# ответ обрывался по finish_reason=length, и content приходил пустым (null),
# то есть задача падала без внятной причины.
MAX_TOKENS_JSON = 16384

# Бюджет для маленьких JSON-ответов (судьи: {score, feedback}, {correct_indexes, explanation}).
# Отдельный от MAX_TOKENS_JSON по измерению: OpenRouter для free-моделей сверяет
# запрошенный max_tokens с остатком кредита на запрос — при max_tokens=16384
# приходил HTTP 402 («can only afford 4415»), а 1024 проходит. Генератору тестов
# нужен большой бюджет, судье — маленький.
MAX_TOKENS_SMALL_JSON = 1024

# Ретрай. Free-модели OpenRouter периодически отвечают пустым content или
# choices=None (rate-limit, перегрев провайдера и т.п.) — это транзиентно,
# поэтому пробуем ещё пару раз перед тем как сдаваться.
_MAX_RETRIES = 3
_RETRY_BACKOFF_SEC = (1.0, 2.0, 4.0)

# Формат ответа деградирует, если провайдер его не поддерживает:
# json_schema → json_object → свободный текст.
_FORMAT_DEGRADE = {"json_schema": "json_object", "json_object": "plain"}


def _summarize_error(raw: str, limit: int = 200) -> str:
    """OpenRouter при ошибке отдаёт портянку JSON. Сокращаем до сути."""
    s = raw.strip()
    if len(s) <= limit:
        return s
    return s[:limit] + f"... [+{len(s) - limit} chars]"


class _TransientLLMError(RuntimeError):
    """Транзиентная ошибка LLM: пустой ответ, choices=None, сетевой сбой.
    Имеет смысл ретраить — в отличие от неверного API-ключа или 4xx от клиента.
    """


class _UnsupportedResponseFormat(RuntimeError):
    """Провайдер отверг выбранный формат ответа (например, json_schema).

    Не транзиентно: повторять тот же формат бессмысленно — надо ослабить
    требования (json_schema → json_object → свободный текст).
    """


class _LLMCreditError(RuntimeError):
    """Провайдер вернул HTTP 402 (Payment Required) — не хватило кредита.

    Не транзиентно: тот же запрос повторять бессмысленно, кредит сам не
    появится. Раньше 402 уезжал в _TransientLLMError, цикл ретраил его
    три раза и писал в лог «transient» — а это не сетевой сбой.
    """


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(api_key=s.openrouter_api_key, base_url=s.base_url)
        self._model = s.llm_model

    async def chat(self, user_message: str, system_prompt: str | None = None) -> str:
        """Один вызов LLM с ретраями на транзиентные ошибки.

        `system_prompt` переопределяет модульный SYSTEM_PROMPT (тот заточен под
        grounded-RAG). Нужен там, где системная роль другая: разбор попытки,
        оценка открытого ответа.

        На выходе — текст ответа или RuntimeError после исчерпания попыток.
        Пустой content / choices=None / сетевые сбои считаются тривиальными
        и ретраятся; всё остальное пробрасывается сразу.
        """
        last_err: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await self._chat_once(user_message, system_prompt)
            except _TransientLLMError as e:
                last_err = e
                if attempt >= _MAX_RETRIES:
                    break
                delay = _RETRY_BACKOFF_SEC[attempt - 1]
                logger.warning(
                    f"LLM transient (attempt {attempt}/{_MAX_RETRIES}): "
                    f"{e}. Retry in {delay}s"
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"LLM не ответил после {_MAX_RETRIES} попыток "
            f"(model={self._model}): {last_err}"
        )

    async def chat_json(
        self,
        user_message: str,
        *,
        validator: Callable[[dict], Any],
        system_prompt: str | None = None,
        max_retries: int = 3,
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> Any:
        """JSON-вызов LLM: парсит ответ, прогоняет через `validator(data)`.

        Поведение:
          - Если передан `schema` — просим у провайдера constrained decoding
            (`response_format={"type": "json_schema"}`): модель физически не
            может вернуть мусор вроде `{}`, дублей ключей или обрезанного JSON.
            Если провайдер такой формат не поддерживает — откатываемся на
            `json_object`, потом на свободный текст.
          - Если LLM вернул текст с преамбулой или обёрнутый в ```json ... ``` —
            вытаскиваем JSON через `_extract_json_block`.
          - Парсинг или валидация упали → retry с ужесточённым system prompt
            ("верни ТОЛЬКО валидный JSON, без пояснений").
          - Возвращает результат `validator(data)`.

        `max_tokens` — бюджет ответа. None → дефолт по формату (MAX_TOKENS_JSON
        для json). Маленькие ответы (судьи) стоит просить явно: OpenRouter
        сверяет запрошенный max_tokens с остатком кредита, и большой бюджет
        упирается в HTTP 402.

        Raises:
            RuntimeError: после исчерпания попыток (parse/validate/transient).
            _LLMCreditError: провайдер вернул 402 — ретраить бессмысленно,
                исключение вылетает сразу.
        """
        last_err: Exception | None = None
        fmt = "json_schema" if schema is not None else "json_object"
        for attempt in range(1, max_retries + 1):
            sys_prompt = (system_prompt or "Ты формируешь структурированный ответ строго в JSON.")
            if attempt > 1:
                sys_prompt += (
                    "\n\nВАЖНО: предыдущий ответ был невалидным. "
                    "Верни ТОЛЬКО один валидный JSON-объект без пояснений до/после."
                )

            try:
                content = await self._chat_once_raw(
                    sys_prompt, user_message, fmt=fmt, schema=schema, max_tokens=max_tokens
                )
            except _UnsupportedResponseFormat as e:
                logger.info(f"chat_json: формат {fmt} не поддержан ({e}), ослабляем требования")
                fmt = _FORMAT_DEGRADE.get(fmt, "plain")
                continue
            except _TransientLLMError as e:
                last_err = e
                logger.warning(
                    f"chat_json transient (attempt {attempt}/{max_retries}): {e}"
                )
                await asyncio.sleep(_RETRY_BACKOFF_SEC[min(attempt - 1, 2)])
                continue

            json_text = _extract_json_block(content)
            try:
                data = _loads_lenient(json_text)
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning(
                    f"chat_json: JSON parse failed (attempt {attempt}/{max_retries}): {e}"
                )
                continue

            try:
                return validator(data)
            except (ValueError, KeyError, TypeError) as e:
                last_err = e
                logger.warning(
                    f"chat_json: validator rejected (attempt {attempt}/{max_retries}): {e}"
                )
                continue

        raise RuntimeError(
            f"chat_json failed after {max_retries} attempts (model={self._model}): {last_err}"
        )

    async def _chat_once(self, user_message: str, system_prompt: str | None = None) -> str:
        content = await self._chat_once_raw(
            system_prompt or SYSTEM_PROMPT, user_message, fmt="plain"
        )
        return content

    async def _chat_once_raw(
        self,
        system_prompt: str,
        user_message: str,
        *,
        fmt: str = "plain",
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Один сырой вызов.

        fmt: "plain" — свободный текст; "json_object" — любой JSON-объект;
        "json_schema" — JSON, соответствующий `schema` (constrained decoding).

        max_tokens: None → дефолт по формату (MAX_TOKENS для plain,
        MAX_TOKENS_JSON для json). Явно заданное значение важно для судьей:
        OpenRouter сверяет max_tokens с остатком кредита и на большом бюджете
        отдаёт 402.

        Бросает _UnsupportedResponseFormat, если провайдер отверг формат ответа,
        _LLMCreditError на 402 и _TransientLLMError на остальных сбоях.
        """
        if max_tokens is None:
            max_tokens = MAX_TOKENS if fmt == "plain" else MAX_TOKENS_JSON
        kwargs: dict[str, Any] = dict(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        if fmt == "json_schema" and schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema},
            }
        elif fmt == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            # 400 — провайдер не понял запрос. Чаще всего это неподдерживаемый
            # формат ответа, а не «неверный ключ»: разбираемся пониже уровнем.
            # Важно: BadRequestError — подкласс APIStatusError, поэтому эта
            # ветка должна стоять ПЕРЕД общей веткой APIStatusError.
            raise _UnsupportedResponseFormat(f"{type(e).__name__}: {e}") from e
        except APIStatusError as e:
            # 402 — не хватило кредита (в openai SDK нет PaymentRequiredError,
            # поэтому сверяем status_code). Это не сетевой сбой: повторять
            # тот же запрос бессмысленно, ретрай-цикл его не ловит.
            if getattr(e, "status_code", None) == 402:
                raise _LLMCreditError(f"{type(e).__name__}: {e}") from e
            raise _TransientLLMError(f"{type(e).__name__}: {e}") from e
        except Exception as e:
            raise _TransientLLMError(f"{type(e).__name__}: {e}") from e

        if not resp.choices:
            raise _TransientLLMError(
                f"choices пуст (model={self._model}): "
                f"{_summarize_error(_safe_dump(resp))}"
            )

        content = (resp.choices[0].message.content or "").strip()
        if not content:
            raise _TransientLLMError(
                f"пустой content (model={self._model}): "
                f"{_summarize_error(_safe_dump(resp))}"
            )
        return content


def _extract_json_block(s: str) -> str:
    """Достать JSON-объект из ответа LLM.

    LLM любит оборачивать ответ в ```json ... ``` или писать пояснения
    до/после. Эта функция вытаскивает:
      1) ```json { ... } ``` или ``` { ... } ``` (если есть)
      2) иначе — первый `{` ... последний `}` (если оба есть)
      3) иначе — как есть
    """
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if m:
        return m.group(1)
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start:end + 1]
    return s


def _merge_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Слить объект, в котором один и тот же ключ встретился дважды.

    Приоритет у второго вхождения (как при обычном переопределении), но ключи,
    которых во втором нет, сохраняются: {"a":{"x":1}} + {"a":{"y":2}} →
    {"a":{"x":1,"y":2}}.
    """
    merged: dict[str, Any] = {}
    for key, value in pairs:
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _loads_lenient(text: str) -> Any:
    """json.loads, терпимый к дублирующимся ключам.

    LLM на свободном json_object иногда отдаёт один и тот же ключ дважды —
    например "answer_key" с explanation и без. Строгий JSON такое отвергает, а
    терять данные нельзя, поэтому дубли сливаются, а не роняют ответ.
    """
    return json.loads(text, object_pairs_hook=_merge_pairs)


def _safe_dump(resp) -> str:
    """model_dump_json() иногда падает на экзотике — fallback на str()."""
    try:
        return resp.model_dump_json()
    except Exception:
        return str(resp)