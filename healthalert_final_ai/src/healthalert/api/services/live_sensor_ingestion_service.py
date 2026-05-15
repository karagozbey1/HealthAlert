from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.healthalert.api.schemas.hybrid_inference_schema import HybridInferenceRequest
from src.healthalert.api.schemas.live_sensor_schema import (
    LiveSensorSampleRequest,
    LiveSensorSampleResponse,
)
from src.healthalert.api.services.hybrid_inference_api_service import HybridInferenceAPIService
from src.healthalert.inference.live_window_buffer import LiveWindowBuffer


log = logging.getLogger("uvicorn.error")


class LiveSensorIngestionService:
    def __init__(
        self,
        *,
        config_path: str = "config/hybrid_runtime_config.yaml",
        persistence_dir: str = "outputs/hybrid_redesign/live_stream",
    ) -> None:
        self.hybrid_api = HybridInferenceAPIService(config_path=config_path)
        self.buffers: Dict[str, LiveWindowBuffer] = {}
        self.persistence_dir = Path(persistence_dir)
        self.persistence_dir.mkdir(parents=True, exist_ok=True)

    def _get_buffer(self, patient_id: str) -> LiveWindowBuffer:
        if patient_id not in self.buffers:
            self.buffers[patient_id] = LiveWindowBuffer()
        return self.buffers[patient_id]

    def ingest_sample(self, payload: LiveSensorSampleRequest) -> LiveSensorSampleResponse:
        sample = payload.model_dump()
        buffer = self._get_buffer(payload.patient_id)
        result = buffer.add_sample(payload.patient_id, sample)

        notes = []
        if not result["accepted_sample"]:
            notes.append(result["reason"])
            log.info(
                "live_sample_skipped patient_id=%s reason=%s buffered_imu_samples=%s",
                payload.patient_id,
                result["reason"],
                result["buffered_imu_samples"],
            )
        elif not result["window_ready"]:
            notes.append("window_buffer_collecting")
            buffered = int(result["buffered_imu_samples"])
            if buffered in {1, 50, 100, 150, 199}:
                log.info(
                    "live_sample_received patient_id=%s buffered_imu_samples=%s window_ready=false",
                    payload.patient_id,
                    buffered,
                )

        missing = {
            "imu_missing": payload.imu is None,
            "ppg_missing": payload.ppg is None,
            "baseline_missing": payload.user_baseline is None,
        }

        if not result["window_ready"]:
            return LiveSensorSampleResponse(
                patient_id=payload.patient_id,
                timestamp=payload.timestamp,
                data_mode="live",
                window_ready=False,
                buffered_imu_samples=result["buffered_imu_samples"],
                inference_triggered=False,
                status="buffering",
                missing_modalities=missing,
                ingestion_notes=notes,
            )

        ready = result["window"]
        if ready is None:
            return LiveSensorSampleResponse(
                patient_id=payload.patient_id,
                timestamp=payload.timestamp,
                data_mode="live",
                window_ready=False,
                buffered_imu_samples=result["buffered_imu_samples"],
                inference_triggered=False,
                status="buffering",
                missing_modalities=missing,
                ingestion_notes=notes + ["window_not_available"],
            )

        req = HybridInferenceRequest(
            patient_id=payload.patient_id,
            timestamp=payload.timestamp,
            data_mode="live",
            imu_window=ready.imu_window.tolist(),
            ppg_window=None if ready.ppg_window is None else ready.ppg_window.squeeze(-1).tolist(),
            heart_rate=ready.vitals_values.get("hr"),
            spo2=ready.vitals_values.get("spo2"),
            user_baseline=payload.user_baseline,
            user_confirmed_okay=payload.user_confirmed_okay,
        )
        inference_result = self.hybrid_api.infer(req)
        inference_event = self._mobile_event(inference_result.model_dump())
        self._persist_event(inference_event)
        self._persist_latest(inference_result.model_dump())
        log.info(
            "live_inference_completed patient_id=%s buffered_imu_samples=%s final_risk_score=%.3f risk_level=%s latest_json=%s",
            payload.patient_id,
            result["buffered_imu_samples"],
            inference_result.risk.final_risk_score,
            inference_result.risk.risk_level,
            self.persistence_dir / f"{payload.patient_id}_latest.json",
        )

        slide_info = buffer.reset_or_slide(payload.patient_id)
        if ready.ppg_window is None:
            notes.append("ppg_missing_window_level")
        notes.extend(["inference_completed", f"window_slide_{slide_info['strategy']}"])

        return LiveSensorSampleResponse(
            patient_id=payload.patient_id,
            timestamp=payload.timestamp,
            data_mode="live",
            window_ready=True,
            buffered_imu_samples=result["buffered_imu_samples"],
            inference_triggered=True,
            status="inference_completed",
            inference_result=inference_result,
            missing_modalities={
                "imu_missing": False,
                "ppg_missing": ready.ppg_window is None,
                "baseline_missing": inference_result.personalization.cold_start_mode,
            },
            ingestion_notes=notes,
        )

    @staticmethod
    def _mobile_event(event: Dict[str, Any]) -> Dict[str, Any]:
        risk = event["risk"]
        return {
            "patient_id": event["patient_id"],
            "timestamp": event["timestamp"],
            "final_risk_score": risk["final_risk_score"],
            "risk_level": risk["risk_level"],
            "recommended_action": risk["recommended_action"],
            "reasons": risk["reasons"],
            "missing_modalities": event["missing_modalities"],
            "experts": event["experts"],
            "data_mode": event["data_mode"],
        }

    def _persist_event(self, event: Dict[str, Any]) -> None:
        patient_id = str(event["patient_id"])
        aggregate = self.persistence_dir / "live_inference_events.jsonl"
        patient_out = self.persistence_dir / f"{patient_id}_events.jsonl"
        line = json.dumps(event, ensure_ascii=True)
        with open(aggregate, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(patient_out, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _persist_latest(self, event: Dict[str, Any]) -> None:
        patient_id = str(event["patient_id"])
        out = self.persistence_dir / f"{patient_id}_latest.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(event, f, indent=2, ensure_ascii=True)
