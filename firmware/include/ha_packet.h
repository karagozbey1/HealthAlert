
#ifndef HA_PACKET_H
#define HA_PACKET_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include "ha_types.h"

class PacketFormatter {
public:
    // DevicePacket yapısını JSON satırına dönüştürür.
    static void toJsonLine(const DevicePacket& pkt, char* buf, size_t buf_size) {
        JsonDocument doc;

        doc["device_id"]       = pkt.device_id;
        doc["timestamp_ms"]    = pkt.timestamp_ms;
        doc["mode"]            = pkt.mode;
        doc["packet_seq"]      = pkt.packet_seq;

        doc["accel_x"]         = _round2(pkt.accel_x);
        doc["accel_y"]         = _round2(pkt.accel_y);
        doc["accel_z"]         = _round2(pkt.accel_z);
        doc["gyro_x"]          = _round2(pkt.gyro_x);
        doc["gyro_y"]          = _round2(pkt.gyro_y);
        doc["gyro_z"]          = _round2(pkt.gyro_z);

        doc["red_value"]       = pkt.red_value;
        doc["ir_value"]        = pkt.ir_value;
        doc["heart_rate"]      = _round1(pkt.heart_rate);
        doc["spo2"]            = _round1(pkt.spo2);
        doc["signal_quality"]  = _round2(pkt.signal_quality);

        doc["imu_ok"]          = pkt.imu_ok;
        doc["ppg_ok"]          = pkt.ppg_ok;
        doc["hr_valid"]        = pkt.hr_valid;
        doc["spo2_valid"]      = pkt.spo2_valid;
        doc["finger_detected"] = pkt.finger_detected;

        doc["state_hint"]      = pkt.state_hint;

        serializeJson(doc, buf, buf_size);
    }

private:
    static float _round1(float v) { return roundf(v * 10.0f) / 10.0f; }
    static float _round2(float v) { return roundf(v * 100.0f) / 100.0f; }
};

#endif
