
#ifndef HA_TYPES_H
#define HA_TYPES_H

#include <Arduino.h>

/// Sensör okuma sonucunu firmware içinde taşır.
struct ImuSample {
    float accel_x;
    float accel_y;
    float accel_z;
    float gyro_x;
    float gyro_y;
    float gyro_z;
    bool  valid;
};

// Measurement state: 0=no_finger, 1=warming_up, 2=stabilizing, 3=stable, 4=unstable, 5=motion_artifact
/// Firmware tarafındaki ilgili donanım veya taşıma sorumluluğunu temsil eder.
enum PpgState : uint8_t {
    PPG_NO_FINGER      = 0,
    PPG_WARMING_UP     = 1,
    PPG_STABILIZING    = 2,
    PPG_STABLE         = 3,
    PPG_UNSTABLE       = 4,
    PPG_MOTION_ARTIFACT = 5,
};

/// Sensör okuma sonucunu firmware içinde taşır.
struct PpgSample {
    uint32_t red_value;
    uint32_t ir_value;
    float    heart_rate;
    float    spo2;
    float    signal_quality;
    float    pi_percent;
    float    r_ratio;
    float    ir_range_percent;
    bool     finger_detected;
    bool     hr_valid;
    bool     spo2_valid;
    bool     valid;
    // Extended diagnostic fields
    float    bpm_raw;           // Last raw BPM from peak detection (before stabilization)
    float    spo2_raw;          // Last raw SpO2 estimate (before ring-buffer smoothing)
    PpgState measurement_state; // Current acquisition state
    bool     motion_artifact;   // True when motion gate invalidated the reading
};

/// Sensör okuma sonucunu firmware içinde taşır.
struct SensorStatus {
    bool imu_present;
    bool ppg_present;
    bool imu_ok;
    bool ppg_ok;
    bool degraded_mode;
    uint8_t last_error;
};

/// Firmware ile mobil uygulama arasında taşınan telemetri verisini temsil eder.
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
    float pi_percent;
    float r_ratio;
    float ir_range_percent;

    bool imu_ok;
    bool ppg_ok;
    bool hr_valid;
    bool spo2_valid;
    bool finger_detected;
    bool motion_artifact;       // True when motion gate fired

    const char* state_hint;
    uint32_t packet_seq;
    // Diagnostic fields — useful for debugging without reprogramming
    float    bpm_raw;           // Raw BPM from peak detection
    float    spo2_raw;          // Raw SpO2 before ring-buffer smoothing
    uint8_t  measurement_state; // PpgState enum value
};

/// Sensör okuma sonucunu firmware içinde taşır.
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
    float pi_percent;
    float r_ratio;
    float ir_range_percent;
};

#endif
