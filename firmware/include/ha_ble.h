#ifndef HA_BLE_H
#define HA_BLE_H

#include <Arduino.h>
#include <esp_bt.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "ha_config.h"
#include "ha_debug.h"

class HaBle {
public:
    enum State { OFF, ADVERTISING, CONNECTED, ERROR };

    void begin() {
        if (_initialized) {
            HA_SERIAL_PRINTLN("[BLE] Already initialized, skipping.");
            return;
        }

        HA_SERIAL_PRINTF("[BLE] Free heap before init: %u bytes\n", esp_get_free_heap_size());

        // Release Classic BT controller memory — required before BLE-only init.
        // Returns ESP_ERR_INVALID_STATE if already released; that is acceptable.
        esp_err_t mem_err = esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT);
        if (mem_err != ESP_OK && mem_err != ESP_ERR_INVALID_STATE) {
            HA_SERIAL_PRINTF("[BLE] Classic BT mem release warning: %d\n", (int)mem_err);
        }

        BLEDevice::init(BLE_DEVICE_NAME);

        _server = BLEDevice::createServer();
        _server->setCallbacks(new ServerCallbacks(this));

        BLEService* service = _server->createService(BLE_SERVICE_UUID);

        _telemetryChar = service->createCharacteristic(
            BLE_TELEMETRY_CHAR_UUID,
            BLECharacteristic::PROPERTY_NOTIFY
        );
        _telemetryChar->addDescriptor(new BLE2902());

        _rawSampleChar = service->createCharacteristic(
            BLE_RAW_SAMPLE_CHARACTERISTIC_UUID,
            BLECharacteristic::PROPERTY_NOTIFY
        );
        _rawSampleChar->addDescriptor(new BLE2902());

        _deviceInfoChar = service->createCharacteristic(
            BLE_DEVICE_INFO_CHAR_UUID,
            BLECharacteristic::PROPERTY_READ
        );
        char infoJson[256];
        snprintf(infoJson, sizeof(infoJson),
                 "{\"device_id\":\"%s\",\"fw_version\":\"%s\",\"fw_name\":\"%s\"}",
                 HA_DEVICE_ID, FW_VERSION, FW_NAME);
        _deviceInfoChar->setValue(infoJson);

        _controlChar = service->createCharacteristic(
            BLE_CONTROL_CHARACTERISTIC_UUID,
            BLECharacteristic::PROPERTY_WRITE
        );
        _controlChar->setCallbacks(new ControlCallbacks(this));

        _statusChar = service->createCharacteristic(
            BLE_STATUS_CHARACTERISTIC_UUID,
            BLECharacteristic::PROPERTY_READ
        );
        _updateStatusValue();

        service->start();

        BLEAdvertising* advertising = BLEDevice::getAdvertising();
        advertising->addServiceUUID(BLE_SERVICE_UUID);
        advertising->setScanResponse(true);
        advertising->setMinPreferred(0x06);
        advertising->setMinPreferred(0x12);
        BLEDevice::startAdvertising();

        _state = ADVERTISING;
        _lastClientActivity = millis();
        _initialized = true;

        HA_SERIAL_PRINTLN("[BLE] GATT server started, advertising...");
    }

    bool sendPacket(const char* jsonBuf) {
        if (!_initialized || _state != CONNECTED || !_clientConnected || !_summaryEnabled) {
            return false;
        }
        size_t len = strlen(jsonBuf);
        if (len > 512) len = 512;
        _telemetryChar->setValue((uint8_t*)jsonBuf, len);
        _telemetryChar->notify();
        _packetsSent++;
        return true;
    }

    bool sendRawSample(const char* jsonBuf) {
        if (!_initialized || _state != CONNECTED || !_clientConnected || !_modelStreamEnabled) {
            return false;
        }
        size_t len = strlen(jsonBuf);
        if (len > 512) len = 512;
        _rawSampleChar->setValue((uint8_t*)jsonBuf, len);
        _rawSampleChar->notify();
        _rawPacketsSent++;
        return true;
    }

    bool isClientConnected() const { return _clientConnected; }
    State getState() const { return _state; }
    uint32_t getPacketsSent() const { return _packetsSent; }
    uint32_t getRawPacketsSent() const { return _rawPacketsSent; }

    bool isModelStreamEnabled() const { return _modelStreamEnabled; }
    bool isSummaryEnabled() const { return _summaryEnabled; }
    uint16_t getRawRateHz() const { return _rawRateHz; }

    bool consumeRequestMockMode() {
        bool v = _requestMockMode;
        _requestMockMode = false;
        return v;
    }
    bool consumeRequestRealMode() {
        bool v = _requestRealMode;
        _requestRealMode = false;
        return v;
    }

    bool isClientTimedOut() const {
        if (_clientConnected) return false;
        return (millis() - _lastClientActivity) > BLE_CLIENT_TIMEOUT_MS;
    }

    void restartAdvertising() {
        if (!_initialized) return;
        BLEDevice::startAdvertising();
        _state = ADVERTISING;
    }

    void shutdown() {
        if (!_initialized) return;
        BLEDevice::deinit(false);
        _state = OFF;
        _initialized = false;
    }

