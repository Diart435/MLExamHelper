from dataclasses import dataclass

import numpy as np


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Both vectors must be 1-D. Returns float in [-1, 1]."""
    na, nb = _normalize(a), _normalize(b)
    return float(np.dot(na, nb))


@dataclass
class Hit:
    chunk_id: str
    text: str
    score: float


class InMemoryVectorStore:
    """Simple in-memory vector store. Not persistent — one process lifetime.

    Chunks are grouped by material_id, and search() filters by material_id
    so chunks from other materials never leak into the answer.
    """

    def __init__(self) -> None:
        # chunk_id -> (text, vector, material_id)
        self._chunks: dict[str, tuple[str, np.ndarray, str]] = {}

    def add(self, chunk_id: str, text: str, vector: np.ndarray, material_id: str) -> None:
        self._chunks[chunk_id] = (text, vector, material_id)

    def __len__(self) -> int:
        return len(self._chunks)

    def materials_indexed(self) -> set[str]:
        return {m for (_t, _v, m) in self._chunks.values()}

    def has_material(self, material_id: str) -> bool:
        return any(m == material_id for (_t, _v, m) in self._chunks.values())

    def search(self, query_vector: np.ndarray, top_k: int = 4, material_id: str | None = None) -> list[Hit]:
        items = [
            (cid, txt, vec)
            for cid, (txt, vec, mid) in self._chunks.items()
            if material_id is None or mid == material_id
        ]
        if not items:
            return []
        scores = [_cosine_similarity(query_vector, vec) for (_c, _t, vec) in items]
        order = np.argsort(scores)[::-1][:top_k]
        return [
            Hit(chunk_id=items[i][0], text=items[i][1], score=float(scores[i]))
            for i in order
        ]
