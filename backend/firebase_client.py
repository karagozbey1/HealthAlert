from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger("firebase_client")

_firestore_client = None
_initialised = False

_firebase_status: Dict[str, Any] = {
    "needed": False,
    "credentials_path_configured": False,
    "credentials_file_exists": False,
    "project_id_configured": False,
    "sdk_initialised": False,
    "firestore_connected": False,
    "error": None,
    "mode": "sqlite",
}

# Firebase gerekip gerekmediğini kontrol eder.
def _needs_firebase() -> bool:
    return settings.DATA_MODE in ("firebase", "hybrid")

# FIREBASE_CREDENTIALS_PATH dosyasını doğrular.
def _validate_credentials_path() -> Optional[str]:
    path = settings.FIREBASE_CREDENTIALS_PATH
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    if not os.path.exists(path):
        return f"FIREBASE_CREDENTIALS_PATH file not found: {path}"
    if not os.path.isfile(path):
        return f"FIREBASE_CREDENTIALS_PATH is not a file: {path}"
    if not path.endswith(".json"):
        return f"FIREBASE_CREDENTIALS_PATH should be a .json file: {path}"
    return None

# Firebase Admin SDK'yı başlatır; sqlite modunda no-op.
def init_firebase() -> None:
    global _firestore_client, _initialised, _firebase_status

    if _initialised:
        return

    _firebase_status["mode"] = settings.DATA_MODE
    _firebase_status["needed"] = _needs_firebase()
    _firebase_status["project_id_configured"] = bool(settings.FIREBASE_PROJECT_ID)
    _firebase_status["credentials_path_configured"] = bool(settings.FIREBASE_CREDENTIALS_PATH)

    if not _needs_firebase():
        logger.info("DATA_MODE=%s – Firebase initialisation skipped.", settings.DATA_MODE)
        _initialised = True
        return

    if not settings.FIREBASE_PROJECT_ID:
        msg = (
            "DATA_MODE=%s requires FIREBASE_PROJECT_ID but it is empty. "
            "Firebase operations will fail; falling back to local storage."
            % settings.DATA_MODE
        )
        logger.warning(msg)
        _firebase_status["error"] = msg
        _initialised = True
        return

    if settings.FIREBASE_CREDENTIALS_PATH:
        path_error = _validate_credentials_path()
        if path_error:
            logger.warning(
                "%s — Firebase will NOT initialise. "
                "Fix the path or remove it to use Application Default Credentials.",
                path_error,
            )
            _firebase_status["error"] = path_error
            _initialised = True
            return
        _firebase_status["credentials_file_exists"] = True
    else:
        logger.info(
            "FIREBASE_CREDENTIALS_PATH not set — "
            "attempting Application Default Credentials (ADC)."
        )

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if settings.FIREBASE_CREDENTIALS_PATH:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                logger.info(
                    "Firebase credentials loaded from: %s",
                    settings.FIREBASE_CREDENTIALS_PATH,
                )
            else:
                cred = credentials.ApplicationDefault()
                logger.info("Firebase using Application Default Credentials.")

            firebase_admin.initialize_app(cred, {
                "projectId": settings.FIREBASE_PROJECT_ID,
            })

        _firebase_status["sdk_initialised"] = True

        _firestore_client = firestore.client()
        _firebase_status["firestore_connected"] = True
        _initialised = True
        logger.info(
            "✅ Firebase initialised successfully (project=%s, DATA_MODE=%s).",
            settings.FIREBASE_PROJECT_ID,
            settings.DATA_MODE,
        )

    except ImportError:
        msg = (
            "firebase-admin package not installed. "
            "Install with: pip install firebase-admin>=6.4.0"
        )
        logger.error(msg)
        _firebase_status["error"] = msg
        _firestore_client = None
        _initialised = True

    except Exception as exc:
        msg = f"Firebase initialisation failed: {exc}"
        logger.exception(msg)
        _firebase_status["error"] = msg
        _firestore_client = None
        _initialised = True

# Firestore istemcisini döndürür.
def get_firestore_client():
    if not _initialised:
        init_firebase()
    return _firestore_client

def get_firebase_status() -> Dict[str, Any]:
    if not _initialised:
        init_firebase()
    return dict(_firebase_status)

async def firebase_smoke_test() -> Dict[str, Any]:
    client = get_firestore_client()
    if client is None:
        return {
            "ok": False,
            "detail": "Firestore client not available. Check Firebase configuration.",
        }

    import asyncio
    from datetime import datetime
    from functools import partial
    from uuid import uuid4

    doc_id = f"smoke-{uuid4().hex[:8]}"
    collection = "_healthalert_smoke"
    test_data = {
        "test": True,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "healthalert-backend",
    }

    loop = asyncio.get_running_loop()
    try:
        ref = client.collection(collection).document(doc_id)
        await loop.run_in_executor(None, partial(ref.set, test_data))

        doc = await loop.run_in_executor(None, ref.get)
        if not doc.exists:
            return {"ok": False, "detail": "Smoke write succeeded but read-back failed."}

        await loop.run_in_executor(None, ref.delete)

        return {
            "ok": True,
            "detail": f"Firestore smoke test passed (project={settings.FIREBASE_PROJECT_ID}).",
        }

    except Exception as exc:
        return {
            "ok": False,
            "detail": f"Firestore smoke test failed: {exc}",
        }
