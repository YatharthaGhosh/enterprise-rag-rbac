"""Evaluate the RAG system against eval/golden.jsonl (40 questions: 24 answerable, 8 restricted, 8 unanswerable).

Three stages:
  1. Retrieval (no LLM, free): hit rate@k, MRR and RBAC leakage for dense / hybrid / hybrid_rerank.
  2. End-to-end (LLM): answer accuracy, refusal accuracy, false refusals, citation accuracy, latency, tokens.
  3. Ragas (optional, --ragas): faithfulness, answer relevancy, context precision, context recall,
     with an LLM judge (EVAL_JUDGE_MODEL, defaults to LLM_MODEL).

Writes eval/results/<timestamp>.json and eval/RESULTS.md.

    python eval/run_eval.py                     # stages 1 + 2
    python eval/run_eval.py --ragas             # + Ragas
    python eval/run_eval.py --retrieval-only    # stage 1 only, no API key needed
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.guardrails import CITATION_RE  # noqa: E402
from app.rag import answer  # noqa: E402
from app.rbac import DEMO_USERS, can_read  # noqa: E402
from app.retrieval import MODES, retrieve  # noqa: E402

GOLDEN = [json.loads(line) for line in (ROOT / "eval" / "golden.jsonl").open()]
RESULTS_DIR = ROOT / "eval" / "results"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def p95(values: list[float]) -> float:
    return statistics.quantiles(values, n=20)[18] if len(values) >= 2 else (values[0] if values else 0)


# ---------------------------------------------------------------- stage 1: retrieval
def eval_retrieval() -> dict:
    k = get_settings().top_k
    out = {}
    for mode in MODES:
        hits, top1, rr, lat, leaked, total, misses = 0, 0, 0.0, [], 0, 0, []
        answerable = [r for r in GOLDEN if r["type"] == "answerable"]
        for row in GOLDEN:
            user = DEMO_USERS[row["user"]]
            t = time.perf_counter()
            passages = retrieve(user, row["question"], mode=mode, top_k=k)
            lat.append((time.perf_counter() - t) * 1000)
            leaked += sum(not can_read(user, p["department"], p["access_level"]) for p in passages)
            total += len(passages)
            if row["type"] == "answerable":
                files = [p["source_file"] for p in passages]
                if row["source"] in files:
                    hits += 1
                    top1 += files[0] == row["source"]
                    rr += 1 / (files.index(row["source"]) + 1)
                if not files or files[0] != row["source"]:
                    misses.append(f"#{row['id']} top1={files[0] if files else None}")
        out[mode] = {
            "hit_rate@1": top1 / len(answerable),
            f"hit_rate@{k}": hits / len(answerable),
            "mrr": rr / len(answerable),
            "leakage_rate": leaked / max(total, 1),
            "latency_p50_ms": statistics.median(lat),
            "latency_p95_ms": p95(lat),
            "top1_misses": misses,
        }
        print(f"[retrieval] {mode:14} hit@1={pct(out[mode]['hit_rate@1'])} hit@{k}={pct(out[mode][f'hit_rate@{k}'])} mrr={out[mode]['mrr']:.3f} "
              f"leak={pct(out[mode]['leakage_rate'])} p50={out[mode]['latency_p50_ms']:.0f}ms misses={misses}")
    return out


# ---------------------------------------------------------------- stage 2: end to end
def eval_end_to_end(mode: str, delay: float) -> tuple[dict, list[dict]]:
    rows = []
    for row in GOLDEN:
        r = answer(DEMO_USERS[row["user"]], row["question"], mode=mode)
        ans = "".join(r["answer"].lower().split())  # ignore whitespace: "15 %" == "15%"
        correct = (not r["refused"]) and all("".join(e.lower().split()) in ans for e in row["expected"])
        cited_right = any(c["source_file"] == row["source"] for c in r["citations"])
        rows.append({**row, "answer": r["answer"], "refused": r["refused"], "correct": correct,
                     "cited_expected_source": cited_right, "relevance_gated": r["relevance_gated"],
                     "invalid_citations": r["invalid_citations"], "contexts": [p["text"] for p in r["passages"]],
                     "latency_ms": r["timings_ms"]["total"], **r["usage"]})
        mark = "OK " if (correct if row["type"] == "answerable" else r["refused"]) else "BAD"
        print(f"[e2e] {mark} #{row['id']:<2} {row['type']:12} {row['user']:7} {row['question'][:55]:55} -> {r['answer'][:70]}")
        if not r["relevance_gated"] and r["usage"]["prompt_tokens"]:
            time.sleep(delay)  # stay under free-tier rate limits

    ans = [r for r in rows if r["type"] == "answerable"]
    should_refuse = [r for r in rows if r["type"] != "answerable"]
    llm_rows = [r for r in rows if r["prompt_tokens"]]
    metrics = {
        "answer_accuracy": sum(r["correct"] for r in ans) / len(ans),
        "citation_accuracy": sum(r["cited_expected_source"] for r in ans) / len(ans),
        "false_refusal_rate": sum(r["refused"] for r in ans) / len(ans),
        "refusal_accuracy": sum(r["refused"] for r in should_refuse) / len(should_refuse),
        "restricted_refusal": sum(r["refused"] for r in should_refuse if r["type"] == "restricted")
        / sum(r["type"] == "restricted" for r in should_refuse),
        "unanswerable_refusal": sum(r["refused"] for r in should_refuse if r["type"] == "unanswerable")
        / sum(r["type"] == "unanswerable" for r in should_refuse),
        "invalid_citations_stripped": sum(len(r["invalid_citations"]) for r in rows),
        "llm_calls_saved_by_relevance_gate": sum(r["relevance_gated"] for r in rows),
        "latency_p50_ms": statistics.median(r["latency_ms"] for r in rows),
        "latency_p95_ms": p95([r["latency_ms"] for r in rows]),
        "avg_prompt_tokens": statistics.mean(r["prompt_tokens"] for r in llm_rows) if llm_rows else 0,
        "avg_completion_tokens": statistics.mean(r["completion_tokens"] for r in llm_rows) if llm_rows else 0,
    }
    return metrics, rows


# ---------------------------------------------------------------- stage 3: ragas
def eval_ragas(rows: list[dict]) -> dict:
    from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
    from langchain_openai import ChatOpenAI
    from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )

    s = get_settings()
    judge = LangchainLLMWrapper(ChatOpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, temperature=0,
                                           model=os.getenv("EVAL_JUDGE_MODEL", s.llm_model)))
    emb = LangchainEmbeddingsWrapper(FastEmbedEmbeddings(model_name=s.dense_model))
    samples = [
        # Citation tags are not claims; strip them so the judge scores only the content.
        SingleTurnSample(user_input=r["question"], response=CITATION_RE.sub("", r["answer"]).strip(),
                         retrieved_contexts=r["contexts"],
                         reference=r["reference"])
        for r in rows if r["type"] == "answerable" and not r["refused"] and r["contexts"]
    ]
    result = evaluate(
        EvaluationDataset(samples=samples),
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()],
        llm=judge, embeddings=emb, run_config=RunConfig(max_workers=2, timeout=120, max_retries=6),
        show_progress=True,
    )
    df = result.to_pandas()
    cols = [c for c in df.columns if c in {"faithfulness", "answer_relevancy", "llm_context_precision_with_reference",
                                           "context_recall"}]
    return {c: float(df[c].mean()) for c in cols} | {"ragas_samples": len(samples)}


# ---------------------------------------------------------------- report
def write_report(retrieval: dict, e2e: dict | None, ragas: dict | None, mode: str) -> str:
    s = get_settings()
    k = s.top_k
    lines = ["# Evaluation results", "",
             f"Run: {datetime.now():%Y-%m-%d %H:%M} · LLM: `{s.llm_model}` · {len(GOLDEN)} golden questions "
             "(24 answerable, 8 role-restricted, 8 unanswerable) · 5 users", "",
             "## Retrieval (no LLM)", "",
             f"| Mode | Hit rate@1 | Hit rate@{k} | MRR | RBAC leakage | p50 latency | p95 latency |",
             "|---|---|---|---|---|---|---|"]
    for m, v in retrieval.items():
        lines.append(f"| {m} | {pct(v['hit_rate@1'])} | {pct(v[f'hit_rate@{k}'])} | {v['mrr']:.3f} | {pct(v['leakage_rate'])} | "
                     f"{v['latency_p50_ms']:.0f} ms | {v['latency_p95_ms']:.0f} ms |")
    if e2e:
        lines += ["", f"## End to end (`{mode}`)", "", "| Metric | Value |", "|---|---|"]
        for key, v in e2e.items():
            val = pct(v) if isinstance(v, float) and v <= 1 and "ms" not in key and "tokens" not in key else (
                f"{v:.0f}" if isinstance(v, float) else str(v))
            lines.append(f"| {key.replace('_', ' ')} | {val} |")
    if ragas:
        lines += ["", "## Ragas", "", "| Metric | Score |", "|---|---|"]
        lines += [f"| {key} | {v:.3f} |" if isinstance(v, float) else f"| {key} | {v} |" for key, v in ragas.items()]
    md = "\n".join(lines) + "\n"
    (ROOT / "eval" / "RESULTS.md").write_text(md, encoding="utf-8")
    return md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--ragas", action="store_true")
    ap.add_argument("--mode", default=get_settings().retrieval_mode)
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between LLM calls (rate limits)")
    args = ap.parse_args()

    retrieval = eval_retrieval()
    e2e = rows = ragas = None
    if not args.retrieval_only:
        e2e, rows = eval_end_to_end(args.mode, args.delay)
        if args.ragas:
            ragas = eval_ragas(rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / f"{stamp}.json").write_text(
        json.dumps({"retrieval": retrieval, "end_to_end": e2e, "ragas": ragas, "rows": rows}, indent=2, default=str),
        encoding="utf-8")
    print("\n" + write_report(retrieval, e2e, ragas, args.mode))


if __name__ == "__main__":
    main()
