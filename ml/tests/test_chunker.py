from app.services.chunker import split_text


def test_splits_long_text_into_multiple_chunks():
    chunks = split_text("Предложение один. " * 200, chunk_size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)


def test_short_text_returns_single_chunk():
    assert split_text("Короткий текст.", chunk_size=800, overlap=100) == ["Короткий текст."]


def test_preserves_paragraph_boundaries():
    text = "Параграф один. " * 10 + "\n\n" + "Параграф два. " * 10
    chunks = split_text(text, chunk_size=200, overlap=20)
    assert any("Параграф один" in c for c in chunks)
    assert any("Параграф два" in c for c in chunks)


def test_chunks_have_overlap():
    chunks = split_text("абв" * 300, chunk_size=300, overlap=50)
    assert len(chunks) >= 2