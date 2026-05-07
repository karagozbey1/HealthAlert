# HealthAlert — Part 2: Sliding Window Infrastructure + ML Inference Shadow Mode

**Tarih:** 29 Nisan 2026  
**Durum:** Tamamlandı  
**Önceki Görevler:** Part 1 (baseline_mvp_report.md), Part 1.1 (runtime_migration_lock_report.md)

---

## 1. Amaç

Canlı sensör paketleri için per-user sliding/ring buffer altyapısı kurmak ve mevcut ML modelini backend canlı akışına **SHADOW MODE** olarak bağlamak.

Shadow mode tanımı:
- ML modeli çalışabilir, tahmin üretebilir.
- ML çıktısı response/log içinde görülebilir metadata olarak döner.
- ML çıktısı **aktif alarm/anomaly/notification kararını yönetmez.**
- Aktif karar mekanizması Part 1'den gelen heuristic + baseline + quality-aware final_risk_score olarak kalır.

---

## 2. Part 1 ve Part 1.1 Üzerine Nasıl İnşa Edildi?

| Bileşen | Part 1'den gelen | Part 2'de yapılan |
|---------|-----------------|-------------------|
| `final_risk_score` | Baseline-aware heuristic risk | Değiştirilmedi — ML shadow bunu okuyacak, değiştirmeyecek |
| `risk_breakdown` | response'a eklendi | Aynen korundu |
| `DevicePacketResponse` | `risk_breakdown` opsiyonel | `window_status` + `ml_shadow_result` opsiyonel eklendi |
| `ingestion_router.py` | Part 1.1'de UnboundLocalError düzeltildi | Buffer + ML shadow bloğu eklendi |
| `database.py` | Part 1.1 schema guard | Değiştirilmedi |
| `config.py` | Baseline settings | 10 ML ayarı eklendi |

---

## 3. Değiştirilen Dosyalar

| Dosya | Değişiklik |
|-------|------------|
| [backend/config.py](../backend/config.py) | 10 `ML_*` ayarı eklendi |
| [backend/schemas.py](../backend/schemas.py) | `DevicePacketResponse`'a `window_status`, `ml_shadow_result` opsiyonel alanları eklendi |
| [backend/routers/ingestion_router.py](../backend/routers/ingestion_router.py) | `asyncio` import; `window_status`/`ml_shadow_result` initialize; Part 2 buffer+shadow bloğu |
| [backend/_smoke_api.py](../backend/_smoke_api.py) | Test 8 eklendi: Part 2 response alanlarını doğrulama |

---

## 4. Eklenen Dosyalar

| Dosya | İçerik |
|-------|--------|
| [backend/services/live_window_buffer.py](../backend/services/live_window_buffer.py) | `WindowSample`, `LiveWindowBufferManager`, modül-seviyesi `live_window_buffer` singleton |
| [backend/services/ml_inference_service.py](../backend/services/ml_inference_service.py) | `MLInferenceService` (lazy-load singleton), modül-seviyesi `ml_inference_service` singleton |
| [backend/tests/module7/test_17_ml_shadow_mode.py](../backend/tests/module7/test_17_ml_shadow_mode.py) | 34 test: A-F senaryoları |

---

## 5. Config Ayarları

```ini
# Master switch — varsayılan kapalı
ML_INFERENCE_ENABLED=false

# Shadow mode — aktif karar VERMEZ, sadece metadata üretir
ML_SHADOW_MODE=true

# Model checkpoint yolu (proje kökünden göreli)
ML_MODEL_PATH=outputs/models/best_final_fusion_model.pt

# Per-user ring buffer boyutu
ML_WINDOW_SIZE=200

# Kaç pakette bir inference çalıştırılır (buffer dolu iken)
ML_INFERENCE_EVERY_N_PACKETS=50

# ML modelin beklediği örnekleme hızı (Hz) — sadece mismatch warning için
ML_EXPECTED_SAMPLE_RATE_HZ=50

# Herhangi bir hata → 500 yerine ml_available=false döner
ML_FAIL_OPEN=true

# Her backend paketi N raw ölçümün özeti olduğunu işaret eder
ML_USE_PACKET_SUMMARY_MODE=true

# estimated_duration >> expected_duration → logger.warning
ML_WARN_ON_SAMPLE_RATE_MISMATCH=true

# ml_shadow_result response JSON'unda görünsün mü?
ML_RESPONSE_INCLUDE_SHADOW_RESULT=true
```

