
#ifndef HA_MAX30102_H
#define HA_MAX30102_H

#include <Arduino.h>
#include <Wire.h>
#include "MAX30105.h"
#include "ha_config.h"
#include "ha_debug.h"
#include "ha_types.h"

/// Firmware tarafındaki ilgili donanım veya taşıma sorumluluğunu temsil eder.
class HaMax30102 {
public:
    // Sensörü başlatır.
    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    bool begin() {
        for (int attempt = 0; attempt < SENSOR_INIT_RETRIES; attempt++) {
            if (_sensor.begin(Wire, I2C_SPEED_FAST, MAX30102_I2C_ADDR)) {
                _configure();
                _initialized = true;
                _ok = true;
                HA_SERIAL_PRINTF("[MAX30102] Init OK (attempt %d)\n", attempt + 1);
                return true;
            }
            HA_SERIAL_PRINTF("[MAX30102] Init failed (attempt %d/%d)\n", attempt + 1, SENSOR_INIT_RETRIES);
            delay(SENSOR_INIT_RETRY_MS);
        }
        _initialized = false;
        _ok = false;
        HA_SERIAL_PRINTLN("[MAX30102] Init FAILED after all retries.");
        return false;
    }

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    PpgSample read() {
        PpgSample sample = {};
        sample.valid = true;
        sample.measurement_state = PPG_NO_FINGER;
        sample.motion_artifact   = false;
        if (!_initialized) return sample;

        uint32_t ir  = _sensor.getIR();
        uint32_t red = _sensor.getRed();

        sample.ir_value  = ir;
        sample.red_value = red;

        bool finger = (ir > 50000);
        sample.finger_detected = finger;

        if (finger) {
            if (!_fingerWasOn) {
                // Fresh finger placement — full state reset
                _fingerWasOn        = true;
                _fingerOnAt         = millis();
                _stableBpm          = 0.0f;
                _bpmConfirmed       = false;
                _pendingBpm         = 0.0f;
                _bpmStableStartMs   = 0;
                _lastValidBpmMs     = 0;
                _wasEverConfirmed   = false;
                _stableSpo2         = 0.0f;
                _spo2Confirmed      = false;
                _spo2StableStartMs  = 0;
                _spo2RingCount      = 0;
                _spo2RingIdx        = 0;
                memset(_spo2Ring, 0, sizeof(_spo2Ring));
            }

            _ir_buffer[_buf_idx]  = ir;
            _red_buffer[_buf_idx] = red;
            _buf_idx = (_buf_idx + 1) % PPG_BUF_SIZE;
            if (_buf_count < PPG_BUF_SIZE) _buf_count++;

            sample.signal_quality = _estimate_signal_quality();
            _estimate_ppg_features(
                sample.pi_percent,
                sample.r_ratio,
                sample.ir_range_percent
            );

            unsigned long fingerAge = millis() - _fingerOnAt;
            bool warmedUp   = fingerAge >= PPG_WARMUP_MS;
            bool goodSignal = (_buf_count >= PPG_BUF_MINIMUM) &&
                              (sample.signal_quality > 0.25f) &&
                              warmedUp;

            // Determine measurement state
            if (!warmedUp) {
                sample.measurement_state = PPG_WARMING_UP;
            } else if (_bpmConfirmed || _spo2Confirmed) {
                sample.measurement_state = PPG_STABLE;
            } else if (_wasEverConfirmed) {
                // Had stable vitals before but lost them (e.g. motion artifact)
                sample.measurement_state = PPG_UNSTABLE;
            } else {
                sample.measurement_state = PPG_STABILIZING;
            }

            if (goodSignal) {
                float rawBpm  = _estimate_heart_rate();
                float rawSpo2 = _estimate_spo2();

                // Store raw debug values regardless of validity
                sample.bpm_raw  = rawBpm;
                sample.spo2_raw = rawSpo2;

                _processBpm(rawBpm);
                _processSpo2(rawSpo2);

                sample.heart_rate = (_stableBpm > 0.0f) ? _stableBpm : 0.0f;
                sample.hr_valid   = _bpmConfirmed &&
                                    (_stableBpm >= 45.0f) &&
                                    (_stableBpm <= 130.0f);

                sample.spo2       = _spo2Confirmed ? _stableSpo2 : 0.0f;
                sample.spo2_valid = _spo2Confirmed &&
                                    (_stableSpo2 >= 88.0f) &&
                                    (sample.pi_percent >= 0.3f);

                if (_bpmConfirmed || _spo2Confirmed) {
                    _wasEverConfirmed = true;
                    sample.measurement_state = PPG_STABLE;
                } else if (_wasEverConfirmed) {
                    sample.measurement_state = PPG_UNSTABLE;
                } else {
                    sample.measurement_state = PPG_STABILIZING;
                }
            }
        } else {
            // Finger removed — full state reset
            _fingerWasOn        = false;
            _fingerOnAt         = 0;
            _buf_count          = 0;
            _buf_idx            = 0;
            _stableBpm          = 0.0f;
            _bpmConfirmed       = false;
            _pendingBpm         = 0.0f;
            _bpmStableStartMs   = 0;
            _lastValidBpmMs     = 0;
            _wasEverConfirmed   = false;
            _stableSpo2         = 0.0f;
            _spo2Confirmed      = false;
            _spo2StableStartMs  = 0;
            _spo2RingCount      = 0;
            _spo2RingIdx        = 0;
            sample.measurement_state = PPG_NO_FINGER;
        }

        _ok = true;
        return sample;
    }

