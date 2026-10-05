import uuid
from dataclasses import dataclass

import numpy as np
from loguru import logger

from app.services.chunker import split_text
from app.services.embeddings import EmbeddingsClient
from app.services.llm import LLMClient
from app.services.vector_store import Hit, InMemoryVectorStore


@dataclass
class RAGAnswer:
    answer: str
    sources: list[Hit]


class RAGService:
    """Index materials and answer questions grounded in them.

    No knowledge of Redis, MinIO, HTTP, or any transport. Demo and worker
    both instantiate this class and call its methods.

    Note: in-memory state is per-process. Single-instance only for MVP.
    """

    NO_INFO_ANSWER = "В документах не нашёл информации."

    def __init__(
        self,
        embeddings: EmbeddingsClient | None = None,
        llm: LLMClient | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> None:
        self.embeddings = embeddings or EmbeddingsClient()
        self.llm = llm or LLMClient()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._store = InMemoryVectorStore()

    async def index_material(self, material_id: str | int, text: str) -> int:
        """Chunk + embed + store under given material_id. Returns chunks count."""
        mid = str(material_id)
        chunks = split_text(text, self.chunk_size, self.chunk_overlap)
        if not chunks:
            logger.warning(f"No chunks produced for material {mid}")
            return 0
        vectors = await self.embeddings.embed_batch(chunks)
        for chunk_text, vec in zip(chunks, vectors):
            chunk_id = f"{mid}:{uuid.uuid4().hex[:8]}"
            self._store.add(chunk_id, chunk_text, np.asarray(vec), mid)
        logger.info(f"Indexed {len(chunks)} chunks for material {mid}")
        return len(chunks)

    def has_material(self, material_id: str | int) -> bool:
        return self._store.has_material(str(material_id))

    def indexed_materials(self) -> set[str]:
        return self._store.materials_indexed()

    async def answer(
        self, material_id: str | int, question: str, top_k: int = 4
    ) -> RAGAnswer:
        """Embed question, find top-k chunks OF THIS MATERIAL, ask LLM."""
        mid = str(material_id)
        if not self._store.has_material(mid):
            return RAGAnswer(answer=self.NO_INFO_ANSWER, sources=[])
        q_vec = np.asarray(await self.embeddings.embed(question))
        hits = self._store.search(q_vec, top_k=top_k, material_id=mid)
        if not hits:
            return RAGAnswer(answer=self.NO_INFO_ANSWER, sources=[])
        context = "\n\n---\n\n".join(h.text for h in hits)
        prompt = (
            f"Вопрос студента: {question}\n\n"
            f"<context>\n{context}\n</context>\n\n"
            f"Ответь на вопрос студента."
        )
        answer = await self.llm.chat(prompt)
        return RAGAnswer(answer=answer, sources=hits)