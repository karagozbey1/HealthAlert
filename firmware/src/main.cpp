#include <Arduino.h>
#include <Wire.h>

#include "ha_config.h"
#include "ha_debug.h"
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
static char rawJsonBuf[1024];
static unsigned long lastPacketTime = 0;
static unsigned long lastRawSampleTime = 0;
static bool useMock = true;

static void printBanner() {
    HA_SERIAL_PRINTLN();
    HA_SERIAL_PRINTLN("========================================");
    HA_SERIAL_PRINTLN("   HealthAlert ESP32 Firmware");
    HA_SERIAL_PRINTF("   Version: %s\n", FW_VERSION);
    HA_SERIAL_PRINTF("   Device:  %s\n", HA_DEVICE_ID);
    HA_SERIAL_PRINTLN("========================================");
    HA_SERIAL_PRINTLN();
}

void setup() {
    HA_SERIAL_BEGIN(SERIAL_BAUD);
    delay(500);
    printBanner();

    HA_SERIAL_PRINTF(
        "[BOOT] I2C init - SDA=%d, SCL=%d, freq=%lu Hz\n",
        I2C_SDA_PIN,
        I2C_SCL_PIN,
        I2C_FREQUENCY
    );
    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setClock(I2C_FREQUENCY);

    I2cScanResult scan = i2c_scan();

#if FORCE_MOCK_MODE
    useMock = true;
    HA_SERIAL_PRINTLN("[BOOT] FORCE_MOCK_MODE=1 -> using mock sensors.");
#else
    if (scan.mpu6050_found || scan.max30102_found) {
        useMock = false;
        HA_SERIAL_PRINTLN("[BOOT] Hardware detected -> using REAL sensors.");
    } else {
        useMock = true;
        HA_SERIAL_PRINTLN("[BOOT] No hardware found -> falling back to MOCK mode.");
    }
#endif

    acq.begin(useMock);

    if (!useMock) {
        bool ok = acq.initRealSensors();
        if (!ok) {
            HA_SERIAL_PRINTLN("[BOOT] All sensor inits failed -> switching to MOCK.");
            acq.setMockMode(true);
            useMock = true;
        }
    }

    serialCmd.begin(&acq.getMock(), &acq.getStatus());

    HA_SERIAL_PRINTF("[BOOT] Sensor mode: %s\n", useMock ? "MOCK" : "REAL");

    HA_SERIAL_PRINTLN("[BOOT] Initializing transport layer...");
    transport.begin();

    HA_SERIAL_PRINTLN("[BOOT] Ready. Type 'help' for commands.");
    HA_SERIAL_PRINTLN();

    lastPacketTime = millis();
    lastRawSampleTime = millis();
}

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
            HA_SERIAL_PRINTLN("[LOOP] In mock mode - no hardware to restart.");
        }
    }

    if (transport.getBle().consumeRequestMockMode()) {
        acq.setMockMode(true);
        useMock = true;
    }
    if (transport.getBle().consumeRequestRealMode()) {
        acq.setMockMode(false);
        useMock = false;
    }

    unsigned long now = millis();
    if (now - lastPacketTime >= SUMMARY_PACKET_INTERVAL_MS) {
        lastPacketTime = now;

        transport.refresh();
        DevicePacket pkt = acq.collect();
        if (transport.getActiveTransport() == TransportOrchestrator::BLE ||
            transport.getActiveTransport() == TransportOrchestrator::SERIAL_ONLY) {
            PacketFormatter::toBleSummaryJson(pkt, jsonBuf, sizeof(jsonBuf));
        } else {
            PacketFormatter::toJsonLine(pkt, jsonBuf, sizeof(jsonBuf));
        }
        transport.sendPacket(jsonBuf);
    }

#if BLE_MODEL_STREAM_ENABLED
    uint16_t rawRateHz = transport.getBle().getRawRateHz();
    if (rawRateHz == 0) rawRateHz = MODEL_STREAM_RATE_HZ;
    unsigned long rawIntervalMs = 1000UL / rawRateHz;
    if (rawIntervalMs == 0) rawIntervalMs = 1;

    if (now - lastRawSampleTime >= rawIntervalMs) {
        lastRawSampleTime = now;
        RawSensorSample raw = acq.collectRawSample(rawRateHz);
        PacketFormatter::rawToJsonLine(raw, rawJsonBuf, sizeof(rawJsonBuf));
        transport.sendRawSample(rawJsonBuf);
    }
#endif
}
