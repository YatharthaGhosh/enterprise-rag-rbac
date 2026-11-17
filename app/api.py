"""FastAPI service.

    POST /auth/login     -> JWT for a demo user
    GET  /me             -> who am I, and what can I read
    POST /query          -> grounded answer with citations (RBAC applied from the token)
    POST /ingest         -> upload a file into <department>/<access_level> (admin only)
    POST /ingest/sync    -> re-sync data/docs incrementally (admin only)
    GET  /health
"""

import logging
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.auth import authenticate, create_token, current_user, require_admin
from app.config import get_settings
from app.ingest import LEVEL_BY_FOLDER, SUPPORTED, ingest_file, sync_directory
from app.rag import answer
from app.ratelimit import SlidingWindowLimiter
from app.rbac import DEPARTMENTS, Level, User, can_read
from app.retrieval import MODES
from app.store import collection_exists, get_client

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Enterprise RAG with RBAC", version="0.1.0")
_limiter = SlidingWindowLimiter(get_settings().demo_queries_per_hour)


def _demo_guard() -> None:
    if get_settings().demo_mode:
        raise HTTPException(403, "Uploading and re-indexing are disabled in the public demo")


class LoginIn(BaseModel):
    username: str
    password: str


class QueryIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str | None = Field(default=None, description=f"one of {MODES}")


@app.get("/health")
def health() -> dict:
    count = get_client().count(get_settings().collection).count if collection_exists() else 0
    return {"status": "ok", "chunks_indexed": count, "demo_mode": get_settings().demo_mode}


@app.post("/auth/login")
def login(body: LoginIn) -> dict:
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user.__dict__}


@app.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    readable = [f"{d}/{lvl}" for d in DEPARTMENTS for lvl, n in LEVEL_BY_FOLDER.items() if can_read(user, d, n)]
    return {"user": user.__dict__, "can_read": readable}


@app.post("/query")
async def query(body: QueryIn, user: User = Depends(current_user)) -> dict:
    if body.mode and body.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {MODES}")
    if get_settings().demo_mode:
        allowed, wait = _limiter.try_acquire()
        if not allowed:
            raise HTTPException(429, f"The public demo's hourly question limit was reached. Try again in {wait // 60 + 1} min.")
    try:
        return await run_in_threadpool(answer, user, body.question, body.mode)
    except RuntimeError as e:  # configuration problem, e.g. missing API key
        raise HTTPException(503, str(e)) from e
    except Exception as e:  # LLM provider down, rate-limited or timed out
        logging.exception("Query failed")
        raise HTTPException(502, f"LLM provider error: {type(e).__name__}") from e


@app.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    department: str = Form(...),
    access_level: str = Form(..., description="public | internal | confidential"),
    _: User = Depends(require_admin),
) -> dict:
    _demo_guard()
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(422, f"Supported types: {sorted(SUPPORTED)}")
    if department not in DEPARTMENTS or access_level not in LEVEL_BY_FOLDER:
        raise HTTPException(422, f"department in {DEPARTMENTS}, access_level in {[lv.name.lower() for lv in Level]}")
    dest = Path(get_settings().docs_dir) / department / access_level / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return (await run_in_threadpool(ingest_file, dest)).__dict__


@app.post("/ingest/sync")
async def ingest_sync(force: bool = False, _: User = Depends(require_admin)) -> dict:
    _demo_guard()
    results = await run_in_threadpool(sync_directory, None, force)
    return {"results": [r.__dict__ for r in results]}
