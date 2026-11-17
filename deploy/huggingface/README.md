---
title: Enterprise RAG with RBAC
emoji: 🔐
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: RAG with role-based access, hybrid search and citations
---

# Enterprise RAG with RBAC: live demo

Ask questions about a fictional company's internal documents. **What you can retrieve depends on who you are**: switch users in the sidebar and ask the same question.

**Try this:** pick *Rahul (Finance manager)* and ask *"Which company is Project Kestrel proposing to acquire?"*. Then switch to *Priya (Engineering employee)* and ask again. Rahul gets a cited answer; Priya gets a refusal, because the access filter is applied inside the vector database search.

- Docling parsing → LlamaIndex + Qdrant hybrid search (dense + BM25) → cross-encoder rerank → grounded LLM answer with checked citations
- 0% leakage of restricted content and 100% correct refusals on a 40-question evaluation set

**Code, tests and evaluation:** https://github.com/YatharthaGhosh/enterprise-rag-rbac

*Public demo: questions are rate-limited (shared LLM quota) and document upload is disabled.*
