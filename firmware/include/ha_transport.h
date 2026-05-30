#ifndef HA_TRANSPORT_H
#define HA_TRANSPORT_H

#include <Arduino.h>
#include "ha_config.h"
#include "ha_debug.h"
#include "ha_ble.h"
#include "ha_wifi_transport.h"

class TransportOrchestrator {
public:
    enum ActiveTransport { NONE, BLE, WIFI, SERIAL_ONLY };

    void begin() {
        _mode = TRANSPORT_MODE;

        switch (_mode) {
            case 0:
                HA_SERIAL_PRINTLN("[Transport] Mode: AUTO (BLE primary, Wi-Fi fallback)");
                _ble.begin();
                _activeTransport = BLE;
                break;
            case 1:
                HA_SERIAL_PRINTLN("[Transport] Mode: BLE only");
                _ble.begin();
                _activeTransport = BLE;
                break;
            case 2:
                HA_SERIAL_PRINTLN("[Transport] Mode: Wi-Fi only");
                _wifi.begin();
                _activeTransport = WIFI;
                break;
            case 3:
                HA_SERIAL_PRINTLN("[Transport] Mode: Serial only (debug)");
                _activeTransport = SERIAL_ONLY;
                break;
            default:
                HA_SERIAL_PRINTLN("[Transport] Unknown mode, defaulting to AUTO");
                _mode = 0;
                _ble.begin();
                _activeTransport = BLE;
                break;
        }

        _initialized = true;
    }

    void refresh() {
        if (_initialized) _updateTransportState();
    }

    bool sendPacket(const char* jsonBuf) {
        if (!_initialized) return false;

        HA_SERIAL_PRINTLN(jsonBuf);
        _updateTransportState();

        bool sent = false;
        switch (_activeTransport) {
            case BLE:
                sent = _ble.sendPacket(jsonBuf);
                if (sent) _blePackets++;
                break;
            case WIFI:
                sent = _wifi.sendPacket(jsonBuf);
                if (sent) _wifiPackets++;
                break;
            case SERIAL_ONLY:
                sent = true;
                break;
            default:
                break;
        }

        _totalPackets++;
        return sent;
    }

    bool sendRawSample(const char* jsonBuf) {
        if (!_initialized) return false;

        HA_SERIAL_PRINTLN(jsonBuf);
        _updateTransportState();

        bool sent = false;
        switch (_activeTransport) {
            case BLE:
                sent = _ble.sendRawSample(jsonBuf);
                if (sent) _blePackets++;
                break;
            case WIFI:
                sent = _wifi.sendRawSample(jsonBuf);
                if (sent) _wifiPackets++;
                break;
            case SERIAL_ONLY:
                sent = true;
                break;
            default:
                break;
        }

        _totalPackets++;
        return sent;
    }

    ActiveTransport getActiveTransport() const { return _activeTransport; }

    bool isModelStreamEnabled() const { return _ble.isModelStreamEnabled(); }

    const char* getActiveTransportName() const {
        switch (_activeTransport) {
            case BLE:         return "BLE";
            case WIFI:        return "Wi-Fi";
            case SERIAL_ONLY: return "Serial";
            default:          return "None";
        }
    }

    HaBle& getBle() { return _ble; }

    HaWifiTransport& getWifi() { return _wifi; }

    uint32_t getTotalPackets() const { return _totalPackets; }
    uint32_t getBlePackets() const { return _blePackets; }
    uint32_t getWifiPackets() const { return _wifiPackets; }

    void printStatus() {
        HA_SERIAL_PRINTLN("--- Transport Status ---");
        HA_SERIAL_PRINTF("  Mode:      %d (%s)\n", _mode, _getModeName());
        HA_SERIAL_PRINTF("  Active:    %s\n", getActiveTransportName());
        HA_SERIAL_PRINTF(
            "  BLE:       %s (sent: %lu)\n",
            _bleStateName(),
            (unsigned long)_ble.getPacketsSent()
        );
        HA_SERIAL_PRINTF(
            "  Wi-Fi:     %s (sent: %lu)\n",
            _wifiStateName(),
            (unsigned long)_wifi.getPacketsSent()
        );
        HA_SERIAL_PRINTF("  Total:     %lu packets\n", (unsigned long)_totalPackets);
        HA_SERIAL_PRINTLN("------------------------");
    }

private:
    HaBle _ble;
    HaWifiTransport _wifi;
    int _mode = 0;
    bool _initialized = false;
    ActiveTransport _activeTransport = NONE;
    uint32_t _totalPackets = 0;
    uint32_t _blePackets = 0;
    uint32_t _wifiPackets = 0;

    void _updateTransportState() {
        if (_mode == 1 || _mode == 2 || _mode == 3) {
            return;
        }

        if (_activeTransport == BLE) {
            if (_ble.isClientTimedOut()) {
                HA_SERIAL_PRINTLN("[Transport] BLE client timeout -> switching to Wi-Fi fallback");
                _switchToWifi();
            }
        } else if (_activeTransport == WIFI) {
            if (_ble.isClientConnected()) {
                HA_SERIAL_PRINTLN("[Transport] BLE client reconnected -> switching back to BLE");
                _switchToBle();
            }
        }
    }

    void _switchToWifi() {
        bool connected = _wifi.begin();
        if (connected) {
            _activeTransport = WIFI;
            HA_SERIAL_PRINTLN("[Transport] Wi-Fi fallback ACTIVE");
        } else {
            HA_SERIAL_PRINTLN("[Transport] Wi-Fi fallback FAILED - staying on BLE (advertising)");
        }
    }

    void _switchToBle() {
        _wifi.disconnect();
        _activeTransport = BLE;
        HA_SERIAL_PRINTLN("[Transport] BLE primary RESTORED");
    }

    const char* _getModeName() const {
        switch (_mode) {
            case 0: return "Auto";
            case 1: return "BLE only";
            case 2: return "Wi-Fi only";
            case 3: return "Serial only";
            default: return "Unknown";
        }
    }

    const char* _bleStateName() const {
        switch (_ble.getState()) {
            case HaBle::OFF:         return "OFF";
            case HaBle::ADVERTISING: return "Advertising";
            case HaBle::CONNECTED:   return "Connected";
            case HaBle::ERROR:       return "Error";
            default:                 return "Unknown";
        }
    }

    const char* _wifiStateName() const {
        switch (_wifi.getState()) {
            case HaWifiTransport::OFF:        return "OFF";
            case HaWifiTransport::CONNECTING: return "Connecting";
            case HaWifiTransport::CONNECTED:  return "Connected";
            case HaWifiTransport::FAILED:     return "Failed";
            default:                          return "Unknown";
        }
    }
};

#endif
