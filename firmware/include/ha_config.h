
#ifndef HA_CONFIG_H
#define HA_CONFIG_H

#include <Arduino.h>

#define FW_VERSION        "1.0.0"
#define FW_NAME           "HealthAlert-ESP32"

#ifndef HA_DEVICE_ID
#define HA_DEVICE_ID      "ha-esp32-001"
#endif

#ifndef HA_PATIENT_ID
#define HA_PATIENT_ID     "demo_patient_001"
#endif

#define I2C_SDA_PIN       21
#define I2C_SCL_PIN       22
#define I2C_FREQUENCY     400000UL

#define SAMPLING_RATE_HZ  25
#define PACKET_INTERVAL_MS 1000

#define BLE_MODEL_STREAM_ENABLED        1
#define MODEL_STREAM_RATE_HZ            50
// PPG ring buffer fills at MODEL_STREAM_RATE_HZ (50 Hz) because
// collectRawSample() calls _ppg.read() at that rate. All sample-count-based
// BPM calculations must use this rate, NOT SAMPLING_RATE_HZ (25 Hz).
#define PPG_EFFECTIVE_SAMPLE_RATE_HZ    MODEL_STREAM_RATE_HZ
#define MODEL_WINDOW_SIZE               200
#define MODEL_WINDOW_DURATION_MS        4000
#define MODEL_STREAM_TRANSPORT          "ble"
#define SUMMARY_PACKET_INTERVAL_MS      1000
#define MODEL_STREAM_SAMPLE_FORMAT      "jsonl_debug"

#ifndef FORCE_MOCK_MODE
#define FORCE_MOCK_MODE   0
#endif

#define SENSOR_INIT_RETRIES     3
#define SENSOR_INIT_RETRY_MS    500
#define SENSOR_READ_TIMEOUT_MS  50

#define SERIAL_BAUD       115200

#ifndef DEBUG_SERIAL
#define DEBUG_SERIAL      1
#endif

#ifndef DEBUG_LOGGING
#define DEBUG_LOGGING     1
#endif

#define MPU6050_I2C_ADDR  0x68
#define MAX30102_I2C_ADDR 0x57

#define MAX30102_LED_BRIGHTNESS   0x1F
#define MAX30102_SAMPLE_AVG       4
#define MAX30102_LED_MODE         2
#define MAX30102_SAMPLE_RATE      100
#define MAX30102_PULSE_WIDTH      411
#define MAX30102_ADC_RANGE        4096

#define MPU6050_ACCEL_RANGE       0
#define MPU6050_GYRO_RANGE        0
#define BLE_DEVICE_NAME           "HealthAlert"
#define BLE_SERVICE_UUID          "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_TELEMETRY_CHAR_UUID   "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_DEVICE_INFO_CHAR_UUID "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_RAW_SAMPLE_CHARACTERISTIC_UUID "6e400004-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_CONTROL_CHARACTERISTIC_UUID    "6e400005-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_STATUS_CHARACTERISTIC_UUID     "6e400006-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_CLIENT_TIMEOUT_MS     15000
#define BLE_ADV_INTERVAL_MS       100

#ifndef WIFI_SSID
#define WIFI_SSID                 ""
#endif
#ifndef WIFI_PASS
#define WIFI_PASS                 ""
#endif
#ifndef WIFI_BACKEND_URL
#define WIFI_BACKEND_URL          "http://192.168.1.100:8000"
#endif
#define WIFI_CONNECT_TIMEOUT_MS   10000
#define WIFI_RECONNECT_INTERVAL_MS 30000

#ifndef TRANSPORT_MODE
#define TRANSPORT_MODE            0
#endif

// ── PPG measurement stability thresholds ──────────────────────────────────
// Extended warmup: 10 s ensures ring buffer (4 s) is fully refreshed with
// stable post-placement data before any measurement is accepted.
#define PPG_WARMUP_MS             10000UL

// BPM: minimum consecutive 1-s period of stable readings before hr_valid=true.
// At 1-s BLE packet rate, BPM_STABLE_WINDOW_MS = 3 s → 3 consecutive packets.
#define BPM_STABLE_WINDOW_MS      3000UL
// BPM jump threshold: changes > this value require re-confirmation.
#define BPM_JUMP_THRESH_BPM       20.0f
// BPM jump confirmation: seconds of new stable reading before accepting jump.
#define BPM_JUMP_WINDOW_MS        3000UL

// SpO2: only report valid SpO2 after this window of consistent estimates.
#define SPO2_STABLE_WINDOW_MS     5000UL
// SpO2 ring buffer size (stores last N valid raw SpO2 estimates).
#define SPO2_RING_SIZE            6
// R-ratio range for physiological SpO2 [88%, 100%] with formula 110-25*R.
// R=0.40 → 100%,  R=0.88 → 88%.
#define SPO2_R_MIN                0.40f
#define SPO2_R_MAX                0.88f
// Maximum allowed spread in SpO2 ring buffer before marking consistent.
#define SPO2_MAX_SPREAD_PCT       5.0f

// Motion gate thresholds
#define MOTION_GYRO_GATE_DPS      25.0f
#define MOTION_ACCEL_GATE_G       0.35f

#endif
