"""RBAC leakage test against the REAL index.

Run scripts/ingest.py first, and stop the API (embedded Qdrant allows one process at a time).

Every golden question is asked as EVERY demo user, in every retrieval mode, and every chunk that
comes back must be readable by that user according to can_read(). The restricted questions matter
most: their answers ARE in the index, so a missing or wrong filter would surface them.
"""

import json
from pathlib import Path

import pytest

from app.rbac import DEMO_USERS, can_read
from app.retrieval import MODES, retrieve
from app.store import collection_exists

GOLDEN = [json.loads(line) for line in (Path(__file__).parent.parent / "eval" / "golden.jsonl").open()]

pytestmark = pytest.mark.skipif(not collection_exists(), reason="index is empty: run scripts/ingest.py")


@pytest.mark.parametrize("mode", MODES)
def test_no_unauthorised_chunk_is_ever_retrieved(mode):
    checked = 0
    for row in GOLDEN:
        for user in DEMO_USERS.values():
            for p in retrieve(user, row["question"], mode=mode, top_k=10):
                assert can_read(user, p["department"], p["access_level"]), (user.username, row["question"], p["source_path"])
                checked += 1
    assert checked > 0


def test_restricted_answers_are_not_retrievable_by_the_asker():
    for row in [r for r in GOLDEN if r["type"] == "restricted"]:
        sources = {p["source_file"] for p in retrieve(DEMO_USERS[row["user"]], row["question"], top_k=10)}
        assert row["source"] not in sources, row
