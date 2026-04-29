
#ifndef HA_BLE_H
#define HA_BLE_H

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "ha_config.h"

class HaBle {
public:
    enum State { OFF, ADVERTISING, CONNECTED, ERROR };

    // Sensörü başlatır.
    void begin() {
        BLEDevice::init(BLE_DEVICE_NAME);

        _server = BLEDevice::createServer();
        _server->setCallbacks(new ServerCallbacks(this));

        BLEService* service = _server->createService(BLE_SERVICE_UUID);

        _telemetryChar = service->createCharacteristic(
            BLE_TELEMETRY_CHAR_UUID,
            BLECharacteristic::PROPERTY_NOTIFY
        );
        _telemetryChar->addDescriptor(new BLE2902());

        _deviceInfoChar = service->createCharacteristic(
            BLE_DEVICE_INFO_CHAR_UUID,
            BLECharacteristic::PROPERTY_READ
        );
        char infoJson[256];
        snprintf(infoJson, sizeof(infoJson),
                 "{\"device_id\":\"%s\",\"fw_version\":\"%s\",\"fw_name\":\"%s\"}",
                 HA_DEVICE_ID, FW_VERSION, FW_NAME);
        _deviceInfoChar->setValue(infoJson);

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

        Serial.println("[BLE] GATT server started, advertising...");
    }

    bool sendPacket(const char* jsonBuf) {
        if (!_initialized || _state != CONNECTED || !_clientConnected) {
            return false;
        }

        size_t len = strlen(jsonBuf);
        if (len > 512) {
            Serial.println("[BLE] Packet too large for BLE, truncating.");
            len = 512;
        }

        _telemetryChar->setValue((uint8_t*)jsonBuf, len);
        _telemetryChar->notify();
        _packetsSent++;
        return true;
    }

    bool isClientConnected() const { return _clientConnected; }

    State getState() const { return _state; }

    bool isClientTimedOut() const {
        if (_clientConnected) return false;
        return (millis() - _lastClientActivity) > BLE_CLIENT_TIMEOUT_MS;
    }

    uint32_t getPacketsSent() const { return _packetsSent; }

    void restartAdvertising() {
        if (!_initialized) return;
        BLEDevice::startAdvertising();
        _state = ADVERTISING;
        Serial.println("[BLE] Re-advertising...");
    }

    void shutdown() {
        if (!_initialized) return;
        BLEDevice::deinit(false);
        _state = OFF;
        _initialized = false;
        Serial.println("[BLE] Shut down.");
    }

private:
    BLEServer* _server = nullptr;
    BLECharacteristic* _telemetryChar = nullptr;
    BLECharacteristic* _deviceInfoChar = nullptr;
    bool _initialized = false;
    volatile bool _clientConnected = false;
    State _state = OFF;
    unsigned long _lastClientActivity = 0;
    uint32_t _packetsSent = 0;

    class ServerCallbacks : public BLEServerCallbacks {
    public:
        ServerCallbacks(HaBle* parent) : _parent(parent) {}

        void onConnect(BLEServer* server) override {
            _parent->_clientConnected = true;
            _parent->_state = CONNECTED;
            _parent->_lastClientActivity = millis();
            Serial.println("[BLE] Client connected.");
        }

        void onDisconnect(BLEServer* server) override {
            _parent->_clientConnected = false;
            _parent->_state = ADVERTISING;
            _parent->_lastClientActivity = millis();
            Serial.println("[BLE] Client disconnected, re-advertising...");
            server->startAdvertising();
        }

    private:
        HaBle* _parent;
    };
};

#endif
