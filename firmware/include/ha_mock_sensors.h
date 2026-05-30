
#ifndef HA_MOCK_SENSORS_H
#define HA_MOCK_SENSORS_H

#include <Arduino.h>
#include <math.h>
#include "ha_config.h"
#include "ha_debug.h"
#include "ha_types.h"

/// Firmware tarafındaki ilgili donanım veya taşıma sorumluluğunu temsil eder.
enum MockScenario : uint8_t {
    SCENARIO_NORMAL            = 0,
    SCENARIO_ELEVATED_HR       = 1,
    SCENARIO_LOW_SPO2          = 2,
    SCENARIO_MOTION_INSTABILITY = 3,
    SCENARIO_WARNING_STATE     = 4,
    SCENARIO_CRITICAL_STATE    = 5,
    SCENARIO_RECOVERY_STATE    = 6,
    SCENARIO_COUNT             = 7,
};

static const char* SCENARIO_NAMES[] = {
    "normal",
    "elevated_hr",
    "low_spo2",
    "motion_instability",
    "warning_state",
    "critical_state",
    "recovery_state",
};

/// Firmware tarafındaki ilgili donanım veya taşıma sorumluluğunu temsil eder.
struct ScenarioProfile {
    float hr_center;
    float hr_amplitude;
    float spo2_center;
    float spo2_amplitude;
    float accel_base;
    float accel_noise;
    float gyro_noise;
    float signal_quality;
    bool  finger_on;
    float ir_base;
    float red_base;
};

static const ScenarioProfile PROFILES[SCENARIO_COUNT] = {
    { 72.0f, 3.0f,  98.0f, 0.5f,  0.01f, 0.02f, 0.5f,  0.92f, true,  80000, 75000 },
    { 105.0f, 6.0f, 96.5f, 0.5f,  0.15f, 0.08f, 2.0f,  0.80f, true,  78000, 72000 },
    { 78.0f, 4.0f,  89.0f, 1.5f,  0.05f, 0.03f, 1.0f,  0.75f, true,  70000, 68000 },
    { 82.0f, 5.0f,  96.0f, 1.0f,  0.80f, 0.40f, 15.0f, 0.55f, true,  65000, 60000 },
    { 120.0f, 8.0f, 94.5f, 1.0f,  0.30f, 0.15f, 4.0f,  0.70f, true,  72000, 68000 },
    { 135.0f, 10.0f, 86.0f, 2.0f, 0.50f, 0.25f, 6.0f,  0.55f, true,  60000, 55000 },
    { 80.0f, 4.0f,  96.5f, 0.8f,  0.08f, 0.04f, 1.5f,  0.85f, true,  77000, 73000 },
};

/// Sensör okuma sonucunu firmware içinde taşır.
class MockSensors {
public:
    // Sensörü başlatır.
    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    void begin() {
        _scenario = SCENARIO_NORMAL;
        _tick = 0;
        _transition_ticks = 0;
        _prev_scenario = SCENARIO_NORMAL;
        HA_SERIAL_PRINTLN("[MOCK] Mock sensor engine initialized.");
    }