    /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
    bool reinit() {
        _initialized        = false;
        _ok                 = false;
        _buf_count          = 0;
        _buf_idx            = 0;
        _fingerWasOn        = false;
        _fingerOnAt         = 0;
        _stableBpm          = 0.0f;
        _bpmConfirmed       = false;
        _pendingBpm         = 0.0f;
        _bpmStableStartMs   = 0;
        _lastValidBpmMs     = 0;
        _wasEverConfirmed   = false;
        _stableSpo2         = 0.0f;
        _spo2Confirmed      = false;
        _spo2StableStartMs  = 0;
        _spo2RingCount      = 0;
        _spo2RingIdx        = 0;
        memset(_spo2Ring, 0, sizeof(_spo2Ring));
        /// İlgili sensör veya iletişim bileşenini kullanıma hazırlar.
        return begin();
    }

    /// Firmware durum bayrağını çağırana sade bool değer olarak döndürür.
    bool isOk() const { return _ok; }
    /// Firmware durum bayrağını çağırana sade bool değer olarak döndürür.
    bool isInitialized() const { return _initialized; }

private:
    static const int PPG_BUF_SIZE    = 100;  // 2 s at 50 Hz (PPG_EFFECTIVE_SAMPLE_RATE_HZ)
    static const int PPG_BUF_MINIMUM = 50;   // 2 s minimum for any estimate

    MAX30105 _sensor;
    bool _initialized = false;
    bool _ok          = false;

    uint32_t _ir_buffer[PPG_BUF_SIZE];
    uint32_t _red_buffer[PPG_BUF_SIZE];
    int _buf_idx   = 0;
    int _buf_count = 0;

    // ── Finger state ──────────────────────────────────────────────────────
    bool          _fingerWasOn = false;
    unsigned long _fingerOnAt  = 0;

    // ── BPM stabilization ─────────────────────────────────────────────────
    // Time-based confirmation: rawBpm must remain stable for BPM_STABLE_WINDOW_MS
    // before hr_valid is set. This prevents a single wrong estimate right after
    // warmup from being accepted as the stable BPM.
    float         _stableBpm        = 0.0f;
    float         _pendingBpm       = 0.0f;
    unsigned long _bpmStableStartMs = 0;
    bool          _bpmConfirmed     = false;
    unsigned long _lastValidBpmMs   = 0;   // last time an in-range raw BPM was seen
    bool          _wasEverConfirmed = false; // true once any vital was first confirmed

