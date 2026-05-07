from __future__ import annotations

from typing import Any, Dict, List


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


# Host tarafindan gelen pencere verisini model girdisine donusturur.
class ModelWindowAdapterService:

    def validate_model_window(self, payload) -> Dict[str, Any]:
        sample_count = int(payload.sample_count)
        sample_rate = int(payload.sample_rate_hz)
        duration_ms = int(payload.window_duration_ms)

        expected_duration_ms = 4000
        duration_error = abs(duration_ms - expected_duration_ms)
        sample_rate_warning = sample_rate != 50

        model_ready = (
            sample_count == 200
            and sample_rate == 50
            and duration_error <= 600
        )

        reason = "ok"
        if sample_count != 200:
            reason = "invalid_sample_count"
        elif sample_rate != 50:
            reason = "sample_rate_mismatch"
        elif duration_error > 600:
            reason = "window_duration_mismatch"

        return {
            "model_ready": model_ready,
            "reason": reason,
            "sample_rate_warning": sample_rate_warning,
            "duration_error_ms": duration_error,
        }

    def compute_model_window_quality(self, payload) -> Dict[str, Any]:
        qs = payload.quality_summary or {}

        sample_count = int(payload.sample_count)
        expected_sample_count = int(qs.get("expected_sample_count", 200))
        duration_ms = int(payload.window_duration_ms)
        effective_sr = (
            (sample_count / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0
        )

        imu_ok_ratio = float(qs.get("imu_ok_ratio", 1.0))
        ppg_ok_ratio = float(qs.get("ppg_ok_ratio", 1.0))
        finger_ratio = float(qs.get("finger_detected_ratio", 1.0))
        avg_signal_quality = _clamp01(float(qs.get("avg_signal_quality", 1.0)))

        missing = max(0, expected_sample_count - sample_count)
        model_ready = (
            sample_count == 200
            and int(payload.sample_rate_hz) == 50
            and duration_ms > 0
            and abs(duration_ms - 4000) <= 600
            and missing == 0
        )

        return {
            "sample_count": sample_count,
            "expected_sample_count": expected_sample_count,
            "missing_sample_count": missing,
            "duration_ms": duration_ms,
            "effective_sample_rate_hz": round(effective_sr, 3),
            "imu_ok_ratio": _clamp01(imu_ok_ratio),
            "ppg_ok_ratio": _clamp01(ppg_ok_ratio),
            "finger_detected_ratio": _clamp01(finger_ratio),
            "avg_signal_quality": avg_signal_quality,
            "model_ready": model_ready,
        }

    def select_ppg_channel(self, payload) -> List[float]:
        ppg_samples = payload.ppg_samples or []
        if not ppg_samples:
            return []

        first = ppg_samples[0]
        if len(first) >= 2:
            # Her iki kanal varsa model girdisinde IR kanalini tercih eder.
            return [float(row[1]) for row in ppg_samples]
        return [float(row[0]) for row in ppg_samples]

    def normalize_window_if_needed(self, payload) -> Dict[str, Any]:
        imu_samples = [[float(v) for v in row] for row in payload.imu_samples]
        ppg_samples = [[float(v) for v in row] for row in payload.ppg_samples]
        return {"imu_samples": imu_samples, "ppg_samples": ppg_samples}

    def to_model_input(self, payload) -> Dict[str, Any]:
        normalized = self.normalize_window_if_needed(payload)
        imu_samples = normalized["imu_samples"]
        ppg_channel = self.select_ppg_channel(payload)

        latest_vitals = payload.latest_vitals or {}
        hr = float(latest_vitals.get("heart_rate", 72.0))
        spo2 = float(latest_vitals.get("spo2", 98.0))
        signal_quality = float(
            latest_vitals.get(
                "signal_quality",
                (payload.quality_summary or {}).get("avg_signal_quality", 1.0),
            )
        )

        return {
            "imu": imu_samples,
            "ppg": [[v] for v in ppg_channel],
            "vitals": [hr, spo2 / 100.0, signal_quality],
            "meta": {
                "device_id": payload.device_id,
                "window_seq": payload.window_seq,
                "sample_rate_hz": payload.sample_rate_hz,
                "sample_count": payload.sample_count,
                "mode": payload.mode,
                "source": payload.source,
            },
        }


model_window_adapter_service = ModelWindowAdapterService()
