# Ogrenme dongusu icin pencere yakalama, geri bildirim ve disa aktarma islemlerini yonetir.
# Bu servis final_risk_score degerini ve alarm karar akislarini degistirmez.
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from config import settings

logger = logging.getLogger("healthalert.learning")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Kullanici veya cihaz kimligini kararlı ve geri donussuz sekilde anonimlestirir.
def _anon_id(raw_id: str) -> str:
    return hashlib.sha256(raw_id.encode()).hexdigest()[:16]


# Kayitsiz UTC zaman damgasi uretir.
def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


# Paket modunu ogrenme kaynagi etiketine cevirir.
def _source_from_packet(packet_mode: str) -> str:
    if packet_mode in {"mock", "demo", "presentation_safe"}:
        return "demo"
    return "live"


# ---------------------------------------------------------------------------
# Capture decision
# ---------------------------------------------------------------------------

# O anki kosullarda bir ogrenme penceresi kaydedilip kaydedilmeyecegini belirler.
def should_capture_window(
    *,
    user_id: str,
    packet_mode: str,
    final_risk_score: float,
    quality_confidence: float,
    risk_level: Optional[str],
    baseline_ready: bool,
) -> bool:
    if not settings.LEARNING_LOOP_ENABLED:
        return False

    if (
        _source_from_packet(packet_mode) == "demo"
        and not settings.LEARNING_ALLOW_DEMO_AS_TRAINING
    ):
        return False

    if risk_level == "critical" and settings.LEARNING_CAPTURE_CRITICAL_ALWAYS:
        return True
    if risk_level == "warning" and settings.LEARNING_CAPTURE_WARNING_ALWAYS:
        return True
    if risk_level == "watch":
        # Capture watch at 3× the normal rate
        return random.random() < min(1.0, settings.LEARNING_CAPTURE_NORMAL_RATE * 3)

    # Normal / None — sample probabilistically
    return random.random() < settings.LEARNING_CAPTURE_NORMAL_RATE


# Kalite ve kaynak kosullarina gore pencerenin egitime aday olup olmadigini belirler.
def _is_training_candidate(
    *,
    quality_confidence: float,
    source: str,
) -> bool:
    if quality_confidence < settings.LEARNING_MIN_QUALITY_CONFIDENCE:
        return False
    if source == "demo" and not settings.LEARNING_ALLOW_DEMO_AS_TRAINING:
        return False
    return True


# ---------------------------------------------------------------------------
# Label suggestion
# ---------------------------------------------------------------------------

# Heuristik, ML ve retrieval sinyallerinden egitim etiketi onerisi uretir.
def suggest_label(
    *,
    final_risk_score: float,
    risk_level: Optional[str],
    risk_breakdown: Optional[Dict[str, Any]],
    ml_shadow_result: Optional[Dict[str, Any]],
    retrieval_shadow_result: Optional[Dict[str, Any]],
    user_feedback: Optional[str] = None,
) -> Dict[str, Any]:
    # If user explicitly gave feedback, map to suggested label
    _feedback_to_label = {
        "ok": "normal",
        "false_alarm": "normal",
        "not_ok": "warning",
        "fall_confirmed": "fall_like",
        "sensor_error": "sensor_error",
        "other": None,
    }
    if user_feedback and user_feedback in _feedback_to_label:
        mapped = _feedback_to_label[user_feedback]
        if mapped:
            return {"suggested_label": mapped, "label_confidence": 0.90}

    # Heuristic baseline label
    heuristic_label_map = {
        "critical": "critical",
        "warning": "warning",
        "watch": "watch",
        None: "normal",
    }
    base_label = heuristic_label_map.get(risk_level, "normal")
    confidence = 0.60

    # ML shadow agreement boosts confidence
    if ml_shadow_result and not ml_shadow_result.get("ml_skipped"):
        ml_level = ml_shadow_result.get("ml_final_risk_level")
        ml_label_map = {
            "critical": "critical",
            "warning": "warning",
            "watch": "watch",
            "normal": "normal",
        }
        ml_label = ml_label_map.get(ml_level)
        if ml_label and ml_label == base_label:
            confidence = min(0.90, confidence + 0.20)

    # Retrieval shadow agreement boosts confidence
    if retrieval_shadow_result and not retrieval_shadow_result.get("retrieval_skipped"):
        support = retrieval_shadow_result.get("support_score", 0.0)
        if support > 0.70:
            confidence = min(0.92, confidence + 0.10)

    return {"suggested_label": base_label, "label_confidence": round(confidence, 3)}


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------

