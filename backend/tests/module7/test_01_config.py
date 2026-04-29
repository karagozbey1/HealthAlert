"""
Module 7 – Test 01: Configuration & DATA_MODE
Verifies that config.py properly exposes DATA_MODE and Firebase fields,
and that defaults are backward-compatible.
"""
import os
import sys
import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestConfigDataMode:
    """Test DATA_MODE and Firebase settings in config.py."""

    def test_default_data_mode_is_sqlite(self):
        from config import Settings
        s = Settings()
        assert s.DATA_MODE == "sqlite"

    def test_data_mode_accepts_firebase(self):
        os.environ["DATA_MODE"] = "firebase"
        try:
            from config import Settings
            s = Settings()
            assert s.DATA_MODE == "firebase"
        finally:
            os.environ.pop("DATA_MODE", None)

    def test_data_mode_accepts_hybrid(self):
        os.environ["DATA_MODE"] = "hybrid"
        try:
            from config import Settings
            s = Settings()
            assert s.DATA_MODE == "hybrid"
        finally:
            os.environ.pop("DATA_MODE", None)

    def test_firebase_project_id_default_empty(self):
        from config import Settings
        s = Settings()
        assert s.FIREBASE_PROJECT_ID == ""

    def test_firebase_credentials_path_default_empty(self):
        from config import Settings
        s = Settings()
        assert s.FIREBASE_CREDENTIALS_PATH == ""

    def test_existing_settings_preserved(self):
        """Existing settings must NOT be broken by Module 7 additions."""
        from config import Settings
        s = Settings()
        assert s.SECRET_KEY != ""
        assert s.ALGORITHM == "HS256"
        assert s.DATABASE_URL.startswith("sqlite")
        assert s.SIMULATION_INTERVAL_SECONDS == 4.0
        assert s.LINK_CODE_EXPIRE_HOURS == 48
        assert s.LINK_CODE_USES == 1
