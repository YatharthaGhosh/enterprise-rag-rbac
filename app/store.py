"""Shared, lazily created singletons: Qdrant client, LlamaIndex vector store/index, embedding model, LLM.

Embedded Qdrant (no qdrant_url set) stores data on disk and allows ONE process at a time.
So run the CLI ingest while the API is stopped, or ingest through the API's /ingest endpoint.
"""

import atexit
from functools import lru_cache

from llama_index.core import Settings as LISettings
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.llms.openai_like import OpenAILike
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import get_settings


@lru_cache
def get_client() -> QdrantClient:
    s = get_settings()
    if s.qdrant_url:
        client = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None)
    else:
        client = QdrantClient(path=s.qdrant_path)
    atexit.register(client.close)  # release the embedded store's file lock cleanly on exit
    return client


@lru_cache
def get_embed_model() -> FastEmbedEmbedding:
    return FastEmbedEmbedding(model_name=get_settings().dense_model)


@lru_cache
def get_vector_store() -> QdrantVectorStore:
    s = get_settings()
    return QdrantVectorStore(
        collection_name=s.collection,
        client=get_client(),
        enable_hybrid=True,  # dense vectors + BM25 sparse vectors in the same collection
        fastembed_sparse_model=s.sparse_model,
        batch_size=32,
        # Indexes make the RBAC filter fast on a real Qdrant server (embedded mode ignores them).
        payload_indexes=[
            {"field_name": "department", "field_schema": "keyword"},
            {"field_name": "access_level", "field_schema": "integer"},
            {"field_name": "source_path", "field_schema": "keyword"},
        ],
    )


@lru_cache
def get_index() -> VectorStoreIndex:
    LISettings.embed_model = get_embed_model()
    LISettings.llm = None  # we call the LLM ourselves in app/rag.py
    storage = StorageContext.from_defaults(vector_store=get_vector_store())
    return VectorStoreIndex.from_vector_store(get_vector_store(), storage_context=storage,
                                              embed_model=get_embed_model())


@lru_cache
def get_llm() -> OpenAILike:
    s = get_settings()
    if not s.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAILike(
        model=s.llm_model,
        api_base=s.llm_base_url,
        api_key=s.llm_api_key,
        is_chat_model=True,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout=60,
        max_retries=3,
        additional_kwargs={"reasoning_effort": s.llm_reasoning_effort} if s.llm_reasoning_effort else {},
    )


def collection_exists() -> bool:
    return get_client().collection_exists(get_settings().collection)