    /// Firmware çalışma ayarı veya senaryo seçimini günceller.
    void setScenario(MockScenario s) {
        if (s >= SCENARIO_COUNT) return;
        if (s == _scenario) return;
        _prev_scenario = _scenario;
        _scenario = s;
        _transition_ticks = 50;
        HA_SERIAL_PRINTF("[MOCK] Scenario -> %s\n", SCENARIO_NAMES[s]);
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    MockScenario getScenario() const { return _scenario; }
    const char* getScenarioName() const { return SCENARIO_NAMES[_scenario]; }

    // IMU verisini okur ve ImuSample döndürür.
    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    ImuSample readImu() {
        ImuSample s;
        const ScenarioProfile& p = _blended_profile();

        float t = _tick * 0.04f;
        s.accel_x = p.accel_base * sinf(t * 1.1f) + _noise(p.accel_noise);
        s.accel_y = p.accel_base * cosf(t * 0.9f) + _noise(p.accel_noise);
        s.accel_z = 1.0f + p.accel_base * sinf(t * 0.7f) + _noise(p.accel_noise);
        s.gyro_x = _noise(p.gyro_noise);
        s.gyro_y = _noise(p.gyro_noise);
        s.gyro_z = _noise(p.gyro_noise);
        s.valid = true;

        return s;
    }

    // PPG verisini okur ve PpgSample döndürür.
    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    PpgSample readPpg() {
        PpgSample s = {
            0, 0,
            0, 0, 0,
            0, 0, 0,
            false, false, false, false
        };
        const ScenarioProfile& p = _blended_profile();

        float t = _tick * 0.04f;

        if (!p.finger_on) {
            s.ir_value = random(500, 2000);
            s.red_value = random(500, 2000);
            s.finger_detected = false;
            s.signal_quality = 0.0f;
            s.valid = true;
            return s;
        }

        float hr_freq = p.hr_center / 60.0f;
        float pulse = sinf(2.0f * PI * hr_freq * t);
        float pulse2 = sinf(2.0f * PI * hr_freq * 2.0f * t) * 0.3f;

        s.ir_value = (uint32_t)(p.ir_base + 3000.0f * (pulse + pulse2) + _noise(500));
        s.red_value = (uint32_t)(p.red_base + 2500.0f * (pulse + pulse2) + _noise(400));
        s.finger_detected = true;
        s.signal_quality = p.signal_quality + _noise(0.05f);
        if (s.signal_quality > 1.0f) s.signal_quality = 1.0f;
        if (s.signal_quality < 0.0f) s.signal_quality = 0.0f;

        s.heart_rate = p.hr_center + p.hr_amplitude * sinf(t * 0.15f) + _noise(1.5f);
        s.spo2 = p.spo2_center + p.spo2_amplitude * sinf(t * 0.08f) + _noise(0.3f);
        if (s.spo2 > 100.0f) s.spo2 = 100.0f;
        if (s.spo2 < 0.0f) s.spo2 = 0.0f;

        s.pi_percent = max(0.1f, p.signal_quality * 3.0f + _noise(0.2f));
        s.r_ratio = max(0.1f, (110.0f - s.spo2) / 25.0f);
        s.ir_range_percent = max(0.1f, s.pi_percent + _noise(0.3f));

        s.hr_valid = (s.signal_quality > 0.3f);
        s.spo2_valid = (s.signal_quality > 0.4f);
        s.valid = true;

        return s;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    void tick() {
        _tick++;
        if (_transition_ticks > 0) _transition_ticks--;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    void enableAutoCycle(bool enable, uint32_t ticks_per_scenario = 150) {
        _auto_cycle = enable;
        _auto_cycle_interval = ticks_per_scenario;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    void updateAutoCycle() {
        if (!_auto_cycle) return;
        if ((_tick % _auto_cycle_interval) == 0 && _tick > 0) {
            MockScenario next = (MockScenario)(((uint8_t)_scenario + 1) % SCENARIO_COUNT);
            setScenario(next);
        }
    }

private:
    MockScenario _scenario = SCENARIO_NORMAL;
    MockScenario _prev_scenario = SCENARIO_NORMAL;
    uint32_t _tick = 0;
    int _transition_ticks = 0;
    bool _auto_cycle = false;
    uint32_t _auto_cycle_interval = 150;

    ScenarioProfile _blended_cache;
    const ScenarioProfile& _blended_profile() {
        if (_transition_ticks <= 0) {
            return PROFILES[_scenario];
        }
        float alpha = (float)_transition_ticks / 50.0f;
        const ScenarioProfile& from = PROFILES[_prev_scenario];
        const ScenarioProfile& to = PROFILES[_scenario];

        _blended_cache.hr_center      = _lerp(from.hr_center, to.hr_center, alpha);
        _blended_cache.hr_amplitude   = _lerp(from.hr_amplitude, to.hr_amplitude, alpha);
        _blended_cache.spo2_center    = _lerp(from.spo2_center, to.spo2_center, alpha);
        _blended_cache.spo2_amplitude = _lerp(from.spo2_amplitude, to.spo2_amplitude, alpha);
        _blended_cache.accel_base     = _lerp(from.accel_base, to.accel_base, alpha);
        _blended_cache.accel_noise    = _lerp(from.accel_noise, to.accel_noise, alpha);
        _blended_cache.gyro_noise     = _lerp(from.gyro_noise, to.gyro_noise, alpha);
        _blended_cache.signal_quality = _lerp(from.signal_quality, to.signal_quality, alpha);
        _blended_cache.finger_on      = to.finger_on;
        _blended_cache.ir_base        = _lerp(from.ir_base, to.ir_base, alpha);
        _blended_cache.red_base       = _lerp(from.red_base, to.red_base, alpha);

        return _blended_cache;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    static float _lerp(float a, float b, float t) {
        return b + (a - b) * t;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    static float _noise(float amplitude) {
        return ((float)random(-1000, 1001) / 1000.0f) * amplitude;
    }
};

#endif
