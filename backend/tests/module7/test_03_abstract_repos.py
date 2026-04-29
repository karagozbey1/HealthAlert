"""
Module 7 – Test 03: Repository abstract base classes
Ensures all abstract contracts exist, are importable, and have the
expected methods.
"""
import os
import sys
import inspect
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from repositories.base import (
    AbstractUserRepo,
    AbstractLinkCodeRepo,
    AbstractRelationRepo,
    AbstractLiveStatusRepo,
    AbstractAnomalyRepo,
    AbstractAlertRepo,
    AbstractPostEventRepo,
    AbstractHistoryRepo,
    AbstractNotificationRepo,
    AbstractClinicalNoteRepo,
    AbstractSettingsRepo,
    AbstractSimulationStateRepo,
    AbstractDeviceRepo,
)

ALL_REPOS = [
    AbstractUserRepo,
    AbstractLinkCodeRepo,
    AbstractRelationRepo,
    AbstractLiveStatusRepo,
    AbstractAnomalyRepo,
    AbstractAlertRepo,
    AbstractPostEventRepo,
    AbstractHistoryRepo,
    AbstractNotificationRepo,
    AbstractClinicalNoteRepo,
    AbstractSettingsRepo,
    AbstractSimulationStateRepo,
    AbstractDeviceRepo,
]


class TestAbstractReposExist:
    """All 13 abstract repositories must be importable."""

    @pytest.mark.parametrize("cls", ALL_REPOS, ids=lambda c: c.__name__)
    def test_is_abstract(self, cls):
        assert inspect.isabstract(cls)

    @pytest.mark.parametrize("cls", ALL_REPOS, ids=lambda c: c.__name__)
    def test_cannot_instantiate(self, cls):
        with pytest.raises(TypeError):
            cls()


class TestUserRepoContract:
    def test_has_expected_methods(self):
        methods = {"get_by_id", "get_by_email", "create", "update", "list_by_role"}
        repo_methods = {m for m in dir(AbstractUserRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestAlertRepoContract:
    def test_has_expected_methods(self):
        methods = {"get_by_id", "create", "update", "list_by_user", "get_active_by_user", "get_countdown_alerts"}
        repo_methods = {m for m in dir(AbstractAlertRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestNotificationRepoContract:
    def test_has_expected_methods(self):
        methods = {"create", "list_by_recipient", "mark_read", "mark_all_read"}
        repo_methods = {m for m in dir(AbstractNotificationRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestDeviceRepoContract:
    def test_has_expected_methods(self):
        methods = {"register_device", "get_registration", "update_registration", "log_packet"}
        repo_methods = {m for m in dir(AbstractDeviceRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestRelationRepoContract:
    def test_has_expected_methods(self):
        methods = {"get_by_id", "create", "update", "find_active_by_self_user",
                   "find_active_by_linked_user", "find_active_link"}
        repo_methods = {m for m in dir(AbstractRelationRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestSettingsRepoContract:
    def test_has_expected_methods(self):
        methods = {"get_or_create", "update"}
        repo_methods = {m for m in dir(AbstractSettingsRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)


class TestClinicalNoteRepoContract:
    def test_has_expected_methods(self):
        methods = {"create", "get_by_id", "update", "delete", "list_by_patient"}
        repo_methods = {m for m in dir(AbstractClinicalNoteRepo) if not m.startswith("_")}
        assert methods.issubset(repo_methods)
