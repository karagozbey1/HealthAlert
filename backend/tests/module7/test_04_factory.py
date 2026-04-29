"""
Module 7 – Test 04: Repository factory (get_repos)
Tests that the factory returns the correct backend based on DATA_MODE.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestFactorySqliteMode:
    """Factory in sqlite mode must return SqliteXxxRepo instances."""

    def setup_method(self):
        os.environ["DATA_MODE"] = "sqlite"

    def teardown_method(self):
        os.environ.pop("DATA_MODE", None)

    def test_returns_repo_set(self):
        from repositories.factory import get_repos, RepoSet
        # We can't pass a real db in unit tests; just check it requires one
        with pytest.raises(ValueError, match="sqlite mode requires"):
            get_repos(db=None, mode="sqlite")

    def test_sqlite_repos_are_correct_types(self):
        """Provide a mock db to verify that the returned repos are Sqlite instances."""
        from unittest.mock import MagicMock
        from repositories.factory import get_repos
        from repositories.sqlite.repos import SqliteUserRepo, SqliteAlertRepo

        mock_db = MagicMock()
        repos = get_repos(db=mock_db, mode="sqlite")
        assert isinstance(repos.users, SqliteUserRepo)
        assert isinstance(repos.alerts, SqliteAlertRepo)
        assert repos.users.db is mock_db


class TestFactoryFirebaseMode:
    """Factory in firebase mode must return FirebaseXxxRepo instances."""

    def setup_method(self):
        os.environ["DATA_MODE"] = "firebase"

    def teardown_method(self):
        os.environ.pop("DATA_MODE", None)

    def test_firebase_mode_no_db_required(self):
        """Firebase mode should not require a db argument, but needs a Firestore client."""
        from repositories.factory import get_repos
        # This will call get_firestore_client() which returns None in test env
        repos = get_repos(db=None, mode="firebase")
        # Repos should be FirebaseXxxRepo instances
        from repositories.firebase.repos import FirebaseUserRepo
        assert isinstance(repos.users, FirebaseUserRepo)


class TestFactoryHybridMode:
    """Hybrid mode must require a db."""

    def test_hybrid_requires_db(self):
        with pytest.raises(ValueError, match="hybrid mode requires"):
            from repositories.factory import get_repos
            get_repos(db=None, mode="hybrid")

    def test_hybrid_returns_hybrid_repos(self):
        from unittest.mock import MagicMock
        from repositories.factory import get_repos, _HybridRepo
        mock_db = MagicMock()
        repos = get_repos(db=mock_db, mode="hybrid")
        assert isinstance(repos.users, _HybridRepo)


class TestRepoSetFields:
    """RepoSet must have all 13 domain repositories."""

    def test_all_fields_present(self):
        from repositories.factory import RepoSet
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RepoSet)}
        expected = {
            "users", "link_codes", "relations", "live_status",
            "anomalies", "alerts", "post_events", "history",
            "notifications", "clinical_notes", "app_settings",
            "simulation", "devices",
        }
        assert expected == fields