    // ── SpO2 stabilization ────────────────────────────────────────────────
    // Ring buffer of last SPO2_RING_SIZE valid SpO2 raw estimates.
    // spo2_valid is only set when the ring is ≥ SPO2_RING_SIZE/2 full, all
    // estimates are within SPO2_MAX_SPREAD_PCT of each other, AND the stable
    // window has elapsed.
    float         _spo2Ring[SPO2_RING_SIZE];
    int           _spo2RingIdx      = 0;
    int           _spo2RingCount    = 0;
    float         _stableSpo2       = 0.0f;
    unsigned long _spo2StableStartMs = 0;
    bool          _spo2Confirmed    = false;

    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
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

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
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

        // Good PPG: moderate CV (0.3%–5% of DC is AC pulsatile component).
        // Very low CV = flat line (no heartbeat). Very high = motion noise.
        if (cv < 0.001f) return 0.05f; // Flat line / no pulsation
        if (cv < 0.004f) return 0.35f; // Weak pulse
        if (cv < 0.020f) return 0.85f; // Good pulse
        if (cv < 0.050f) return 0.55f; // Some motion
        if (cv < 0.120f) return 0.25f; // Motion artifact
        return 0.08f;                  // Heavy noise
    }

    // Chronological ring-buffer accessors (0 = oldest, n-1 = newest)
    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    inline float _irAt(int chron) const {
        int n = min(_buf_count, PPG_BUF_SIZE);
        int oldest = (_buf_idx - n + PPG_BUF_SIZE) % PPG_BUF_SIZE;
        return (float)_ir_buffer[(oldest + chron) % PPG_BUF_SIZE];
    }
    /// Sensör, BLE veya Wi-Fi akışındaki yardımcı firmware adımını yürütür.
    inline float _redAt(int chron) const {
        int n = min(_buf_count, PPG_BUF_SIZE);
        int oldest = (_buf_idx - n + PPG_BUF_SIZE) % PPG_BUF_SIZE;
        return (float)_red_buffer[(oldest + chron) % PPG_BUF_SIZE];
    }

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
    float _estimate_heart_rate() {
        int n = min(_buf_count, PPG_BUF_SIZE);
        if (n < PPG_BUF_MINIMUM) return 0.0f;

        // DC level (mean)
        float sum = 0;
        for (int i = 0; i < n; i++) sum += _irAt(i);
        float mean = sum / n;

        // AC range — needed for threshold and PI check
        float ir_min = 1e9f, ir_max = -1e9f;
        for (int i = 0; i < n; i++) {
            float v = _irAt(i);
            if (v < ir_min) ir_min = v;
            if (v > ir_max) ir_max = v;
        }
        float ac_range = ir_max - ir_min;

        // Need a meaningful pulsatile signal (PI > 0.1%)
        if (ac_range < mean * 0.001f || ac_range < 500.0f) return 0.0f;

        // Peak detection with refractory period
        // 180 BPM max → min 0.33 s between peaks → ~8 samples at 25 Hz
        const int refract = (int)(PPG_EFFECTIVE_SAMPLE_RATE_HZ * 0.30f);
        float thresh = mean + ac_range * 0.35f;

        int peaks[16];
        int np = 0;
        int last_peak = -refract;
        bool above = false;
        int cand = -1;
        float cand_val = -1e9f;

        for (int i = 0; i < n && np < 15; i++) {
            float v = _irAt(i);
            if (v >= thresh) {
                if (!above) { above = true; cand = i; cand_val = v; }
                else if (v > cand_val) { cand = i; cand_val = v; }
            } else {
                if (above && cand >= 0 && (cand - last_peak) >= refract) {
                    peaks[np++] = cand;
                    last_peak = cand;
                }
                above = false; cand = -1; cand_val = -1e9f;
            }
        }

        if (np < 2) return 0.0f;

        // Average inter-peak BPM; reject implausible intervals
        float bpm_sum = 0;
        int valid = 0;
        for (int i = 1; i < np; i++) {
            float interval_sec = (float)(peaks[i] - peaks[i - 1]) / (float)PPG_EFFECTIVE_SAMPLE_RATE_HZ;
            float bpm = 60.0f / interval_sec;
            if (bpm >= 40.0f && bpm <= 200.0f) { bpm_sum += bpm; valid++; }
        }
        return (valid > 0) ? (bpm_sum / valid) : 0.0f;
    }

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
    void _processBpm(float rawBpm) {
        if (rawBpm < 40.0f || rawBpm > 200.0f) {
            // Out-of-range: reset pending but keep stable value.
            // Do NOT reset _bpmStableStartMs here — that would make
            // millis()-0 always exceed the 10 s threshold immediately.
            _pendingBpm = 0.0f;
            // Expire confirmed state only when no valid beat for > 10 s
            if (_bpmConfirmed && (millis() - _lastValidBpmMs) > 10000UL) {
                _bpmConfirmed     = false;
                _stableBpm        = 0.0f;
                _bpmStableStartMs = 0;
            }
            return;
        }
        _lastValidBpmMs = millis();  // Record last in-range raw BPM timestamp

        if (_stableBpm <= 0.0f) {
            // ── Initial acquisition ───────────────────────────────────────
            if (_pendingBpm > 0.0f &&
                fabsf(rawBpm - _pendingBpm) < BPM_JUMP_THRESH_BPM) {
                // Consistent with pending: apply slow EMA to pending estimate
                _pendingBpm = 0.85f * _pendingBpm + 0.15f * rawBpm;
                unsigned long elapsed = millis() - _bpmStableStartMs;
                if (elapsed >= BPM_STABLE_WINDOW_MS) {
                    _stableBpm    = _pendingBpm;
                    _bpmConfirmed = true;
                    _pendingBpm   = 0.0f;
                }
            } else {
                // New candidate or too different — restart timer
                _pendingBpm       = rawBpm;
                _bpmStableStartMs = millis();
            }
            return;
        }

        // ── Already have a stable BPM ─────────────────────────────────────
        float diff = fabsf(rawBpm - _stableBpm);
        if (diff > BPM_JUMP_THRESH_BPM) {
            // Large jump detected
            if (_pendingBpm > 0.0f &&
                fabsf(rawBpm - _pendingBpm) < BPM_JUMP_THRESH_BPM) {
                // Consecutive readings consistent with the new level
                _pendingBpm = 0.85f * _pendingBpm + 0.15f * rawBpm;
                unsigned long elapsed = millis() - _bpmStableStartMs;
                if (elapsed >= BPM_JUMP_WINDOW_MS) {
                    // Accept jump: FULL replace — do NOT blend stale + new.
                    _stableBpm    = _pendingBpm;
                    _bpmConfirmed = true;
                    _pendingBpm   = 0.0f;
                    _bpmStableStartMs = 0;
                }
            } else {
                // New jump candidate
                _pendingBpm       = rawBpm;
                _bpmStableStartMs = millis();
                _bpmConfirmed     = false; // Lose confirmation during jump
            }
        } else {
            // Small variation: slow EMA
            _stableBpm    = 0.85f * _stableBpm + 0.15f * rawBpm;
            _pendingBpm   = 0.0f;
            _bpmConfirmed = true;
        }
    }

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
    float _estimate_spo2() {
        int n = min(_buf_count, PPG_BUF_SIZE);
        if (n < PPG_BUF_MINIMUM) return 0.0f;

        float red_sum = 0, ir_sum = 0;
        for (int i = 0; i < n; i++) {
            red_sum += _redAt(i);
            ir_sum  += _irAt(i);
        }
        float dc_red = red_sum / n;
        float dc_ir  = ir_sum  / n;

        if (dc_ir < 10000.0f || dc_red < 5000.0f) return 0.0f;

        float ac_red_sq = 0, ac_ir_sq = 0;
        for (int i = 0; i < n; i++) {
            float dr = _redAt(i) - dc_red;
            float di = _irAt(i)  - dc_ir;
            ac_red_sq += dr * dr;
            ac_ir_sq  += di * di;
        }
        float ac_red_rms = sqrtf(ac_red_sq / n);
        float ac_ir_rms  = sqrtf(ac_ir_sq  / n);

        // Need meaningful pulsatile component (PI > 0.15%)
        if (ac_ir_rms < 100.0f || (ac_ir_rms / dc_ir) < 0.0015f) return 0.0f;

        float R = (ac_red_rms / dc_red) / (ac_ir_rms / dc_ir);

        // Tight physiological gate: only accept R that maps to SpO2 ≥ 88%
        // With 110−25·R: R=0.40→100%, R=0.88→88%.
        if (R < SPO2_R_MIN || R > SPO2_R_MAX) return 0.0f;

        float spo2 = 110.0f - 25.0f * R;

        // Belt-and-suspenders: should always be [88,100] given R gate above
        if (spo2 < 88.0f || spo2 > 100.0f) return 0.0f;

        return spo2;
    }

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
    void _processSpo2(float rawSpo2) {
        if (rawSpo2 < 88.0f || rawSpo2 > 100.0f) {
            // Invalid raw estimate — don't add to ring.
            // Reset timer if invalid persists > 15 s (finger quality degraded).
            if (_spo2StableStartMs > 0 &&
                (millis() - _spo2StableStartMs) > 15000UL) {
                _spo2RingCount     = 0;
                _spo2RingIdx       = 0;
                _stableSpo2        = 0.0f;
                _spo2Confirmed     = false;
                _spo2StableStartMs = 0;
                memset(_spo2Ring, 0, sizeof(_spo2Ring));
            }
            return;
        }

        // Add to ring buffer
        _spo2Ring[_spo2RingIdx] = rawSpo2;
        _spo2RingIdx = (_spo2RingIdx + 1) % SPO2_RING_SIZE;
        if (_spo2RingCount < SPO2_RING_SIZE) _spo2RingCount++;

        // Need at least half the ring filled
        int minSamples = SPO2_RING_SIZE / 2;  // = 3
        if (_spo2RingCount < minSamples) {
            _spo2StableStartMs = millis();
            return;
        }

        // Compute min/max to check spread
        float vmin = _spo2Ring[0], vmax = _spo2Ring[0];
        for (int i = 1; i < _spo2RingCount; i++) {
            if (_spo2Ring[i] < vmin) vmin = _spo2Ring[i];
            if (_spo2Ring[i] > vmax) vmax = _spo2Ring[i];
        }
        float spread = vmax - vmin;

        if (spread > SPO2_MAX_SPREAD_PCT) {
            // Too inconsistent — reset stability timer but keep ring
            _spo2StableStartMs = millis();
            return;
        }

        // Consistent ring — compute simple average as the stable estimate
        float sum = 0;
        for (int i = 0; i < _spo2RingCount; i++) sum += _spo2Ring[i];
        float ringMean = sum / _spo2RingCount;

        if (_spo2StableStartMs == 0) _spo2StableStartMs = millis();

        // Apply slow EMA to track gradual drift
        if (_stableSpo2 < 88.0f) {
            _stableSpo2 = ringMean;
        } else {
            _stableSpo2 = 0.85f * _stableSpo2 + 0.15f * ringMean;
        }

        if ((millis() - _spo2StableStartMs) >= SPO2_STABLE_WINDOW_MS) {
            _spo2Confirmed = true;
        }
    }

    /// Ham sensör örneklerinden kullanılacak ölçüm değerini hesaplar.
    void _estimate_ppg_features(float& pi, float& r, float& ir_range) {
        pi = 0.0f;
        r = 0.0f;
        ir_range = 0.0f;

        int n = min(_buf_count, PPG_BUF_SIZE);
        if (n < 10) return;

        float red_sum = 0, ir_sum = 0;
        float red_min = 1e9, red_max = 0;
        float ir_min = 1e9, ir_max = 0;

        for (int i = 0; i < n; i++) {
            float rv = _redAt(i);
            float iv = _irAt(i);
            red_sum += rv;
            ir_sum  += iv;
            if (rv < red_min) red_min = rv;
            if (rv > red_max) red_max = rv;
            if (iv < ir_min) ir_min = iv;
            if (iv > ir_max) ir_max = iv;
        }

        float dc_red = red_sum / n;
        float dc_ir  = ir_sum  / n;
        if (dc_ir < 1.0f) return;

        float ac_red = red_max - red_min;
        float ac_ir  = ir_max  - ir_min;
        pi       = (ac_ir / dc_ir) * 100.0f;
        ir_range = pi;

        if (dc_red >= 1.0f && ac_ir >= 1.0f) {
            r = (ac_red / dc_red) / (ac_ir / dc_ir);
        }
    }
};

#endif
