
#ifndef HA_PACKET_H
#define HA_PACKET_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <math.h>
#include "ha_config.h"
#include "ha_types.h"

class PacketFormatter {
public:
    // Paket verisini JSON satirina donusturur.
    static void toJsonLine(const DevicePacket& pkt, char* buf, size_t buf_size) {
        JsonDocument doc;

        doc["patient_id"]      = HA_PATIENT_ID;
        doc["timestamp"]       = String(pkt.timestamp_ms);
        doc["source"]          = "esp32";

        JsonObject imu = doc["imu"].to<JsonObject>();
        imu["acc_x"]           = _round2(pkt.accel_x);
        imu["acc_y"]           = _round2(pkt.accel_y);
        imu["acc_z"]           = _round2(pkt.accel_z);
        imu["gyro_x"]          = _round2(pkt.gyro_x);
        imu["gyro_y"]          = _round2(pkt.gyro_y);
        imu["gyro_z"]          = _round2(pkt.gyro_z);

        if (pkt.ppg_ok || pkt.ir_value > 0 || pkt.red_value > 0) {
            JsonObject ppg = doc["ppg"].to<JsonObject>();
            ppg["ir"]          = pkt.ir_value;
            ppg["red"]         = pkt.red_value;
        }

        if (pkt.hr_valid) doc["heart_rate"] = _round1(pkt.heart_rate);
        else doc["heart_rate"] = nullptr;
        if (pkt.spo2_valid) doc["spo2"] = _round1(pkt.spo2);
        else doc["spo2"] = nullptr;

        doc["device_id"]       = pkt.device_id;
        doc["timestamp_ms"]    = pkt.timestamp_ms;
        doc["mode"]            = pkt.mode;
        doc["packet_seq"]      = pkt.packet_seq;
        doc["signal_quality"]  = _round2(pkt.signal_quality);
        doc["pi_percent"]      = _round2(pkt.pi_percent);
        doc["r_ratio"]         = _round2(pkt.r_ratio);
        doc["ir_range_percent"] = _round2(pkt.ir_range_percent);

        doc["imu_ok"]          = pkt.imu_ok;
        doc["ppg_ok"]          = pkt.ppg_ok;
        doc["hr_valid"]        = pkt.hr_valid;
        doc["spo2_valid"]      = pkt.spo2_valid;
        doc["finger_detected"] = pkt.finger_detected;

        doc["state_hint"]      = pkt.state_hint;

        serializeJson(doc, buf, buf_size);
    }

    // Final demo BLE summary payload. This carries measurements only:
    // personalized risk interpretation stays in the mobile/backend/model layer.
    static void toBleSummaryJson(const DevicePacket& pkt, char* buf, size_t buf_size) {
        JsonDocument doc;

        float accTotal = sqrtf(
            pkt.accel_x * pkt.accel_x +
            pkt.accel_y * pkt.accel_y +
            pkt.accel_z * pkt.accel_z
        );
        float gyroTotal = sqrtf(
            pkt.gyro_x * pkt.gyro_x +
            pkt.gyro_y * pkt.gyro_y +
            pkt.gyro_z * pkt.gyro_z
        );

        doc["t"] = pkt.timestamp_ms;
        doc["fp"] = pkt.finger_detected ? 1 : 0;
        if (pkt.hr_valid) doc["bpm"] = _round1(pkt.heart_rate);
        else doc["bpm"] = nullptr;
        doc["bv"] = pkt.hr_valid ? 1 : 0;
        if (pkt.spo2_valid) doc["spo2e"] = _round1(pkt.spo2);
        else doc["spo2e"] = nullptr;
        doc["sv"] = pkt.spo2_valid ? 1 : 0;
        doc["q"] = (int)roundf(_clamp01(pkt.signal_quality) * 100.0f);
        doc["ir"] = pkt.ir_value;
        doc["red"] = pkt.red_value;

        if (pkt.ppg_ok && pkt.finger_detected) {
            doc["pi"] = _round2(pkt.pi_percent);
            doc["rr"] = _round2(pkt.r_ratio);
            doc["irg"] = _round2(pkt.ir_range_percent);
        } else {
            doc["pi"] = nullptr;
            doc["rr"] = nullptr;
            doc["irg"] = nullptr;
        }

        // Diagnostic fields — help debug stability without reprogramming
        doc["ms"] = (int)pkt.measurement_state;  // PpgState enum value
        doc["ma"] = pkt.motion_artifact ? 1 : 0; // motion artifact flag
        if (pkt.ppg_ok && pkt.finger_detected) {
            doc["br"] = _round1(pkt.bpm_raw);    // raw BPM from peak detection
            doc["sr"] = _round1(pkt.spo2_raw);   // raw SpO2 before ring-buffer
        } else {
            doc["br"] = nullptr;
            doc["sr"] = nullptr;
        }

        doc["ax"] = _round2(pkt.accel_x);
        doc["ay"] = _round2(pkt.accel_y);
        doc["az"] = _round2(pkt.accel_z);
        doc["gx"] = _round2(pkt.gyro_x);
        doc["gy"] = _round2(pkt.gyro_y);
        doc["gz"] = _round2(pkt.gyro_z);
        doc["at"] = _round2(accTotal);
        doc["gt"] = _round2(gyroTotal);

        serializeJson(doc, buf, buf_size);
    }

    // RawSensorSample yapÄ±sÄ±nÄ± JSON satÄ±rÄ±na dÃ¶nÃ¼ÅŸtÃ¼rÃ¼r.
    static void rawToJsonLine(const RawSensorSample& s, char* buf, size_t buf_size) {
        JsonDocument doc;

        doc["patient_id"] = HA_PATIENT_ID;
        doc["timestamp"] = String(s.timestamp_ms);
        doc["source"] = "esp32";

        JsonObject imu = doc["imu"].to<JsonObject>();
        imu["acc_x"] = _round2(s.accel_x);
        imu["acc_y"] = _round2(s.accel_y);
        imu["acc_z"] = _round2(s.accel_z);
        imu["gyro_x"] = _round2(s.gyro_x);
        imu["gyro_y"] = _round2(s.gyro_y);
        imu["gyro_z"] = _round2(s.gyro_z);

        if (s.ppg_ok || s.ir_value > 0 || s.red_value > 0) {
            JsonObject ppg = doc["ppg"].to<JsonObject>();
            ppg["ir"] = s.ir_value;
            ppg["red"] = s.red_value;
        }

        doc["heart_rate"] = nullptr;
        doc["spo2"] = nullptr;

        doc["device_id"] = s.device_id;
        doc["timestamp_ms"] = s.timestamp_ms;
        doc["sample_seq"] = s.sample_seq;
        doc["window_seq"] = s.window_seq;
        doc["sample_rate_hz"] = s.sample_rate_hz;
        doc["mode"] = s.mode;
        doc["imu_ok"] = s.imu_ok;
        doc["ppg_ok"] = s.ppg_ok;
        doc["finger_detected"] = s.finger_detected;
        doc["signal_quality"] = _round2(s.signal_quality);
        doc["pi_percent"] = _round2(s.pi_percent);
        doc["r_ratio"] = _round2(s.r_ratio);
        doc["ir_range_percent"] = _round2(s.ir_range_percent);

        serializeJson(doc, buf, buf_size);
    }

private:
    static float _round1(float v) { return roundf(v * 10.0f) / 10.0f; }
    static float _round2(float v) { return roundf(v * 100.0f) / 100.0f; }
    static float _clamp01(float v) {
        if (v < 0.0f) return 0.0f;
        if (v > 1.0f) return 1.0f;
        return v;
    }
};

#endif
