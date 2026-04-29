
#ifndef HA_SERIAL_CMD_H
#define HA_SERIAL_CMD_H

#include <Arduino.h>
#include "ha_config.h"
#include "ha_mock_sensors.h"
#include "ha_types.h"

class SerialCmd {
public:
    // Sensörü başlatır.
    void begin(MockSensors* mock, SensorStatus* status) {
        _mock = mock;
        _status = status;
        _buf_pos = 0;
    }

    bool poll() {
        while (Serial.available()) {
            char c = Serial.read();
            if (c == '\n' || c == '\r') {
                if (_buf_pos > 0) {
                    _buf[_buf_pos] = '\0';
                    _process(_buf);
                    _buf_pos = 0;
                    return true;
                }
            } else if (_buf_pos < CMD_BUF_SIZE - 1) {
                _buf[_buf_pos++] = c;
            }
        }
        return false;
    }

    bool request_real_mode = false;
    bool request_mock_mode = false;
    bool request_restart_sensors = false;

private:
    static const int CMD_BUF_SIZE = 128;
    char _buf[CMD_BUF_SIZE];
    int _buf_pos = 0;
    MockSensors* _mock = nullptr;
    SensorStatus* _status = nullptr;

    void _process(const char* cmd) {
        String s(cmd);
        s.trim();
        s.toLowerCase();

        if (s == "help") {
            _print_help();
        } else if (s == "status") {
            _print_status();
        } else if (s == "scan") {
            Serial.println("[CMD] Triggering I2C rescan...");
            request_restart_sensors = true;
        } else if (s == "mode mock") {
            request_mock_mode = true;
            Serial.println("[CMD] Switching to MOCK mode.");
        } else if (s == "mode real") {
            request_real_mode = true;
            Serial.println("[CMD] Switching to REAL mode (requires hardware).");
        } else if (s.startsWith("scenario ")) {
            String name = s.substring(9);
            _set_scenario(name);
        } else if (s == "restart_sensors") {
            request_restart_sensors = true;
            Serial.println("[CMD] Sensor restart requested.");
        } else if (s == "print_config") {
            _print_config();
        } else if (s == "autocycle on") {
            if (_mock) { _mock->enableAutoCycle(true); }
            Serial.println("[CMD] Auto-cycle enabled.");
        } else if (s == "autocycle off") {
            if (_mock) { _mock->enableAutoCycle(false); }
            Serial.println("[CMD] Auto-cycle disabled.");
        } else {
            Serial.printf("[CMD] Unknown command: '%s'. Type 'help'.\n", cmd);
        }
    }

    void _print_help() {
        Serial.println("=== HealthAlert Serial Commands ===");
        Serial.println("  help                 – Show this help");
        Serial.println("  status               – Print sensor status");
        Serial.println("  scan                 – Re-scan I2C bus");
        Serial.println("  mode mock            – Switch to mock sensor mode");
        Serial.println("  mode real            – Switch to real sensor mode");
        Serial.println("  scenario <name>      – Set mock scenario");
        Serial.println("    Scenarios: normal, elevated_hr, low_spo2,");
        Serial.println("      motion_instability, warning_state,");
        Serial.println("      critical_state, recovery_state");
        Serial.println("  restart_sensors      – Reinitialize sensors");
        Serial.println("  print_config         – Print current config");
        Serial.println("  autocycle on|off     – Auto-cycle mock scenarios");
        Serial.println("===================================");
    }

    void _print_status() {
        Serial.println("=== Sensor Status ===");
        Serial.printf("  IMU present:      %s\n", _status->imu_present ? "YES" : "NO");
        Serial.printf("  PPG present:      %s\n", _status->ppg_present ? "YES" : "NO");
        Serial.printf("  IMU OK:           %s\n", _status->imu_ok ? "YES" : "NO");
        Serial.printf("  PPG OK:           %s\n", _status->ppg_ok ? "YES" : "NO");
        Serial.printf("  Degraded mode:    %s\n", _status->degraded_mode ? "YES" : "NO");
        Serial.printf("  Last error:       %u\n", _status->last_error);
        if (_mock) {
            Serial.printf("  Mock scenario:    %s\n", _mock->getScenarioName());
        }
        Serial.println("=====================");
    }

    void _print_config() {
        Serial.println("=== Configuration ===");
        Serial.printf("  Firmware:         %s v%s\n", FW_NAME, FW_VERSION);
        Serial.printf("  Device ID:        %s\n", HA_DEVICE_ID);
        Serial.printf("  I2C SDA:          %d\n", I2C_SDA_PIN);
        Serial.printf("  I2C SCL:          %d\n", I2C_SCL_PIN);
        Serial.printf("  I2C freq:         %lu Hz\n", I2C_FREQUENCY);
        Serial.printf("  Sample rate:      %d Hz\n", SAMPLING_RATE_HZ);
        Serial.printf("  Packet interval:  %d ms\n", PACKET_INTERVAL_MS);
        Serial.printf("  Force mock:       %d\n", FORCE_MOCK_MODE);
        Serial.printf("  Serial baud:      %d\n", SERIAL_BAUD);
        Serial.printf("  Debug logging:    %d\n", DEBUG_LOGGING);
        Serial.println("=====================");
    }

    void _set_scenario(const String& name) {
        if (!_mock) {
            Serial.println("[CMD] Mock engine not available.");
            return;
        }
        for (int i = 0; i < SCENARIO_COUNT; i++) {
            if (name == SCENARIO_NAMES[i]) {
                _mock->setScenario((MockScenario)i);
                return;
            }
        }
        Serial.printf("[CMD] Unknown scenario: '%s'\n", name.c_str());
        Serial.println("[CMD] Available: normal, elevated_hr, low_spo2,");
        Serial.println("  motion_instability, warning_state, critical_state, recovery_state");
    }
};

#endif
