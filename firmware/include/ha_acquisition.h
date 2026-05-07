
#ifndef HA_ACQUISITION_H
#define HA_ACQUISITION_H

#include <Arduino.h>
#include "ha_config.h"
#include "ha_types.h"
#include "ha_mpu6050.h"
#include "ha_max30102.h"
#include "ha_mock_sensors.h"

class AcquisitionManager {
public:

    
    // Sensörü başlatır.
    void begin(bool useMock) {
        _useMock = useMock;
        _packetSeq = 0;
        _rawSampleSeq = 0;

        _status.imu_present = false;
        _status.ppg_present = false;
        _status.imu_ok = false;
        _status.ppg_ok = false;
        _status.degraded_mode = false;
        _status.last_error = 0;

        if (_useMock) {
            _mock.begin();
        }
    }

    
    // Gerçek donanım sensörlerini başlatır.
    bool initRealSensors() {
        bool any_ok = false;

        if (_imu.begin()) {
            _status.imu_present = true;
            _status.imu_ok = true;
            any_ok = true;
        } else {
            Serial.println("[ACQ] MPU6050 unavailable – IMU degraded.");
            _status.imu_present = false;
            _status.imu_ok = false;
            _status.last_error |= 0x01;
        }

        if (_ppg.begin()) {
            _status.ppg_present = true;
            _status.ppg_ok = true;
            any_ok = true;
        } else {
            Serial.println("[ACQ] MAX30102 unavailable – PPG degraded.");
            _status.ppg_present = false;
            _status.ppg_ok = false;
            _status.last_error |= 0x02;
        }

        _status.degraded_mode = !(_status.imu_ok && _status.ppg_ok);

        if (_status.degraded_mode) {
            Serial.printf("[ACQ] Degraded mode active (imu=%d ppg=%d err=0x%02X)\n",
                          _status.imu_ok, _status.ppg_ok, _status.last_error);
        }

        return any_ok;
    }

    
    // Sensörleri yeniden başlatır.
    bool reinitSensors() {
        if (_useMock) return true;

        _status.imu_ok = false;
        _status.ppg_ok = false;
        _status.last_error = 0;

        bool imu_ok = _imu.reinit();
        bool ppg_ok = _ppg.reinit();

        _status.imu_ok = imu_ok;
        _status.ppg_ok = ppg_ok;
        _status.imu_present = imu_ok;
        _status.ppg_present = ppg_ok;
        _status.degraded_mode = !(imu_ok && ppg_ok);

        if (!imu_ok) _status.last_error |= 0x01;
        if (!ppg_ok) _status.last_error |= 0x02;

        return imu_ok || ppg_ok;
    }

    
    // Mock/gerçek sensör modunu çalışma anında değiştirir.
    void setMockMode(bool useMock) {
        if (_useMock == useMock) return;
        _useMock = useMock;

        if (_useMock) {
            _mock.begin();
            _status.imu_ok = true;
            _status.ppg_ok = true;
            _status.degraded_mode = false;
            _status.last_error = 0;
            Serial.println("[ACQ] Switched to MOCK mode.");
        } else {
            Serial.println("[ACQ] Switched to REAL mode – call initRealSensors() to activate.");
        }
    }

    
    // Tum sensor verilerini tek paket icinde toplar.
    DevicePacket collect() {
        DevicePacket pkt;

        pkt.device_id   = HA_DEVICE_ID;
        pkt.timestamp_ms = millis();
        pkt.mode        = _useMock ? "mock" : "real";
        pkt.packet_seq  = _packetSeq++;
        pkt.state_hint  = _useMock ? _mock.getScenarioName() : "real";

        if (_useMock) {
            _collectMock(pkt);
        } else {
            _collectReal(pkt);
        }

        return pkt;
    }

    // Model-window hattÄ± iÃ§in 50Hz ham ornek toplar.
    RawSensorSample collectRawSample(uint16_t sampleRateHz) {
        DevicePacket pkt;
        pkt.device_id = HA_DEVICE_ID;
        pkt.timestamp_ms = millis();
        pkt.mode = _useMock ? "mock" : "real";
        pkt.packet_seq = _packetSeq;
        pkt.state_hint = _useMock ? _mock.getScenarioName() : "real";

        if (_useMock) {
            _collectMock(pkt);
        } else {
            _collectReal(pkt);
        }

        RawSensorSample raw;
        raw.device_id = pkt.device_id;
        raw.timestamp_ms = pkt.timestamp_ms;
        raw.mode = pkt.mode;
        raw.sample_seq = _rawSampleSeq++;
        raw.window_seq = raw.sample_seq / MODEL_WINDOW_SIZE;
        raw.sample_rate_hz = sampleRateHz;
        raw.accel_x = pkt.accel_x;
        raw.accel_y = pkt.accel_y;
        raw.accel_z = pkt.accel_z;
        raw.gyro_x = pkt.gyro_x;
        raw.gyro_y = pkt.gyro_y;
        raw.gyro_z = pkt.gyro_z;
        raw.red_value = pkt.red_value;
        raw.ir_value = pkt.ir_value;
        raw.imu_ok = pkt.imu_ok;
        raw.ppg_ok = pkt.ppg_ok;
        raw.finger_detected = pkt.finger_detected;
        raw.signal_quality = pkt.signal_quality;
        return raw;
    }

