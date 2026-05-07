import pytest
from packet_schema import DevicePacketSchema, validate_packet


# Geçerli bir paket sözlüğü üretir ve verilen alanları üzerine yazar.
def _valid_packet(**overrides) -> dict:
    base = {
        "device_id": "ha-esp32-001",
        "timestamp_ms": 123456789,
        "mode": "mock",
        "packet_seq": 42,
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


class TestPacketSchemaValid:
    # Geçerli paketin şemadan sorunsuz geçtiğini doğrular.
    def test_valid_packet(self):
        pkt = validate_packet(_valid_packet())
        assert pkt.device_id == "ha-esp32-001"
        assert pkt.packet_seq == 42
        assert pkt.mode == "mock"

    # Gerçek mod değerinin kabul edildiğini doğrular.
    def test_real_mode(self):
        pkt = validate_packet(_valid_packet(mode="real"))
        assert pkt.mode == "real"

    # Sahte mod değerinin kabul edildiğini doğrular.
    def test_mock_mode(self):
        pkt = validate_packet(_valid_packet(mode="mock"))
        assert pkt.mode == "mock"

    # Alt sınır değerleriyle paketin kabul edildiğini doğrular.
    def test_minimum_values(self):
        pkt = validate_packet(_valid_packet(
            timestamp_ms=0, packet_seq=0, red_value=0, ir_value=0,
            heart_rate=0, spo2=0, signal_quality=0,
        ))
        assert pkt.timestamp_ms == 0
        assert pkt.spo2 == 0

    # SpO2 üst sınırının kabul edildiğini doğrular.
    def test_maximum_spo2(self):
        pkt = validate_packet(_valid_packet(spo2=100.0))
        assert pkt.spo2 == 100.0

    # Sinyal kalitesi sınır değerlerinin kabul edildiğini doğrular.
    def test_signal_quality_range(self):
        pkt = validate_packet(_valid_packet(signal_quality=0.0))
        assert pkt.signal_quality == 0.0
        pkt = validate_packet(_valid_packet(signal_quality=1.0))
        assert pkt.signal_quality == 1.0

    # Tüm bayraklar kapalıyken paketin yine doğrulandığını kontrol eder.
    def test_all_flags_false(self):
        pkt = validate_packet(_valid_packet(
            imu_ok=False, ppg_ok=False, hr_valid=False,
            spo2_valid=False, finger_detected=False,
        ))
        assert not pkt.imu_ok
        assert not pkt.finger_detected

    # state_hint alanı yoksa varsayılan değerin atandığını doğrular.
    def test_default_state_hint(self):
        data = _valid_packet()
        del data["state_hint"]
        pkt = validate_packet(data)
        assert pkt.state_hint == "normal"


class TestPacketSchemaInvalid:
    # Geçersiz mod değerinin reddedildiğini doğrular.
    def test_invalid_mode(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(mode="invalid"))

    # device_id alanı eksik olduğunda doğrulamanın hata verdiğini kontrol eder.
    def test_missing_device_id(self):
        data = _valid_packet()
        del data["device_id"]
        with pytest.raises(Exception):
            validate_packet(data)

    # Boş device_id değerinin reddedildiğini doğrular.
    def test_empty_device_id(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(device_id=""))

    # Negatif zaman damgasının reddedildiğini doğrular.
    def test_negative_timestamp(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(timestamp_ms=-1))

    # Negatif paket sırasının reddedildiğini doğrular.
    def test_negative_packet_seq(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(packet_seq=-1))

    # 100 üzerindeki SpO2 değerinin reddedildiğini doğrular.
    def test_spo2_over_100(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(spo2=101))

    # 1 üzerindeki sinyal kalitesinin reddedildiğini doğrular.
    def test_signal_quality_over_1(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(signal_quality=1.5))

    # Negatif kırmızı kanal değerinin reddedildiğini doğrular.
    def test_negative_red_value(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(red_value=-1))

    # Zorunlu alan eksik olduğunda doğrulamanın hata verdiğini kontrol eder.
    def test_missing_required_field(self):
        data = _valid_packet()
        del data["heart_rate"]
        with pytest.raises(Exception):
            validate_packet(data)

    # Sayısal alan türü bozulduğunda doğrulamanın hata verdiğini kontrol eder.
    def test_wrong_type_accel(self):
        with pytest.raises(Exception):
            validate_packet(_valid_packet(accel_x="not_a_float"))
