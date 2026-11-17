"""Public-demo protections: uploads/re-indexing are blocked and questions are rate-limited."""

from fastapi.testclient import TestClient

from app import api
from app.config import get_settings
from app.ratelimit import SlidingWindowLimiter


def test_demo_mode_blocks_ingest_and_rate_limits(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(api, "_limiter", SlidingWindowLimiter(max_calls=1))
    monkeypatch.setattr(api, "answer", lambda user, q, mode: {"answer": "ok"})
    c = TestClient(api.app)
    admin = {"Authorization": f"Bearer {c.post('/auth/login', json={'username': 'admin', 'password': 'demo'}).json()['access_token']}"}

    assert c.post("/ingest/sync", headers=admin).status_code == 403
    assert c.post("/query", headers=admin, json={"question": "first question"}).status_code == 200
    assert c.post("/query", headers=admin, json={"question": "second question"}).status_code == 429
