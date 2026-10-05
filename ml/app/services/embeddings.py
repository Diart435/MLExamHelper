from openai import AsyncOpenAI
from loguru import logger

from app.core.config import get_settings


class EmbeddingsClient:
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncOpenAI(api_key=s.openrouter_api_key, base_url=s.base_url)
        self._model = s.embed_model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        logger.info(f"Embedded {len(texts)} texts via {self._model}")
        return [d.embedding for d in resp.data]