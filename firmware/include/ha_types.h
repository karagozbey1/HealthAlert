
#ifndef HA_TYPES_H
#define HA_TYPES_H

#include <Arduino.h>

struct ImuSample {
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    bool  valid;
};

struct PpgSample {
    uint32_t red_value;
    uint32_t ir_value;
    float    heart_rate;
    float    spo2;
    float    signal_quality;
    bool     finger_detected;
    bool     hr_valid;
    bool     spo2_valid;
    bool     valid;
};

struct SensorStatus {
    bool imu_present;
    bool ppg_present;
    bool imu_ok;
    bool ppg_ok;
    bool degraded_mode;
    uint8_t last_error;
};

struct DevicePacket {
    const char* device_id;
    unsigned long timestamp_ms;
    const char* mode;

    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;

    uint32_t red_value;
    uint32_t ir_value;
    float heart_rate;
    float spo2;
    float signal_quality;

    bool imu_ok;
    bool ppg_ok;
    bool hr_valid;
    bool spo2_valid;
    bool finger_detected;

    const char* state_hint;
    uint32_t packet_seq;
};

struct RawSensorSample {
    const char* device_id;
    unsigned long timestamp_ms;
    const char* mode;
    uint32_t sample_seq;
    uint32_t window_seq;
    uint16_t sample_rate_hz;

    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;

    uint32_t red_value;
    uint32_t ir_value;

    bool imu_ok;
    bool ppg_ok;
    bool finger_detected;
    float signal_quality;
};

#endif