**Güvenli varsayılanlar:** `ML_INFERENCE_ENABLED=False` → hiçbir şey değişmez. Server kodu ilk gün gibi çalışır.

---

## 6. Sliding Window Buffer Tasarımı

```
LiveWindowBufferManager
  ├── _buffers: dict[user_id → deque(maxlen=ML_WINDOW_SIZE)]
  ├── _packet_counts: dict[user_id → int]   # monoton sayaç
  └── _lock: threading.Lock

add_packet(user_id, packet, motion_score, final_risk_score, qc) → status_dict
get_window(user_id) → list[WindowSample] | None
should_run_inference(user_id) → bool
get_status(user_id) → dict
reset_user(user_id) → None
```

**Ring buffer:** `collections.deque(maxlen=ML_WINDOW_SIZE)` — yeni paket gelince en eski otomatik silinir.

**Inference cadence:** Buffer dolu (`current_size >= ML_WINDOW_SIZE`) VE `packet_count % ML_INFERENCE_EVERY_N_PACKETS == 0`.

**Thread safety:** Tüm mutasyonlar `threading.Lock` altında. Async handler'dan direkt çağrı güvenli.

---

## 7. Window Sample Alanları

```python
@dataclass
class WindowSample:
    timestamp_ms: int
    packet_seq: int
    mode: str
    # IMU
    accel_x, accel_y, accel_z: float
    gyro_x, gyro_y, gyro_z: float
    # PPG raw ADC
    red_value: int
    ir_value: int
    # Vitals
    heart_rate: float
    spo2: float
    signal_quality: float
    # Validity flags
    imu_ok, ppg_ok, hr_valid, spo2_valid, finger_detected: bool
    # Derived (ingestion router tarafından üretilir)
    motion_score: float
    final_risk_score: float
    quality_confidence: float
```

---

## 8. Firmware Packet Frekansı vs ML Window Beklentisi

| Parametre | Değer | Kaynak |
|-----------|-------|--------|
| `SAMPLING_RATE_HZ` | 25 Hz | `firmware/include/ha_config.h` |
| `PACKET_INTERVAL_MS` | 1000 ms → 1 pkt/s | `firmware/include/ha_config.h` |
| `target_sr` | 50 Hz | `healthalert_final_ai/config/base.yaml` |
| `window_size` | 200 samples | `healthalert_final_ai/config/base.yaml` |
| ML beklenen window süresi | 200/50 = **4 saniye** | |
| Backend'in 200 pkt toplama süresi | ~**200 saniye** | firmware 1 pkt/s gönderir |

**Sonuç:** Backend, 200 paketi ~200 saniyede toplar. ML modeli 200 paketi 4 saniye zannetmektedir. Bu uyumsuzluk kodu bozmaz; `sample_rate_warning` alanı ile raporlanır.

---

## 9. Sampling Mismatch Tespiti

`LiveWindowBufferManager.get_status()` şunu yapar:
1. İlk ve son `timestamp_ms` farkından `estimated_window_duration_sec` hesaplar.
2. `expected_duration_sec = ML_WINDOW_SIZE / ML_EXPECTED_SAMPLE_RATE_HZ = 4.0 s`
3. Oran > 3× ise `sample_rate_warning = True`
4. Oran > 5× ise `logger.warning(...)` ile detaylı uyarı yazar

Test sonucu (test_17 E senaryosu):
```
200 paket × 1000 ms = 199 s estimated
expected = 4.0 s
ratio = 49.75 >> 3 → sample_rate_warning = True ✓
```

---

## 10. MLInferenceService Tasarımı

