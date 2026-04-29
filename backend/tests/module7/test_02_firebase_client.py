"""
Module 7 – Test 02: Firebase client initialisation
Tests init_firebase() behaviour in sqlite-only mode and error paths.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestFirebaseClientSqliteMode:
    """When DATA_MODE=sqlite, Firebase should NOT be initialised."""

    def setup_method(self):
        os.environ["DATA_MODE"] = "sqlite"
        # Reset module state
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None

    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        os.environ.pop("DATA_MODE", None)

    def test_init_firebase_noop_in_sqlite_mode(self):
        import firebase_client
        firebase_client.init_firebase()
        assert firebase_client._initialised is True
        assert firebase_client._firestore_client is None

    def test_get_firestore_client_returns_none_in_sqlite_mode(self):
        import firebase_client
        client = firebase_client.get_firestore_client()
        assert client is None

    def test_init_firebase_idempotent(self):
        import firebase_client
        firebase_client.init_firebase()
        firebase_client.init_firebase()  # second call should be no-op
        assert firebase_client._initialised is True

    def test_needs_firebase_false_for_sqlite(self):
        import firebase_client
        assert firebase_client._needs_firebase() is False


class TestFirebaseClientFirebaseMode:
    """When DATA_MODE=firebase but no credentials, should fail gracefully."""

    def setup_method(self):
        os.environ["DATA_MODE"] = "firebase"
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None

    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        os.environ.pop("DATA_MODE", None)

    def test_needs_firebase_true(self):
        import firebase_client
        from unittest.mock import patch
        with patch.object(firebase_client.settings, "DATA_MODE", "firebase"):
            assert firebase_client._needs_firebase() is True

    def test_init_firebase_handles_missing_credentials_gracefully(self):
        """Without firebase_admin installed or credentials, should fallback."""
        import firebase_client
        firebase_client.init_firebase()
        # Should be marked as initialised even on error (fallback)
        assert firebase_client._initialised is True
