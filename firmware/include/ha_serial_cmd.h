#ifndef HA_SERIAL_CMD_H
#define HA_SERIAL_CMD_H

#include <Arduino.h>
#include "ha_config.h"
#include "ha_debug.h"
#include "ha_mock_sensors.h"
#include "ha_types.h"

class SerialCmd {
public:
    void begin(MockSensors* mock, SensorStatus* status) {
        _mock = mock;
        _status = status;
        _buf_pos = 0;
    }

    bool poll() {
        while (HA_SERIAL_AVAILABLE()) {
            char c = (char)HA_SERIAL_READ();
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
            HA_SERIAL_PRINTLN("[CMD] Triggering I2C rescan...");
            request_restart_sensors = true;
        } else if (s == "mode mock") {
            request_mock_mode = true;
            HA_SERIAL_PRINTLN("[CMD] Switching to MOCK mode.");
        } else if (s == "mode real") {
            request_real_mode = true;
            HA_SERIAL_PRINTLN("[CMD] Switching to REAL mode (requires hardware).");
        } else if (s.startsWith("scenario ")) {
            String name = s.substring(9);
            _set_scenario(name);
        } else if (s == "restart_sensors") {
            request_restart_sensors = true;
            HA_SERIAL_PRINTLN("[CMD] Sensor restart requested.");
        } else if (s == "print_config") {
            _print_config();
        } else if (s == "autocycle on") {
            if (_mock) { _mock->enableAutoCycle(true); }
            HA_SERIAL_PRINTLN("[CMD] Auto-cycle enabled.");
        } else if (s == "autocycle off") {
            if (_mock) { _mock->enableAutoCycle(false); }
            HA_SERIAL_PRINTLN("[CMD] Auto-cycle disabled.");
        } else {
            HA_SERIAL_PRINTF("[CMD] Unknown command: '%s'. Type 'help'.\n", cmd);
        }
    }

    void _print_help() {
        HA_SERIAL_PRINTLN("=== HealthAlert Serial Commands ===");
        HA_SERIAL_PRINTLN("  help                 - Show this help");
        HA_SERIAL_PRINTLN("  status               - Print sensor status");
        HA_SERIAL_PRINTLN("  scan                 - Re-scan I2C bus");
        HA_SERIAL_PRINTLN("  mode mock            - Switch to mock sensor mode");
        HA_SERIAL_PRINTLN("  mode real            - Switch to real sensor mode");
        HA_SERIAL_PRINTLN("  scenario <name>      - Set mock scenario");
        HA_SERIAL_PRINTLN("    Scenarios: normal, elevated_hr, low_spo2,");
        HA_SERIAL_PRINTLN("      motion_instability, warning_state,");
        HA_SERIAL_PRINTLN("      critical_state, recovery_state");
        HA_SERIAL_PRINTLN("  restart_sensors      - Reinitialize sensors");
        HA_SERIAL_PRINTLN("  print_config         - Print current config");
        HA_SERIAL_PRINTLN("  autocycle on|off     - Auto-cycle mock scenarios");
        HA_SERIAL_PRINTLN("===================================");
    }

    void _print_status() {
        HA_SERIAL_PRINTLN("=== Sensor Status ===");
        HA_SERIAL_PRINTF("  IMU present:      %s\n", _status->imu_present ? "YES" : "NO");
        HA_SERIAL_PRINTF("  PPG present:      %s\n", _status->ppg_present ? "YES" : "NO");
        HA_SERIAL_PRINTF("  IMU OK:           %s\n", _status->imu_ok ? "YES" : "NO");
        HA_SERIAL_PRINTF("  PPG OK:           %s\n", _status->ppg_ok ? "YES" : "NO");
        HA_SERIAL_PRINTF("  Degraded mode:    %s\n", _status->degraded_mode ? "YES" : "NO");
        HA_SERIAL_PRINTF("  Last error:       %u\n", _status->last_error);
        if (_mock) {
            HA_SERIAL_PRINTF("  Mock scenario:    %s\n", _mock->getScenarioName());
        }
        HA_SERIAL_PRINTLN("=====================");
    }

    void _print_config() {
        HA_SERIAL_PRINTLN("=== Configuration ===");
        HA_SERIAL_PRINTF("  Firmware:         %s v%s\n", FW_NAME, FW_VERSION);
        HA_SERIAL_PRINTF("  Device ID:        %s\n", HA_DEVICE_ID);
        HA_SERIAL_PRINTF("  I2C SDA:          %d\n", I2C_SDA_PIN);
        HA_SERIAL_PRINTF("  I2C SCL:          %d\n", I2C_SCL_PIN);
        HA_SERIAL_PRINTF("  I2C freq:         %lu Hz\n", I2C_FREQUENCY);
        HA_SERIAL_PRINTF("  Sample rate:      %d Hz\n", SAMPLING_RATE_HZ);
        HA_SERIAL_PRINTF("  Packet interval:  %d ms\n", PACKET_INTERVAL_MS);
        HA_SERIAL_PRINTF("  Force mock:       %d\n", FORCE_MOCK_MODE);
        HA_SERIAL_PRINTF("  Serial baud:      %d\n", SERIAL_BAUD);
        HA_SERIAL_PRINTF("  Debug logging:    %d\n", DEBUG_LOGGING);
        HA_SERIAL_PRINTLN("=====================");
    }

    void _set_scenario(const String& name) {
        if (!_mock) {
            HA_SERIAL_PRINTLN("[CMD] Mock engine not available.");
            return;
        }
        for (int i = 0; i < SCENARIO_COUNT; i++) {
            if (name == SCENARIO_NAMES[i]) {
                _mock->setScenario((MockScenario)i);
                return;
            }
        }
        HA_SERIAL_PRINTF("[CMD] Unknown scenario: '%s'\n", name.c_str());
        HA_SERIAL_PRINTLN("[CMD] Available: normal, elevated_hr, low_spo2,");
        HA_SERIAL_PRINTLN("  motion_instability, warning_state, critical_state, recovery_state");
    }
};

#endif
