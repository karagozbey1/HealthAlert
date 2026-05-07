import numpy as np
from typing import Dict, Generator, Tuple


# Demo ve test amacli sentetik sensor akislari uretir.
class SyntheticStream:

    # Ornekleme hizi, gurultu ve rastgelelik ayarlarini baslatir.
    def __init__(self, sr: int = 50, noise_std: float = 0.05, seed: int = 42):
        self.sr = sr
        self.noise_std = noise_std
        self.rng = np.random.RandomState(seed)

    # Normal yurus veya dinlenme akisini temsil eden veri uretir.
    def generate_normal(self, duration: float = 10.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Hafif salinimli normal hareketi ivme ve gyro alanina yansitir.
        accel_x = 0.3 * np.sin(2 * np.pi * 1.5 * t) + self._noise(n)
        accel_y = 0.2 * np.sin(2 * np.pi * 1.5 * t + 0.5) + self._noise(n)
        accel_z = 9.81 + 0.4 * np.sin(2 * np.pi * 3.0 * t) + self._noise(n)

        gyro_x = 0.1 * np.sin(2 * np.pi * 1.5 * t) + self._noise(n) * 0.5
        gyro_y = 0.1 * np.cos(2 * np.pi * 1.5 * t) + self._noise(n) * 0.5
        gyro_z = 0.05 * np.sin(2 * np.pi * 0.7 * t) + self._noise(n) * 0.3

        hr = 72 + 5 * np.sin(2 * np.pi * 0.1 * t) + self._noise(n) * 2
        spo2 = np.full(n, 97.0) + self._noise(n) * 0.5

        return self._pack(t, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, hr, spo2)

    # Düşme olayi iceren ani darbe ve sonrasini sentetik olarak uretir.
    def generate_fall(self, duration: float = 10.0, fall_time: float = 5.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)
        fall_idx = int(fall_time * self.sr)
        impact_duration = int(0.3 * self.sr)

        # Taban davranis olarak normal akisi baslangic noktasi alir.
        data = self.generate_normal(duration)
        accel = np.column_stack([data["accel_x"], data["accel_y"], data["accel_z"]])
        gyro = np.column_stack([data["gyro_x"], data["gyro_y"], data["gyro_z"]])

        # Dusme oncesi kisa serbest dusus evresini taklit eder.
        pre_fall = max(0, fall_idx - int(0.2 * self.sr))
        accel[pre_fall:fall_idx, 2] = 2.0 + self._noise(fall_idx - pre_fall)

        # Darbe aninda tum eksenlerde sivri hareket olusturur.
        end_impact = min(n, fall_idx + impact_duration)
        accel[fall_idx:end_impact, 0] = 15 * self.rng.randn(end_impact - fall_idx)
        accel[fall_idx:end_impact, 1] = 12 * self.rng.randn(end_impact - fall_idx)
        accel[fall_idx:end_impact, 2] = 25 + 10 * self.rng.randn(end_impact - fall_idx)

        gyro[fall_idx:end_impact, :] = 8 * self.rng.randn(end_impact - fall_idx, 3)

    # Dusme sonrasi yan yatma ve hareketsizlik etkisini yazar.
        post_fall = min(n, fall_idx + int(1.0 * self.sr))
        accel[post_fall:, 0] = self._noise(n - post_fall) * 0.1
    accel[post_fall:, 1] = 9.81 + self._noise(n - post_fall) * 0.1
        accel[post_fall:, 2] = self._noise(n - post_fall) * 0.1
        gyro[post_fall:, :] = self._noise(n - post_fall)[:, None] * 0.05

    # Nabiz tarafinda olaya verilen fizyolojik tepkiyi simule eder.
        hr = data["heart_rate"].copy()
        hr[fall_idx:min(n, fall_idx + int(3 * self.sr))] += 30
        hr[min(n, fall_idx + int(3 * self.sr)):] += 15

        return self._pack(t, accel[:, 0], accel[:, 1], accel[:, 2],
                         gyro[:, 0], gyro[:, 1], gyro[:, 2], hr, data["spo2"])

    # Bayginlik oncesi benzeri dengesizlik ve vital bozulma senaryosu uretir.
    def generate_presyncope(self, duration: float = 15.0) -> Dict[str, np.ndarray]:
        n = int(duration * self.sr)
        t = np.linspace(0, duration, n)

        # Zamanla artan dengesizlik katsayisini kurar.
        instability = np.linspace(0, 2.0, n)

        accel_x = instability * np.sin(2 * np.pi * 0.8 * t) + self._noise(n)
        accel_y = instability * 0.7 * np.cos(2 * np.pi * 0.6 * t) + self._noise(n)
        accel_z = 9.81 + instability * 0.5 * np.sin(2 * np.pi * 1.2 * t) + self._noise(n)

        gyro_x = instability * 0.5 * np.sin(2 * np.pi * 0.5 * t) + self._noise(n) * 0.3
        gyro_y = instability * 0.3 * np.cos(2 * np.pi * 0.4 * t) + self._noise(n) * 0.3
        gyro_z = instability * 0.2 + self._noise(n) * 0.2

        # Nabzin asamali sekilde dusmesini simule eder.
        hr = 80 - 25 * (t / duration) + self._noise(n) * 3

        # SpO2 tarafinda hafif dusus ekler.
        spo2 = 97 - 5 * (t / duration) + self._noise(n) * 0.5

        return self._pack(t, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, hr, spo2)

    # Uretilen akisi pencereleyerek sirali veri akisi gibi verir.
    def generate_stream(
        self,
        scenario: str = "mixed",
        duration: float = 60.0,
        window_size: int = 200,
        stride: int = 100,
    ) -> Generator[Dict[str, np.ndarray], None, None]:
        if scenario == "normal":
            data = self.generate_normal(duration)
        elif scenario == "fall":
            data = self.generate_fall(duration)
        elif scenario == "presyncope":
            data = self.generate_presyncope(duration)
        else:
            # Karma akis icin birden fazla senaryoyu pes pese ekler.
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

    # Belirtilen uzunlukta gurultu dizisi uretir.
    def _noise(self, n: int) -> np.ndarray:
        return self.rng.randn(n) * self.noise_std

    # Ayrik sinyal kolonlarini tek bir veri sozlugunde toplar.
    def _pack(self, t, ax, ay, az, gx, gy, gz, hr, spo2) -> Dict[str, np.ndarray]:
        return {
            "timestamp": t,
            "accel_x": ax, "accel_y": ay, "accel_z": az,
            "gyro_x": gx, "gyro_y": gy, "gyro_z": gz,
            "heart_rate": hr, "spo2": spo2,
        }

    # Birden fazla sentetik akisi zaman eksenini koruyarak birlestirir.
    def _concatenate_streams(self, *streams) -> Dict[str, np.ndarray]:
        result = {}
        for key in streams[0]:
            arrays = [s[key] for s in streams]
            if key == "timestamp":
                # Zaman damgalarini ardışık hale getirir.
                adjusted = [arrays[0]]
                for i in range(1, len(arrays)):
                    offset = adjusted[-1][-1] + 1.0 / self.sr
                    adjusted.append(arrays[i] + offset)
                result[key] = np.concatenate(adjusted)
            else:
                result[key] = np.concatenate(arrays)
        return result
