import numpy as np
from app.services.vector_store import InMemoryVectorStore


def test_add_and_search_returns_most_similar():
    store = InMemoryVectorStore()
    store.add("mat-1:c1", "текст 1", np.array([1.0, 0.0, 0.0]), material_id="mat-1")
    store.add("mat-1:c2", "текст 2", np.array([0.0, 1.0, 0.0]), material_id="mat-1")
    store.add("mat-1:c3", "текст 3", np.array([0.9, 0.1, 0.0]), material_id="mat-1")
    hits = store.search(np.array([1.0, 0.0, 0.0]), top_k=2, material_id="mat-1")
    assert hits[0].chunk_id == "mat-1:c1"
    assert hits[1].chunk_id == "mat-1:c3"


def test_search_filters_by_material_id():
    """Chunks from another material must NOT appear in results."""
    store = InMemoryVectorStore()
    store.add("mat-1:c1", "текст 1", np.array([1.0, 0.0, 0.0]), material_id="mat-1")
    store.add("mat-2:c1", "текст 2 (другой материал)", np.array([1.0, 0.0, 0.0]), material_id="mat-2")
    hits = store.search(np.array([1.0, 0.0, 0.0]), top_k=4, material_id="mat-1")
    assert all(h.chunk_id.startswith("mat-1:") for h in hits)


def test_search_empty_store_returns_empty_list():
    assert InMemoryVectorStore().search(np.array([1.0, 0.0]), top_k=4, material_id="x") == []


def test_top_k_limits_results():
    store = InMemoryVectorStore()
    for i in range(10):
        store.add(f"mat-1:c{i}", f"t{i}", np.random.rand(8), material_id="mat-1")
    assert len(store.search(np.random.rand(8), top_k=3, material_id="mat-1")) == 3