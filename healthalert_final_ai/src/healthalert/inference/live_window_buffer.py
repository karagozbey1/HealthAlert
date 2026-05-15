from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional

import numpy as np


WINDOW_SIZE = 200
TARGET_HZ = 50
DEFAULT_OVERLAP_SIZE = 100


@dataclass
class LiveWindowReady:
    imu_window: np.ndarray
    ppg_window: Optional[np.ndarray]
    vitals_values: Dict[str, float]
    metadata: Dict[str, Any]


class LiveWindowBuffer:
    """
    Patient-specific streaming buffer for ESP32 samples.

    Window contract:
    - Target IMU cadence is 50 Hz.
    - One inference window is 4 seconds / 200 samples.
    - IMU output shape is (200, 6).
    - PPG output shape is (200, 1) when present, otherwise None.
    - Inference is called only after a full IMU window is ready.
    - After inference the buffer slides by 50% overlap, retaining 100 samples.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        target_hz: int = TARGET_HZ,
        overlap_size: int = DEFAULT_OVERLAP_SIZE,
    ) -> None:
        if overlap_size < 0 or overlap_size >= window_size:
            raise ValueError("overlap_size must be >= 0 and smaller than window_size")
        self.window_size = int(window_size)
        self.target_hz = int(target_hz)
        self.overlap_size = int(overlap_size)
        self.window_seconds = self.window_size / float(self.target_hz)
        self._imu: Deque[np.ndarray] = deque(maxlen=window_size)
        self._ppg: Deque[Optional[float]] = deque(maxlen=window_size)
        self._hr: Deque[Optional[float]] = deque(maxlen=window_size)
        self._spo2: Deque[Optional[float]] = deque(maxlen=window_size)
        self._timestamps: Deque[str] = deque(maxlen=window_size)
        self._skipped_samples = 0
        self._last_patient_id = ""

    @staticmethod
    def _extract_imu(sample: Dict[str, Any]) -> Optional[np.ndarray]:
        imu = sample.get("imu") or {}
        keys = ("acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z")
        values = []
        for key in keys:
            val = imu.get(key)
            if val is None:
                return None
            values.append(float(val))
        return np.asarray(values, dtype=np.float32)

    @staticmethod
    def _extract_ppg(sample: Dict[str, Any]) -> Optional[float]:
        ppg = sample.get("ppg") or {}
        ir = ppg.get("ir")
        red = ppg.get("red")
        if ir is None and red is None:
            return None
        if ir is not None:
            return float(ir)
        return float(red)

    def add_sample(self, patient_id: str, sample: Dict[str, Any]) -> Dict[str, Any]:
        self._last_patient_id = patient_id
        if "patient_id" not in sample:
            sample = {**sample, "patient_id": patient_id}
        return self.push_sample(sample)

    def push_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        patient_id = str(sample.get("patient_id", self._last_patient_id))
        self._last_patient_id = patient_id

        imu_vec = self._extract_imu(sample)
        if imu_vec is None:
            self._skipped_samples += 1
            return {
                "window_ready": False,
                "accepted_sample": False,
                "reason": "imu_sample_incomplete_skipped",
                "buffered_imu_samples": len(self._imu),
            }

        self._imu.append(imu_vec)
        self._ppg.append(self._extract_ppg(sample))
        self._hr.append(sample.get("heart_rate"))
        self._spo2.append(sample.get("spo2"))
        self._timestamps.append(str(sample.get("timestamp", "")))

        if not self.is_ready(patient_id):
            return {
                "window_ready": False,
                "accepted_sample": True,
                "reason": "window_not_full",
                "buffered_imu_samples": len(self._imu),
            }

        return {
            "window_ready": True,
            "accepted_sample": True,
            "buffered_imu_samples": len(self._imu),
            "window": self.get_window(patient_id),
        }

    def is_ready(self, patient_id: str) -> bool:
        self._last_patient_id = patient_id
        return len(self._imu) >= self.window_size

    def get_window(self, patient_id: str) -> Optional[LiveWindowReady]:
        self._last_patient_id = patient_id
        if not self.is_ready(patient_id):
            return None
        return self._build_ready_window(patient_id)

    def reset_or_slide(self, patient_id: str) -> Dict[str, Any]:
        self._last_patient_id = patient_id
        samples_to_drop = self.window_size - self.overlap_size
        for _ in range(min(samples_to_drop, len(self._imu))):
            self._imu.popleft()
            self._ppg.popleft()
            self._hr.popleft()
            self._spo2.popleft()
            self._timestamps.popleft()
        return {
            "strategy": "50_percent_overlap",
            "retained_samples": len(self._imu),
            "next_ready_after_samples": max(0, self.window_size - len(self._imu)),
        }

    def _build_ready_window(self, patient_id: str) -> LiveWindowReady:
        imu_window = np.stack(list(self._imu), axis=0).astype(np.float32)
        ppg_values = [v for v in self._ppg if v is not None]
        ppg_window: Optional[np.ndarray]
        if not ppg_values:
            ppg_window = None
        else:
            seq = np.asarray([np.nan if v is None else float(v) for v in self._ppg], dtype=np.float32)
            valid_idx = np.where(~np.isnan(seq))[0]
            if len(valid_idx) > 0:
                first = valid_idx[0]
                last = valid_idx[-1]
                seq[:first] = seq[first]
                seq[last + 1 :] = seq[last]
                missing = np.isnan(seq)
                if np.any(missing):
                    seq[missing] = 0.0
            else:
                seq = np.zeros(self.window_size, dtype=np.float32)
            ppg_window = seq.reshape(-1, 1)

        hr_vals = [float(v) for v in self._hr if v is not None]
        spo2_vals = [float(v) for v in self._spo2 if v is not None]
        vitals = {}
        if hr_vals:
            vitals["hr"] = float(np.mean(hr_vals))
        if spo2_vals:
            vitals["spo2"] = float(np.mean(spo2_vals))

        return LiveWindowReady(
            imu_window=imu_window,
            ppg_window=ppg_window,
            vitals_values=vitals,
            metadata={
                "patient_id": patient_id,
                "buffered_imu_samples": len(self._imu),
                "window_size": self.window_size,
                "target_hz": self.target_hz,
                "window_seconds": self.window_seconds,
                "overlap_size": self.overlap_size,
                "overlap_strategy": "50_percent_overlap",
                "ppg_present": ppg_window is not None,
                "latest_timestamp": self._timestamps[-1] if self._timestamps else "",
                "skipped_samples": self._skipped_samples,
            },
        )
