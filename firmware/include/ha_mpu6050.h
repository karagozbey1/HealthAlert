
#ifndef HA_MPU6050_H
#define HA_MPU6050_H

#include <Arduino.h>
#include <Wire.h>
#include "ha_config.h"
#include "ha_debug.h"
#include "ha_types.h"

/// Firmware tarafındaki ilgili donanım veya taşıma sorumluluğunu temsil eder.
class HaMpu6050 {
public:
    // Sensörü başlatır.
    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    bool begin() {
        for (int attempt = 0; attempt < SENSOR_INIT_RETRIES; attempt++) {
            if (_try_init()) {
                _initialized = true;
                _ok = true;
                HA_SERIAL_PRINTF("[MPU6050] Init OK (attempt %d)\n", attempt + 1);
                _calibrate();
                return true;
            }
            HA_SERIAL_PRINTF("[MPU6050] Init failed (attempt %d/%d)\n", attempt + 1, SENSOR_INIT_RETRIES);
            delay(SENSOR_INIT_RETRY_MS);
        }
        _initialized = false;
        _ok = false;
        HA_SERIAL_PRINTLN("[MPU6050] Init FAILED after all retries.");
        return false;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    ImuSample read() {
        ImuSample sample = {0, 0, 0, 0, 0, 0, false};
        if (!_initialized) return sample;

        Wire.beginTransmission(MPU6050_I2C_ADDR);
        Wire.write(0x3B);
        if (Wire.endTransmission(false) != 0) {
            _ok = false;
            return sample;
        }

        uint8_t received = Wire.requestFrom((uint8_t)MPU6050_I2C_ADDR, (uint8_t)14, (uint8_t)true);
        if (received < 14) {
            _ok = false;
            return sample;
        }

        int16_t ax_raw = (Wire.read() << 8) | Wire.read();
        int16_t ay_raw = (Wire.read() << 8) | Wire.read();
        int16_t az_raw = (Wire.read() << 8) | Wire.read();
        Wire.read(); Wire.read();
        int16_t gx_raw = (Wire.read() << 8) | Wire.read();
        int16_t gy_raw = (Wire.read() << 8) | Wire.read();
        int16_t gz_raw = (Wire.read() << 8) | Wire.read();

        sample.accel_x = (ax_raw - _ax_offset) / 16384.0f;
        sample.accel_y = (ay_raw - _ay_offset) / 16384.0f;
        sample.accel_z = (az_raw - _az_offset) / 16384.0f;
        sample.gyro_x  = (gx_raw - _gx_offset) / 131.0f;
        sample.gyro_y  = (gy_raw - _gy_offset) / 131.0f;
        sample.gyro_z  = (gz_raw - _gz_offset) / 131.0f;
        sample.valid = true;
        _ok = true;

        return sample;
    }

    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    bool reinit() {
        _initialized = false;
        _ok = false;
        /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
        return begin();
    }

    /// Firmware durum bayrağını çağırana sade bool değer olarak döndürür.
    bool isOk() const { return _ok; }
    /// Firmware durum bayrağını çağırana sade bool değer olarak döndürür.
    bool isInitialized() const { return _initialized; }

private:
    bool _initialized = false;
    bool _ok = false;
    int16_t _ax_offset = 0, _ay_offset = 0, _az_offset = 0;
    int16_t _gx_offset = 0, _gy_offset = 0, _gz_offset = 0;

    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    bool _try_init() {
        Wire.beginTransmission(MPU6050_I2C_ADDR);
        Wire.write(0x75);
        if (Wire.endTransmission(false) != 0) return false;
        Wire.requestFrom((uint8_t)MPU6050_I2C_ADDR, (uint8_t)1, (uint8_t)true);
        uint8_t who = Wire.read();
        if (who != 0x68 && who != 0x72) return false;

        _write_reg(0x6B, 0x00);
        delay(10);

        _write_reg(0x1C, MPU6050_ACCEL_RANGE << 3);
        _write_reg(0x1B, MPU6050_GYRO_RANGE << 3);
        _write_reg(0x1A, 0x03);

        return true;
    }

    /// Sensör başlangıcında kullanılacak ofset değerlerini hesaplar.
    void _calibrate() {
        HA_SERIAL_PRINTLN("[MPU6050] Calibrating (128 samples)...");
        delay(200); // let vibration settle after USB-connect
        int32_t sax = 0, say = 0, saz = 0, sgx = 0, sgy = 0, sgz = 0;
        const int N = 128;
        for (int i = 0; i < N; i++) {
            Wire.beginTransmission(MPU6050_I2C_ADDR);
            Wire.write(0x3B);
            Wire.endTransmission(false);
            Wire.requestFrom((uint8_t)MPU6050_I2C_ADDR, (uint8_t)14, (uint8_t)true);
            sax += (int16_t)((Wire.read() << 8) | Wire.read());
            say += (int16_t)((Wire.read() << 8) | Wire.read());
            saz += (int16_t)((Wire.read() << 8) | Wire.read());
            Wire.read(); Wire.read();
            sgx += (int16_t)((Wire.read() << 8) | Wire.read());
            sgy += (int16_t)((Wire.read() << 8) | Wire.read());
            sgz += (int16_t)((Wire.read() << 8) | Wire.read());
            delay(5);
        }
        _ax_offset = sax / N;
        _ay_offset = say / N;
        _az_offset = (saz / N) - 16384;
        _gx_offset = sgx / N;
        _gy_offset = sgy / N;
        _gz_offset = sgz / N;
        HA_SERIAL_PRINTLN("[MPU6050] Calibration done.");
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    void _write_reg(uint8_t reg, uint8_t val) {
        Wire.beginTransmission(MPU6050_I2C_ADDR);
        Wire.write(reg);
        Wire.write(val);
        Wire.endTransmission();
    }
};

#endif
