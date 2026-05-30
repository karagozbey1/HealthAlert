
#ifndef HA_WIFI_TRANSPORT_H
#define HA_WIFI_TRANSPORT_H

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "ha_config.h"
#include "ha_debug.h"

class HaWifiTransport {
public:
    enum State { OFF, CONNECTING, CONNECTED, FAILED };

    // Sensörü başlatır.
    bool begin() {
        if (strlen(WIFI_SSID) == 0) {
            HA_SERIAL_PRINTLN("[WiFi] No SSID configured. Wi-Fi transport disabled.");
            _state = FAILED;
            return false;
        }

        if (WiFi.status() == WL_CONNECTED) {
            _state = CONNECTED;
            return true;
        }

        _state = CONNECTING;
        HA_SERIAL_PRINTF("[WiFi] Connecting to %s...\n", WIFI_SSID);

        WiFi.mode(WIFI_STA);
        WiFi.begin(WIFI_SSID, WIFI_PASS);

        unsigned long start = millis();
        while (WiFi.status() != WL_CONNECTED) {
            if (millis() - start > WIFI_CONNECT_TIMEOUT_MS) {
                HA_SERIAL_PRINTLN("[WiFi] Connection timeout.");
                _state = FAILED;
                _lastConnectAttempt = millis();
                return false;
            }
            delay(100);
        }

        _state = CONNECTED;
        _lastConnectAttempt = millis();
        HA_SERIAL_PRINTF("[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
        return true;
    }

    bool sendPacket(const char* jsonBuf) {
        if (_state != CONNECTED || WiFi.status() != WL_CONNECTED) {
            if (millis() - _lastConnectAttempt > WIFI_RECONNECT_INTERVAL_MS) {
                if (!begin()) return false;
            } else {
                return false;
            }
        }

        HTTPClient http;
        String url = String(WIFI_BACKEND_URL) + "/api/healthalert/sensor-sample";
        http.begin(url);
        http.addHeader("Content-Type", "application/json");

        if (strlen(_authToken) > 0) {
            http.addHeader("Authorization", String("Bearer ") + _authToken);
        }

        int httpCode = http.POST(jsonBuf);
        http.end();

        if (httpCode >= 200 && httpCode < 300) {
            _packetsSent++;
            _consecutiveFailures = 0;
            return true;
        } else {
            _consecutiveFailures++;
            if (_consecutiveFailures % 10 == 1) {
                HA_SERIAL_PRINTF("[WiFi] POST failed: HTTP %d (failures: %d)\n",
                              httpCode, _consecutiveFailures);
            }
            return false;
        }
    }

    bool sendRawSample(const char* jsonBuf) {
        return sendPacket(jsonBuf);
    }

    bool isConnected() const {
        return _state == CONNECTED && WiFi.status() == WL_CONNECTED;
    }

    State getState() const { return _state; }

    uint32_t getPacketsSent() const { return _packetsSent; }

    void disconnect() {
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
        _state = OFF;
        HA_SERIAL_PRINTLN("[WiFi] Disconnected.");
    }

    void setAuthToken(const char* token) {
        strncpy(_authToken, token, sizeof(_authToken) - 1);
        _authToken[sizeof(_authToken) - 1] = '\0';
    }

private:
    State _state = OFF;
    unsigned long _lastConnectAttempt = 0;
    uint32_t _packetsSent = 0;
    uint32_t _consecutiveFailures = 0;
    char _authToken[256] = "";
};

#endif
