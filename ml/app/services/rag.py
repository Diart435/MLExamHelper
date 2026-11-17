import uuid
from dataclasses import dataclass

import numpy as np
from loguru import logger

from app.services.chunker import split_text
from app.services.embeddings import EmbeddingsClient
from app.services.llm import LLMClient
from app.services.reranker import Reranker
from app.services.vector_store import (
    Hit,
    InMemoryVectorStore,
    VectorStore,
    create_vector_store,
    normalize_chunk_id,
)


@dataclass
class RAGAnswer:
    answer: str
    sources: list[Hit]


@dataclass
class ChunkRef:
    """Чанк материала в контексте генерации теста.

    `ref` — короткая метка («C7»), которую LLM копирует в `source_chunk_ref`;
    `chunk_id` — настоящий идентификатор чанка (UUID из `material_chunks`),
    который backend запишет в `test_questions.source_chunk_id`.

    Метка нужна потому, что модель не выдумывает UUID: в JSON Schema метка
    задаётся enum'ом реальных меток, поэтому вопрос не может сослаться на
    несуществующий чанк.
    """

    __test__ = False  # не pytest-класс
    ref: str
    chunk_id: str
    text: str


class RAGService:
    """Index materials and answer questions grounded in them.

    No knowledge of Redis, MinIO, HTTP, or any transport. Demo and worker
    both instantiate this class and call its methods.

    Vector store backend (in-memory vs pgvector) выбирается в `__init__` через
    `create_vector_store()` либо пробрасывается явно (для тестов).
    """

    NO_INFO_ANSWER = "В документах не нашёл информации."

    def __init__(
        self,
        embeddings: EmbeddingsClient | None = None,
        llm: LLMClient | None = None,
        reranker: Reranker | None = None,
        store: VectorStore | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> None:
        # NB: используем `is not None`, а не `store or ...`. VectorStore
        # определяет __len__, и пустой InMemoryVectorStore делает `bool(store)
        # == False` — `or` тогда отбросил бы его и подсунул create_vector_store().
        self.embeddings = embeddings if embeddings is not None else EmbeddingsClient()
        self.llm = llm if llm is not None else LLMClient()
        self.reranker = reranker if reranker is not None else Reranker(llm=self.llm)
        self._store: VectorStore = store if store is not None else create_vector_store()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

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
            await self._store.add(chunk_id, chunk_text, np.asarray(vec), mid)
        logger.info(f"Indexed {len(chunks)} chunks for material {mid}")
        return len(chunks)

    async def has_material(self, material_id: str | int) -> bool:
        return await self._store.has_material(str(material_id))

    async def indexed_materials(self) -> set[str]:
        return await self._store.materials_indexed()

    async def context_for_materials(
        self,
        material_ids: list[str | int],
        max_chunks_total: int = 60,
    ) -> list[tuple[str, list[ChunkRef]]]:
        """Собрать контекст по списку материалов для генерации теста.

        Возвращает список кортежей (material_id, [ChunkRef]) в исходном
        порядке. Чанки берутся в порядке chunk_id (≈ порядок появления в
        исходном документе). Per-material лимит распределяется равномерно
        (max_chunks_total // N), минимум 2 чанка на материал.

        Метки (`C1`, `C2`, …) сквозные на весь контекст, не на материал: в
        дайджесте они однозначно указывают на чанк, и вопрос ссылается ровно
        на один из них.

        Пропускает материалы, которые не проиндексированы — вызывающий код
        решает, что с этим делать.
        """
        ids = [str(m) for m in material_ids]
        if not ids:
            return []
        per_mat = max(2, max_chunks_total // max(1, len(ids)))
        out: list[tuple[str, list[ChunkRef]]] = []
        counter = 0
        for mid in ids:
            hits = await self._store.get_chunks(mid, limit=per_mat)
            if not hits:
                continue
            chunks: list[ChunkRef] = []
            for h in hits:
                counter += 1
                chunks.append(ChunkRef(
                    ref=f"C{counter}",
                    chunk_id=normalize_chunk_id(h.chunk_id),
                    text=h.text,
                ))
            out.append((mid, chunks))
        return out

    async def answer(
        self,
        material_id: str | int,
        question: str,
        top_k: int = 4,
        retrieve_n: int | None = None,
        rerank: bool = False,
    ) -> RAGAnswer:
        """Two-stage retrieval: vector store → optional reranker → LLM.

        1. Берём `retrieve_n` (по умолчанию `top_k`) ближайших чанков по cosine.
        2. Если `retrieve_n > top_k` И `rerank=True`, прогоняем кандидатов через
           LLM-reranker (LLM-as-judge, +1 API-вызов) и оставляем top-`top_k`.
           Если rerank недоступен — фоллбек на косинус-порядок.
        3. Если `retrieve_n > top_k` без rerank — просто режем head по cosine.
        4. По top-`top_k` чанкам собираем контекст, отдаём LLM.
        """
        mid = str(material_id)
        if not await self._store.has_material(mid):
            return RAGAnswer(answer=self.NO_INFO_ANSWER, sources=[])
        q_vec = np.asarray(await self.embeddings.embed(question))
        candidate_n = max(int(retrieve_n or top_k), top_k)
        candidates = await self._store.search(q_vec, top_k=candidate_n, material_id=mid)
        if not candidates:
            return RAGAnswer(answer=self.NO_INFO_ANSWER, sources=[])
        if rerank and candidate_n > top_k:
            candidates = await self.reranker.rerank(question, candidates, top_k=top_k)
        else:
            candidates = candidates[:top_k]
        context = "\n\n---\n\n".join(h.text for h in candidates)
        prompt = (
            f"Вопрос студента: {question}\n\n"
            f"<context>\n{context}\n</context>\n\n"
            f"Ответь на вопрос студента."
        )
        answer = await self.llm.chat(prompt)
        return RAGAnswer(answer=answer, sources=candidates)
