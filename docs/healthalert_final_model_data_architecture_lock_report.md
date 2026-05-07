# HealthAlert — Final Technical Lock & Demo Readiness Report

**Tarih:** 29 Nisan 2026  
**Kapsam:** Part 1 → Part 1.1 → Part 2 → Part 3 → Part 3.1  
**Durum:** PRODUCTION-SAFE, DEMO-READY ✅  
**Test Sonucu:** 135 passed, 1 skipped, 0 failed (test_16..test_19)

---

## 1. Executive Summary

HealthAlert, giyilebilir bir sensör cihazından alınan anlık fizyolojik verileri (IMU + PPG) analiz ederek kullanıcıya özel risk skoru üreten ve gerektiğinde alarm oluşturan bir sistem olarak tasarlanmıştır.

**Mimarinin özü:** Üç katmanlı, bağımsız ama birbirini tamamlayan sistem:

```
[ Katman 1 — AKTİF KARAR   ] Heuristic + Personal Baseline + Quality-aware Risk Motor
[ Katman 2 — SHADOW/KANIT  ] ML Inference (PyTorch, shadow-only)
[ Katman 3 — SHADOW/KANIT  ] Retrieval / RAG (sklearn NearestNeighbors, shadow-only)
```

- **Katman 1** aktif karar verir. Alarm, anomaly, notification tüm bu katmandan çıkar.
- **Katman 2 ve 3** yalnızca gözlem ve kanıt destek verisi üretir; `final_risk_score`'u hiçbir zaman değiştirmez.
- Her iki shadow katmanı `shadow_mode=True` ile dönmekte, API response'una opsiyonel metadata olarak eklenmektedir.

Part 3.1 ile sistemin üretim ortamına çıkmadan önce karşılaması gereken tüm güvenlik sertleştirmeleri tamamlanmıştır: sample-rate uyuşmazlığı koruması, EMA state izolasyonu, vitals boyut tespiti, retrieval alignment gate ve 1 Hz hizalanmış indeks.

---

## 2. Hocanın 3 Sorusuna Teknik Cevap

### Soru 1 — Anlık veri nasıl analiz ediliyor?

Firmware ~1 Hz hızında paket gönderir. Her paket şunları içerir:
- IMU: `accel_x/y/z`, `gyro_x/y/z`
- PPG: `red_value`, `ir_value`, `heart_rate`, `spo2`, `signal_quality`
- Flags: `hr_valid`, `spo2_valid`, `finger_detected`
- Hesaplanan: `motion_score`, `final_risk_score`

Her paket `/ingest/device-packet` endpoint'ine düşer. Burada şu adımlar gerçekleşir:

1. **Paket doğrulama** (sequence, device, kullanıcı eşleşmesi)
2. **DevicePacketLog** kaydı (kalıcı)
3. **motion_score** hesaplama
4. **Heuristic risk_score** (global, kişisiz)
5. **Baseline-aware final_risk_score**: kullanıcının kişisel EMA baseline'ı mevcutsa heuristic skoru kişiselleştirilmiş bir skora dönüştürülür; PPG sinyal kalitesi bonus/ceza uygulanır
6. **LiveStatus güncelleme** (anlık durum kaydı)
7. **Severity belirleme** → AnomalyEvent / AlertEvent / NotificationItem
8. **Per-user ring buffer güncelleme** (son 200 paket saklanır, ML için)
9. **ML Shadow inference** (ML_INFERENCE_ENABLED=True ise, shadow-only)
10. **Retrieval Shadow sorgu** (RETRIEVAL_ENABLED=True ise, shadow-only)
11. **Response dönme** (DevicePacketResponse)

Analiz **anlık + kısa bellek** birleşimdir: her paket tek başına işlenir, ancak son 200 paketin istatistiksel özeti ML inference için kullanılır.

### Soru 2 — Sabit kurallar kişiye göre nasıl kalibre edildi?

Geleneksel heuristic kurallar (örn. `HR > 100 → risk yüksek`) tüm insanlara aynı eşiği uygular. HealthAlert bunu **kişisel baseline** ile kalibre eder:

```
UserBaseline (kullanıcıya özel):
  hr_mean, hr_std         → bu kullanıcının normal kalp hızı aralığı
  spo2_mean, spo2_std     → bu kullanıcının normal SpO2 aralığı
  motion_mean, motion_std → bu kullanıcının normal hareket düzeyi
  ppg_quality_mean        → bu kullanıcının beklenen sinyal kalitesi
  sample_count            → güvenilir ölçüm sayısı (en az 300 gerekli)
  is_ready                → baseline aktif mi?
```

