from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import ModelWindowLog
from repositories.factory import RepoSet
from routers.deps import get_repo_set
from schemas import DeviceModelWindowRequest, DeviceModelWindowResponse
from services.adaptive_personalization_service import adaptive_personalization_service
from services.ml_evidence_fusion_service import ml_evidence_fusion_service
from services.ml_inference_service import ml_inference_service
from services.model_window_adapter_service import model_window_adapter_service
from services.learning_data_service import learning_data_service

router = APIRouter(prefix="/ingest", tags=["model-window-ingestion"])


@router.post("/model-window", response_model=DeviceModelWindowResponse)
async def ingest_model_window(
    payload: DeviceModelWindowRequest,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
):
    reg = await repos.devices.get_registration(payload.device_id)
    user_id = reg["user_id"] if reg else None

    validation = model_window_adapter_service.validate_model_window(payload)
    quality = model_window_adapter_service.compute_model_window_quality(payload)
    model_ready = bool(validation["model_ready"] and quality["model_ready"])

    ml_live_result: dict | None = None
    ml_evidence_result: dict | None = None
    fusion_result: dict | None = None
    final_risk_score: float | None = None
    reason = validation["reason"]

    if user_id:
        model_input = model_window_adapter_service.to_model_input(payload)
        model_input["meta"]["model_ready"] = model_ready
        model_input["meta"]["sample_rate_warning"] = validation["sample_rate_warning"]

        if model_ready:
            ml_live_result = await asyncio.to_thread(
                ml_inference_service.predict_model_window,
                model_input,
            )
        else:
            ml_live_result = {
                "fall_probability": 0.0,
                "instability_probability": 0.0,
                "ppg_quality_score": quality.get("avg_signal_quality", 1.0),
                "ml_risk_score": 0.0,
                "confidence": 0.0,
                "ml_available": False,
                "sample_rate_warning": validation["sample_rate_warning"],
                "model_ready": False,
                "ml_skipped": True,
                "reason": "model_window_not_ready",
            }

        ml_evidence_result = ml_evidence_fusion_service.compute_ml_evidence_score(
            ml_live_result, quality
        )

        current = await repos.live_status.get_by_user(user_id)
        personalized_risk_score = float(current["risk_score"]) if current else 0.0
        fusion_result = ml_evidence_fusion_service.apply_ml_evidence_adjustment(
            personalized_risk_score,
            ml_evidence_result,
            model_ready=model_ready,
            sample_rate_warning=validation["sample_rate_warning"],
        )
        final_risk_score = float(fusion_result["final_risk_score"])

        latest = payload.latest_vitals or {}
        heart_rate = float(
            latest.get("heart_rate", current["heart_rate"] if current else 72.0)
        )
        spo2 = float(latest.get("spo2", current["spo2"] if current else 98.0))
        motion = float(current["motion_score"]) if current else 0.0
        scenario = (
            current["scenario"]
            if current and current.get("scenario")
            else "model_window_ingest"
        )

        await repos.live_status.upsert(
            user_id,
            {
                "heart_rate": heart_rate,
                "spo2": spo2,
                "motion_score": motion,
                "risk_score": final_risk_score,
                "scenario": scenario,
                "timestamp": datetime.utcnow(),
            },
        )

        await adaptive_personalization_service.update_profile_from_ml_window(
            repos=repos,
            user_id=user_id,
            ml_evidence_result=ml_evidence_result,
            fusion_result=fusion_result,
            window_quality=quality,
        )

        await learning_data_service.capture_model_window_export(
            user_id=user_id,
            device_id=payload.device_id,
            payload=payload.model_dump(),
            quality_summary=quality,
            ml_result=ml_live_result,
            ml_evidence_result=ml_evidence_result,
        )

    # Store compact metadata log only; raw samples are not persisted.
    try:
        db.add(
            ModelWindowLog(
                id=str(uuid4()),
                user_id=user_id,
                device_id=payload.device_id,
                window_seq=payload.window_seq,
                sample_rate_hz=payload.sample_rate_hz,
                sample_count=payload.sample_count,
                mode=payload.mode,
                source=payload.source,
                model_ready=model_ready,
                avg_signal_quality=quality.get("avg_signal_quality"),
                ml_evidence_score=(
                    ml_evidence_result.get("ml_evidence_score")
                    if ml_evidence_result
                    else None
                ),
                ml_adjustment=(
                    fusion_result.get("ml_adjustment") if fusion_result else None
                ),
                created_at=datetime.utcnow(),
            )
        )
    except Exception:
        # Log yazimi basarisiz olsa bile ingestion akisini kesmez.
        pass

    await db.commit()

    if not user_id:
        reason = "device_unregistered"

    return DeviceModelWindowResponse(
        status="accepted",
        device_id=payload.device_id,
        user_id=user_id,
        window_seq=payload.window_seq,
        model_ready=model_ready,
        ml_live_result=ml_live_result,
        ml_evidence_result=ml_evidence_result,
        fusion_result=fusion_result,
        final_risk_score=final_risk_score,
        reason=reason,
    )
