import math
import pytest
import sys
from pathlib import Path

# packet_schema modulu icin host_bridge dizinini arama yoluna ekler.
sys.path.insert(0, str(Path(__file__).parent.parent))

from packet_schema import DevicePacketSchema, validate_packet


# Gecerli bir paket sozlugu olusturur ve ustune alan guncellemeleri uygular.
def _valid_packet(**overrides) -> dict:
    base = {
        "device_id": "ha-esp32-test",
        "timestamp_ms": 100000,
        "mode": "mock",
        "packet_seq": 1,
        "accel_x": 0.01,
        "accel_y": -0.02,
        "accel_z": 1.0,
        "gyro_x": 0.5,
        "gyro_y": -0.3,
        "gyro_z": 0.1,
        "red_value": 75000,
        "ir_value": 80000,
        "heart_rate": 72.5,
        "spo2": 97.8,
        "signal_quality": 0.91,
        "imu_ok": True,
        "ppg_ok": True,
        "hr_valid": True,
        "spo2_valid": True,
        "finger_detected": True,
        "state_hint": "normal",
    }
    base.update(overrides)
    return base


# Ingestion mantigindaki hareket skoru hesabini test icin tekrarlar.

# IMU ve gyro verisinden hareket skorunu hesaplar.
def compute_motion_score(ax, ay, az, gx, gy, gz):
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)


# Nabiz, SpO2 ve hareketten basit risk skorunu hesaplar.
def compute_risk_score(hr, spo2, hr_valid, spo2_valid, motion):
    risk = 0.0
    if hr_valid:
        if hr > 120:
            risk += 0.3
        elif hr > 100:
            risk += 0.15
        elif hr < 50:
            risk += 0.2
    if spo2_valid:
        if spo2 < 90:
            risk += 0.4
        elif spo2 < 94:
            risk += 0.2
    risk += motion * 0.2
    return round(min(1.0, risk), 3)


class TestMotionScoreComputation:
    # Hareketsiz durumda skorun dusuk kaldigini dogrular.
    def test_stationary(self):
        score = compute_motion_score(0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        assert score < 0.05

    # Hafif hareketin orta-alt seviyede skor urettiğini doğrular.
    def test_slight_motion(self):
        score = compute_motion_score(0.1, 0.05, 1.0, 2.0, 1.0, 0.5)
        assert 0.01 < score < 0.5

    # Belirgin hareketin yuksek skor urettiğini doğrular.
    def test_heavy_motion(self):
        score = compute_motion_score(0.8, 0.5, 1.5, 20.0, 15.0, 10.0)
        assert score > 0.5

    # Asiri hareket durumunda sonucun bire kirlendigini kontrol eder.
    def test_extreme_motion_clamps_to_1(self):
        score = compute_motion_score(5.0, 5.0, 5.0, 100.0, 100.0, 100.0)
        assert score == 1.0

    # Yercekimi referansi olmadiginda bile sifirdan buyuk skor ciktigini dogrular.
    def test_zero_gravity(self):
        score = compute_motion_score(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert score > 0


class TestRiskScoreComputation:
    # Normal vital degerlerde riskin dusuk kaldigini dogrular.
    def test_normal_vitals_low_risk(self):
        risk = compute_risk_score(72, 98, True, True, 0.05)
        assert risk < 0.1

    # Yuksek nabzin riski artirdigini kontrol eder.
    def test_high_hr_increases_risk(self):
        risk_normal = compute_risk_score(72, 98, True, True, 0.05)
        risk_high = compute_risk_score(125, 98, True, True, 0.05)
        assert risk_high > risk_normal

    # Cok yuksek nabzin en az kritik esik kadar etki yaptigini dogrular.
    def test_very_high_hr(self):
        risk = compute_risk_score(125, 98, True, True, 0.0)
        assert risk >= 0.3

    # Cok dusuk SpO2 degerinin kritik risk olusturdugunu dogrular.
    def test_low_spo2_critical(self):
        risk = compute_risk_score(72, 85, True, True, 0.0)
        assert risk >= 0.4

    # Uyari seviyesindeki SpO2 dususunun riske yansidigini dogrular.
    def test_low_spo2_warning(self):
        risk = compute_risk_score(72, 92, True, True, 0.0)
        assert risk >= 0.2

    # Dusuk nabzin riski artirdigini kontrol eder.
    def test_low_hr(self):
        risk = compute_risk_score(45, 98, True, True, 0.0)
        assert risk >= 0.2

    # Gecersiz vital bayraklarinda nabiz ve SpO2 etkisinin kapandigini dogrular.
    def test_invalid_vitals_no_risk_from_hr(self):
        risk = compute_risk_score(200, 60, False, False, 0.0)
        assert risk == 0.0

    # Hareket artisinin toplam riski yukselttigini kontrol eder.
    def test_motion_adds_risk(self):
        risk_still = compute_risk_score(72, 98, True, True, 0.0)
        risk_moving = compute_risk_score(72, 98, True, True, 0.8)
        assert risk_moving > risk_still

    # Birlesik olumsuz sinyallerde riskin kritik duzeye ciktigini dogrular.
    def test_combined_critical(self):
        risk = compute_risk_score(130, 85, True, True, 0.8)
        assert risk >= 0.8

    # Risk hesabinin bir ust siniri asmadigini dogrular.
    def test_risk_clamps_to_1(self):
        risk = compute_risk_score(200, 50, True, True, 1.0)
        assert risk <= 1.0


class TestIngestionSchemaValidation:
    # Gecerli paketin sema dogrulamasindan gectigini kontrol eder.
    def test_valid_packet_accepted(self):
        pkt = validate_packet(_valid_packet())
        assert pkt.device_id == "ha-esp32-test"

    # Gecersiz mod degerinin reddedildigini dogrular.
    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(mode="invalid"))

    # Zorunlu alan eksiginde dogrulamanin hata verdigini kontrol eder.
    def test_missing_field_rejected(self):
        data = _valid_packet()
        del data["heart_rate"]
        with pytest.raises(Exception):
            validate_packet(data)

    # mock modunun kabul edildigini dogrular.
    def test_mock_mode_accepted(self):
        pkt = validate_packet(_valid_packet(mode="mock"))
        assert pkt.mode == "mock"

    # real modunun kabul edildigini dogrular.
    def test_real_mode_accepted(self):
        pkt = validate_packet(_valid_packet(mode="real"))
        assert pkt.mode == "real"

    # Art arda gelen paketlerde sira numarasinin korundugunu kontrol eder.
    def test_multiple_packets_sequential(self):
        for seq in range(10):
            pkt = validate_packet(_valid_packet(packet_seq=seq))
            assert pkt.packet_seq == seq

    # Bozulmus IMU bayragiyla paketin yine dogrulandigini kontrol eder.
    def test_degraded_mode_packet(self):
        pkt = validate_packet(_valid_packet(imu_ok=False, ppg_ok=True))
        assert not pkt.imu_ok
        assert pkt.ppg_ok

    # Parmak algilanmadiginda ilgili bayraklarin korundugunu dogrular.
    def test_no_finger_packet(self):
        pkt = validate_packet(_valid_packet(
            finger_detected=False, hr_valid=False, spo2_valid=False,
            signal_quality=0.0, heart_rate=0, spo2=0,
        ))
        assert not pkt.finger_detected
        assert not pkt.hr_valid
