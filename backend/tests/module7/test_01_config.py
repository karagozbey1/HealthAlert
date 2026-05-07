import os
import sys
import pytest

# Backend paketini dogrudan ice aktarilabilir hale getirir.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestConfigDataMode:
    # Varsayilan veri modunun sqlite oldugunu dogrular.
    def test_default_data_mode_is_sqlite(self):
        from config import Settings
        s = Settings()
        assert s.DATA_MODE == "sqlite"

    # Firebase modunun kabul edildigini dogrular.
    def test_data_mode_accepts_firebase(self):
        os.environ["DATA_MODE"] = "firebase"
        try:
            from config import Settings
            s = Settings()
            assert s.DATA_MODE == "firebase"
        finally:
            os.environ.pop("DATA_MODE", None)

    # Hybrid modunun kabul edildigini dogrular.
    def test_data_mode_accepts_hybrid(self):
        os.environ["DATA_MODE"] = "hybrid"
        try:
            from config import Settings
            s = Settings()
            assert s.DATA_MODE == "hybrid"
        finally:
            os.environ.pop("DATA_MODE", None)

    # Firebase proje kimliginin varsayilaninin bos oldugunu kontrol eder.
    def test_firebase_project_id_default_empty(self):
        from config import Settings
        s = Settings()
        assert s.FIREBASE_PROJECT_ID == ""

    # Firebase kimlik dosyasi yolunun varsayilaninin bos oldugunu kontrol eder.
    def test_firebase_credentials_path_default_empty(self):
        from config import Settings
        s = Settings()
        assert s.FIREBASE_CREDENTIALS_PATH == ""

    # Yeni ayarlar eklenirken eski konfigurasyon davranisinin korunmasini dogrular.
    def test_existing_settings_preserved(self):
        from config import Settings
        s = Settings()
        assert s.SECRET_KEY != ""
        assert s.ALGORITHM == "HS256"
        assert s.DATABASE_URL.startswith("sqlite")
        assert s.SIMULATION_INTERVAL_SECONDS == 4.0
        assert s.LINK_CODE_EXPIRE_HOURS == 48
        assert s.LINK_CODE_USES == 1
