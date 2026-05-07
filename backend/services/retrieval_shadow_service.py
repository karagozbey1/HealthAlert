from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from config import settings  # module-level for mock.patch testability

logger = logging.getLogger("healthalert.retrieval_shadow")

# Indeks dizinlerini proje kokune gore cozer.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_AI_ROOT = os.path.join(_PROJECT_ROOT, "healthalert_final_ai")


# Verilen indeks yolunu mutlak dizine cevirir.
def _resolve_index_dir(path: str) -> str:
    if os.path.isabs(path):
        return path
    candidate = os.path.join(_PROJECT_ROOT, path)
    if os.path.isdir(candidate):
        return candidate
    candidate2 = os.path.join(_BACKEND_DIR, path)
    if os.path.isdir(candidate2):
        return candidate2
    return os.path.join(_PROJECT_ROOT, path)


# Yavas indeks klasorunun ve zorunlu dosyalarinin varligini denetler.
def _slow_index_available() -> bool:
    if not settings.RETRIEVAL_USE_SLOW_INDEX:
        return False
    slow_dir = _resolve_index_dir(settings.RETRIEVAL_SLOW_INDEX_DIR)
    return os.path.isfile(os.path.join(slow_dir, "retrieval_index.joblib"))


# Retrieval shadow sorgularini fail-open sekilde yoneten servistir.
class RetrievalShadowService:

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # 50Hz index (Part 3)
        self._loaded: bool = False
        self._available: bool = False
        self._load_error: Optional[str] = None
        self._engine = None  # RetrievalEngine instance

        # Slow (1Hz-aligned) index (Part 3.1)
        self._slow_loaded: bool = False
        self._slow_available: bool = False
        self._slow_engine = None  # RetrievalEngine instance for slow index

    # 50 Hz retrieval motorunun kullanima hazir olup olmadigini bildirir.
    def is_available(self) -> bool:
        return self._available

    # 50 Hz retrieval motorunu tek sefer yukleyip sonucunu dondurur.
    def load_once(self) -> bool:
        with self._lock:
            if self._loaded:
                return self._available
            return self._do_load()

    # Yavas indeks motorunu tek sefer yukleyip sonucunu dondurur.
    def _load_slow_once(self) -> bool:
        with self._lock:
            if self._slow_loaded:
                return self._slow_available
            return self._do_load_slow()

    # 50 Hz retrieval indeksini kilit altinda yukler.
    def _do_load(self) -> bool:
        if not settings.RETRIEVAL_ENABLED:
            self._loaded = True
            self._available = False
            self._load_error = "RETRIEVAL_ENABLED=False"
            return False

        try:
            if _AI_ROOT not in sys.path:
                sys.path.insert(0, _AI_ROOT)

            from src.inference.retrieval_engine import RetrievalEngine

            index_dir = _resolve_index_dir(settings.RETRIEVAL_INDEX_DIR)
            engine = RetrievalEngine()
            ok = engine.load(index_dir)
            if ok:
                self._engine = engine
                self._available = True
                logger.info("RetrievalShadowService: 50Hz engine loaded from %s", index_dir)
            else:
                self._load_error = (
                    f"RetrievalEngine.load() failed: {engine._load_error}"
                )
                logger.warning("RetrievalShadowService (50Hz): %s", self._load_error)

        except Exception as exc:
            self._load_error = str(exc)
            self._available = False
            logger.error("RetrievalShadowService (50Hz) load failed: %s", exc)
        finally:
            self._loaded = True

        return self._available

    # 1 Hz hizina uyarlanmis retrieval indeksini kilit altinda yukler.
    def _do_load_slow(self) -> bool:
        if not settings.RETRIEVAL_ENABLED or not settings.RETRIEVAL_USE_SLOW_INDEX:
            self._slow_loaded = True
            self._slow_available = False
            return False

        try:
            if _AI_ROOT not in sys.path:
                sys.path.insert(0, _AI_ROOT)

            from src.inference.retrieval_engine import RetrievalEngine

            slow_dir = _resolve_index_dir(settings.RETRIEVAL_SLOW_INDEX_DIR)
            engine = RetrievalEngine()
            ok = engine.load(slow_dir)
            if ok:
                self._slow_engine = engine
                self._slow_available = True
                logger.info(
                    "RetrievalShadowService: slow (1Hz) engine loaded from %s", slow_dir
                )
            else:
                logger.info(
                    "RetrievalShadowService: slow index not available at %s "
                    "(run build_retrieval_slow_index.py to generate it)",
                    slow_dir,
                )

        except Exception as exc:
            logger.debug("RetrievalShadowService (slow) load failed: %s", exc)
        finally:
            self._slow_loaded = True

        return self._slow_available

    def query_window(
        self,
        window: List[Any],
        window_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # Canli pencereyi uygun indeksle sorgulayip retrieval sonucunu dondurur.
        if not self._loaded:
            self.load_once()

        sample_rate_warning = (
            window_status.get("sample_rate_warning", False)
            if window_status
            else False
        )

        if sample_rate_warning:
            # Ornekleme hizi uyusmazsa once yavas indeks denenir.
            if settings.RETRIEVAL_USE_SLOW_INDEX:
                if not self._slow_loaded:
                    self._load_slow_once()
                if self._slow_available and self._slow_engine is not None:
                    return self._query_with_engine(
                        self._slow_engine,
                        window,
                        window_status,
                        aligned_mode="slow_1hz",
                        low_confidence=False,
                    )

            # Yavas indeks yoksa dusuk guvenli sorgu izni kontrol edilir.
            if not settings.RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY:
                if settings.RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH:
                    logger.info(
                        "Retrieval SKIPPED: sample_rate_mismatch "
                        "(no slow index; set RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True to override)"
                    )
                    return {
                        "retrieval_available": False,
                        "retrieval_skipped": True,
                        "skip_reason": "sample_rate_mismatch",
                        "shadow_mode": True,
                        "low_confidence": True,
                    }

            # Gerekirse 50 Hz indeksine dusuk guven etiketiyle devam eder.
            if not self._available:
                return {
                    "retrieval_available": False,
                    "shadow_mode": True,
                    "error": self._load_error or "Engine not available",
                }
            return self._query_with_engine(
                self._engine,
                window,
                window_status,
                aligned_mode=None,
                low_confidence=True,
            )

        # Ornekleme hizi normalse varsayilan 50 Hz indeksini kullanir.
        if not self._available:
            return {
                "retrieval_available": False,
                "shadow_mode": True,
                "error": self._load_error or "Engine not available",
            }

        return self._query_with_engine(
            self._engine,
            window,
            window_status,
            aligned_mode=None,
            low_confidence=False,
        )

    def _query_with_engine(
        self,
        engine,
        window: List[Any],
        window_status: Optional[Dict[str, Any]],
        aligned_mode: Optional[str],
        low_confidence: bool,
    ) -> Dict[str, Any]:
        # Secilen motorla ozellik cikartip sorguyu tamamlar.
        try:
            feat_vec = self._build_feature_vector(window)
            result = engine.query(feat_vec, top_k=settings.RETRIEVAL_TOP_K)

            result["shadow_mode"] = True
            result["low_confidence"] = low_confidence
            if aligned_mode:
                result["aligned_mode"] = aligned_mode

            if low_confidence and not aligned_mode:
                result["low_confidence_reason"] = (
                    "Backend window collected at ~1 pkt/s (firmware PACKET_INTERVAL_MS=1000) "
                    "but retrieval index built on 50 Hz data. "
                    "Temporal features (frequency, duration) are on different scales."
                )

            return result

        except Exception as exc:
            logger.error("RetrievalShadowService._query_with_engine error: %s", exc)
            return {
                "retrieval_available": False,
                "shadow_mode": True,
                "error": str(exc),
            }

    # Servisin yukleme durumunu sifirlayip testler icin temiz baslangic saglar.
    def reset(self) -> None:
        with self._lock:
            self._loaded = False
            self._available = False
            self._load_error = None
            self._engine = None
            self._slow_loaded = False
            self._slow_available = False
            self._slow_engine = None

    @staticmethod
    # Pencere orneklerini retrieval ozellik vektorune donusturur.
    def _build_feature_vector(window: List[Any]) -> "np.ndarray":
        import numpy as np

        if _AI_ROOT not in sys.path:
            sys.path.insert(0, _AI_ROOT)

        from src.data.feature_engineering.feature_pipeline import (
            extract_all_handcrafted_features,
        )

        accel = np.array(
            [[s.accel_x, s.accel_y, s.accel_z] for s in window], dtype=np.float32
        )
        gyro = np.array(
            [[s.gyro_x, s.gyro_y, s.gyro_z] for s in window], dtype=np.float32
        )
        hr_signal = np.array([s.heart_rate for s in window], dtype=np.float32)
        spo2_signal = np.array([s.spo2 for s in window], dtype=np.float32)
        ppg_quality = float(np.mean([s.signal_quality for s in window]))

        feat_vec, _ = extract_all_handcrafted_features(
            accel=accel,
            gyro=gyro,
            hr_signal=hr_signal,
            spo2_signal=spo2_signal,
            ppg_quality=ppg_quality,
            sr=50,  # nominal â€” actual rate is ~1 pkt/s; flagged via low_confidence
        )

        return np.nan_to_num(feat_vec, nan=0.0, posinf=0.0, neginf=0.0)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
retrieval_shadow_service = RetrievalShadowService()
