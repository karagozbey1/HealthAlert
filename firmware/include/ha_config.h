
#ifndef HA_CONFIG_H
#define HA_CONFIG_H

#include <Arduino.h>

#define FW_VERSION        "1.0.0"
#define FW_NAME           "HealthAlert-ESP32"

#ifndef HA_DEVICE_ID
#define HA_DEVICE_ID      "ha-esp32-001"
#endif

#define I2C_SDA_PIN       21
#define I2C_SCL_PIN       22
#define I2C_FREQUENCY     400000UL

#define SAMPLING_RATE_HZ  25
#define PACKET_INTERVAL_MS 1000

#ifndef FORCE_MOCK_MODE
#define FORCE_MOCK_MODE   1
#endif

#define SENSOR_INIT_RETRIES     3
#define SENSOR_INIT_RETRY_MS    500
#define SENSOR_READ_TIMEOUT_MS  50

#define SERIAL_BAUD       115200

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
#endif
