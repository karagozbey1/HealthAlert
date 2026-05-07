import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestFactorySqliteMode:
    # SQLite modundaki factory davranışlarını doğrular.
    # Her testten önce sqlite modunu etkinleştirir.
    def setup_method(self):
        os.environ["DATA_MODE"] = "sqlite"

    # Her testten sonra DATA_MODE değişkenini temizler.
    def teardown_method(self):
        os.environ.pop("DATA_MODE", None)

    # SQLite modunda veritabanı bağımlılığının zorunlu olduğunu doğrular.
    def test_returns_repo_set(self):
        from repositories.factory import get_repos, RepoSet
        # We can't pass a real db in unit tests; just check it requires one
        with pytest.raises(ValueError, match="sqlite mode requires"):
            get_repos(db=None, mode="sqlite")

    # SQLite modunda doğru repository türlerinin döndüğünü kontrol eder.
    def test_sqlite_repos_are_correct_types(self):
        from unittest.mock import MagicMock
        from repositories.factory import get_repos
        from repositories.sqlite.repos import SqliteUserRepo, SqliteAlertRepo

        mock_db = MagicMock()
        repos = get_repos(db=mock_db, mode="sqlite")
        assert isinstance(repos.users, SqliteUserRepo)
        assert isinstance(repos.alerts, SqliteAlertRepo)
        assert repos.users.db is mock_db


class TestFactoryFirebaseMode:
    # Firebase modundaki factory davranışlarını doğrular.
    # Her testten önce firebase modunu etkinleştirir.
    def setup_method(self):
        os.environ["DATA_MODE"] = "firebase"

    # Her testten sonra DATA_MODE değişkenini temizler.
    def teardown_method(self):
        os.environ.pop("DATA_MODE", None)

    # Firebase modunda repo kümesinin db olmadan kurulabildiğini doğrular.
    def test_firebase_mode_no_db_required(self):
        from repositories.factory import get_repos
        # This will call get_firestore_client() which returns None in test env
        repos = get_repos(db=None, mode="firebase")
        # Repos should be FirebaseXxxRepo instances
        from repositories.firebase.repos import FirebaseUserRepo
        assert isinstance(repos.users, FirebaseUserRepo)


class TestFactoryHybridMode:
    # Hibrit modun db gereksinimini doğrular.
    # Hibrit modda db verilmezse hata oluştuğunu kontrol eder.
    def test_hybrid_requires_db(self):
        with pytest.raises(ValueError, match="hybrid mode requires"):
            from repositories.factory import get_repos
            get_repos(db=None, mode="hybrid")

    # Hibrit modda sarmalayıcı repository nesnelerinin döndüğünü doğrular.
    def test_hybrid_returns_hybrid_repos(self):
        from unittest.mock import MagicMock
        from repositories.factory import get_repos, _HybridRepo
        mock_db = MagicMock()
        repos = get_repos(db=mock_db, mode="hybrid")
        assert isinstance(repos.users, _HybridRepo)


class TestRepoSetFields:
    # RepoSet içindeki alan listesini doğrular.
    # Beklenen repository alanlarının mevcut olduğunu kontrol eder.
    def test_all_fields_present(self):
        from repositories.factory import RepoSet
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RepoSet)}
        expected = {
            "users", "link_codes", "relations", "live_status",
            "anomalies", "alerts", "post_events", "history",
            "notifications", "clinical_notes", "app_settings",
            "simulation", "devices", "baselines",
        }
        assert expected == fields