```
MLInferenceService (singleton)
  ├── is_available() → bool
  ├── load_once() → bool        # idempotent, lock korumalı
  ├── predict_window(user_id, window, context) → dict   # asyncio.to_thread ile çağrılır
  ├── build_predictor_inputs(window) → {imu, ppg, vitals}
  └── reset_user_state(user_id)

Load lifecycle:
  _loaded=False → ilk inference trigger'da load_once() çağrılır
  _loaded=True, _available=False → model yüklenemedi, fail-open döner
  _loaded=True, _available=True  → model hazır
```

Lazy load avantajı: Server startup süresi etkilenmez. Model yükü sadece ilk ML inference trigger'ında gerçekleşir.

---

## 11. Predictor Input Mapping

`HealthAlertPredictor.predict()` beklentisi:

| Input | Shape | Kaynak | Normalizasyon |
|-------|-------|--------|---------------|
| `imu` | (T, 6) | accel_x/y/z + gyro_x/y/z | Ham değerler |
| `ppg` | (T, 1) | `ir_value` | `/ 100_000.0` |
| `vitals` | (3,) | son sample'dan | `[hr_raw, spo2/100, signal_quality]` |

**PPG proxy:** Firmware'de `ir_value` max30102 ADC ham çıktısıdır. Normalize edilerek PPG kanalı olarak kullanılır.

**Vitals:** Predictor `vitals[1] * 100.0` yaparak SpO2'yi geri elde eder. Quality `vitals[2]`'den extract edilir.

---

## 12. RiskPostprocessorV2 Kullanıldı mı?

Evet. `MLInferenceService._do_load()` içinde `RiskPostprocessorV2()` instance'ı oluşturulur. `predict_window` içinde:

1. `HealthAlertPredictor.predict()` → raw dict: `{fall_prob, instability_prob, quality_score, risk_score}`
2. `RiskPostprocessorV2.process(predictions, vitals)` → structured dict: `{fall_probability, instability_probability, final_risk_level, immediate_alert, reasons, recommendations, ...}`

**İki kez postprocess yoktur.** Predictor'ın kendi çıktısı doğrudan postprocessor'a girer.

---

## 13. Shadow Mode Davranışı

```
POST /ingest/device-packet
  │
  ├─ Packet logged ────────────────────────────────────────── (her zaman)
  ├─ Motion score computed ────────────────────────────────── (user varsa)
  ├─ Global risk score ────────────────────────────────────── (user varsa)
  ├─ Baseline adjustment → final_risk_score ───────────────── (user varsa)
  ├─ Severity → AnomalyEvent / AlertEvent (heuristic) ─────── (user varsa)
  │
  ├─ [Part 2] live_window_buffer.add_packet() ─────────────── (user varsa)
  │    └─ window_status → response'a eklenir
  │
  └─ [Part 2 + ML_INFERENCE_ENABLED=True]
       └─ should_run_inference() → True?
            └─ asyncio.to_thread(ml_inference_service.predict_window)
                 └─ ml_shadow_result → log + response'a eklenir
                      ⚠️ bu sonuç severity'yi DEĞİŞTİRMEZ
                      ⚠️ AlertEvent / AnomalyEvent OLUŞTURMAZ
```

---

## 14. Neden ML Aktif Alarm Kararına Bağlanmadı?

1. **Güvenilirlik:** Shadow mode, modelin canlı ortamdaki davranışını gözlemlememizi sağlar. Yanlış pozitif oranı gözlemlenene kadar aktif kararlar verilmemelidir.
2. **Kalibrasyon sorunu:** Firmware 1 pkt/s, model 50 Hz için eğitilmiş. Temporal featureler (frekans, süre) farklı ölçekte hesaplanır. Shadow çıktısının güvenilirliği henüz doğrulanmamıştır.
3. **Part 3 hazırlığı:** Part 3'te shadow çıktısı analiz edilerek güven eşiği belirlendikten sonra aktif karar entegrasyonu yapılacak.

---

## 15. Fail-Open Davranışı