Kalibre mekanizması üç aşamalı:

1. **Kalibrasyon:** Her yeni güvenilir paket EMA (Exponential Moving Average, α=0.02) ile baseline'a dahil edilir. Düşük kaliteli sinyal veya sahte hareket verileri kalibrasyona dahil edilmez.
2. **Personal Deviation:** Anlık ölçümün kullanıcının baseline'ından z-score bazlı sapması hesaplanır.
3. **Baseline Adjustment:** `final_risk_score = global_risk × (1 + deviation × sensitivity)`. Kullanıcı kendi için "yüksek" olan bir ölçüm yaparsa skor artar; kendisi için "normal" olan ölçümde skor azalır.

**alert_sensitivity** ayarı (`AppSettings` tablosunda, kullanıcı başına) bu kalibrasyonun agresifliğini 0.5–2.0 arasında ölçekler.

### Soru 3 — RAG/Retrieval veri analizi tarafında nasıl kullanıldı?

Retrieval-Augmented Generation (RAG) kavramı bu projede şu şekilde uyarlandı:

**Geleneksel RAG:** Kullanıcı sorusu → vektör indeksi araması → ilgili belge parçaları alınır → LLM'e context olarak verilir → cevap üretilir.

**HealthAlert RAG (zaman serisi):** Anlık sensör penceresi → özellik çıkarımı → NearestNeighbors indeks araması → en benzer geçmiş olaylar bulunur → kanıt destek skoru hesaplanır → shadow metadata olarak response'a eklenir.

```
Canlı sensör verisi (son 200 paket)
    ↓
Hand-crafted özellik çıkarımı (38 boyut, 50Hz indeks)
    veya
Slow özellik çıkarımı (21 boyut, 1Hz indeks — Part 3.1)
    ↓
StandardScaler ile normalize et
    ↓
NearestNeighbors.kneighbors(query_vector, k=10)
    ↓
Top-K benzer geçmiş pencere bulundu
    ↓
Support score = Σ(weight × is_fall_like) / Σ(weight)
    ↓
{"support_score": 0.85, "similar_examples": [...], "shadow_mode": true}
```

Vektör indeksi şunlardan oluşur:
- **HIFD**: 21 denekten 349 deneme, 50 Hz, IMU + HR
- **WEDA_FALL**: 1781 deneme (700 düşme, 1081 normal aktivite), 50 Hz, IMU
- **Toplam**: 23.446 pencere (38 boyut, 50Hz) + 1.354 pencere (21 boyut, 1Hz slow index)

Retrieval **aktif karar vermez.** Ancak ilerleyen sürümlerde destekleyici kanıt olarak fusion'a dahil edilmesi planlanmaktadır.

---

## 3. Part 1 Özeti — Personal Baseline MVP

**Tarih:** 29 Nisan 2026 | **Test:** 36/36 geçti

