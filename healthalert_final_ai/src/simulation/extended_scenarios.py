"""Extended synthetic scenarios for comprehensive demo/testing.

Six canonical scenarios:
    1. stable_normal    — healthy walking
    2. hr_rising        — gradually increasing heart rate
    3. spo2_drop        — gradually decreasing SpO2
    4. motion_instability — increasing postural sway
    5. combined_risk    — HR rising + SpO2 drop + instability
    6. sudden_critical  — normal → sudden fall event
"""

import numpy as np
from typing import Dict, List

from src.simulation.synthetic_stream import SyntheticStream


class ExtendedScenarioGenerator:
    """Generate the six canonical test scenarios."""

    def __init__(self, sr: int = 50, seed: int = 42):
        self.sr = sr
        self.stream = SyntheticStream(sr=sr, seed=seed)
        self.rng = np.random.RandomState(seed)

    def stable_normal(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        """Scenario 1: Stable normal walking — no risk."""
        return self.stream.generate_normal(duration)

    def hr_rising(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        """Scenario 2: Heart rate gradually rises (stress/exertion)."""
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        data = self.stream.generate_normal(duration)

        # Override HR: rising trend from 75 to 135
        hr_base = 75 + 60 * (t / duration)
        hr_noise = self.rng.randn(n) * 3
        data["heart_rate"] = hr_base + hr_noise

        # SpO2 slightly decreasing due to exertion
        data["spo2"] = 97 - 2 * (t / duration) + self.rng.randn(n) * 0.3

        return data

    def spo2_drop(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        """Scenario 3: SpO2 gradually drops (hypoxemia onset)."""
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        data = self.stream.generate_normal(duration)

        # SpO2 drops from 97 to 86
        data["spo2"] = 97 - 11 * (t / duration) + self.rng.randn(n) * 0.5

        # HR elevates slightly in response
        data["heart_rate"] = 78 + 15 * (t / duration) + self.rng.randn(n) * 2

        return data

    def motion_instability(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        """Scenario 4: Increasing motion instability (near-fall)."""
        return self.stream.generate_presyncope(duration)

    def combined_risk(self, duration: float = 20.0) -> Dict[str, np.ndarray]:
        """Scenario 5: Multiple signals deteriorate simultaneously.

        HR rising + SpO2 dropping + increasing instability.
        """
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Progressive instability
        instability = np.linspace(0, 2.5, n)

        accel_x = instability * np.sin(2 * np.pi * 0.8 * t) + self.rng.randn(n) * 0.05
        accel_y = instability * 0.7 * np.cos(2 * np.pi * 0.6 * t) + self.rng.randn(n) * 0.05
        accel_z = 9.81 + instability * 0.5 * np.sin(2 * np.pi * 1.2 * t) + self.rng.randn(n) * 0.05

        gyro_x = instability * 0.5 * np.sin(2 * np.pi * 0.5 * t) + self.rng.randn(n) * 0.03
        gyro_y = instability * 0.3 * np.cos(2 * np.pi * 0.4 * t) + self.rng.randn(n) * 0.03
        gyro_z = instability * 0.2 + self.rng.randn(n) * 0.02

        # HR rising from 80 to 130
        hr = 80 + 50 * (t / duration) + self.rng.randn(n) * 3

        # SpO2 dropping from 97 to 88
        spo2 = 97 - 9 * (t / duration) + self.rng.randn(n) * 0.5

        return {
            "timestamp": t,
            "accel_x": accel_x, "accel_y": accel_y, "accel_z": accel_z,
            "gyro_x": gyro_x, "gyro_y": gyro_y, "gyro_z": gyro_z,
            "heart_rate": hr, "spo2": spo2,
        }

    def sudden_critical(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        """Scenario 6: Normal → sudden fall event.

        First 5s normal, then fall impact + post-fall.
        """
        fall_time = duration * 0.5
        return self.stream.generate_fall(duration, fall_time)

    def generate_all(self) -> List[Dict]:
        """Generate all six scenarios with metadata."""
        return [
            {
                "name": "stable_normal",
                "data": self.stable_normal(),
                "expected_risk": "normal",
                "description": "Normal walking, no risk indicators",
            },
            {
                "name": "hr_rising",
                "data": self.hr_rising(),
                "expected_risk": "warning",
                "description": "Heart rate gradually rising from 75 to 135 bpm",
            },
            {
                "name": "spo2_drop",
                "data": self.spo2_drop(),
                "expected_risk": "warning",
                "description": "SpO2 dropping from 97% to 86%",
            },
            {
                "name": "motion_instability",
                "data": self.motion_instability(),
                "expected_risk": "watch",
                "description": "Increasing postural sway and unsteadiness",
            },
            {
                "name": "combined_risk",
                "data": self.combined_risk(),
                "expected_risk": "critical",
                "description": "HR rising + SpO2 dropping + motion instability",
            },
            {
                "name": "sudden_critical",
                "data": self.sudden_critical(),
                "expected_risk": "critical",
                "description": "Normal activity → sudden fall impact",
            },
        ]
