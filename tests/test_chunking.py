from app.chunking import chunk_text, merge_chunks


def test_short_text_single_chunk():
    chunks = chunk_text("Hello world", chunk_size=100)
    assert chunks == ["Hello world"]


def test_empty_text():
    assert chunk_text("  ") == []


def test_long_text_split():
    text = "word " * 500
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)  # chunk_size + overlap
    # Rejoined content should be a superset-ish of the original pieces.
    assert "word word" in chunks[0]


def test_overlap_preserves_boundaries():
    text = " ".join(f"sentence{i}" for i in range(200))
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    joined = " ".join(chunks)
    assert len(chunks) >= 1
    assert chunks == [c.strip() for c in chunks]


def test_merge_chunks_rebuilds_the_document_without_duplicating_overlap():
    """Regression: rejoining overlapping chunks duplicated ~20% of the text.

    That inflation pushed a 20.7K document over the 24K prompt budget even
    though it had passed the upload gate.
    """
    text = "\n\n".join(
        f"Paragraph {i}: " + "lorem ipsum dolor sit amet " * 8 for i in range(30)
    )

    chunks = chunk_text(text)
    merged = merge_chunks(chunks)

    assert merged == text.strip()
    assert sum(len(c) for c in chunks) > len(merged)  # the overlap was real


def test_merge_chunks_handles_repetitive_text():
    """Identical runs must not make the merge cut more than one overlap."""
    text = "alpha beta gamma delta. " * 200

    assert merge_chunks(chunk_text(text)) == text.strip()


def test_merge_chunks_empty_list():
    assert merge_chunks([]) == ""


def test_merge_chunks_single_chunk_is_identity():
    assert merge_chunks(["only chunk"]) == "only chunk"
