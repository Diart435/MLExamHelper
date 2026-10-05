from openai import AsyncOpenAI
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


class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(api_key=s.openrouter_api_key, base_url=s.base_url)
        self._model = s.llm_model

    async def chat(self, user_message: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
        )
        answer = resp.choices[0].message.content or ""
        logger.info(f"LLM responded ({len(answer)} chars)")
        return answer