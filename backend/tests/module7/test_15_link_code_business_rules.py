"""
Business rule tests for link code flow:
- SELF can generate codes
- RELATIVE/DOCTOR can redeem codes
- role compatibility and duplicate protection
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from schemas import LinkCodeGenerateRequest, RedeemCodeRequest
from routers.link_codes_router import generate_code, redeem_code

pytestmark = pytest.mark.asyncio


class _User:
    def __init__(self, uid: str, role: str, full_name: str):
        self.id = uid
        self.role = role
        self.full_name = full_name


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class _FakeLinkCodeRepo:
    def __init__(self):
        self.codes = {}

    async def get_by_code(self, code: str):
        for c in self.codes.values():
            if c["code"] == code:
                return c
        return None

    async def get_by_id(self, code_id: str):
        return self.codes.get(code_id)

    async def create(self, data):
        data = dict(data)
        data.setdefault("created_at", datetime.utcnow())
        self.codes[data["id"]] = data
        return data

    async def update(self, code_id: str, updates):
        if code_id not in self.codes:
            return None
        self.codes[code_id].update(updates)
        return self.codes[code_id]

    async def list_by_owner(self, owner_id: str):
        return [c for c in self.codes.values() if c["owner_id"] == owner_id]


class _FakeRelationRepo:
    def __init__(self):
        self.relations = {}

    async def get_by_id(self, relation_id: str):
        return self.relations.get(relation_id)

    async def create(self, data):
        data = dict(data)
        data.setdefault("created_at", datetime.utcnow())
        self.relations[data["id"]] = data
        return data

    async def update(self, relation_id: str, updates):
        if relation_id not in self.relations:
            return None
        self.relations[relation_id].update(updates)
        return self.relations[relation_id]

    async def find_active_by_self_user(self, self_user_id: str):
        return [
            r for r in self.relations.values()
            if r["self_user_id"] == self_user_id and r.get("is_active", True)
        ]

    async def find_active_by_linked_user(self, linked_user_id: str):
        return [
            r for r in self.relations.values()
            if r["linked_user_id"] == linked_user_id and r.get("is_active", True)
        ]

    async def find_active_link(self, self_user_id: str, linked_user_id: str):
        for r in self.relations.values():
            if (
                r["self_user_id"] == self_user_id
                and r["linked_user_id"] == linked_user_id
                and r.get("is_active", True)
            ):
                return r
        return None


class _FakeUserRepo:
    def __init__(self, users):
        self.users = users

    async def get_by_id(self, user_id: str):
        return self.users.get(user_id)


class _FakeWriteRepo:
    def __init__(self):
        self.items = []

    async def create(self, data):
        self.items.append(dict(data))
        return data


class _FakeRepos:
    def __init__(self, users):
        self.link_codes = _FakeLinkCodeRepo()
        self.relations = _FakeRelationRepo()
        self.users = _FakeUserRepo(users)
        self.notifications = _FakeWriteRepo()
        self.history = _FakeWriteRepo()


async def _seed_code(repos, owner_id: str, code_type: str, code: str = "123456", uses=1):
    now = datetime.utcnow()
    await repos.link_codes.create({
        "id": f"lc-{owner_id}-{code_type}",
        "code": code,
        "owner_id": owner_id,
        "code_type": code_type,
        "is_active": True,
        "uses_remaining": uses,
        "expires_at": now + timedelta(hours=12),
        "created_at": now,
    })


async def test_self_can_generate_code_for_relative():
    db = _FakeDB()
    users = {"self1": {"id": "self1", "role": "SELF", "full_name": "Self One"}}
    repos = _FakeRepos(users)

    resp = await generate_code(
        body=LinkCodeGenerateRequest(relation_type="RELATIVE"),
        db=db,
        current_user=_User("self1", "SELF", "Self One"),
        repos=repos,
    )

    assert resp["owner_id"] == "self1"
    assert resp["code_type"] == "RELATIVE"
    assert db.commits == 1


async def test_non_self_cannot_generate_code():
    db = _FakeDB()
    repos = _FakeRepos({})

    with pytest.raises(HTTPException) as exc:
        await generate_code(
            body=LinkCodeGenerateRequest(relation_type="DOCTOR"),
            db=db,
            current_user=_User("rel1", "RELATIVE", "Relative One"),
            repos=repos,
        )

    assert exc.value.status_code == 403


async def test_relative_can_redeem_relative_code():
    db = _FakeDB()
    users = {
        "self1": {"id": "self1", "role": "SELF", "full_name": "Self One"},
        "rel1": {"id": "rel1", "role": "RELATIVE", "full_name": "Relative One"},
    }
    repos = _FakeRepos(users)
    await _seed_code(repos, owner_id="self1", code_type="RELATIVE", code="222222")

    resp = await redeem_code(
        body=RedeemCodeRequest(code="222222"),
        db=db,
        current_user=_User("rel1", "RELATIVE", "Relative One"),
        repos=repos,
    )

    assert resp.self_user_id == "self1"
    assert resp.linked_user_id == "rel1"
    assert resp.relation_type == "RELATIVE"
    assert db.commits == 1


async def test_doctor_cannot_redeem_relative_only_code():
    db = _FakeDB()
    users = {
        "self1": {"id": "self1", "role": "SELF", "full_name": "Self One"},
        "doc1": {"id": "doc1", "role": "DOCTOR", "full_name": "Doctor One"},
    }
    repos = _FakeRepos(users)
    await _seed_code(repos, owner_id="self1", code_type="RELATIVE", code="333333")

    with pytest.raises(HTTPException) as exc:
        await redeem_code(
            body=RedeemCodeRequest(code="333333"),
            db=db,
            current_user=_User("doc1", "DOCTOR", "Doctor One"),
            repos=repos,
        )

    assert exc.value.status_code == 400


async def test_self_cannot_redeem_code():
    db = _FakeDB()
    users = {"self1": {"id": "self1", "role": "SELF", "full_name": "Self One"}}
    repos = _FakeRepos(users)
    await _seed_code(repos, owner_id="self1", code_type="RELATIVE", code="444444")

    with pytest.raises(HTTPException) as exc:
        await redeem_code(
            body=RedeemCodeRequest(code="444444"),
            db=db,
            current_user=_User("self1", "SELF", "Self One"),
            repos=repos,
        )

    assert exc.value.status_code == 403


async def test_duplicate_relation_is_blocked():
    db = _FakeDB()
    users = {
        "self1": {"id": "self1", "role": "SELF", "full_name": "Self One"},
        "rel1": {"id": "rel1", "role": "RELATIVE", "full_name": "Relative One"},
    }
    repos = _FakeRepos(users)
    await _seed_code(repos, owner_id="self1", code_type="RELATIVE", code="555555", uses=2)

    await redeem_code(
        body=RedeemCodeRequest(code="555555"),
        db=db,
        current_user=_User("rel1", "RELATIVE", "Relative One"),
        repos=repos,
    )

    with pytest.raises(HTTPException) as exc:
        await redeem_code(
            body=RedeemCodeRequest(code="555555"),
            db=db,
            current_user=_User("rel1", "RELATIVE", "Relative One"),
            repos=repos,
        )

    assert exc.value.status_code == 400


async def test_invalid_code_returns_404():
    db = _FakeDB()
    users = {
        "self1": {"id": "self1", "role": "SELF", "full_name": "Self One"},
        "doc1": {"id": "doc1", "role": "DOCTOR", "full_name": "Doctor One"},
    }
    repos = _FakeRepos(users)

    with pytest.raises(HTTPException) as exc:
        await redeem_code(
            body=RedeemCodeRequest(code="999999"),
            db=db,
            current_user=_User("doc1", "DOCTOR", "Doctor One"),
            repos=repos,
        )

    assert exc.value.status_code == 404
