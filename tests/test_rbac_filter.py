"""The Qdrant filter must select exactly the chunks that can_read() allows, for every user and label."""

import itertools

from qdrant_client import QdrantClient, models

from app.rbac import DEMO_USERS, DEPARTMENTS, Level, User, can_read, qdrant_filter


def _client_with_every_label() -> QdrantClient:
    client = QdrantClient(":memory:")
    client.create_collection("t", vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE))
    points = [
        models.PointStruct(id=i, vector=[1.0], payload={"department": d, "access_level": int(lvl)})
        for i, (d, lvl) in enumerate(itertools.product(DEPARTMENTS, Level))
    ]
    client.upsert("t", points)
    return client


def _visible(client: QdrantClient, user: User) -> set[tuple[str, int]]:
    pts, _ = client.scroll("t", scroll_filter=qdrant_filter(user), limit=100, with_payload=True)
    return {(p.payload["department"], p.payload["access_level"]) for p in pts}


def test_filter_matches_reference_rule_for_all_users():
    client = _client_with_every_label()
    users = list(DEMO_USERS.values()) + [User(f"{r}-{d}", r, d) for r in ("employee", "manager") for d in DEPARTMENTS]
    for user in users:
        expected = {(d, int(lvl)) for d, lvl in itertools.product(DEPARTMENTS, Level) if can_read(user, d, lvl)}
        assert _visible(client, user) == expected, user


def test_unknown_role_sees_nothing():
    assert _visible(_client_with_every_label(), User("x", "contractor", "sales")) == set()


def test_rule_examples():
    priya = DEMO_USERS["priya"]  # engineering employee
    assert can_read(priya, "finance", Level.PUBLIC)
    assert can_read(priya, "engineering", Level.INTERNAL)
    assert not can_read(priya, "sales", Level.INTERNAL)
    assert not can_read(priya, "engineering", Level.CONFIDENTIAL)
    rahul = DEMO_USERS["rahul"]  # finance manager
    assert can_read(rahul, "sales", Level.INTERNAL)
    assert can_read(rahul, "finance", Level.CONFIDENTIAL)
    assert not can_read(rahul, "hr", Level.CONFIDENTIAL)
