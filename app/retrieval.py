"""Retrieval: RBAC-filtered search in Qdrant, then optional cross-encoder reranking.

Modes (compared in eval/run_eval.py):
    dense          dense vectors only
    hybrid         dense + BM25 sparse, fused
    hybrid_rerank  hybrid, then a cross-encoder re-scores the candidates and keeps the best top_k

The RBAC filter is passed as `qdrant_filters`, so Qdrant applies it inside BOTH the dense and the
sparse search. Chunks the user may not read are never returned to Python at all.
"""

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder
from llama_index.core.schema import NodeWithScore

from app.config import get_settings
from app.rbac import User, qdrant_filter
from app.store import collection_exists, get_index

MODES = ("dense", "hybrid", "hybrid_rerank")


@lru_cache
def _reranker() -> TextCrossEncoder:
    return TextCrossEncoder(model_name=get_settings().rerank_model)


def _search(user: User, question: str, mode: str, k: int) -> list[NodeWithScore]:
    kwargs = {"vector_store_kwargs": {"qdrant_filters": qdrant_filter(user)}, "similarity_top_k": k}
    if mode != "dense":
        kwargs |= {"vector_store_query_mode": "hybrid", "sparse_top_k": k, "hybrid_top_k": k}
    return get_index().as_retriever(**kwargs).retrieve(question)


def rerank(question: str, nodes: list[NodeWithScore], top_k: int) -> list[NodeWithScore]:
    if not nodes:
        return []
    scores = list(_reranker().rerank(question, [n.node.get_content() for n in nodes]))
    for n, s in zip(nodes, scores, strict=True):
        n.score = float(s)
    return sorted(nodes, key=lambda n: n.score, reverse=True)[:top_k]


def retrieve(user: User, question: str, mode: str | None = None, top_k: int | None = None) -> list[dict]:
    """Returns passages: dicts with text, score and the chunk's metadata."""
    s = get_settings()
    mode = mode or s.retrieval_mode
    top_k = top_k or s.top_k
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not collection_exists():
        return []
    if mode == "hybrid_rerank":
        nodes = rerank(question, _search(user, question, "hybrid", s.prefetch_k), top_k)
    else:
        nodes = _search(user, question, mode, top_k)
    return [
        {"id": n.node.node_id, "text": n.node.get_content(), "score": round(float(n.score or 0.0), 4), **n.node.metadata}
        for n in nodes
    ]
