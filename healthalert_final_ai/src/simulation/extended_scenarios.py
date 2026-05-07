import numpy as np
from typing import Dict, List

from src.simulation.synthetic_stream import SyntheticStream


# Demo ve rapor akislari icin alti temel senaryoyu uretir.
class ExtendedScenarioGenerator:

    # Ortak sentetik akisi ve rastgelelik kaynagini baslatir.
    def __init__(self, sr: int = 50, seed: int = 42):
        self.sr = sr
        self.stream = SyntheticStream(sr=sr, seed=seed)
        self.rng = np.random.RandomState(seed)

    # Risk gostergesi tasimayan dengeli temel senaryoyu uretir.
    def stable_normal(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        return self.stream.generate_normal(duration)

    # Nabzin kademeli yukseldigi efor benzeri senaryoyu uretir.
    def hr_rising(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        data = self.stream.generate_normal(duration)

    # Nabzi asamali olarak yukselen bir trende donusturur.
        hr_base = 75 + 60 * (t / duration)
        hr_noise = self.rng.randn(n) * 3
        data["heart_rate"] = hr_base + hr_noise

        # Efora bagli hafif SpO2 dususu ekler.
        data["spo2"] = 97 - 2 * (t / duration) + self.rng.randn(n) * 0.3

        return data

    # SpO2 seviyesinin kademeli dustugu hipoksemi baslangici senaryosu uretir.
    def spo2_drop(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        data = self.stream.generate_normal(duration)

        # SpO2 degerini belirgin dusus trendine cevirir.
        data["spo2"] = 97 - 11 * (t / duration) + self.rng.randn(n) * 0.5

        # Buna eslik eden hafif nabiz artisi ekler.
        data["heart_rate"] = 78 + 15 * (t / duration) + self.rng.randn(n) * 2

        return data

    # Artan postural salinim iceren dengesizlik senaryosu uretir.
    def motion_instability(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        return self.stream.generate_presyncope(duration)

    # Birden fazla sinyalin birlikte bozuldugu yuksek riskli senaryoyu kurar.
    def combined_risk(self, duration: float = 20.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Dengesizlik katsayisini zamanla artirir.
        instability = np.linspace(0, 2.5, n)

        accel_x = instability * np.sin(2 * np.pi * 0.8 * t) + self.rng.randn(n) * 0.05
        accel_y = instability * 0.7 * np.cos(2 * np.pi * 0.6 * t) + self.rng.randn(n) * 0.05
        accel_z = 9.81 + instability * 0.5 * np.sin(2 * np.pi * 1.2 * t) + self.rng.randn(n) * 0.05

        gyro_x = instability * 0.5 * np.sin(2 * np.pi * 0.5 * t) + self.rng.randn(n) * 0.03
        gyro_y = instability * 0.3 * np.cos(2 * np.pi * 0.4 * t) + self.rng.randn(n) * 0.03
        gyro_z = instability * 0.2 + self.rng.randn(n) * 0.02

        # Nabzi artan bir egilimle bozar.
        hr = 80 + 50 * (t / duration) + self.rng.randn(n) * 3

        # SpO2 degerini asamali dusurur.
        spo2 = 97 - 9 * (t / duration) + self.rng.randn(n) * 0.5

        return {
            "timestamp": t,
            "accel_x": accel_x, "accel_y": accel_y, "accel_z": accel_z,
            "gyro_x": gyro_x, "gyro_y": gyro_y, "gyro_z": gyro_z,
            "heart_rate": hr, "spo2": spo2,
        }

    # Normal akistan ani dusmeye gecen kritik senaryoyu uretir.
    def sudden_critical(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        fall_time = duration * 0.5
        return self.stream.generate_fall(duration, fall_time)

    # Alti temel senaryoyu aciklama ve beklenen risk bilgisiyle toplar.
    def generate_all(self) -> List[Dict]:
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