private:
    BLEServer* _server = nullptr;
    BLECharacteristic* _telemetryChar = nullptr;
    BLECharacteristic* _rawSampleChar = nullptr;
    BLECharacteristic* _deviceInfoChar = nullptr;
    BLECharacteristic* _controlChar = nullptr;
    BLECharacteristic* _statusChar = nullptr;

    bool _initialized = false;
    volatile bool _clientConnected = false;
    State _state = OFF;
    unsigned long _lastClientActivity = 0;
    uint32_t _packetsSent = 0;
    uint32_t _rawPacketsSent = 0;

    bool _modelStreamEnabled = BLE_MODEL_STREAM_ENABLED;
    bool _summaryEnabled = true;
    uint16_t _rawRateHz = MODEL_STREAM_RATE_HZ;
    bool _requestMockMode = false;
    bool _requestRealMode = false;

    void _updateStatusValue() {
        if (!_statusChar) return;
        char statusJson[256];
        snprintf(
            statusJson, sizeof(statusJson),
            "{\"model_stream_enabled\":%s,\"summary_enabled\":%s,\"raw_rate_hz\":%u,\"raw_packets_sent\":%lu,\"summary_packets_sent\":%lu}",
            _modelStreamEnabled ? "true" : "false",
            _summaryEnabled ? "true" : "false",
            (unsigned)_rawRateHz,
            (unsigned long)_rawPacketsSent,
            (unsigned long)_packetsSent
        );
        _statusChar->setValue(statusJson);
    }

    void _handleControlCommand(const String& commandRaw) {
        String cmd = commandRaw;
        cmd.trim();
        cmd.toLowerCase();

        if (cmd == "model_stream_on") _modelStreamEnabled = true;
        else if (cmd == "model_stream_off") _modelStreamEnabled = false;
        else if (cmd == "raw_rate_50") _rawRateHz = 50;
        else if (cmd == "raw_rate_25") _rawRateHz = 25;
        else if (cmd == "summary_on") _summaryEnabled = true;
        else if (cmd == "summary_off") _summaryEnabled = false;
        else if (cmd == "mock_mode") _requestMockMode = true;
        else if (cmd == "real_mode") _requestRealMode = true;

        _updateStatusValue();
        HA_SERIAL_PRINTF("[BLE] Control command: %s\n", cmd.c_str());
    }

    class ServerCallbacks : public BLEServerCallbacks {
    public:
        explicit ServerCallbacks(HaBle* parent) : _parent(parent) {}

        void onConnect(BLEServer* server) override {
            (void)server;
            _parent->_clientConnected = true;
            _parent->_state = CONNECTED;
            _parent->_lastClientActivity = millis();
            _parent->_updateStatusValue();
            HA_SERIAL_PRINTLN("[BLE] Client connected.");
        }

        void onDisconnect(BLEServer* server) override {
            _parent->_clientConnected = false;
            _parent->_state = ADVERTISING;
            _parent->_lastClientActivity = millis();
            _parent->_updateStatusValue();
            HA_SERIAL_PRINTLN("[BLE] Client disconnected, re-advertising...");
            server->startAdvertising();
        }

    private:
        HaBle* _parent;
    };

    class ControlCallbacks : public BLECharacteristicCallbacks {
    public:
        explicit ControlCallbacks(HaBle* parent) : _parent(parent) {}

        void onWrite(BLECharacteristic* characteristic) override {
            std::string value = characteristic->getValue();
            if (value.empty()) return;
            _parent->_handleControlCommand(String(value.c_str()));
        }

    private:
        HaBle* _parent;
    };
};

#endif
