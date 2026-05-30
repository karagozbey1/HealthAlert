#ifndef HA_I2C_SCAN_H
#define HA_I2C_SCAN_H

#include <Arduino.h>
#include <Wire.h>
#include "ha_config.h"
#include "ha_debug.h"

struct I2cScanResult {
    bool mpu6050_found;
    bool max30102_found;
    uint8_t device_count;
};

inline I2cScanResult i2c_scan() {
    I2cScanResult result = {false, false, 0};

    HA_SERIAL_PRINTLN("[I2C] Scanning bus...");
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            result.device_count++;
            HA_SERIAL_PRINTF("[I2C]   Found device at 0x%02X", addr);
            if (addr == MPU6050_I2C_ADDR) {
                result.mpu6050_found = true;
                HA_SERIAL_PRINT(" (MPU6050)");
            } else if (addr == MAX30102_I2C_ADDR) {
                result.max30102_found = true;
                HA_SERIAL_PRINT(" (MAX30102)");
            }
            HA_SERIAL_PRINTLN();
        }
    }
    HA_SERIAL_PRINTF("[I2C] Scan complete - %u device(s) found.\n", result.device_count);
    return result;
}

#endif
