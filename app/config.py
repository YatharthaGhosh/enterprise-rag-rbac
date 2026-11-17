"""All settings in one place, read from environment variables or a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM: any OpenAI-compatible endpoint (Groq, Gemini, OpenAI, Ollama, ...)
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2000  # reasoning models spend part of this on hidden reasoning
    llm_reasoning_effort: str = "low"  # "" to omit for models that do not support it

    # Embeddings and reranker run locally through FastEmbed (ONNX, CPU), so they cost nothing.
    dense_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    # Vector store. If qdrant_url is empty, Qdrant runs embedded in this process, stored on disk at qdrant_path.
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = str(ROOT / "data" / "qdrant")
    collection: str = "company_docs"

    # Retrieval
    prefetch_k: int = 20  # candidates from each of dense and sparse search
    top_k: int = 5  # chunks passed to the LLM
    retrieval_mode: str = "hybrid_rerank"  # dense | hybrid | hybrid_rerank
    # Relevance gate (rerank mode only): if even the best chunk scores below this, refuse without calling the LLM.
    # Measured on the golden set, answerable and unanswerable top scores overlap (paraphrased questions can score
    # -7 while an unanswerable one scored +5), so this is a cost filter for clearly irrelevant results only;
    # the grounded prompt and citation check make the final refuse/answer decision.
    min_rerank_score: float = -8.0


    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_ttl_minutes: int = 480

    docs_dir: str = str(ROOT / "data" / "docs")

    # Public demo: disable uploads/re-indexing and cap questions per hour (shared LLM quota)
    demo_mode: bool = False
    demo_queries_per_hour: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