| Hata Durumu | Sonuç |
|-------------|-------|
| `ML_INFERENCE_ENABLED=False` | Buffer çalışır, ML çalışmaz |
| PyTorch yüklü değil | `ml_available=False, ml_error=...` |
| Model checkpoint yok | `ml_available=False, ml_error=...` |
| Import hatası (healthalert_final_ai) | `ml_available=False, ml_error=...` |
| Inference sırasında exception | `ml_available=False, ml_error=...` (ML_FAIL_OPEN=True) |
| Buffer overflow | Deque ring buffer — veri kaybı yok, oldest silinir |

**Hiçbir senaryoda backend 500 vermez.** `final_risk_score` ve severity her zaman heuristic pipeline'dan gelir.

---

## 16. ingestion_router Entegrasyonu

Eklenen kod Part 2 bloğu, mevcut anomaly/alert chain'in **sonrasında** çalışır:

```python
# Part 2: Sliding window buffer + ML shadow inference
window_status: dict | None = None    # handler başında initialize
ml_shadow_result: dict | None = None # handler başında initialize

try:
    qc = risk_breakdown.get("quality_confidence", 1.0) if risk_breakdown else 1.0
    window_status = live_window_buffer.add_packet(
        user_id=user_id, packet=pkt, motion_score=motion_score,
        final_risk_score=risk_score, quality_confidence=qc,
    )
    if settings.ML_INFERENCE_ENABLED and live_window_buffer.should_run_inference(user_id):
        window = live_window_buffer.get_window(user_id)
        if window:
            ml_shadow_result = await asyncio.to_thread(
                ml_inference_service.predict_window, user_id, window,
            )
            if ml_shadow_result:
                ml_shadow_result["window_status"] = window_status
            logger.info("ML shadow inference user=%s risk_level=%s latency=%.1fms", ...)
except Exception as exc:
    logger.warning("Live window / ML shadow error (ignored): %s", exc)
```

**Önemli:** Tüm Part 2 kodu kendi `try/except` içinde. Herhangi bir hata anomaly/alert zincirini veya db.commit()'i etkilemez.

---

## 17. Response Geriye Uyumluluğu

`DevicePacketResponse` değişikliği:
```python
# Eski (Part 1)
class DevicePacketResponse(BaseModel):
    status: str
    packet_seq: int
    device_id: str
    user_id: Optional[str] = None
    risk_breakdown: Optional[dict] = None

# Yeni (Part 2)
class DevicePacketResponse(BaseModel):
    status: str
    packet_seq: int
    device_id: str
    user_id: Optional[str] = None
    risk_breakdown: Optional[dict] = None
    window_status: Optional[dict] = None      # yeni — opsiyonel, None default
    ml_shadow_result: Optional[dict] = None   # yeni — opsiyonel, None default
```

Eski client'lar yeni alanları görmezden gelir. Kayıtsız cihazlar (user_id=None) için `window_status=null`, `ml_shadow_result=null` döner.

---

## 18. Test Edilen Senaryolar

| Senaryo | Test Sayısı | Sonuç |
|---------|-------------|-------|
| A) Config / disabled mode | 7 | ✅ 7/7 PASS |
| B) Model unavailable / fail-open | 3 | ✅ 3/3 PASS |
| C) Buffer behaviour | 10 | ✅ 10/10 PASS |
| D) Shadow safety | 5 | ✅ 5/5 PASS |
| E) Sampling mismatch | 3 | ✅ 3/3 PASS |
| F) Regression (Part 1) | 6 | ✅ 6/6 PASS |
| **Toplam Part 2** | **34** | **✅ 34/34** |

---

## 19. Çalıştırılan Komutlar ve Sonuçları

### Part 2 Unit Tests

```powershell
$env:DATA_MODE="sqlite"; python -m pytest tests/module7/test_17_ml_shadow_mode.py -v --tb=short
# Sonuç: 34 passed in 0.25s
```

### Full Regression (Part 1 + Part 2)

```powershell
$env:DATA_MODE="sqlite"; python -m pytest tests/module7/test_16_baseline_mvp.py tests/module7/test_04_factory.py::TestRepoSetFields tests/module7/test_04_factory.py::TestFactorySqliteMode tests/module7/test_05_sqlite_repos.py tests/module7/test_17_ml_shadow_mode.py -v --tb=short
# Sonuç: 90 passed, 1 skipped
```

