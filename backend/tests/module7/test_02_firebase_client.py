import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestFirebaseClientSqliteMode:
    # SQLite modunda baslangic ortam degiskenlerini temizler.
    def setup_method(self):
        os.environ["DATA_MODE"] = "sqlite"
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None

    # Her testten sonra Firebase istemci durumunu sifirlar.
    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        os.environ.pop("DATA_MODE", None)

    # SQLite modunda init_firebase cagrisi istemci olusturmadan tamamlanir.
    def test_init_firebase_noop_in_sqlite_mode(self):
        import firebase_client
        firebase_client.init_firebase()
        assert firebase_client._initialised is True
        assert firebase_client._firestore_client is None

    # SQLite modunda Firestore istemcisinin None dondurdugunu dogrular.
    def test_get_firestore_client_returns_none_in_sqlite_mode(self):
        import firebase_client
        client = firebase_client.get_firestore_client()
        assert client is None

    # Aynı init cagrısının tekrarlandığında idempotent kaldığını kontrol eder.
    def test_init_firebase_idempotent(self):
        import firebase_client
        firebase_client.init_firebase()
        firebase_client.init_firebase()  # second call should be no-op
        assert firebase_client._initialised is True

    # SQLite modunda Firebase ihtiyacının kapalı olduğunu dogrular.
    def test_needs_firebase_false_for_sqlite(self):
        import firebase_client
        assert firebase_client._needs_firebase() is False


class TestFirebaseClientFirebaseMode:
    # Firebase modu icin ortam degiskenini ve modulu test baslangicina hazirlar.
    def setup_method(self):
        os.environ["DATA_MODE"] = "firebase"
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None

    # Her testten sonra Firebase modu ortamını ve modül durumunu temizler.
    def teardown_method(self):
        import firebase_client
        firebase_client._initialised = False
        firebase_client._firestore_client = None
        os.environ.pop("DATA_MODE", None)

    # Firebase modunda ihtiyac bayraginin acildigini dogrular.
    def test_needs_firebase_true(self):
        import firebase_client
        from unittest.mock import patch
        with patch.object(firebase_client.settings, "DATA_MODE", "firebase"):
            assert firebase_client._needs_firebase() is True

    # Kimlik bilgisi olmasa bile init akisinin fail-open tamamlandigini dogrular.
    def test_init_firebase_handles_missing_credentials_gracefully(self):
        import firebase_client
        firebase_client.init_firebase()
        assert firebase_client._initialised is True
