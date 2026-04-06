from pathlib import Path

from rag import build_prompt, build_tree, retrieve_tree, split_text


def test_split_text_creates_chunks():
    text = "This is a test document. " * 100
    chunks = split_text(text, chunk_size=20, overlap=5)
    assert len(chunks) > 1
    assert all(len(chunk.split()) <= 20 for chunk in chunks)


def test_build_tree_creates_hierarchical_nodes(tmp_path):
    (tmp_path / "doc1.txt").write_text("apple banana orange " * 20)
    root = build_tree(tmp_path)

    assert root.children
    assert all(child.children for child in root.children)
    assert root.children[0].children[0].children


def test_retrieve_tree_prefers_relevant_chunks(tmp_path):
    (tmp_path / "doc1.txt").write_text("apple orange banana " * 20)
    (tmp_path / "doc2.txt").write_text("car bus train " * 20)

    root = build_tree(tmp_path)
    results = retrieve_tree("apple", root)

    assert results
    assert any("apple" in chunk for chunk in results)


def test_build_prompt_includes_query_and_context():
    prompt = build_prompt("What is vectorless RAG?", ["A short text chunk."])
    assert "What is vectorless RAG?" in prompt
    assert "A short text chunk." in prompt
