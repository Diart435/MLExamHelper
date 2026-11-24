import numpy as np
import pytest

from app.services.vector_store import InMemoryVectorStore


@pytest.mark.asyncio
async def test_add_and_search_returns_most_similar():
    store = InMemoryVectorStore()
    await store.add("mat-1:c1", "текст 1", np.array([1.0, 0.0, 0.0]), material_id="mat-1")
    await store.add("mat-1:c2", "текст 2", np.array([0.0, 1.0, 0.0]), material_id="mat-1")
    await store.add("mat-1:c3", "текст 3", np.array([0.9, 0.1, 0.0]), material_id="mat-1")
    hits = await store.search(np.array([1.0, 0.0, 0.0]), top_k=2, material_id="mat-1")
    assert hits[0].chunk_id == "mat-1:c1"
    assert hits[1].chunk_id == "mat-1:c3"


@pytest.mark.asyncio
async def test_search_filters_by_material_id():
    """Chunks from another material must NOT appear in results."""
    store = InMemoryVectorStore()
    await store.add("mat-1:c1", "текст 1", np.array([1.0, 0.0, 0.0]), material_id="mat-1")
    await store.add("mat-2:c1", "текст 2 (другой материал)", np.array([1.0, 0.0, 0.0]), material_id="mat-2")
    hits = await store.search(np.array([1.0, 0.0, 0.0]), top_k=4, material_id="mat-1")
    assert all(h.chunk_id.startswith("mat-1:") for h in hits)


@pytest.mark.asyncio
async def test_search_empty_store_returns_empty_list():
    store = InMemoryVectorStore()
    hits = await store.search(np.array([1.0, 0.0]), top_k=4, material_id="x")
    assert hits == []


@pytest.mark.asyncio
async def test_top_k_limits_results():
    store = InMemoryVectorStore()
    for i in range(10):
        await store.add(f"mat-1:c{i}", f"t{i}", np.random.rand(8), material_id="mat-1")
    hits = await store.search(np.random.rand(8), top_k=3, material_id="mat-1")
    assert len(hits) == 3


@pytest.mark.asyncio
async def test_has_material_true_and_false():
    store = InMemoryVectorStore()
    assert await store.has_material("none") is False
    await store.add("a:c1", "x", np.array([1.0, 0.0]), material_id="a")
    assert await store.has_material("a") is True
    assert await store.has_material("b") is False


@pytest.mark.asyncio
async def test_materials_indexed_returns_unique_set():
    store = InMemoryVectorStore()
    await store.add("a:c1", "x", np.array([1.0, 0.0]), material_id="a")
    await store.add("a:c2", "y", np.array([0.0, 1.0]), material_id="a")
    await store.add("b:c1", "z", np.array([1.0, 1.0]), material_id="b")
    assert await store.materials_indexed() == {"a", "b"}
