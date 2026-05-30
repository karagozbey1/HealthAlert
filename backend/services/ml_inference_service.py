# Golge ML inference servisi tahminleri yalnizca ek metadata olarak uretir.
# Bu katman severity, alarm ve bildirim kararlarini hicbir zaman degistirmez.
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from config import settings  # module-level for testability (mock target)

logger = logging.getLogger("healthalert.ml_inference")

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# ml_inference_service.py  →  backend/services/
# backend/services/        →  backend/
# backend/                 →  project_root/
# project_root/            →  healthalert_final_ai/  (AI package)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_AI_ROOT = os.path.join(_PROJECT_ROOT, "healthalert_final_ai")


# Model dosyasi yolunu proje yapisina gore mutlak yola cozer.
def _resolve_model_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    candidate = os.path.join(_PROJECT_ROOT, path)
    if os.path.exists(candidate):
        return candidate
    candidate2 = os.path.join(_BACKEND_DIR, path)
    if os.path.exists(candidate2):
        return candidate2
    return path


# ---------------------------------------------------------------------------
# Servis
# ---------------------------------------------------------------------------

# Model yuklemesini tembel yapan ve kullanici bazli EMA durumunu ayiran servistir.
class MLInferenceService:
        # Yukleme, kullanilabilirlik ve EMA durum depolarini baslatir.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: bool = False
        self._available: bool = False
        self._load_error: Optional[str] = None
        self._predictor = None
        self._postprocessor = None
        self._model_version = "unloaded"

        # Her kullanici icin ayri EMA durumunu izler.
        self._ema_states_by_user: Dict[str, Dict[str, float]] = {}

        # Vitals boyutunu yukleme aninda cozer.
        self._resolved_vitals_dim: int = 3

    # Modelin yuklenip inference icin hazir olup olmadigini bildirir.
    def is_available(self) -> bool:
        return self._available

    # Modeli gerekirse bir kez yuklemeyi dener ve sonucu dondurur.
    def load_once(self) -> bool:
        with self._lock:
            if self._loaded:
                return self._available
            self._loaded = True
            return self._do_load()

    # Kilit altinda gercek model yukleme adimlarini calistirir.
    def _do_load(self) -> bool:
        if not settings.ML_INFERENCE_ENABLED:
            logger.info(
                "ML inference disabled (ML_INFERENCE_ENABLED=False). "
                "Shadow service will not load model."
            )
            self._load_error = "ML_INFERENCE_ENABLED=False"
            return False

        # Inject AI package into sys.path (idempotent).
        if _AI_ROOT not in sys.path:
            sys.path.insert(0, _AI_ROOT)

        model_path = _resolve_model_path(settings.ML_MODEL_PATH)
        self._model_version = os.path.splitext(os.path.basename(model_path))[0] or "unknown"

        if not os.path.exists(model_path):
            err = f"Checkpoint not found: {model_path!r}"
            logger.warning("ML inference unavailable — %s", err)
            self._load_error = err
            return False

        try:
            from src.inference.predictor import HealthAlertPredictor  # type: ignore
            from src.inference.risk_postprocessor_v2 import (  # type: ignore
                RiskPostprocessorV2,
            )

            self._predictor = HealthAlertPredictor.from_checkpoint(
                checkpoint_path=model_path,
                device="cpu",
                ema_alpha=0.3,
            )
            self._postprocessor = RiskPostprocessorV2()

            # Part 3.1 — resolve vitals dimension from config or model introspection.
            self._resolved_vitals_dim = self._detect_vitals_dim()

            self._available = True
            logger.info(
                "ML model loaded successfully from %s (vitals_dim=%d)",
                model_path,
                self._resolved_vitals_dim,
            )
            return True

        except ImportError as exc:
            err = f"Import error (PyTorch or healthalert_final_ai missing?): {exc}"
            logger.warning("ML inference unavailable — %s", err)
            self._load_error = err
            return False

        except Exception as exc:
            err = f"Model load failed: {exc}"
            logger.warning("ML inference unavailable — %s", err)
            self._load_error = err
            return False

    # ------------------------------------------------------------------
    # Part 3.1: Vitals dimension detection
    # ------------------------------------------------------------------

        # Modelin bekledigi vitals boyutunu ayardan veya modelden cikarir.
    def _detect_vitals_dim(self) -> int:
        cfg_dim = settings.ML_VITALS_DIM
        if cfg_dim and cfg_dim > 0:
            logger.info("vitals_dim from config: %d", cfg_dim)
            return int(cfg_dim)

        # Introspection: try to find VitalsMLP input dimension from model.
        try:
            import torch.nn as nn  # noqa: F401
            if self._predictor is not None and hasattr(self._predictor, "model"):
                model = self._predictor.model
                for name, module in model.named_modules():
                    if "vital" in name.lower():
                        for child in module.modules():
                            if hasattr(child, "in_features"):
                                detected = int(child.in_features)
                                logger.info(
                                    "vitals_dim auto-detected from model "
                                    "(%s.in_features): %d",
                                    name,
                                    detected,
                                )
                                return detected
        except Exception as exc:
            logger.debug("vitals_dim introspection failed: %s", exc)

        logger.info("vitals_dim fallback: 3")
        return 3

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    # Dolu pencere uzerinde golge inference calistirir ve sonuc sozlugunu dondurur.
    # Hata veya uyumsuzluk durumlarinda fail-open sonuc uretir.
    def predict_window(
        self,
        user_id: str,
        window: list,
        context: Optional[Dict[str, Any]] = None,
        window_status: Optional[Dict[str, Any]] = None,
    ) -> dict:
        # ── Part 3.1: Sample-rate alignment gate ────────────────────────────
        if window_status is not None:
            sample_rate_warning = window_status.get("sample_rate_warning", False)
            if (
                sample_rate_warning
                and settings.ML_SKIP_ON_SAMPLE_RATE_MISMATCH
                and not settings.ML_ALLOW_LOW_CONFIDENCE_INFERENCE
            ):
                logger.info(
                    "ML shadow SKIPPED for user=%s: sample_rate_mismatch "
                    "(estimated=%.1fs, expected=%.1fs). "
                    "Set ML_ALLOW_LOW_CONFIDENCE_INFERENCE=True to override.",
                    user_id,
                    window_status.get("estimated_window_duration_sec") or 0,
                    window_status.get("expected_duration_sec") or 0,
                )
                return {
                    "ml_available": False,
                    "ml_skipped": True,
                    "skip_reason": "sample_rate_mismatch",
                    "shadow_mode": True,
                    "low_confidence": True,
                    "estimated_window_duration_sec": window_status.get(
                        "estimated_window_duration_sec"
                    ),
                    "expected_duration_sec": window_status.get("expected_duration_sec"),
                    "ml_error": None,
                    "fall_probability": None,
                    "instability_probability": None,
                    "ppg_quality_score": None,
                    "ml_risk_score": None,
                    "ml_final_risk_level": None,
                    "ml_immediate_alert": None,
                    "ml_reasons": [],
                    "ml_recommendations": [],
                    "inference_latency_ms": None,
                    "window_status": None,
                }

        # Ilk inference cagrisinda modeli gerekirse yukler.
        if not self._loaded:
            self.load_once()

        if not self._available or self._predictor is None:
            return self._unavailable_result()

        try:
            import numpy as np  # noqa: F401 — ensures numpy available

            t0 = time.perf_counter_ns()

            # ── Part 3.1: EMA state isolation per user ───────────────────
            # Swap in the user's EMA state before predict(), swap out after.
            _default_ema = {
                "fall_prob": 0.0,
                "instability_prob": 0.0,
                "quality_score": 1.0,
                "risk_score": 0.0,
            }
            with self._lock:
                user_ema = self._ema_states_by_user.setdefault(
                    user_id, _default_ema.copy()
                )
                self._predictor._ema_state = user_ema.copy()

            inputs = self.build_predictor_inputs(window)
            raw_preds = self._predictor.predict(
                imu=inputs["imu"],
                ppg=inputs["ppg"],
                vitals=inputs["vitals"],
                smooth=True,
            )

            # Persist updated EMA state for this user.
            with self._lock:
                self._ema_states_by_user[user_id] = self._predictor._ema_state.copy()

            # Derive vitals context from the last sample.
            vitals_ctx: Dict[str, float] = {}
            if window:
                last = window[-1]
                vitals_ctx = {
                    "heart_rate": float(last.heart_rate),
                    "spo2": float(last.spo2),
                }

            result = self._postprocessor.process(
                predictions=raw_preds,
                vitals=vitals_ctx,
            )

            latency_ms = round((time.perf_counter_ns() - t0) / 1_000_000.0, 2)

            return {
                "ml_available": True,
                "ml_skipped": False,
                "ml_error": None,
                "fall_probability": result.get("fall_probability"),
                "instability_probability": result.get("instability_probability"),
                "ppg_quality_score": result.get("ppg_quality_score"),
                "ml_risk_score": result.get("early_risk_score"),
                "ml_final_risk_level": result.get("final_risk_level"),
                "ml_immediate_alert": result.get("immediate_alert"),
                "ml_reasons": result.get("reasons", []),
                "ml_recommendations": result.get("recommendations", []),
                "inference_latency_ms": latency_ms,
                "vitals_dim_used": self._resolved_vitals_dim,
                "window_status": None,  # populated by caller
                "shadow_mode": True,
            }

        except Exception as exc:
            logger.warning(
                "ML shadow inference failed for user=%s (fail-open): %s",
                user_id,
                exc,
            )
            if settings.ML_FAIL_OPEN:
                return {
                    "ml_available": False,
                    "ml_skipped": False,
                    "ml_error": str(exc),
                    "fall_probability": None,
                    "instability_probability": None,
                    "ppg_quality_score": None,
                    "ml_risk_score": None,
                    "ml_final_risk_level": None,
                    "ml_immediate_alert": None,
                    "ml_reasons": [],
                    "ml_recommendations": [],
                    "inference_latency_ms": None,
                    "window_status": None,
                    "shadow_mode": True,
                }
            raise

    # ------------------------------------------------------------------
    # Input construction
    # ------------------------------------------------------------------

        # WindowSample listesini predictorun bekledigi numpy girdilerine cevirir.
    def build_predictor_inputs(self, window: list) -> Dict[str, Any]:
        import numpy as np

        T = len(window)
        imu = np.zeros((T, 6), dtype=np.float32)
        ppg = np.zeros((T, 1), dtype=np.float32)

        for i, s in enumerate(window):
            imu[i, 0] = float(s.accel_x)
            imu[i, 1] = float(s.accel_y)
            imu[i, 2] = float(s.accel_z)
            imu[i, 3] = float(s.gyro_x)
            imu[i, 4] = float(s.gyro_y)
            imu[i, 5] = float(s.gyro_z)
            ppg[i, 0] = float(s.ir_value) / 100_000.0

        last = window[-1] if window else None
        if last is not None:
            hr = float(last.heart_rate)
            spo2_norm = float(last.spo2) / 100.0
            quality = float(last.signal_quality)
        else:
            hr, spo2_norm, quality = 72.0, 0.98, 1.0

        vitals_dim = self._resolved_vitals_dim
        if vitals_dim == 2:
            vitals = np.array([hr, spo2_norm], dtype=np.float32)
        else:
            vitals = np.array([hr, spo2_norm, quality], dtype=np.float32)

        return {"imu": imu, "ppg": ppg, "vitals": vitals}

    # Ham model cikisini backend fusion kontratina normalize eder.
    def normalize_model_output(
        self,
        raw_output: Optional[Dict[str, Any]],
        *,
        reason: str = "ok",
        ml_available: bool = True,
        model_ready: bool = True,
        sample_rate_warning: bool = False,
    ) -> Dict[str, Any]:
        raw_output = raw_output or {}
        return {
            "fall_probability": float(raw_output.get("fall_probability", 0.0) or 0.0),
            "instability_probability": float(
                raw_output.get("instability_probability", 0.0) or 0.0
            ),
            "ppg_quality_score": float(raw_output.get("ppg_quality_score", 1.0) or 1.0),
            "ml_risk_score": float(raw_output.get("ml_risk_score", 0.0) or 0.0),
            "confidence": float(raw_output.get("confidence", 0.0) or 0.0),
            "model_version": raw_output.get("model_version") or self._model_version,
            "ml_available": bool(ml_available and raw_output.get("ml_available", True)),
            "sample_rate_warning": bool(sample_rate_warning),
            "model_ready": bool(model_ready),
            "ml_skipped": bool(raw_output.get("ml_skipped", False)),
            "reason": reason,
        }

    # Hazir 50Hz model penceresi icin dogrudan inference calistirir.
    def predict_model_window(self, model_input: Dict[str, Any]) -> dict:
        if not self._loaded:
            self.load_once()

        sample_rate_warning = bool(
            (model_input.get("meta") or {}).get("sample_rate_warning", False)
        )
        model_ready = bool((model_input.get("meta") or {}).get("model_ready", False))
        base_result = self.normalize_model_output(
            None,
            reason="unavailable",
            ml_available=False,
            model_ready=model_ready,
            sample_rate_warning=sample_rate_warning,
        )

        if not self._available or self._predictor is None or self._postprocessor is None:
            return base_result

        try:
            import numpy as np

            imu = np.asarray(model_input.get("imu", []), dtype=np.float32)
            ppg = np.asarray(model_input.get("ppg", []), dtype=np.float32)
            vitals = np.asarray(model_input.get("vitals", [72.0, 0.98, 1.0]), dtype=np.float32)

            if imu.ndim != 2 or imu.shape[1] != 6:
                out = dict(base_result)
                out["reason"] = "invalid_imu_shape"
                out["ml_skipped"] = True
                return out

            if ppg.ndim != 2 or ppg.shape[0] != imu.shape[0] or ppg.shape[1] not in (1, 2):
                out = dict(base_result)
                out["reason"] = "invalid_ppg_shape"
                out["ml_skipped"] = True
                return out

            if ppg.shape[1] == 2:
                ppg = ppg[:, 1:2]

            # Predictor supports vitals vector length 2 or 3.
            if vitals.ndim != 1 or vitals.shape[0] not in (2, 3):
                out = dict(base_result)
                out["reason"] = "invalid_vitals_shape"
                out["ml_skipped"] = True
                return out

            raw_preds = self._predictor.predict(
                imu=imu,
                ppg=ppg,
                vitals=vitals,
                smooth=False,
            )
            post = self._postprocessor.process(
                predictions=raw_preds,
                vitals={
                    "heart_rate": float(vitals[0]) if vitals.shape[0] > 0 else 72.0,
                    "spo2": float(vitals[1] * 100.0) if vitals.shape[0] > 1 else 98.0,
                },
            )

            confidence = float(post.get("confidence", 0.0) or 0.0)
            return self.normalize_model_output(
                {
                    "fall_probability": float(post.get("fall_probability", 0.0) or 0.0),
                    "instability_probability": float(
                        post.get("instability_probability", 0.0) or 0.0
                    ),
                    "ppg_quality_score": float(post.get("ppg_quality_score", 1.0) or 1.0),
                    "ml_risk_score": float(post.get("early_risk_score", 0.0) or 0.0),
                    "confidence": confidence,
                    "model_version": self._model_version,
                    "ml_available": True,
                },
                reason="ok",
                ml_available=True,
                model_ready=model_ready,
                sample_rate_warning=sample_rate_warning,
            )
        except Exception as exc:
            logger.warning("Model-window inference failed (fail-open): %s", exc)
            if settings.ML_FAIL_OPEN:
                out = dict(base_result)
                out["reason"] = "inference_exception"
                out["ml_error"] = str(exc)
                return out
            raise

    # ------------------------------------------------------------------
    # Per-user state reset
    # ------------------------------------------------------------------

    # Kullaniciya ait EMA durumunu temizleyerek yeni bir baslangic saglar.
    def reset_user_state(self, user_id: str) -> None:
        with self._lock:
            self._ema_states_by_user.pop(user_id, None)
        if self._predictor is not None:
            try:
                self._predictor.reset()
            except Exception:
                pass

    # Servis kullanilamaz durumdayken donulecek standart sonucu uretir.
    def _unavailable_result(self) -> dict:
        return {
            "ml_available": False,
            "ml_skipped": False,
            "ml_error": self._load_error or "Service not initialised",
            "fall_probability": None,
            "instability_probability": None,
            "ppg_quality_score": None,
            "ml_risk_score": None,
            "ml_final_risk_level": None,
            "ml_immediate_alert": None,
            "ml_reasons": [],
            "ml_recommendations": [],
            "inference_latency_ms": None,
            "window_status": None,
            "shadow_mode": True,
        }


# ---------------------------------------------------------------------------
# Module-level singleton used by ingestion_router
# ---------------------------------------------------------------------------

ml_inference_service = MLInferenceService()
