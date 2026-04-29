

#include <Arduino.h>
#include <Wire.h>

#include "ha_config.h"
#include "ha_types.h"
#include "ha_i2c_scan.h"
#include "ha_acquisition.h"
#include "ha_packet.h"
#include "ha_serial_cmd.h"
#include "ha_transport.h"

AcquisitionManager acq;
SerialCmd serialCmd;
TransportOrchestrator transport;
static char jsonBuf[1024];
static unsigned long lastPacketTime = 0;
static bool useMock = true;

static void printBanner() {
    Serial.println();
    Serial.println("╔══════════════════════════════════════╗");
    Serial.println("║   HealthAlert ESP32 Firmware         ║");
    Serial.printf( "║   Version: %-25s ║\n", FW_VERSION);
    Serial.printf( "║   Device:  %-25s ║\n", HA_DEVICE_ID);
    Serial.println("╚══════════════════════════════════════╝");
    Serial.println();
}

// ESP32 başlangıç yapılandırmasını yapar.
void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(500);
    printBanner();

    Serial.printf("[BOOT] I2C init – SDA=%d, SCL=%d, freq=%lu Hz\n",
                  I2C_SDA_PIN, I2C_SCL_PIN, I2C_FREQUENCY);
    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setClock(I2C_FREQUENCY);

    I2cScanResult scan = i2c_scan();

#if FORCE_MOCK_MODE
    useMock = true;
    Serial.println("[BOOT] FORCE_MOCK_MODE=1 → using mock sensors.");
#else
    if (scan.mpu6050_found || scan.max30102_found) {
        useMock = false;
        Serial.println("[BOOT] Hardware detected → using REAL sensors.");
    } else {
        useMock = true;
        Serial.println("[BOOT] No hardware found → falling back to MOCK mode.");
    }
#endif

    acq.begin(useMock);

    if (!useMock) {
        bool ok = acq.initRealSensors();
        if (!ok) {
            Serial.println("[BOOT] All sensor inits failed → switching to MOCK.");
            acq.setMockMode(true);
            useMock = true;
        }
    }

    serialCmd.begin(&acq.getMock(), &acq.getStatus());

    Serial.printf("[BOOT] Sensor mode: %s\n", useMock ? "MOCK" : "REAL");

    Serial.println("[BOOT] Initializing transport layer...");
    transport.begin();

    Serial.println("[BOOT] Ready. Type 'help' for commands.");
    Serial.println();

    lastPacketTime = millis();
}

// Ana döngü: paket topla, JSON'a çevir, gönder.
void loop() {
    serialCmd.poll();

    if (serialCmd.request_mock_mode) {
        serialCmd.request_mock_mode = false;
        acq.setMockMode(true);
        useMock = true;
    }
    if (serialCmd.request_real_mode) {
        serialCmd.request_real_mode = false;
        acq.setMockMode(false);
        useMock = false;
    }
    if (serialCmd.request_restart_sensors) {
        serialCmd.request_restart_sensors = false;
        if (!useMock) {
            Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
            Wire.setClock(I2C_FREQUENCY);
            i2c_scan();
            acq.reinitSensors();
        } else {
            Serial.println("[LOOP] In mock mode – no hardware to restart.");
        }
    }

    unsigned long now = millis();
    if (now - lastPacketTime >= PACKET_INTERVAL_MS) {
        lastPacketTime = now;

        DevicePacket pkt = acq.collect();
        PacketFormatter::toJsonLine(pkt, jsonBuf, sizeof(jsonBuf));

        transport.sendPacket(jsonBuf);
    }
}