    MockSensors&  getMock()   { return _mock; }
    // Sensör durum yapısını döndürür.
    SensorStatus& getStatus() { return _status; }

    bool isMockMode() const { return _useMock; }

private:
    bool          _useMock = true;
    uint32_t      _packetSeq = 0;
    uint32_t      _rawSampleSeq = 0;

    HaMpu6050     _imu;
    HaMax30102    _ppg;
    MockSensors   _mock;
    SensorStatus  _status;

    void _collectReal(DevicePacket& pkt) {
        if (_status.imu_ok) {
            ImuSample imu = _imu.read();
            if (imu.valid) {
                pkt.accel_x = imu.accel_x;
                pkt.accel_y = imu.accel_y;
                pkt.accel_z = imu.accel_z;
                pkt.gyro_x  = imu.gyro_x;
                pkt.gyro_y  = imu.gyro_y;
                pkt.gyro_z  = imu.gyro_z;
                pkt.imu_ok  = true;
                _status.imu_ok = true;
            } else {
                _setImuFailed(pkt);
            }
        } else {
            if ((_packetSeq & 0xFF) == 0) {
                if (_imu.reinit()) {
                    _status.imu_ok = true;
                    _status.imu_present = true;
                    _status.last_error &= ~0x01;
                    Serial.println("[ACQ] IMU recovered.");
                }
            }
            _setImuFailed(pkt);
        }

        if (_status.ppg_ok) {
            PpgSample ppg = _ppg.read();
            if (ppg.valid) {
                pkt.red_value       = ppg.red_value;
                pkt.ir_value        = ppg.ir_value;
                pkt.heart_rate      = ppg.heart_rate;
                pkt.spo2            = ppg.spo2;
                pkt.signal_quality  = ppg.signal_quality;
                pkt.finger_detected = ppg.finger_detected;
                pkt.hr_valid        = ppg.hr_valid;
                pkt.spo2_valid      = ppg.spo2_valid;
                pkt.ppg_ok          = true;
                _status.ppg_ok      = true;
            } else {
                _setPpgFailed(pkt);
            }
        } else {
            if ((_packetSeq & 0xFF) == 0) {
                if (_ppg.reinit()) {
                    _status.ppg_ok = true;
                    _status.ppg_present = true;
                    _status.last_error &= ~0x02;
                    Serial.println("[ACQ] PPG recovered.");
                }
            }
            _setPpgFailed(pkt);
        }

        _status.degraded_mode = !(pkt.imu_ok && pkt.ppg_ok);

#if DEBUG_LOGGING
        if (_status.degraded_mode) {
            Serial.printf("[ACQ] Degraded – imu=%d ppg=%d seq=%lu\n",
                          pkt.imu_ok, pkt.ppg_ok, (unsigned long)pkt.packet_seq);
        }
#endif
    }

    void _collectMock(DevicePacket& pkt) {
        _mock.updateAutoCycle();

        ImuSample imu = _mock.readImu();
        PpgSample ppg = _mock.readPpg();

        pkt.accel_x = imu.accel_x;
        pkt.accel_y = imu.accel_y;
        pkt.accel_z = imu.accel_z;
        pkt.gyro_x  = imu.gyro_x;
        pkt.gyro_y  = imu.gyro_y;
        pkt.gyro_z  = imu.gyro_z;
        pkt.imu_ok  = imu.valid;

        pkt.red_value       = ppg.red_value;
        pkt.ir_value        = ppg.ir_value;
        pkt.heart_rate      = ppg.heart_rate;
        pkt.spo2            = ppg.spo2;
        pkt.signal_quality  = ppg.signal_quality;
        pkt.finger_detected = ppg.finger_detected;
        pkt.hr_valid        = ppg.hr_valid;
        pkt.spo2_valid      = ppg.spo2_valid;
        pkt.ppg_ok          = ppg.valid;

        _mock.tick();
    }

    void _setImuFailed(DevicePacket& pkt) {
        pkt.accel_x = 0.0f;
        pkt.accel_y = 0.0f;
        pkt.accel_z = 0.0f;
        pkt.gyro_x  = 0.0f;
        pkt.gyro_y  = 0.0f;
        pkt.gyro_z  = 0.0f;
        pkt.imu_ok  = false;
        _status.imu_ok = false;
        _status.last_error |= 0x01;
    }

    void _setPpgFailed(DevicePacket& pkt) {
        pkt.red_value       = 0;
        pkt.ir_value        = 0;
        pkt.heart_rate      = 0.0f;
        pkt.spo2            = 0.0f;
        pkt.signal_quality  = 0.0f;
        pkt.finger_detected = false;
        pkt.hr_valid        = false;
        pkt.spo2_valid      = false;
        pkt.ppg_ok          = false;
        _status.ppg_ok = false;
        _status.last_error |= 0x02;
    }
};

#endif