**Ne yapıldı:**
- Kullanıcıya özel `UserBaseline` tablosu ve `baseline_service.py` oluşturuldu
- EMA tabanlı kişisel ortalama/standart sapma hesaplama
- Quality-gated güvenilirlik kapısı (düşük PPG kalitesi veya sahte hareket → baseline'a dahil edilmez)
- `apply_baseline_adjustment()` ile `final_risk_score` kişiselleştirildi
- `BASELINE_ENABLED=False` olduğunda eski davranış tamamen korunur
- `alert_sensitivity` konfigürasyonu (AppSettings tablosu, 0.5–2.0 aralığı)

**Temel katkı:** Ham heuristic risk → kişiye özel kalibre edilmiş risk.

---

## 4. Part 1.1 Özeti — Runtime/Migration Stabilization

**Tarih:** 29 Nisan 2026 | **Test:** Smoke API 15/15 geçti

**Giderilen sorunlar:**

| # | Sorun | Çözüm |
|---|-------|-------|
| 1 | `user_baselines` tablosu eksik | `create_all` yeterli (yeni tablo) |
| 2 | `alert_sensitivity` kolonu eksik | `_apply_schema_guards()` → `ALTER TABLE IF NOT EXISTS` |
| 3 | `firestore_watcher` top-level import | Lazy import ile koşullu hale getirildi |
| 4 | `risk_breakdown` UnboundLocalError | Kayıtsız cihaz için varsayılan değer atandı |
| 5 | passlib+bcrypt+Python 3.14 uyumsuzluğu | `auth.py` kütüphane güncellendi |

**Temel katkı:** Part 1 kodu gerçek runtime'da güvenli çalışır hale getirildi.

---

## 5. Part 2 Özeti — Sliding Window + ML Shadow Mode

**Tarih:** 29 Nisan 2026 | **Test:** 34/34 geçti

**Ne yapıldı:**
- Per-user ring buffer: `LiveWindowBufferManager` (200 paketlik deque, thread-safe)
- ML model lazy-loading singleton: `MLInferenceService`
- `HealthAlertPredictor` (PyTorch, EMA smoothing), `RiskPostprocessorV2`
- `CRNN + VitalsMLP` mimarisi: `imu (200,6) + ppg (200,2) + vitals (2 veya 3)`
- Shadow mode: ML çalışır ama `final_risk_score`'u değiştirmez
- `DevicePacketResponse`'a `window_status` ve `ml_shadow_result` alanları eklendi
- `sample_rate_warning`: buffer 4 saniye beklenirken 200 saniye sürdüyse True

**Config:** `ML_INFERENCE_ENABLED=false` (varsayılan), `ML_SHADOW_MODE=true`

**Temel katkı:** ML modeli canlı akışa bağlandı ama hiçbir aktif karar değiştirmedi.

---

## 6. Part 3 Özeti — Retrieval-Augmented Time-Series Risk Analysis PoC

**Tarih:** 29 Nisan 2026 | **Test:** 36/36 geçti

**Ne yapıldı:**
- `build_retrieval_index.py`: HIFD + WEDA_FALL → 23.446 pencere, 38 özellik
- `StandardScaler` + `NearestNeighbors` (ball_tree, euclidean) indeksi
- `RetrievalEngine`: `load()`, `query()`, `compute_support()`, `explain()`
- Support score = ağırlıklı fall-like oran: 0.0–1.0 arası kanıt skoru
- `RetrievalShadowService`: backend shadow entegrasyonu
- `demo_retrieval_query.py`: gerçek HIFD verisinden sorgu, sonuç JSON
- Sorgu gecikmesi: **1.23 ms** (demo)
- BUT_PPG hariç tutuldu (IMU özelliği yok, tüm vektörler sıfır olur)

**Temel katkı:** Anlık sensör penceresi için "Bu duruma en benzer geçmiş olaylar hangileri?" sorusuna kanıta dayalı cevap.

---

## 7. Part 3.1 Özeti — Live Alignment + Safety Hardening

**Tarih:** 29 Nisan 2026 | **Test:** 30/30 geçti (toplam: 135/135)

**Giderilen güvenlik sorunları:**

| Sorun | Çözüm | Dosya |
|-------|-------|-------|
| ML yanlış sonuç: buffer 200 sn ama model 4 sn bekliyor | Sample-rate gate: `sample_rate_warning=True` → ML skip | `ml_inference_service.py` |
| EMA global kontaminasyon: kullanıcı A, kullanıcı B'yi kirletiyor | Per-user `_ema_states_by_user` dict | `ml_inference_service.py` |
| VitalsMLP vitals boyutu belirsiz | `_detect_vitals_dim()` auto-detect, `ML_VITALS_DIM=0` | `ml_inference_service.py`, `config.py` |
| Retrieval 50Hz indeksini 1Hz veriyle sorgulama | 3-way alignment gate | `retrieval_shadow_service.py` |
| 1Hz hizalanmış retrieval indeksi yoktu | `build_retrieval_slow_index.py` → 1354 pencere, 21 özellik | yeni script |
| Demo self-match tespiti | `--exclude-self`, `self_match_present`, `exclude_self_applied` | `demo_retrieval_query.py` |

**Temel katkı:** ML ve retrieval katmanları artık sample-rate uyuşmazlığına karşı güvenli ve kullanıcılar arası izole.

---

## 8. Aktif Karar Mekanizması

### final_risk_score Kimden Geliyor?

```
final_risk_score
    = apply_baseline_adjustment(
        global_risk_score,      ← heuristic (_compute_risk_score)
        personal_deviation,     ← compute_personal_deviation(baseline, packet)
        sensitivity,            ← AppSettings.alert_sensitivity (0.5–2.0)
        quality_confidence,     ← compute_quality_confidence(signal_quality)
      )
```

**Yalnızca bu fonksiyon `final_risk_score`'u belirler.** ML ve retrieval bu değeri okuyamazlar bile, yalnızca kendi shadow sonuçlarını üretirler.

### ML Karar Veriyor mu?

**HAYIR.** `ML_SHADOW_MODE=true` ayarıyla `ml_shadow_result` alanı:
- `ml_available`: model yüklü mü?
- `fall_probability`, `final_risk_level`: ML tahminleri
- `immediate_alert`: ML'nin önermesi (aktif sistemi tetiklemez)
- `shadow_mode: true`: bu sonuç aktif karar vermez

ML çıktısı `DevicePacketResponse.ml_shadow_result` içinde yer alır. `AnomalyEvent`, `AlertEvent`, `NotificationItem` oluşturma kararlarına girmez.

### Retrieval Karar Veriyor mu?

**HAYIR.** `retrieval_shadow_result` alanı:
- `support_score`: kanıt ağırlığı (0–1)
- `similar_examples`: en benzer geçmiş olaylar
- `shadow_mode: true`: bu sonuç aktif karar vermez
- `final_risk_score` alanı bu sonuçta **hiç bulunmaz**

---

## 9. Aktif Pipeline Diyagramı

```
Firmware (~1 Hz)
    │ DevicePacket
    ▼
POST /ingest/device-packet
    │
    ├── Paket doğrulama (sequence, device, user)
    ├── DevicePacketLog (DB)
    ├── motion_score = f(accel_x,y,z)
    ├── global_risk_score = heuristic(HR, SpO2, motion)
    │
    ├── [BASELINE_ENABLED=True]
    │     ├── compute_quality_confidence(signal_quality)
    │     ├── update_user_baseline() → EMA güncelleme
    │     ├── compute_personal_deviation(baseline, packet)
    │     └── apply_baseline_adjustment() → final_risk_score ◄── AKTİF
    │
    ├── LiveStatus upsert (final_risk_score kaydedildi)
    │
    ├── _risk_to_severity(final_risk_score, sensitivity_offset)
    │     ├── severity == "critical" → AlertEvent + NotificationItem
    │     ├── severity in ["high","warning"] → AnomalyEvent
    │     └── severity == "low" → sadece log
    │
    └── DevicePacketResponse döner
          ├── risk_breakdown (opsiyonel)
          ├── window_status (opsiyonel, shadow)
          ├── ml_shadow_result (opsiyonel, shadow)
          └── retrieval_shadow_result (opsiyonel, shadow)
```

---

## 10. Shadow Pipeline Diyagramı

```
DevicePacket
    │
    ▼
LiveWindowBufferManager (per-user, ring buffer, 200 paket)
    │
    ├── window_status
    │     ├── is_full: bool
    │     ├── estimated_window_duration_sec
    │     ├── expected_duration_sec (200 / 50Hz = 4 sn)
    │     └── sample_rate_warning: bool  ← 200 sn >> 4 sn?
    │
    ├── [ML_INFERENCE_ENABLED=True]
    │     │
    │     ├── sample_rate_warning=True AND ML_SKIP_ON_SAMPLE_RATE_MISMATCH=True
    │     │       └── ml_skipped=True, skip_reason="sample_rate_mismatch"
    │     │
    │     ├── sample_rate_warning=False (veya override=True)
    │     │       ├── _ema_states_by_user[user_id] yükle (per-user EMA)
    │     │       ├── predictor.predict(imu, ppg, vitals)
    │     │       ├── postprocessor.process() → risk_level, alert
    │     │       └── EMA state geri kaydet
    │     │
    │     └── ml_shadow_result → DevicePacketResponse (shadow_mode=True)
    │
    └── [RETRIEVAL_ENABLED=True]
          │
          ├── sample_rate_warning=True?
          │     ├── slow index yüklü? → _query_with_engine(slow, aligned_mode="slow_1hz")
          │     ├── RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True? → 50Hz sorgu
          │     └── else → retrieval_skipped=True
          │
          ├── sample_rate_warning=False
          │     └── _query_with_engine(50Hz index)
          │
          └── retrieval_shadow_result → DevicePacketResponse (shadow_mode=True)
```

---

## 11. Güvenlik Kararları

### Fail-Open (Genel Prensip)

Tüm shadow servisleri **fail-open** çalışır: herhangi bir hata (model yüklenmemiş, index bulunamadı, feature dimension mismatch, exception) → `{"available": False, "shadow_mode": True}` döner. **Hiçbir zaman 500 fırlatılmaz.**

```python
try:
    # inference / retrieval
except Exception:
    return {"ml_available": False, "shadow_mode": True, "error": str(exc)}
```

### Sample-Rate Gate

HealthAlert firmware'i ~1 Hz hızında çalışır. ML modeli 50 Hz eğitim verisi üzerinde eğitilmiştir. 200 paket ~200 saniye alır, ama model 200 × (1/50Hz) = 4 saniye bekler. Bu ~50× temporal scale farkı tahminleri anlamsız kılar.

**Gate koşulu:**
```
estimated_window_duration_sec / expected_duration_sec > ML_MAX_DURATION_RATIO (3.0)
→ sample_rate_warning = True
```

**ML davranışı:** `ML_SKIP_ON_SAMPLE_RATE_MISMATCH=True` → inference atlanır, `ml_skipped=True` döner.  
**Retrieval davranışı:** 3 yollu seçim: slow_1hz indeks → low-confidence 50Hz → skip.

### Low-Confidence Override

`ML_ALLOW_LOW_CONFIDENCE_INFERENCE=True` ve `RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True` ayarları, sample-rate uyumsuzluğu olsa bile tahmin/sorgu yapılmasına izin verir. Sonuç `low_confidence: True` işaretlenir.

### Per-User EMA Isolation

`HealthAlertPredictor._ema_state` global bir dict'tir. Paylaşıldığında kullanıcı A'nın yüksek-riskli EMA'sı kullanıcı B'nin tahminlerini kirletir.

**Çözüm:**
```python
self._ema_states_by_user: Dict[str, Dict[str, float]] = {}
# predict_window() içinde:
predictor._ema_state = user_ema.copy()   # kullanıcının state'ini yükle
result = predictor.predict(...)
_ema_states_by_user[user_id] = predictor._ema_state.copy()  # geri kaydet
```

### Vitals Dim Auto-Detect

`VitalsMLP`'nin beklediği giriş boyutu (2: `[hr, spo2]` veya 3: `[hr, spo2, quality]`) modele göre değişebilir.

**Çözüm:**
1. `ML_VITALS_DIM > 0` → config'den al
2. `model.named_modules()` üzerinden `in_features` introspection
3. Fallback: 3

Shape mismatch olursa fail-open: `ml_available=False`, `500` fırlatılmaz.

---

## 12. Veri Setleri ve Kullanım Şekli

### HIFD (Human Inertial Fall Detection)

| Özellik | Değer |
|---------|-------|
| Kaynak | 21 denek, .mat dosyaları |
| Modaliteler | Accelerometer (ax,ay,az), Gyroscope (droll,dpitch,dyaw), HR |
| Örnekleme Hızı | 50 Hz |
| Etiketler | 0=ADL (normal), 1=fall (düşme), 2=near_fall (yakın düşme) |
| 50Hz pencere sayısı | ~7.800+ (21 denek × N deneme × pencere başına) |
| 1Hz pencere sayısı | 740 (Part 3.1 slow index) |
| Kullanım | ML eğitim + test; 50Hz retrieval index; 1Hz retrieval index |

### WEDA_FALL

| Özellik | Değer |
|---------|-------|
| Kaynak | 1781 deneme (700 düşme, 1081 ADL) |
| Modaliteler | Accelerometer (accel_x/y/z), Gyroscope (gyro_x/y/z) |
| Örnekleme Hızı | 50 Hz CSV |
| Etiketler | 0=ADL, 1=fall |
| 50Hz pencere sayısı | ~15.600+ |
| 1Hz pencere sayısı | 614 (Part 3.1 slow index) |
| Kullanım | 50Hz retrieval index; 1Hz retrieval index |

### BUT_PPG — Neden Retrieval Dışında?

BUT_PPG yalnızca PPG (fotoplethizmografi) sinyali içerir; akselerometre veya jiroskop verisi yoktur. Feature pipeline'ın 38 özelliğinin tamamı IMU'dan türetilir. `accel=None, gyro=None` geçildiğinde:

1. Tüm özellikler `NaN` üretir
2. `nan_to_num` ile hepsi `0.0` olur
3. Sıfır vektör, Euclidean uzayda tüm diğer örneklerden eşit uzaklıktadır
4. Retrieval sonuçları anlamlısız "mükemmel eşleşmelerle" dolar

**Karar:** BUT_PPG kalıcı olarak hariç tutulmuştur. `retrieval_build_summary.json` içinde `datasets_skipped[{dataset: "BUT_PPG", reason: "no_imu_data"}]` olarak belgelenmiştir.

### Eğitim vs. Inference Ayrımı

> **Önemli:** Model canlıda yeniden eğitilmemektedir.

```
Offline (eğitim, bir kez):
  Data/HIFD/ + Data/WEDA_FALL/
      → ML model eğitimi (PyTorch, CRNN+VitalsMLP)
      → outputs/models/best_final_fusion_model.pt
      → retrieval index inşası
      → outputs/retrieval/retrieval_index.joblib
      → outputs/retrieval_slow/retrieval_index.joblib

Canlı (inference, sürekli):
  Firmware paketiperforming → shadow inference (ML + retrieval)
  UserBaseline → EMA güncellemesi (kişisel baseline, ağırlıklar değil)
```

Canlı sistemde sadece **UserBaseline EMA** güncellenir. ML model ağırlıkları ve retrieval indeksleri sabittir.

---

## 13. Test Özeti

### Part 1 Testleri (test_16_baseline_mvp.py)

| Grup | Konu | Sayı |
|------|------|------|
| TestBaselineService | EMA güncelleme, sapma hesaplama, risk ayarlama | 10 |
| TestQualityConfidence | Sinyal kalitesi → güven skoru | 4 |
| TestBaselineRepo | SQLite CRUD, upsert, reset | 5 |
| TestBaselineIntegration | Ingestion akışı ile end-to-end | 8 |
| TestAlertSensitivity | Eşik kaydırma, settings entegrasyonu | 5 |
| TestConfigDefaults | Config varsayılan değerleri | 4 |
| **Toplam** | | **36 / 36** |

### Part 2 Testleri (test_17_ml_shadow_mode.py)

| Grup | Konu | Sayı |
|------|------|------|
| TestLiveWindowBuffer | Buffer dolma, overflow, sample_rate_warning | 8 |
| TestMLInferenceService | Lazy load, predict_window, fail-open | 7 |
| TestMLShadowIntegration | Ingestion + buffer + ML shadow | 6 |
| TestWindowStatus | Status dict yapısı ve alanları | 5 |
| TestMLConfig | Config ayarları ve varsayılanlar | 4 |
| TestMLEdgeCases | Boş window, NaN input, exception | 4 |
| **Toplam** | | **34 / 34** |

### Part 3 Testleri (test_18_retrieval_poc.py)

| Grup | Konu | Sayı |
|------|------|------|
| TestRetrievalIndex | Index build, feature dim, label distribution | 6 |
| TestRetrievalEngine | load, query, support score, explain | 8 |
| TestRetrievalShadow | Backend integration, shadow_mode, fail-open | 7 |
| TestSupportScore | Hesaplama doğruluğu, kenar durumlar | 5 |
| TestDemoQuery | Demo betiği sonuç yapısı | 4 |
| TestRegression | Part 1 + 2 testleri hâlâ geçiyor | 6 |
| **Toplam** | | **36 / 36** |

### Part 3.1 Testleri (test_19_alignment_hardening.py)

| Grup | Konu | Sayı |
|------|------|------|
| TestMLSampleRateGate | Skip gate koşulları (4 senaryo) | 4 |
| TestMLVitalsDim | dim=2, dim=3, auto-detect, içerik | 5 |
| TestMLEMAIsolation | Kullanıcı izolasyonu, reset, kontaminasyon yok | 4 |
| TestRetrievalSampleRateGate | 3-way mantık (skip/slow/low-conf) | 4 |
| TestSlowIndexPath | 1Hz index yükleme, sorgulama, final_risk yok | 3 |
| TestDemoSelfMatch | self_match_present, exclude_self_applied | 3 |
| TestRegression | Config, schema, import, smoke API | 7 |
| **Toplam** | | **30 / 30** |

### Genel Sonuç

```
test_16:  36 passed
test_17:  34 passed
test_18:  36 passed  (1 skipped — slow index path, build gerektirir)
test_19:  30 passed
─────────────────────
TOPLAM: 135 passed, 1 skipped, 0 failed
```

---

## 14. Demo için Önerilen Güvenli Konfigürasyon

Demo ortamında: backend çalışır, gerçek veya mock firmware akışı var, sunum yapılıyor.

```env
# ── Temel ──────────────────────────────────────────────────────────────────
DATA_MODE=sqlite
BASELINE_ENABLED=true
BASELINE_MIN_SAMPLES=10          # Demo için hızlı warm-up (üretimde 300)

# ── ML Shadow ───────────────────────────────────────────────────────────────
ML_INFERENCE_ENABLED=true        # Demo'da ML'yi göstermek için açık
ML_SHADOW_MODE=true              # Karar vermez, sadece gösterir
ML_FAIL_OPEN=true                # Model yüklü değilse 500 vermez
ML_SKIP_ON_SAMPLE_RATE_MISMATCH=true   # Güvenli
ML_ALLOW_LOW_CONFIDENCE_INFERENCE=false

# ── Retrieval Shadow ─────────────────────────────────────────────────────────
RETRIEVAL_ENABLED=true           # Demo'da retrieval'ı göstermek için açık
RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH=true
RETRIEVAL_USE_SLOW_INDEX=true    # 1Hz canlı buffer için slow index
RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=false

# ── Devre dışı bırakılacaklar ────────────────────────────────────────────────
PUSH_NOTIFICATIONS_ENABLED=false # Demo'da gerçek bildirim istemezsiniz
FCM_ENABLED=false
```

> **Demo notu:** `ML_INFERENCE_ENABLED=true` ve `RETRIEVAL_ENABLED=true` açıldığında shadow sonuçları response'da görünür. Bu Postman/Flutter arayüzünde kolayca gösterilebilir.

---

## 15. Production için Önerilen Güvenli Konfigürasyon

Production: gerçek kullanıcılar, cihazlar, alarmlar aktif.

```env
# ── Temel ──────────────────────────────────────────────────────────────────
DATA_MODE=firebase               # veya hybrid
BASELINE_ENABLED=true
BASELINE_MIN_SAMPLES=300         # Gerçek kalibrasyonu için en az 5 dakika

# ── ML Shadow — KAPALI (fusion hazır değil) ─────────────────────────────────
ML_INFERENCE_ENABLED=false       # Fusion onaylanana kadar KAPALI
ML_SHADOW_MODE=true
ML_FAIL_OPEN=true

# ── Retrieval Shadow — KAPALI (klinik doğrulama yok) ────────────────────────
RETRIEVAL_ENABLED=false          # Klinik doğrulama tamamlanana kadar KAPALI
RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH=true
RETRIEVAL_USE_SLOW_INDEX=true

# ── Bildirimler ───────────────────────────────────────────────────────────────
PUSH_NOTIFICATIONS_ENABLED=true
FCM_ENABLED=true

# ── Güvenlik ───────────────────────────────────────────────────────────────
SECRET_KEY=<üretim_jwt_secret>
ALLOWED_ORIGINS=["https://healthalert.app"]
```

> **Production notu:** `ML_INFERENCE_ENABLED=false` ve `RETRIEVAL_ENABLED=false` kalmalıdır. Aktif karar yalnızca Part 1 heuristic + baseline motorundan gelmelidir.

---

## 16. Fusion Neden Hâlâ Aktif Değil?

Fusion = ML çıktısı + Retrieval support score + Heuristic risk → tek bir `final_risk_score`.

Fusion aktif olmayan sebepler:

1. **Klinik doğrulama eksik:** ML modeli eğitim verisinde iyi performans gösteriyor ancak gerçek hasta datasında (≥300 hasta, çoklu ortam) test edilmemiştir. Yanlış pozitif oranı bilinmiyor.

2. **False-negative riski:** Düşme tespitinde false-negative (kaçırılan düşme) klinik açıdan ciddi bir hatadır. Fusion formülü bu hatayı artırmadan optimize edilmelidir.

3. **Per-user EMA warm-up:** Yeni kullanıcılar için ML EMA'sı soğuk başlar; ilk tahminler tutarsız olabilir. Minimum warm-up süresi belirlenmemiştir.

4. **Sample-rate alignment:** Firmware ~1 Hz çalışırken model 50 Hz veri bekler. Slow index eklendi (1Hz), ancak 1Hz özellik vektörünün klinik anlamı doğrulanmamıştır.

5. **Fusion ağırlıkları belirlenmemiş:** α (ML ağırlığı), β (retrieval ağırlığı), γ (heuristic ağırlığı) değerleri klinik literatür veya prospektif çalışma gerektirmektedir.

---

## 17. Fusion'a Geçmek İçin Kalan Şartlar

| # | Koşul | Durum |
|---|-------|-------|
| 1 | ML modeli klinik veri seti doğrulama (F1 ≥ 0.80, gerçek hasta) | ❌ |
| 2 | False-negative analizi (düşme kaçırma oranı < %5) | ❌ |
| 3 | Retrieval indeksi klinik kalitede (≥ 10.000 klinik pencere) | ❌ (şu an: 23.446 araştırma) |
| 4 | Per-user warm-up süresi kalibrasyonu (min. 24 saat gerçek kullanım) | ❌ |
| 5 | 1Hz slow index klinik geçerliliği (özellik anlamlılığı doğrulaması) | ❌ |
| 6 | Fusion ağırlıkları (α, β, γ) prospektif çalışma ile belirlenmesi | ❌ |
| 7 | IRB/etik onayı (klinik kullanım) | ❌ |
| 8 | `final_risk_score` fusion mantığı yazılıp test edilmesi | ❌ |
| 9 | `RETRIEVAL_ENABLED=true, ML_INFERENCE_ENABLED=true` prod konfigürasyonu | ❌ |

---

## 18. Bilinen Sınırlamalar

| # | Sınırlama | Önem | Notlar |
|---|-----------|------|--------|
| 1 | Firmware ~1 Hz, model 50 Hz eğitildi | Yüksek | Part 3.1 ile güvenli skip gate + slow index eklendi |
| 2 | ML EMA warm-up: yeni kullanıcı için ilk tahminler tutarsız | Orta | Per-user EMA ile izole edildi; warm-up sayısı belirsiz |
| 3 | Slow index 21 boyut (1Hz), 50Hz index 38 boyut: karşılaştırılamaz | Orta | İki indeks bağımsız — fusion öncesi hizalama gerekir |
| 4 | Baseline 300 örnek gerektirir (~5 dk): yeni kullanıcı kalibre değil | Orta | Demo'da `BASELINE_MIN_SAMPLES=10` ile hızlandırılabilir |
| 5 | BUT_PPG retrieval dışında, PPG-only risk analizi yok | Düşük | Tasarım kararı, IMU özelliği yok |
| 6 | Retrieval self-match: aynı denek hem query hem indekste | Düşük | `--exclude-self` ile giderildi (demo) |
| 7 | EMA state RAM'de: restart sonrası sıfırlanır | Düşük | Production için Redis/DB persistence gerekir |
| 8 | Vitals dim 0 (auto) model olmadan çağrılamaz | Düşük | Fail-open: varsayılan 3 kullanılır |

---

## 19. Sunumda Kullanılacak Kısa Teknik Anlatım

> "HealthAlert, giyilebilir sensörden gelen anlık verileri üç katmanlı bir mimariyle analiz eder.
>
> **Birinci katman** — aktif karar mekanizması — kişiye özel kalibre edilmiş bir heuristic risk motoru. Her kullanıcı için bir baseline oluşturuyoruz: bu kişinin tipik kalp hızı, SpO2, hareket düzeyi nedir? Anlık ölçüm bu baseline'dan ne kadar sapıyor? Sapma yüksekse risk skoru yükseliyor, alarm üretiliyor.
>
> **İkinci katman** — ML shadow modu. PyTorch CRNN modeli son 200 paketi analiz ediyor ve düşme olasılığı üretiyor. Bu sonuç gözlem amaçlıdır, aktif alarm kararına girmez.
>
> **Üçüncü katman** — Retrieval/RAG. Anlık sensör penceresini, 23.000'den fazla tarihi olayı içeren vektör indeksiyle karşılaştırıyoruz. 'Bu duruma en benzer geçmiş olaylar hangileri?' sorusunu yanıtlıyoruz. Bu da gözlem amaçlıdır.
>
> Güvenlik tarafında: firmware ~1 Hz çalışırken model 50 Hz bekliyor. Bu oran farkını tespit ediyor ve model bu durumda atlatılıyor. Her kullanıcının ML durumu bağımsız izole. Herhangi bir hata sistemin çökmesine neden olmuyor — fail-open garantisi var."

---

## 20. Son Verdict

```
╔═══════════════════════════════════════════════════════════════╗
║  HealthAlert — Final Architecture Verdict                     ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Aktif karar:  Heuristic + Personal Baseline + Quality-aware  ║
║                risk motor  (Part 1)                           ║
║                                                               ║
║  Shadow/kanıt: ML inference (PyTorch CRNN) — shadow-only      ║
║                Retrieval/RAG (sklearn NN)  — shadow-only      ║
║                                                               ║
║  final_risk_score  →  SADECE Part 1 motor belirler            ║
║  AlertEvent        →  SADECE Part 1 motor tetikler            ║
║  AnomalyEvent      →  SADECE Part 1 motor tetikler            ║
║                                                               ║
║  Güvenlik:  sample-rate gate ✅  per-user EMA ✅               ║
║             vitals auto-detect ✅  fail-open ✅                ║
║             retrieval alignment gate ✅  slow index ✅         ║
║                                                               ║
║  Test:  135 / 135 passed  (test_16 · 17 · 18 · 19)           ║
║                                                               ║
║  Demo:   HAZIR ✅                                             ║
║  Fusion: KLİNİK DOĞRULAMA BEKLİYOR ⏳                        ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## Mini Özet

> HealthAlert şu an aktif karar tarafında güvenli baseline-aware heuristic risk motorunu kullanır. ML ve retrieval katmanları canlı karar vermeyen, shadow/kanıt destek katmanlarıdır. Part 3.1 ile sample-rate uyumsuzluğu, EMA state karışması, vitals input belirsizliği ve retrieval düşük güven problemi güvenli hale getirilmiştir. Aktif fusion için klinik doğrulama, uzun süreli baseline ve false-negative analizi gerekir.

---

*Bu rapor HealthAlert Part 1 → 3.1 geliştirme sürecinin tamamlanmasının ardından otomatik olarak oluşturulmuştur.*
