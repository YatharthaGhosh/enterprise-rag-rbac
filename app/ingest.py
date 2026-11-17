"""Ingestion: Docling parses each file, HybridChunker splits it, LlamaIndex embeds and stores it in Qdrant.

Access labels come from the folder a file lives in:  data/docs/<department>/<public|internal|confidential>/

Incremental indexing: each file's SHA-256 is stored on its chunks.
- same hash already indexed  -> skipped (no re-embedding)
- different hash             -> old chunks deleted by source_path, new chunks inserted
- file no longer on disk     -> its chunks are purged (sync_directory)
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from llama_index.core.schema import TextNode
from qdrant_client import models
from transformers import AutoTokenizer

from app.config import get_settings
from app.rbac import DEPARTMENTS, Level
from app.store import collection_exists, get_client, get_index

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".docx", ".xlsx"}
LEVEL_BY_FOLDER = {"public": Level.PUBLIC, "internal": Level.INTERNAL, "confidential": Level.CONFIDENTIAL}
MAX_TOKENS = 400  # bge-small accepts 512 tokens; leave room for the heading/context prefix


class _MarkdownTables(ChunkingSerializerProvider):
    """Serialise tables as markdown (default is 'key = value' triplets), which LLMs read more reliably."""

    def get_serializer(self, doc):
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


@lru_cache
def _converter() -> DocumentConverter:
    pdf_opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True)  # our PDFs are digital, no OCR needed
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts)})


@lru_cache
def _chunker() -> HybridChunker:
    tok = HuggingFaceTokenizer(tokenizer=AutoTokenizer.from_pretrained(get_settings().dense_model), max_tokens=MAX_TOKENS)
    return HybridChunker(tokenizer=tok, merge_peers=True, serializer_provider=_MarkdownTables())


@dataclass
class IngestResult:
    source_path: str
    status: str  # "indexed" | "updated" | "skipped" | "deleted" | "error"
    chunks: int = 0
    detail: str = ""


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def labels_from_path(path: Path, docs_dir: Path) -> tuple[str, int]:
    rel = path.resolve().relative_to(docs_dir.resolve())
    if len(rel.parts) < 3:
        raise ValueError(f"{rel} must be inside <department>/<access_level>/")
    dept, level = rel.parts[0].lower(), rel.parts[1].lower()
    if dept not in DEPARTMENTS or level not in LEVEL_BY_FOLDER:
        raise ValueError(f"Unknown department/access level in path: {rel}")
    return dept, int(LEVEL_BY_FOLDER[level])


def _title(path: Path) -> str:
    return path.stem.replace("_", " ").title()


def _source_filter(source_path: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="source_path", match=models.MatchValue(value=source_path))])


def indexed_hash(source_path: str) -> str | None:
    if not collection_exists():
        return None
    points, _ = get_client().scroll(get_settings().collection, scroll_filter=_source_filter(source_path),
                                    limit=1, with_payload=["doc_hash"], with_vectors=False)
    return points[0].payload.get("doc_hash") if points else None


def delete_source(source_path: str) -> None:
    if collection_exists():
        get_client().delete(get_settings().collection, points_selector=models.FilterSelector(filter=_source_filter(source_path)))


def build_nodes(path: Path, department: str, access_level: int, source_path: str, doc_hash: str) -> list[TextNode]:
    doc = _converter().convert(path).document
    title = _title(path)
    nodes = []
    for i, chunk in enumerate(_chunker().chunk(doc)):
        pages = sorted({p.page_no for item in chunk.meta.doc_items for p in (item.prov or [])})
        headings = chunk.meta.headings or []
        text = f"Document: {title}\n{_chunker().contextualize(chunk)}"
        meta = {
            "source_file": path.name,
            "source_path": source_path,
            "title": title,
            "department": department,
            "access_level": access_level,
            "page_number": pages[0] if pages else 1,
            "section": headings[-1] if headings else title,
            "doc_hash": doc_hash,
            "chunk_index": i,
        }
        node = TextNode(text=text, metadata=meta, id_=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_path}:{doc_hash}:{i}")))
        # The text already starts with the title and headings, so don't also embed the raw metadata.
        node.excluded_embed_metadata_keys = list(meta)
        node.excluded_llm_metadata_keys = list(meta)
        nodes.append(node)
    return nodes


def ingest_file(path: Path, docs_dir: Path | None = None, force: bool = False) -> IngestResult:
    docs_dir = docs_dir or Path(get_settings().docs_dir)
    source_path = path.resolve().relative_to(docs_dir.resolve()).as_posix()
    try:
        department, level = labels_from_path(path, docs_dir)
        new_hash = file_sha256(path)
        old_hash = indexed_hash(source_path)
        if old_hash == new_hash and not force:
            return IngestResult(source_path, "skipped", detail="unchanged")
        nodes = build_nodes(path, department, level, source_path, new_hash)
        if old_hash is not None:
            delete_source(source_path)  # remove the previous version's chunks first
        get_index().insert_nodes(nodes)
        return IngestResult(source_path, "updated" if old_hash else "indexed", len(nodes))
    except Exception as e:  # one bad file must not stop the whole sync
        log.exception("Failed to ingest %s", path)
        return IngestResult(source_path, "error", detail=str(e))


def indexed_sources() -> set[str]:
    if not collection_exists():
        return set()
    seen, offset = set(), None
    while True:
        points, offset = get_client().scroll(get_settings().collection, limit=256, offset=offset,
                                             with_payload=["source_path"], with_vectors=False)
        seen.update(p.payload["source_path"] for p in points if p.payload)
        if offset is None:
            return seen


def sync_directory(docs_dir: Path | None = None, force: bool = False) -> list[IngestResult]:
    docs_dir = docs_dir or Path(get_settings().docs_dir)
    files = sorted(p for p in docs_dir.rglob("*") if p.suffix.lower() in SUPPORTED)
    results = [ingest_file(p, docs_dir, force) for p in files]
    on_disk = {p.resolve().relative_to(docs_dir.resolve()).as_posix() for p in files}
    for gone in indexed_sources() - on_disk:
        delete_source(gone)
        results.append(IngestResult(gone, "deleted"))
    return results
