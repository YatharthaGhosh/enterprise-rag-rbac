# Evaluation results

Run: 2026-11-17 11:59 · LLM: `openai/gpt-oss-120b` · 40 golden questions (24 answerable, 8 role-restricted, 8 unanswerable) · 5 users

## Retrieval (no LLM)

| Mode | Hit rate@1 | Hit rate@5 | MRR | RBAC leakage | p50 latency | p95 latency |
|---|---|---|---|---|---|---|
| dense | 87.5% | 95.8% | 0.917 | 0.0% | 10 ms | 14 ms |
| hybrid | 95.8% | 95.8% | 0.958 | 0.0% | 15 ms | 18 ms |
| hybrid_rerank | 95.8% | 95.8% | 0.958 | 0.0% | 619 ms | 1555 ms |

## End to end (`hybrid_rerank`)

| Metric | Value |
|---|---|
| answer accuracy | 87.5% |
| citation accuracy | 87.5% |
| false refusal rate | 8.3% |
| refusal accuracy | 100.0% |
| restricted refusal | 100.0% |
| unanswerable refusal | 100.0% |
| invalid citations stripped | 0 |
| llm calls saved by relevance gate | 9 |
| latency p50 ms | 1303 |
| latency p95 ms | 2249 |
| avg prompt tokens | 621 |
| avg completion tokens | 60 |
