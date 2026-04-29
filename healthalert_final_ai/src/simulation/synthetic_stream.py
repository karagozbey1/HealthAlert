"""Synthetic data stream generator for testing and demos.

Generates realistic-looking IMU + PPG data streams with
controllable scenarios (normal, fall, presyncope, etc.).
"""

import numpy as np
from typing import Dict, Generator, Tuple


class SyntheticStream:
    """Generate synthetic sensor data for demo and testing.

    Produces streams that mimic wrist-worn MPU6050 + MAX30102 output.
    """

    def __init__(self, sr: int = 50, noise_std: float = 0.05, seed: int = 42):
        self.sr = sr
        self.noise_std = noise_std
        self.rng = np.random.RandomState(seed)

    def generate_normal(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        """Generate normal walking/resting data."""
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Normal walking: gentle oscillation
        accel_x = 0.3 * np.sin(2 * np.pi * 1.5 * t) + self._noise(n)
        accel_y = 0.2 * np.sin(2 * np.pi * 1.5 * t + 0.5) + self._noise(n)
        accel_z = 9.81 + 0.4 * np.sin(2 * np.pi * 3.0 * t) + self._noise(n)

        gyro_x = 0.1 * np.sin(2 * np.pi * 1.5 * t) + self._noise(n) * 0.5
        gyro_y = 0.1 * np.cos(2 * np.pi * 1.5 * t) + self._noise(n) * 0.5
        gyro_z = 0.05 * np.sin(2 * np.pi * 0.7 * t) + self._noise(n) * 0.3

        hr = 72 + 5 * np.sin(2 * np.pi * 0.1 * t) + self._noise(n) * 2
        spo2 = np.full(n, 97.0) + self._noise(n) * 0.5

        return self._pack(t, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, hr, spo2)

    def generate_fall(self, duration: float = 10.0, fall_time: float = 5.0) -> Dict[str, np.ndarray]:
        """Generate data with a fall event."""
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)
        fall_idx = int(fall_time * self.sr)
        impact_duration = int(0.3 * self.sr)

        # Start with normal
        data = self.generate_normal(duration)
        accel = np.column_stack([data["accel_x"], data["accel_y"], data["accel_z"]])
        gyro = np.column_stack([data["gyro_x"], data["gyro_y"], data["gyro_z"]])

        # Pre-fall: brief free-fall (reduced gravity)
        pre_fall = max(0, fall_idx - int(0.2 * self.sr))
        accel[pre_fall:fall_idx, 2] = 2.0 + self._noise(fall_idx - pre_fall)  # Low-g

        # Impact: spike in all axes
        end_impact = min(n, fall_idx + impact_duration)
        accel[fall_idx:end_impact, 0] = 15 * self.rng.randn(end_impact - fall_idx)
        accel[fall_idx:end_impact, 1] = 12 * self.rng.randn(end_impact - fall_idx)
        accel[fall_idx:end_impact, 2] = 25 + 10 * self.rng.randn(end_impact - fall_idx)

        gyro[fall_idx:end_impact, :] = 8 * self.rng.randn(end_impact - fall_idx, 3)

        # Post-fall: lying still
        post_fall = min(n, fall_idx + int(1.0 * self.sr))
        accel[post_fall:, 0] = self._noise(n - post_fall) * 0.1
        accel[post_fall:, 1] = 9.81 + self._noise(n - post_fall) * 0.1  # Lying on side
        accel[post_fall:, 2] = self._noise(n - post_fall) * 0.1
        gyro[post_fall:, :] = self._noise(n - post_fall)[:, None] * 0.05

        # HR response: spike then drop
        hr = data["heart_rate"].copy()
        hr[fall_idx:min(n, fall_idx + int(3 * self.sr))] += 30
        hr[min(n, fall_idx + int(3 * self.sr)):] += 15

        return self._pack(t, accel[:, 0], accel[:, 1], accel[:, 2],
                         gyro[:, 0], gyro[:, 1], gyro[:, 2], hr, data["spo2"])

    def generate_presyncope(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        """Generate presyncope (near-fainting) scenario.

        Gradual HR drop + increasing unsteadiness.
        """
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Gradually increasing unsteadiness
        instability = np.linspace(0, 2.0, n)

        accel_x = instability * np.sin(2 * np.pi * 0.8 * t) + self._noise(n)
        accel_y = instability * 0.7 * np.cos(2 * np.pi * 0.6 * t) + self._noise(n)
        accel_z = 9.81 + instability * 0.5 * np.sin(2 * np.pi * 1.2 * t) + self._noise(n)

        gyro_x = instability * 0.5 * np.sin(2 * np.pi * 0.5 * t) + self._noise(n) * 0.3
        gyro_y = instability * 0.3 * np.cos(2 * np.pi * 0.4 * t) + self._noise(n) * 0.3
        gyro_z = instability * 0.2 + self._noise(n) * 0.2

        # HR drops gradually
        hr = 80 - 25 * (t / duration) + self._noise(n) * 3

        # SpO2 slight decrease
        spo2 = 97 - 5 * (t / duration) + self._noise(n) * 0.5

        return self._pack(t, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, hr, spo2)

    def generate_stream(
        self,
        scenario: str = "mixed",
        duration: float = 60.0,
        window_size: int = 200,
        stride: int = 100,
    ) -> Generator[Dict[str, np.ndarray], None, None]:
        """Generate a streaming sequence of windows.

        Args:
            scenario: "normal", "fall", "presyncope", or "mixed".
            duration: Total stream duration in seconds.
            window_size: Samples per window.
            stride: Step between windows.

        Yields:
            Dict with windowed sensor data + metadata.
        """
        if scenario == "normal":
            data = self.generate_normal(duration)
        elif scenario == "fall":
            data = self.generate_fall(duration)
        elif scenario == "presyncope":
            data = self.generate_presyncope(duration)
        else:
            # Mixed: concatenate scenarios
            normal1 = self.generate_normal(duration * 0.4)
            fall = self.generate_fall(duration * 0.3)
            presync = self.generate_presyncope(duration * 0.3)
            data = self._concatenate_streams(normal1, fall, presync)

        n = len(data["timestamp"])
        for start in range(0, n - window_size + 1, stride):
            end = start + window_size
            window = {}
            for key in data:
                window[key] = data[key][start:end]
            window["window_start"] = start / self.sr
            window["window_end"] = end / self.sr
            yield window

    def _noise(self, n: int) -> np.ndarray:
        return self.rng.randn(n) * self.noise_std

    def _pack(self, t, ax, ay, az, gx, gy, gz, hr, spo2) -> Dict[str, np.ndarray]:
        return {
            "timestamp": t,
            "accel_x": ax, "accel_y": ay, "accel_z": az,
            "gyro_x": gx, "gyro_y": gy, "gyro_z": gz,
            "heart_rate": hr, "spo2": spo2,
        }

    def _concatenate_streams(self, *streams) -> Dict[str, np.ndarray]:
        result = {}
        for key in streams[0]:
            arrays = [s[key] for s in streams]
            if key == "timestamp":
                # Adjust timestamps to be sequential
                adjusted = [arrays[0]]
                for i in range(1, len(arrays)):
                    offset = adjusted[-1][-1] + 1.0 / self.sr
                    adjusted.append(arrays[i] + offset)
                result[key] = np.concatenate(adjusted)
            else:
                result[key] = np.concatenate(arrays)
        return result