# Repository katmani uzerinden ogrenme penceresi ve geri bildirim islemlerini yurutur.
class LearningDataService:
    # Gelen olaydan ogrenme penceresi olusturup depoya kaydeder.
    # Tum hatalar yutulur ve fail-open olarak None doner.
    async def build_and_save_window(
        self,
        *,
        repos,
        user_id: str,
        device_id: str,
        packet_mode: str,
        final_risk_score: float,
        quality_confidence: float,
        risk_level: Optional[str],
        baseline_ready: bool,
        risk_breakdown: Optional[Dict[str, Any]],
        window_status: Optional[Dict[str, Any]],
        ml_shadow_result: Optional[Dict[str, Any]],
        retrieval_shadow_result: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        try:
            if repos.learning is None:
                return None

            source = _source_from_packet(packet_mode)
            training_candidate = _is_training_candidate(
                quality_confidence=quality_confidence,
                source=source,
            )

            label_info = suggest_label(
                final_risk_score=final_risk_score,
                risk_level=risk_level,
                risk_breakdown=risk_breakdown,
                ml_shadow_result=ml_shadow_result,
                retrieval_shadow_result=retrieval_shadow_result,
            )

            now = _utcnow()

            # Compact shadow summaries — only relevant keys
            ml_summary = None
            if ml_shadow_result:
                ml_summary = {
                    k: ml_shadow_result.get(k)
                    for k in (
                        "ml_final_risk_level",
                        "ml_risk_score",
                        "ml_skipped",
                        "shadow_mode",
                        "inference_latency_ms",
                    )
                    if ml_shadow_result.get(k) is not None
                }

            retrieval_summary = None
            if retrieval_shadow_result:
                retrieval_summary = {
                    k: retrieval_shadow_result.get(k)
                    for k in (
                        "support_score",
                        "retrieval_skipped",
                        "low_confidence",
                        "shadow_mode",
                        "top_k_labels",
                    )
                    if retrieval_shadow_result.get(k) is not None
                }

            sample_count = (
                window_status.get("current_size", 1) if window_status else 1
            )

            window_data = {
                "id": str(uuid4()),
                "user_id": user_id,
                "device_id": device_id,
                "session_id": None,
                "window_start_at": now,
                "window_end_at": now,
                "duration_sec": float(sample_count),
                "sample_count": sample_count,
                "source": source,
                "risk_level_at_capture": risk_level or "normal",
                "final_risk_score": float(final_risk_score),
                "quality_confidence": float(quality_confidence),
                "baseline_ready": bool(baseline_ready),
                "ml_shadow_summary": ml_summary,
                "retrieval_shadow_summary": retrieval_summary,
                "assistant_mode": None,
                "user_feedback_label": None,
                "suggested_label": label_info.get("suggested_label"),
                "label_confidence": label_info.get("label_confidence"),
                "training_candidate": training_candidate,
                "exported_at": None,
                "created_at": now,
            }

            saved = await repos.learning.create_window(window_data)
            logger.debug(
                "LearningWindow created id=%s user=%s candidate=%s label=%s",
                saved["id"], user_id, training_candidate, label_info.get("suggested_label"),
            )

            return {
                "captured": True,
                "window_id": saved["id"],
                "training_candidate": training_candidate,
                "suggested_label": label_info.get("suggested_label"),
            }

        except Exception as exc:
            logger.warning(
                "Learning capture failed for user=%s (ignored): %s", user_id, exc
            )
            return None

    # Kullanici geri bildirimini kaydeder ve bagli pencere etiketini gunceller.
    async def attach_feedback(
        self,
        *,
        repos,
        user_id: str,
        related_window_id: Optional[str],
        related_alert_id: Optional[str],
        feedback_type: str,
        feedback_source: str,
        note: Optional[str],
    ) -> Dict[str, Any]:
        if repos.learning is None:
            raise RuntimeError("learning repo unavailable")

        feedback_data = {
            "id": str(uuid4()),
            "user_id": user_id,
            "related_window_id": related_window_id,
            "related_alert_id": related_alert_id,
            "feedback_type": feedback_type,
            "feedback_source": feedback_source,
            "note": note,
            "created_at": _utcnow(),
        }
        saved = await repos.learning.create_feedback(feedback_data)

        # Update linked window
        if related_window_id:
            try:
                # sensor_error → exclude from training; false_alarm → keep but re-label
                await repos.learning.update_window_feedback(
                    related_window_id, feedback_type
                )
            except Exception as exc:
                logger.warning(
                    "Could not update window feedback label window=%s: %s",
                    related_window_id, exc,
                )
        # Feedback olayini personalization memory katmanina da baglar.
        try:
            if repos.personalization is not None:
                await repos.personalization.add_risk_memory({
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "event_type": feedback_type,
                    "risk_score": 0.0,
                    "severity": None,
                    "context_json": {
                        "feedback_source": feedback_source,
                        "related_window_id": related_window_id,
                        "related_alert_id": related_alert_id,
                    },
                    "created_at": _utcnow(),
                })
        except Exception as exc:
            logger.warning(
                "Could not attach feedback to personalization memory: %s", exc
            )
        return saved

    # Egitime hazir pencereleri anonimlestirilmis JSONL dosyalari olarak disa aktarir.
    async def export_training_dataset(
        self,
        *,
        repos,
        user_id: Optional[str] = None,
        include_demo: bool = False,
        min_quality_confidence: Optional[float] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        if repos.learning is None:
            raise RuntimeError("learning repo unavailable")

        min_qc = (
            min_quality_confidence
            if min_quality_confidence is not None
            else settings.LEARNING_MIN_QUALITY_CONFIDENCE
        )

        windows = await repos.learning.list_windows_for_export(
            user_id=user_id,
            include_demo=include_demo,
            min_quality_confidence=min_qc,
            limit=limit,
        )

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(settings.LEARNING_EXPORT_DIR, timestamp_str)
        os.makedirs(export_dir, exist_ok=True)

        window_ids = []
        feedback_rows: List[Dict[str, Any]] = []

        windows_path = os.path.join(export_dir, "windows.jsonl")
        with open(windows_path, "w", encoding="utf-8") as f:
            for w in windows:
                window_ids.append(w["id"])
                # Collect feedback for this window
                fb_list = await repos.learning.get_feedback_for_window(w["id"])
                feedback_rows.extend(fb_list)

                row = {
                    "window_id": w["id"],
                    "user_id_hash": _anon_id(w["user_id"]),
                    "device_id_hash": _anon_id(w["device_id"]),
                    "window_start_at": w["window_start_at"].isoformat()
                    if hasattr(w["window_start_at"], "isoformat")
                    else str(w["window_start_at"]),
                    "duration_sec": w["duration_sec"],
                    "source": w["source"],
                    "risk_level_at_capture": w["risk_level_at_capture"],
                    "final_risk_score": w["final_risk_score"],
                    "quality_confidence": w["quality_confidence"],
                    "baseline_ready": w["baseline_ready"],
                    "ml_shadow_summary": w.get("ml_shadow_summary"),
                    "retrieval_shadow_summary": w.get("retrieval_shadow_summary"),
                    "user_feedback_label": w.get("user_feedback_label"),
                    "suggested_label": w.get("suggested_label"),
                    "label_confidence": w.get("label_confidence"),
                    "training_candidate": w["training_candidate"],
                }
                f.write(json.dumps(row, default=str) + "\n")

        feedback_path = os.path.join(export_dir, "feedback.jsonl")
        with open(feedback_path, "w", encoding="utf-8") as f:
            for fb in feedback_rows:
                row = {
                    "feedback_id": fb["id"],
                    "user_id_hash": _anon_id(fb["user_id"]),
                    "related_window_id": fb.get("related_window_id"),
                    "feedback_type": fb["feedback_type"],
                    "feedback_source": fb["feedback_source"],
                    "created_at": fb["created_at"].isoformat()
                    if hasattr(fb["created_at"], "isoformat")
                    else str(fb["created_at"]),
                }
                f.write(json.dumps(row, default=str) + "\n")

        # Mark windows as exported
        exported_count = await repos.learning.mark_windows_exported(window_ids)

        summary = {
            "export_dir": export_dir,
            "window_count": len(windows),
            "feedback_count": len(feedback_rows),
            "exported_at": datetime.utcnow().isoformat(),
            "filters": {
                "user_id": user_id,
                "include_demo": include_demo,
                "min_quality_confidence": min_qc,
                "limit": limit,
            },
        }
        summary_path = os.path.join(export_dir, "export_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(
            "Training export complete: %d windows, %d feedback → %s",
            len(windows), len(feedback_rows), export_dir,
        )
        return summary

    # Model-window ham penceresini (opsiyonel) anonimlestirip JSONL olarak disa yazar.
    async def capture_model_window_export(
        self,
        *,
        user_id: str,
        device_id: str,
        payload: Dict[str, Any],
        quality_summary: Dict[str, Any],
        ml_result: Optional[Dict[str, Any]],
        ml_evidence_result: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not settings.MODEL_WINDOW_RAW_EXPORT_ENABLED:
            return None

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H")
        export_dir = os.path.join("outputs", "model_windows", timestamp_str)
        os.makedirs(export_dir, exist_ok=True)

        windows_path = os.path.join(export_dir, "windows.jsonl")
        labels_path = os.path.join(export_dir, "labels.jsonl")
        summary_path = os.path.join(export_dir, "summary.json")

        window_id = (
            f"mw_{payload.get('window_seq')}_{payload.get('timestamp_start_ms')}"
        )
        row = {
            "window_id": window_id,
            "user_id_hash": _anon_id(user_id),
            "device_id_hash": _anon_id(device_id),
            "sample_rate_hz": payload.get("sample_rate_hz"),
            "sample_count": payload.get("sample_count"),
            "imu_samples": payload.get("imu_samples", []),
            "ppg_samples": payload.get("ppg_samples", []),
            "ml_result": ml_result or {},
            "ml_evidence_result": ml_evidence_result or {},
            "user_feedback_label": None,
            "suggested_label": (ml_result or {}).get("final_risk_level"),
            "source": payload.get("source"),
            "mode": payload.get("mode"),
            "quality_summary": quality_summary or {},
        }
        with open(windows_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")

        label_row = {
            "window_id": window_id,
            "user_id_hash": row["user_id_hash"],
            "suggested_label": row["suggested_label"],
            "ml_confidence": (ml_evidence_result or {}).get("ml_confidence"),
            "created_at": datetime.utcnow().isoformat(),
        }
        with open(labels_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(label_row, default=str) + "\n")

        summary = {
            "export_type": "model_window_raw",
            "raw_export_enabled": True,
            "updated_at": datetime.utcnow().isoformat(),
            "directory": export_dir,
        }
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

        return {"export_dir": export_dir, "window_id": window_id}

    # Kullaniciya ait ogrenme verisinin toplu istatistiklerini dondurur.
    async def summarize_user_learning_data(
        self,
        *,
        repos,
        user_id: str,
    ) -> Dict[str, Any]:
        if repos.learning is None:
            return {"user_id": user_id, "available": False, "reason": "learning repo unavailable"}

        windows = await repos.learning.list_windows(user_id=user_id, limit=10_000)
        total = len(windows)
        candidates = sum(1 for w in windows if w["training_candidate"])
        exported = sum(1 for w in windows if w.get("exported_at"))
        with_feedback = sum(1 for w in windows if w.get("user_feedback_label"))

        label_dist: Dict[str, int] = {}
        for w in windows:
            lbl = w.get("suggested_label") or "unknown"
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

        source_dist: Dict[str, int] = {}
        for w in windows:
            src = w.get("source") or "unknown"
            source_dist[src] = source_dist.get(src, 0) + 1

        return {
            "user_id": user_id,
            "available": True,
            "total_windows": total,
            "training_candidates": candidates,
            "exported_windows": exported,
            "windows_with_feedback": with_feedback,
            "label_distribution": label_dist,
            "source_distribution": source_dist,
        }


# Module-level singleton
learning_data_service = LearningDataService()

