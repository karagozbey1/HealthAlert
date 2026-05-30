# Kullanici bazli kayan pencere tamponunu bellekte tutar ve ML golge cagrilarini besler.
# Tum degisiklikler tek bir lock altinda yapilarak async akis icinde guvenli tutulur.
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from config import settings

logger = logging.getLogger("healthalert.live_window")


# ---------------------------------------------------------------------------
# Pencere ornegi
# ---------------------------------------------------------------------------

# Her paket icin halkali tamponda saklanan yogunlastirilmis ornek kaydidir.
@dataclass
class WindowSample:

    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    timestamp_ms: int
    packet_seq: int
    mode: str

    # IMU alanlarini tasir.
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

    # Ham PPG ADC degerlerini saklar.
    red_value: int
    ir_value: int

    # Turetilmis vital degerleri saklar.
    heart_rate: float
    spo2: float
    signal_quality: float

    # Sensor gecerlilik bayraklarini saklar.
    imu_ok: bool
    ppg_ok: bool
    hr_valid: bool
    spo2_valid: bool
    finger_detected: bool

    # Hesaplanmis skor alanlarini saklar.
    motion_score: float
    final_risk_score: float
    quality_confidence: float


# ---------------------------------------------------------------------------
# Tampon yoneticisi
# ---------------------------------------------------------------------------

