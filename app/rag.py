"""The full question-answering pipeline: retrieve (RBAC-filtered) -> generate -> check citations."""

import time

from llama_index.core.llms import ChatMessage

from app.config import get_settings
from app.guardrails import REFUSAL, SYSTEM_PROMPT, build_user_prompt, check_answer
from app.rbac import User
from app.retrieval import retrieve
from app.store import get_llm


def _usage(resp) -> dict:
    raw = getattr(resp, "raw", None)
    usage = getattr(raw, "usage", None) if raw is not None else None
    if usage is None and isinstance(raw, dict):
        usage = raw.get("usage")
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
    return {"prompt_tokens": get("prompt_tokens", 0) or 0, "completion_tokens": get("completion_tokens", 0) or 0}


def answer(user: User, question: str, mode: str | None = None) -> dict:
    t0 = time.perf_counter()
    s = get_settings()
    mode = mode or s.retrieval_mode
    passages = retrieve(user, question, mode=mode)
    gated = mode == "hybrid_rerank" and bool(passages) and passages[0]["score"] < s.min_rerank_score
    if gated:
        passages = []
    t1 = time.perf_counter()

    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if passages:
        resp = get_llm().chat([
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=build_user_prompt(question, passages)),
        ])
        raw = resp.message.content or ""
        usage = _usage(resp)
    else:
        raw = REFUSAL  # nothing the user may read matched, so don't even call the LLM
    t2 = time.perf_counter()

    checked = check_answer(raw, passages)
    return {
        "answer": checked.answer,
        "refused": checked.refused,
        "citations": checked.citations,
        "invalid_citations": checked.invalid_citations,
        "raw_answer": raw,
        "relevance_gated": gated,
        "mode": mode,
        "passages": [
            {k: p[k] for k in ("id", "source_file", "page_number", "section", "department", "access_level", "score", "text")}
            for p in passages
        ],
        "timings_ms": {"retrieval": round((t1 - t0) * 1000), "generation": round((t2 - t1) * 1000),
                       "total": round((t2 - t0) * 1000)},
        "usage": usage,
    }
