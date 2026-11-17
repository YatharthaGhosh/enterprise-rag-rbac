"""Incremental indexing: unchanged files are skipped, changed files replace their old chunks, deleted files are purged."""

from pathlib import Path

import pytest
from docx import Document

from app import ingest, store
from app.config import get_settings

COLLECTION = "test_incremental"


@pytest.fixture
def temp_collection(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "collection", COLLECTION)
    monkeypatch.setattr(s, "docs_dir", str(tmp_path))
    store.get_vector_store.cache_clear()
    store.get_index.cache_clear()
    yield tmp_path
    if store.get_client().collection_exists(COLLECTION):
        store.get_client().delete_collection(COLLECTION)
    monkeypatch.undo()
    store.get_vector_store.cache_clear()
    store.get_index.cache_clear()


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading("Test Policy", level=1)
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(path)


def _hashes(source_path: str) -> set[str]:
    pts, _ = store.get_client().scroll(COLLECTION, limit=100, with_payload=True)
    return {p.payload["doc_hash"] for p in pts if p.payload["source_path"] == source_path}


def test_skip_update_and_purge(temp_collection):
    f = temp_collection / "hr" / "public" / "policy.docx"
    _write_docx(f, ["The office opens at 9 am."])

    assert [r.status for r in ingest.sync_directory(temp_collection)] == ["indexed"]
    old_hash = ingest.file_sha256(f)

    assert [r.status for r in ingest.sync_directory(temp_collection)] == ["skipped"]

    _write_docx(f, ["The office opens at 10 am.", "Visitors must sign in at reception."])
    assert [r.status for r in ingest.sync_directory(temp_collection)] == ["updated"]
    hashes = _hashes("hr/public/policy.docx")
    assert hashes == {ingest.file_sha256(f)} and old_hash not in hashes  # no stale chunks left behind

    f.unlink()
    assert [r.status for r in ingest.sync_directory(temp_collection)] == ["deleted"]
    assert _hashes("hr/public/policy.docx") == set()


def test_labels_come_from_folder(tmp_path):
    assert ingest.labels_from_path(tmp_path / "finance" / "confidential" / "x.pdf", tmp_path) == ("finance", 2)
    with pytest.raises(ValueError):
        ingest.labels_from_path(tmp_path / "x.pdf", tmp_path)
