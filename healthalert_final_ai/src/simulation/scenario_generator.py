import numpy as np
from typing import Dict, List

from src.simulation.synthetic_stream import SyntheticStream


# Test ve dogrulama icin etiketli senaryo setleri uretir.
class ScenarioGenerator:

    # Temel sentetik akisi kullanacak ureteci baslatir.
    def __init__(self, sr: int = 50, seed: int = 42):
        self.stream = SyntheticStream(sr=sr, seed=seed)
        self.sr = sr

    # Beklenen risk etiketiyle ana senaryo setini dondurur.
    def generate_all_scenarios(self) -> List[Dict]:
        scenarios = []

        # Normal aktiviteleri referans senaryolar olarak ekler.
        for name, dur in [("normal_rest", 10), ("normal_walk", 10)]:
            data = self.stream.generate_normal(dur)
            scenarios.append({
                "name": name,
                "data": data,
                "expected_risk": "normal",
                "expected_fall": False,
            })

        # Farkli zamanlarda dusme iceren senaryolari ekler.
        for fall_time in [3.0, 5.0, 7.0]:
            data = self.stream.generate_fall(10.0, fall_time)
            scenarios.append({
                "name": f"fall_at_{fall_time}s",
                "data": data,
                "expected_risk": "critical",
                "expected_fall": True,
                "fall_time": fall_time,
            })

        # Bayginlik oncesi benzeri bozulum senaryosunu ekler.
        data = self.stream.generate_presyncope(15.0)
        scenarios.append({
            "name": "presyncope",
            "data": data,
            "expected_risk": "warning",
            "expected_fall": False,
        })

        return scenarios

    # Saglamlik testleri icin uc senaryo uretir.
    def generate_edge_cases(self) -> List[Dict]:
        cases = []

        # Tum sensorlerin sustugu ariza durumunu kurar.
        n = 200
        zeros = {
            "timestamp": np.linspace(0, 4, n),
            "accel_x": np.zeros(n), "accel_y": np.zeros(n), "accel_z": np.zeros(n),
            "gyro_x": np.zeros(n), "gyro_y": np.zeros(n), "gyro_z": np.zeros(n),
            "heart_rate": np.zeros(n), "spo2": np.zeros(n),
        }
        cases.append({"name": "sensor_failure", "data": zeros, "expected_risk": "watch"})

        # Asiri degerlerin kritik skora yol actigi durumu kurar.
        extreme = {
            "timestamp": np.linspace(0, 4, n),
            "accel_x": np.full(n, 100.0), "accel_y": np.full(n, 100.0),
            "accel_z": np.full(n, 100.0),
            "gyro_x": np.full(n, 50.0), "gyro_y": np.full(n, 50.0),
            "gyro_z": np.full(n, 50.0),
            "heart_rate": np.full(n, 200.0), "spo2": np.full(n, 70.0),
        }
        cases.append({"name": "extreme_values", "data": extreme, "expected_risk": "critical"})

        # Verinin bir kismina NaN bulastirarak dayanikliligi sinar.
        nan_data = self.stream.generate_normal(4.0)
        for key in ["accel_x", "heart_rate"]:
            nan_data[key][50:100] = np.nan
        cases.append({"name": "nan_contamination", "data": nan_data, "expected_risk": "watch"})

        return cases
