
#ifndef HA_MAX30102_H
#define HA_MAX30102_H

#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"
#include "ha_config.h"
#include "ha_types.h"

class HaMax30102 {
public:
    // Sensörü başlatır.
    bool begin() {
        for (int attempt = 0; attempt < SENSOR_INIT_RETRIES; attempt++) {
            if (_sensor.begin(Wire, I2C_SPEED_FAST, MAX30102_I2C_ADDR)) {
                _configure();
                _initialized = true;
                _ok = true;
                Serial.printf("[MAX30102] Init OK (attempt %d)\n", attempt + 1);
                return true;
            }
            Serial.printf("[MAX30102] Init failed (attempt %d/%d)\n", attempt + 1, SENSOR_INIT_RETRIES);
            delay(SENSOR_INIT_RETRY_MS);
        }
        _initialized = false;
        _ok = false;
        Serial.println("[MAX30102] Init FAILED after all retries.");
        return false;
    }

    PpgSample read() {
        PpgSample sample = {0, 0, 0.0f, 0.0f, 0.0f, false, false, false, false};
        if (!_initialized) return sample;

        uint32_t ir = _sensor.getIR();
        uint32_t red = _sensor.getRed();

        sample.ir_value = ir;
        sample.red_value = red;

        bool finger = (ir > 50000);
        sample.finger_detected = finger;

        if (finger) {
            _ir_buffer[_buf_idx] = ir;
            _red_buffer[_buf_idx] = red;
            _buf_idx = (_buf_idx + 1) % PPG_BUF_SIZE;
            if (_buf_count < PPG_BUF_SIZE) _buf_count++;

            sample.signal_quality = _estimate_signal_quality();

            if (_buf_count >= PPG_BUF_MINIMUM && sample.signal_quality > 0.3f) {
                sample.heart_rate = _estimate_heart_rate();
                sample.hr_valid = (sample.heart_rate >= 30.0f && sample.heart_rate <= 220.0f);

                sample.spo2 = _estimate_spo2();
                sample.spo2_valid = (sample.spo2 >= 70.0f && sample.spo2 <= 100.0f);
            }
        } else {
            _buf_count = 0;
            _buf_idx = 0;
        }

        sample.valid = true;
        _ok = true;
        return sample;
    }

    bool reinit() {
        _initialized = false;
        _ok = false;
        _buf_count = 0;
        _buf_idx = 0;
        return begin();
    }

    bool isOk() const { return _ok; }
    bool isInitialized() const { return _initialized; }

private:
    static const int PPG_BUF_SIZE = 100;
    static const int PPG_BUF_MINIMUM = 50;

    MAX30105 _sensor;
    bool _initialized = false;
    bool _ok = false;

    uint32_t _ir_buffer[PPG_BUF_SIZE];
    uint32_t _red_buffer[PPG_BUF_SIZE];
    int _buf_idx = 0;
    int _buf_count = 0;

    void _configure() {
        _sensor.setup(
            MAX30102_LED_BRIGHTNESS,
            MAX30102_SAMPLE_AVG,
            MAX30102_LED_MODE,
            MAX30102_SAMPLE_RATE,
            MAX30102_PULSE_WIDTH,
            MAX30102_ADC_RANGE
        );
        _sensor.enableDIETEMPRDY();
    }

    float _estimate_signal_quality() {
        if (_buf_count < 10) return 0.0f;

        int start = (_buf_idx - min(_buf_count, 20) + PPG_BUF_SIZE) % PPG_BUF_SIZE;
        float sum = 0;
        int n = min(_buf_count, 20);
        for (int i = 0; i < n; i++) {
            sum += _ir_buffer[(start + i) % PPG_BUF_SIZE];
        }
        float mean = sum / n;

        float var_sum = 0;
        for (int i = 0; i < n; i++) {
            float diff = _ir_buffer[(start + i) % PPG_BUF_SIZE] - mean;
            var_sum += diff * diff;
        }
        float cv = sqrt(var_sum / n) / mean;

        if (cv < 0.005f) return 0.95f;
        if (cv < 0.02f)  return 0.85f;
        if (cv < 0.05f)  return 0.70f;
        if (cv < 0.10f)  return 0.45f;
        if (cv < 0.20f)  return 0.25f;
        return 0.10f;
    }

    float _estimate_heart_rate() {
        int n = min(_buf_count, PPG_BUF_SIZE);
        if (n < PPG_BUF_MINIMUM) return 0.0f;

        float sum = 0;
        for (int i = 0; i < n; i++) sum += _ir_buffer[i];
        float mean = sum / n;

        int crossings = 0;
        bool above = (_ir_buffer[0] > mean);
        for (int i = 1; i < n; i++) {
            bool now_above = (_ir_buffer[i] > mean);
            if (now_above && !above) crossings++;
            above = now_above;
        }

        float duration_sec = (float)n / (float)SAMPLING_RATE_HZ;
        if (duration_sec < 1.0f) return 0.0f;

        float bpm = (crossings / duration_sec) * 60.0f;
        return bpm;
    }

    float _estimate_spo2() {
        int n = min(_buf_count, PPG_BUF_SIZE);
        if (n < PPG_BUF_MINIMUM) return 0.0f;

        float red_sum = 0, ir_sum = 0;
        float red_min = 1e9, red_max = 0;
        float ir_min = 1e9, ir_max = 0;

        for (int i = 0; i < n; i++) {
            float rv = (float)_red_buffer[i];
            float iv = (float)_ir_buffer[i];
            red_sum += rv;
            ir_sum += iv;
            if (rv < red_min) red_min = rv;
            if (rv > red_max) red_max = rv;
            if (iv < ir_min) ir_min = iv;
            if (iv > ir_max) ir_max = iv;
        }

        float dc_red = red_sum / n;
        float dc_ir = ir_sum / n;
        if (dc_red < 1.0f || dc_ir < 1.0f) return 0.0f;

        float ac_red = red_max - red_min;
        float ac_ir = ir_max - ir_min;
        if (ac_ir < 1.0f) return 0.0f;

        float R = (ac_red / dc_red) / (ac_ir / dc_ir);
        float spo2 = 110.0f - 25.0f * R;

        if (spo2 > 100.0f) spo2 = 100.0f;
        if (spo2 < 0.0f) spo2 = 0.0f;

        return spo2;
    }
};

#endif