# Kullanici bazli halkali tamponlari ve paket sayaclarini yonetir.
class LiveWindowBufferManager:
    # Tampon ve sayac depolarini baslatir.
    """HealthAlert backend içinde ilgili sorumluluğu bir arada tutar."""
    def __init__(self) -> None:
        """live window buffer servisindeki HealthAlert iş kuralını uygular."""
        self._lock = threading.Lock()
        # Her kullanici icin sabit boyutlu tampon tutar.
        self._buffers: Dict[str, deque] = {}
        # Paket sayacini sifirlamadan artirarak tetikleme kadansini korur.
        self._packet_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Ic yardimcilar
    # ------------------------------------------------------------------

    # Kullanici icin tamponu getirir; yoksa olusturur.
    def _get_or_create_buffer(self, user_id: str) -> deque:
        """live window buffer servisinde gereken veriyi okuyup çağırana döndürür."""
        if user_id not in self._buffers:
            self._buffers[user_id] = deque(maxlen=settings.ML_WINDOW_SIZE)
            self._packet_counts[user_id] = 0
        return self._buffers[user_id]

    # ------------------------------------------------------------------
    # Acik API
    # ------------------------------------------------------------------

    # Yeni paketi ornek kayda cevirip kullanicinin tamponuna ekler.
    # Donus degeri ekleme sonrasi guncel tampon ozetidir.
    def add_packet(
        self,
        user_id: str,
        packet,
        motion_score: float,
        final_risk_score: float,
        quality_confidence: float = 1.0,
    ) -> dict:
        """live window buffer servisindeki HealthAlert iş kuralını uygular."""
        sample = WindowSample(
            timestamp_ms=packet.timestamp_ms,
            packet_seq=packet.packet_seq,
            mode=packet.mode,
            accel_x=packet.accel_x,
            accel_y=packet.accel_y,
            accel_z=packet.accel_z,
            gyro_x=packet.gyro_x,
            gyro_y=packet.gyro_y,
            gyro_z=packet.gyro_z,
            red_value=packet.red_value,
            ir_value=packet.ir_value,
            heart_rate=packet.heart_rate,
            spo2=packet.spo2,
            signal_quality=packet.signal_quality,
            imu_ok=packet.imu_ok,
            ppg_ok=packet.ppg_ok,
            hr_valid=packet.hr_valid,
            spo2_valid=packet.spo2_valid,
            finger_detected=packet.finger_detected,
            motion_score=motion_score,
            final_risk_score=final_risk_score,
            quality_confidence=quality_confidence,
        )

        with self._lock:
            buf = self._get_or_create_buffer(user_id)
            buf.append(sample)
            self._packet_counts[user_id] += 1

        return self.get_status(user_id)

    # Kullaniciya ait pencerenin anlik kopyasini dondurur.
    def get_window(self, user_id: str) -> Optional[list]:
        """live window buffer servisinde gereken veriyi okuyup çağırana döndürür."""
        with self._lock:
            if user_id not in self._buffers:
                return None
            return list(self._buffers[user_id])

    # Doluluk ve paket kadansina gore inference calisip calismayacagini belirler.
    def should_run_inference(self, user_id: str) -> bool:
        """live window buffer servisindeki HealthAlert iş kuralını uygular."""
        if not settings.ML_INFERENCE_ENABLED:
            return False

        with self._lock:
            if user_id not in self._buffers:
                return False
            buf = self._buffers[user_id]
            if len(buf) < settings.ML_WINDOW_SIZE:
                return False
            count = self._packet_counts[user_id]

        every_n = max(1, settings.ML_INFERENCE_EVERY_N_PACKETS)
        return (count % every_n) == 0

    # Tamponun doluluk ve sure ozetini serilestirilebilir dict olarak dondurur.
    def get_status(self, user_id: str) -> dict:
        """live window buffer servisinde gereken veriyi okuyup çağırana döndürür."""
        expected_duration = round(
            settings.ML_WINDOW_SIZE / max(1, settings.ML_EXPECTED_SAMPLE_RATE_HZ), 2
        )

        with self._lock:
            if user_id not in self._buffers:
                return {
                    "current_size": 0,
                    "target_size": settings.ML_WINDOW_SIZE,
                    "is_full": False,
                    "packets_until_full": settings.ML_WINDOW_SIZE,
                    "last_packet_seq": None,
                    "estimated_window_duration_sec": None,
                    "expected_duration_sec": expected_duration,
                    "sample_rate_warning": False,
                    "packet_summary_mode": settings.ML_USE_PACKET_SUMMARY_MODE,
                }

            buf_list = list(self._buffers[user_id])

        current_size = len(buf_list)
        is_full = current_size >= settings.ML_WINDOW_SIZE
        packets_until_full = max(0, settings.ML_WINDOW_SIZE - current_size)
        last_seq = buf_list[-1].packet_seq if buf_list else None

        # Ilk ve son zaman damgasindan gercek pencere suresini tahmin eder.
        estimated_duration: Optional[float] = None
        sample_rate_warning = False

        if len(buf_list) >= 2:
            ts_first = buf_list[0].timestamp_ms
            ts_last = buf_list[-1].timestamp_ms
            if ts_last > ts_first:
                estimated_duration = round((ts_last - ts_first) / 1000.0, 2)

                # Gercek sure beklenenden cok uzunsa ornekleme uyumsuzlugunu isaretler.
                if settings.ML_WARN_ON_SAMPLE_RATE_MISMATCH and is_full:
                    ratio = (
                        estimated_duration / expected_duration
                        if expected_duration > 0
                        else 1.0
                    )
                    if ratio > 3.0:
                        sample_rate_warning = True
                        if ratio > 5.0:
                            logger.warning(
                                "Sample rate mismatch for user=%s: "
                                "estimated_window_duration=%.1fs but "
                                "expected=%.1fs (ML trained at %dHz, "
                                "firmware sends ~1 pkt/s). "
                                "Shadow inference runs but temporal "
                                "features may be sub-optimal.",
                                user_id,
                                estimated_duration,
                                expected_duration,
                                settings.ML_EXPECTED_SAMPLE_RATE_HZ,
                            )

        return {
            "current_size": current_size,
            "target_size": settings.ML_WINDOW_SIZE,
            "is_full": is_full,
            "packets_until_full": packets_until_full,
            "last_packet_seq": last_seq,
            "estimated_window_duration_sec": estimated_duration,
            "expected_duration_sec": expected_duration,
            "sample_rate_warning": sample_rate_warning,
            "packet_summary_mode": settings.ML_USE_PACKET_SUMMARY_MODE,
        }

    # Kullaniciya ait tamponu ve paket sayacini sifirlar.
    def reset_user(self, user_id: str) -> None:
        """live window buffer servisindeki HealthAlert iş kuralını uygular."""
        with self._lock:
            self._buffers.pop(user_id, None)
            self._packet_counts.pop(user_id, None)


# ---------------------------------------------------------------------------
# Ingestion akisi tarafindan ortak kullanilan tampon nesnesini olusturur.
# ---------------------------------------------------------------------------

live_window_buffer = LiveWindowBufferManager()
