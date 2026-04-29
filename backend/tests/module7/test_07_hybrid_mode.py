"""
Module 7 – Test 07: Hybrid mode proxy behaviour
Verifies that _HybridRepo delegates reads to primary, writes to both,
and silently swallows secondary failures on write.
"""
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class FakePrimary:
    """Mimics a SQLite repo – primary for reads & writes."""
    async def get_by_id(self, uid):
        return {"id": uid, "source": "primary"}

    async def list_by_user(self, uid):
        return [{"id": "1", "source": "primary"}]

    async def create(self, data):
        return {**data, "source": "primary"}

    async def update(self, uid, data):
        return {"id": uid, **data, "source": "primary"}

    async def delete(self, uid):
        return True

    async def find_active_link(self, a, b):
        return {"a": a, "b": b, "source": "primary"}


class FakeSecondary:
    """Mimics a Firebase repo – secondary for writes only."""
    def __init__(self, should_fail=False):
        self._should_fail = should_fail
        self.created = []
        self.updated = []
        self.deleted = []

    async def get_by_id(self, uid):
        return {"id": uid, "source": "secondary"}

    async def create(self, data):
        if self._should_fail:
            raise RuntimeError("Firebase down!")
        self.created.append(data)
        return {**data, "source": "secondary"}

    async def update(self, uid, data):
        if self._should_fail:
            raise RuntimeError("Firebase down!")
        self.updated.append((uid, data))
        return {"id": uid, **data, "source": "secondary"}

    async def delete(self, uid):
        if self._should_fail:
            raise RuntimeError("Firebase down!")
        self.deleted.append(uid)
        return True


@pytest.fixture
def hybrid_repo():
    from repositories.factory import _HybridRepo
    primary = FakePrimary()
    secondary = FakeSecondary()
    return _HybridRepo(primary, secondary), primary, secondary


@pytest.fixture
def hybrid_repo_failing():
    from repositories.factory import _HybridRepo
    primary = FakePrimary()
    secondary = FakeSecondary(should_fail=True)
    return _HybridRepo(primary, secondary), primary, secondary


# ---------------------------------------------------------------
# Read operations → primary only
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_get_by_id_uses_primary(hybrid_repo):
    proxy, primary, secondary = hybrid_repo
    result = await proxy.get_by_id("u1")
    assert result["source"] == "primary"


@pytest.mark.asyncio
async def test_read_list_by_user_uses_primary(hybrid_repo):
    proxy, _, _ = hybrid_repo
    result = await proxy.list_by_user("u1")
    assert result[0]["source"] == "primary"


@pytest.mark.asyncio
async def test_read_find_active_link_uses_primary(hybrid_repo):
    proxy, _, _ = hybrid_repo
    result = await proxy.find_active_link("a", "b")
    assert result["source"] == "primary"


# ---------------------------------------------------------------
# Write operations → both (returns primary result)
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_create_goes_to_both(hybrid_repo):
    proxy, primary, secondary = hybrid_repo
    result = await proxy.create({"id": "x1", "name": "test"})
    # Returns primary result
    assert result["source"] == "primary"
    # Secondary also received the call
    assert len(secondary.created) == 1
    assert secondary.created[0]["id"] == "x1"


@pytest.mark.asyncio
async def test_write_update_goes_to_both(hybrid_repo):
    proxy, primary, secondary = hybrid_repo
    result = await proxy.update("x1", {"name": "updated"})
    assert result["source"] == "primary"
    assert len(secondary.updated) == 1


@pytest.mark.asyncio
async def test_write_delete_goes_to_both(hybrid_repo):
    proxy, primary, secondary = hybrid_repo
    result = await proxy.delete("x1")
    assert result is True
    assert "x1" in secondary.deleted


# ---------------------------------------------------------------
# Write operations → secondary failure is tolerated
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_create_tolerates_secondary_failure(hybrid_repo_failing):
    proxy, primary, secondary = hybrid_repo_failing
    # Should NOT raise even though secondary raises RuntimeError
    result = await proxy.create({"id": "x2", "name": "test"})
    assert result["source"] == "primary"


@pytest.mark.asyncio
async def test_write_update_tolerates_secondary_failure(hybrid_repo_failing):
    proxy, _, _ = hybrid_repo_failing
    result = await proxy.update("x2", {"name": "up"})
    assert result["source"] == "primary"


@pytest.mark.asyncio
async def test_write_delete_tolerates_secondary_failure(hybrid_repo_failing):
    proxy, _, _ = hybrid_repo_failing
    result = await proxy.delete("x2")
    assert result is True


# ---------------------------------------------------------------
# RepoSet structure
# ---------------------------------------------------------------

def test_reposet_has_all_fields():
    from repositories.factory import RepoSet
    import dataclasses
    fields = {f.name for f in dataclasses.fields(RepoSet)}
    expected = {
        "users", "link_codes", "relations", "live_status",
        "anomalies", "alerts", "post_events", "history",
        "notifications", "clinical_notes", "app_settings",
        "simulation", "devices",
    }
    assert expected.issubset(fields)