### Smoke API Tests (Part 1.1 + Part 2)

```
== 1. Health check ==         [PASS] GET /health → 200
== 2. Login ==                [PASS] POST /auth/login → 200
== 3. GET /settings ==        [PASS] alert_sensitivity default=normal
== 4. PUT /settings ==        [PASS] high, reset to normal
== 5. POST /ingest normal ==  [PASS] → 200, window_status=null (unregistered)
== 6. POST /ingest low q ==   [PASS] → 200
== 7. Invalid sensitivity ==  [PASS] → 422
== 8. Part 2 schema ==        [PASS] window_status/ml_shadow_result keys present

SMOKE TEST RESULTS: 15/15 PASSED
```

### Sampling Mismatch Test

```
200 paket × 1000 ms/pkt = 199 s (estimated_window_duration_sec)
expected_duration_sec = 200 / 50 = 4.0 s
ratio = 49.75 >> 3 → sample_rate_warning = True ✓
```

---

## 20. Bilinen Sınırlamalar

1. **Sampling mismatch:** Firmware 1 pkt/s, model 50 Hz. Buffer 200 paketi ~200 saniyede toplar. Temporal feature'lar (FFT, periyot) farklı zaman ölçeğinde hesaplanır. Shadow çıktısının kalitatif doğruluğu düşük olabilir. Bu nedenle aktif alarm kararı verilmemektedir.

2. **VitalsMLP input_dim belirsizliği:** `base.yaml` `vitals_dim: 2` diyor, predictor (3,) bekliyor. Eğer checkpoint `input_dim=2` ile eğitildiyse `predict()` shape hatası alır ve fail-open döner. Part 3'te checkpoint introspection eklenmelidir.

3. **Model EMA state per-user değil global:** `HealthAlertPredictor._ema_state` tek instance içinde tutulur. Farklı kullanıcıların inference'ları birbirinin EMA state'ini etkileyebilir. Part 3'te per-user predictor instance veya EMA state reset gerekli.

4. **asyncio.to_thread overhead:** CPU-bound inference her 50 pakette bir thread pool'a gönderilir. Yüksek kullanıcı sayısında thread starvation riski. Part 3'te inference queue veya process pool değerlendirilebilir.

5. **Firebase/Hybrid mode:** Firestore schema yönetimi bu görevde ele alınmadı. Known limitation olarak kalmaktadır.

6. **Mismatch warning eşiği:** Oran > 3× ise `sample_rate_warning=True` mantığı heuristiktir. Gerçek deployment ortamına göre kalibre edilmeli.

---

## 21. Part 3 Retrieval/RAG İçin Hazırlık Notları

Part 3 muhtemelen şunları gerektirecek:

1. **ML active decision integration:**
   - `ml_shadow_result["ml_final_risk_level"]` güvenilir mi? Shadow gözlemleri analiz et.
   - Sampling mismatch çözüldüyse (gerçek 50 Hz firmware) aktif karar verilebilir.
   - `ai_bridge.process_ai_result()` çağrısını burada yapabilirsiniz.

2. **Per-user EMA state:**
   - `MLInferenceService`'e `_ema_states: dict[user_id → ...]` ekle.
   - `reset_user_state(user_id)` gerçekten per-user reset yapacak.

3. **Clinical notes RAG:**
   - Ingestion akışındaki `ml_shadow_result` verileri `ClinicalNote` olarak saklanabilir.
   - Vektör indeksi için `ml_reasons` ve `ml_recommendations` text alanları kullanılabilir.

4. **Schema guard (Part 3 için):**
   - Part 2 yeni tablo/kolon eklemedi.
   - Part 3 yeni tablo eklerse `database.py._apply_schema_guards()` içine guard ekle.

5. **Smoke tests:**
   - `_smoke_api.py`'ye ML enabled mode için test ekle.
   - Registered cihaz ile `window_status.is_full=True` ve `ml_shadow_result.ml_available=True` doğrula.
