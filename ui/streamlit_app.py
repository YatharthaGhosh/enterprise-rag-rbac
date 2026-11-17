"""Streamlit front end. Talks to the FastAPI service only (never to Qdrant directly), so RBAC is always enforced.

    streamlit run ui/streamlit_app.py
"""

import os

import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
USERS = {
    "priya": "Priya · Employee · Engineering",
    "ananya": "Ananya · Employee · Sales",
    "rahul": "Rahul · Manager · Finance",
    "vikram": "Vikram · Manager · HR",
    "admin": "Admin · All access",
}
LEVELS = {0: "public", 1: "internal", 2: "confidential"}
EXAMPLES = [
    "How many days of paid annual leave do employees get each year?",
    "Within how much time must a SEV1 incident be acknowledged?",
    "Which company is Project Kestrel proposing to acquire?",
    "What was the revenue in Q3 FY2026-27?",
    "What is the maximum discount a sales rep can give?",
]

st.set_page_config(page_title="Enterprise RAG", page_icon="🔐", layout="wide")


def login(username: str) -> None:
    r = requests.post(f"{API}/auth/login", json={"username": username, "password": "demo"}, timeout=10)
    r.raise_for_status()
    st.session_state.token = r.json()["access_token"]
    st.session_state.user = username
    st.session_state.history = []
    me = requests.get(f"{API}/me", headers=_auth(), timeout=10).json()
    st.session_state.can_read = me["can_read"]


def _auth() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("🔐 Signed in as")
    choice = st.radio("Demo user", list(USERS), format_func=USERS.get, label_visibility="collapsed")
    try:
        if st.session_state.get("user") != choice:
            login(choice)
    except requests.RequestException as e:
        st.error(f"API not reachable at {API}. Start it with `uvicorn app.api:app`.\n\n{e}")
        st.stop()
    st.caption("Can read: " + ", ".join(f"`{x}`" for x in st.session_state.can_read))
    mode = st.selectbox("Retrieval mode", ["hybrid_rerank", "hybrid", "dense"])
    demo = False
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
        demo = health.get("demo_mode", False)
        st.caption(f"Chunks indexed: {health['chunks_indexed']}")
    except requests.RequestException:
        pass
    if demo:
        st.info("Public demo: questions are rate-limited and uploads are disabled. "
                "Source: github.com/YatharthaGhosh/enterprise-rag-rbac")

    if choice == "admin" and not demo:
        st.divider()
        st.subheader("Upload a document")
        f = st.file_uploader("PDF, DOCX or XLSX", type=["pdf", "docx", "xlsx"])
        dept = st.selectbox("Department", ["hr", "engineering", "finance", "sales"])
        level = st.selectbox("Access level", ["public", "internal", "confidential"])
        if f and st.button("Ingest"):
            with st.spinner("Parsing with Docling and embedding..."):
                r = requests.post(f"{API}/ingest", headers=_auth(), files={"file": (f.name, f.getvalue())},
                                  data={"department": dept, "access_level": level}, timeout=600)
            st.json(r.json())
        if st.button("Re-sync data/docs"):
            with st.spinner("Syncing..."):
                r = requests.post(f"{API}/ingest/sync", headers=_auth(), timeout=1800)
            st.json(r.json())

# ---------------------------------------------------------------- main
st.title("Company Knowledge Assistant")
st.caption("Answers come only from documents your role may read, with citations. "
           "Switch users in the sidebar to see access control in action.")

cols = st.columns(len(EXAMPLES))
picked = None
for c, q in zip(cols, EXAMPLES, strict=True):
    if c.button(q, use_container_width=True):
        picked = q

for turn in st.session_state.history:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        st.write(turn["r"]["answer"])

question = st.chat_input("Ask about company policies, runbooks, finances...") or picked
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Retrieving and answering..."):
            resp = requests.post(f"{API}/query", headers=_auth(), json={"question": question, "mode": mode}, timeout=120)
        if resp.status_code != 200:
            st.error(resp.text)
            st.stop()
        r = resp.json()
        st.write(r["answer"])
        st.session_state.history.append({"q": question, "r": r})

        t = r["timings_ms"]
        st.caption(f"⏱ retrieval {t['retrieval']} ms · generation {t['generation']} ms · "
                   f"tokens {r['usage']['prompt_tokens']}+{r['usage']['completion_tokens']}"
                   + (" · 🚧 relevance gate: no LLM call" if r.get("relevance_gated") else ""))
        if r["invalid_citations"]:
            st.warning(f"Removed citations not backed by retrieved context: {r['invalid_citations']}")
        if r["citations"]:
            st.markdown("**Sources:** " + " · ".join(f"`{c['source_file']}, p. {c['page_number']}`" for c in r["citations"]))
        with st.expander(f"Retrieved passages ({len(r['passages'])})"):
            for p in r["passages"]:
                st.markdown(f"**{p['source_file']}**, p. {p['page_number']} · {p['section']} · "
                            f"`{p['department']}/{LEVELS[p['access_level']]}` · score {p['score']}")
                st.text(p["text"][:800])
