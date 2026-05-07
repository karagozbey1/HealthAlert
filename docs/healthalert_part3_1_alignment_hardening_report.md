# HealthAlert Part 3.1 — Live Alignment, ML/Retrieval Safety Hardening
## Rapor

**Tarih:** 2026-04-29  
**Durum:** TAMAMLANDI ✅  
**Önceki durum:** 105/135 testler geçiyordu (Part 1, 1.1, 2, 3 eksiksiz)  
**Yeni durum:** 135/135 testler geçiyor (test_16..test_19 eksiksiz)

---

## 1. Amaç

Part 3.1, canlı firmware akışı ile ML ve retrieval modellerinin sample-rate uyuşmazlığından kaynaklanan güvenlik sorunlarını gidermek için tasarlanmıştır. HealthAlert firmware'i ~1 Hz hızında paket gönderirken, eğitim verileri 50 Hz'den alınmaktadır. Bu oran farkı tahminlerin güvenilirliğini ciddi ölçüde etkileyebilir.

Temel hedefler:

- ML tahmincisini düşük sample-rate durumunda güvenli şekilde atlatmak (skip gate)
- ML EMA durumunu kullanıcı başına izole etmek (global kontaminasyonu önlemek)
- VitalsMLP vitals input_dim boyutunu dinamik olarak tespit etmek
- Retrieval hizmetine sample-rate uyarısına göre 3 yollu mantık eklemek
- 1 Hz hizalanmış (slow) retrieval indeksini oluşturmak
- Demo betikline self-match tespiti eklemek
- Gereksiz import'ı temizlemek

---

## 2. Giderilen Sorunlar Listesi

| ID  | Sorun | Giderildi mi? |
|-----|-------|---------------|
| A   | ML modeli yavaş canlı buffer'larda yanlış sonuç üretiyor | ✅ |
| B   | Kullanıcı EMA durumu diğer kullanıcıları kirletiyor | ✅ |
| C   | VitalsMLP vitals giriş boyutu belirsiz (2 mi, 3 mü?) | ✅ |
| D1  | Retrieval 50Hz indeksini 1Hz veriyle sorguluyor | ✅ |
| D2  | 1Hz hizalanmış retrieval indeksi yoktu | ✅ |
| E   | Demo betikinde self-match tespit edilmiyordu | ✅ |
| F   | `retrieval_shadow_service.py`'de gereksiz `import numpy as np` | ✅ |
| G   | Geriye dönük uyumluluk (tüm eski testler hâlâ geçmeli) | ✅ |

---

## 3. ML Sample-Rate Gate (A)

### Yapılan Değişiklikler

**`backend/config.py`** — 4 yeni ayar eklendi:

```python
ML_SKIP_ON_SAMPLE_RATE_MISMATCH: bool = True
ML_MAX_DURATION_RATIO: float = 3.0
ML_ALLOW_LOW_CONFIDENCE_INFERENCE: bool = False
ML_VITALS_DIM: int = 0   # 0=auto, 2=[hr,spo2], 3=[hr,spo2,quality]
```

**`backend/services/ml_inference_service.py`** — `predict_window()` başına gate eklendi:

```python
if (window_status and window_status.get("sample_rate_warning")
        and settings.ML_SKIP_ON_SAMPLE_RATE_MISMATCH
        and not settings.ML_ALLOW_LOW_CONFIDENCE_INFERENCE):
    return {
        "ml_available": False,
        "ml_skipped": True,
        "skip_reason": "sample_rate_mismatch",
        "shadow_mode": True,
        "low_confidence": True,
        "estimated_window_duration_sec": ...,
        "expected_duration_sec": ...,
    }
```

**`backend/routers/ingestion_router.py`** — `predict_window` çağrısına `window_status` eklendi:

```python
ml_shadow_result = await asyncio.to_thread(
    ml_inference_service.predict_window,
    user_id, window, None, window_status,   # window_status artık iletiliyor
)
```

### Davranış

| `sample_rate_warning` | `ML_SKIP_ON_SAMPLE_RATE_MISMATCH` | `ML_ALLOW_LOW_CONFIDENCE_INFERENCE` | Sonuç |
|----|----|----|---|
| False | True | False | Normal tahmin |
| True | True | False | **Skip** (ml_skipped=True) |
| True | True | True | Override: Tahmin yapılır |
| True | False | False | Gate devre dışı: Tahmin yapılır |

---

## 4. ML Per-User EMA State Isolation (B)

### Problem

`HealthAlertPredictor._ema_state` tüm kullanıcılar arasında paylaşılan tek bir dict'ti. Yüksek riskli kullanıcının tahmini diğer kullanıcıların sonuçlarını kirletiyordu.

### Çözüm

`MLInferenceService.__init__()` içine kullanıcı başına EMA haritası eklendi:

```python
self._ema_states_by_user: Dict[str, Dict[str, float]] = {}
```

`predict_window()` içinde her çağrıda:

1. Kullanıcının EMA durumu `_ema_states_by_user` haritasından alınır
2. `predictor._ema_state = user_ema.copy()` ile predictor'a yüklenir
3. Tahmin yapılır
4. Güncellenmiş EMA durumu haritaya kaydedilir (`_ema_states_by_user[user_id] = predictor._ema_state.copy()`)

`reset_user_state(user_id)`:

```python
def reset_user_state(self, user_id: str) -> None:
    with self._lock:
        self._ema_states_by_user.pop(user_id, None)
        if self._predictor is not None:
            self._predictor.reset()
```

---

## 5. Vitals Input Dim Detection (C)

### Problem

`VitalsMLP`'nin `in_features` değeri 2 mi (hr, spo2) yoksa 3 mü (hr, spo2, quality) bilinmiyordu.

### Çözüm

**`config.py`** — `ML_VITALS_DIM: int = 0` (0 = otomatik tespit)

**`ml_inference_service.py`** — `_detect_vitals_dim()`:

```python
def _detect_vitals_dim(self) -> int:
    if settings.ML_VITALS_DIM > 0:
        return settings.ML_VITALS_DIM
    # Model introspection
    for name, mod in self._predictor.model.named_modules():
        if "vital" in name.lower() and hasattr(mod, "in_features"):
            return int(mod.in_features)
    return 3  # fallback
```

`build_predictor_inputs()` — `_resolved_vitals_dim` kullanıyor:

```python
if self._resolved_vitals_dim == 2:
    vitals = np.array([hr, spo2_norm], dtype=np.float32)
else:  # 3
    vitals = np.array([hr, spo2_norm, quality], dtype=np.float32)
```

---

## 6. Retrieval Mismatch Gate (D1)

### Yapılan Değişiklikler

**`backend/config.py`** — 4 yeni ayar:

```python
RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH: bool = True
RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY: bool = False
RETRIEVAL_USE_SLOW_INDEX: bool = True
RETRIEVAL_SLOW_INDEX_DIR: str = "outputs/retrieval_slow"
```

**`backend/services/retrieval_shadow_service.py`** — `query_window()` içinde 3 yollu mantık:

```
sample_rate_warning=True durumunda:
  1. RETRIEVAL_USE_SLOW_INDEX=True ve slow engine yüklü
       → _query_with_engine(slow_engine, ..., aligned_mode="slow_1hz", low_confidence=False)
  2. RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY=True
       → _query_with_engine(50hz_engine, ..., low_confidence=True)
  3. RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH=True
       → {"retrieval_skipped": True, "skip_reason": "sample_rate_mismatch", ...}
```

---

## 7. Slow-Rate Retrieval Index Yapıldı mı? → EVET ✅

İndeks başarıyla oluşturuldu:

```
outputs/retrieval_slow/
├── retrieval_index.joblib          (NearestNeighbors, ball_tree, euclidean)
├── retrieval_scaler.joblib         (StandardScaler, 21 feature)
├── retrieval_features.npy          (1354, 21) float32
├── retrieval_metadata.json         (1354 kayıt)
└── retrieval_build_summary.json
```

---

## 8. outputs/retrieval_slow/ Çıktıları

```json
{
  "total_windows": 1354,
  "feature_dim": 21,
  "slow_index": true,
  "downsample_factor": 50,
  "slow_window_size": 30,
  "slow_stride": 10,
  "target_sample_rate_hz": 1,
  "datasets_included": ["HIFD", "WEDA_FALL"],
  "datasets_skipped": [{"dataset": "BUT_PPG", "reason": "no_imu_data"}],
  "label_distribution": {"fall": 386, "normal": 862, "near_fall": 106},
  "build_time_sec": 6.7,
  "n_neighbors": 10
}
```

Beklenen 21 boyut ve 1354 pencere başarıyla oluşturuldu.

---

## 9. Slow İndeks Oluşturma Detayları

**Tasarım kararları:**

| Parametre | Değer | Neden |
|-----------|-------|-------|
| `DOWNSAMPLE_FACTOR` | 50 | 50Hz → 1Hz için 50 örnek/bin |
| `SLOW_WINDOW` | 30 saniye | Yeterli istatistiksel bağlam |
| `SLOW_STRIDE` | 10 saniye | %67 örtüşme, veri zenginleştirme |
| `MIN_SLOW_WINDOW` | 10 saniye | Kısa trial'lar için tolerans |
| Feature dim | 21 | Frekans özellikleri çıkarıldı (1Hz'de anlamsız) |

**Slow özellikler (21 toplam):**
- Accel magnitude: mean, std, max, min, range, motion_energy, jerk_proxy (7)
- Gyro magnitude: mean, std, max, min, range (5)
- HR: mean, std, min, max (4)
- SpO2: mean, std, min, max (4)
- Quality: mean (1)

---

## 10. Demo Self-Match Düzeltmesi (E)

**`healthalert_final_ai/scripts/demo_retrieval_query.py`**

Eklenen CLI argümanı:

```bash
python scripts/demo_retrieval_query.py --exclude-self
```

Eklenen çıktı alanları:

```json
{
  "self_match_present": true,
  "exclude_self_applied": true
}
```

**Self-match tespit mantığı:**
- `distance < 1e-6` olan sonuçlar → kesin self-match
- Aynı `subject_id` + `dataset=HIFD` → olası self-match

`--exclude-self` aktif olduğunda bu sonuçlar filtrelenir.

**Test sonucu:**
```
Self-match exclusion applied: 10 → 7 examples
```

---

## 11. Değiştirilen Dosyalar

| Dosya | Değişiklik Özeti |
|-------|-----------------|
| `backend/config.py` | +8 alignment ayarı |
| `backend/services/ml_inference_service.py` | Sample-rate gate, per-user EMA, vitals_dim |
| `backend/services/retrieval_shadow_service.py` | 3 yollu alignment gate, slow index desteği, gereksiz import kaldırıldı |
| `backend/routers/ingestion_router.py` | `predict_window` çağrısına `window_status` eklendi |
| `backend/_smoke_api.py` | `retrieval_shadow_result` key kontrolü eklendi |
| `healthalert_final_ai/scripts/demo_retrieval_query.py` | `--exclude-self`, `self_match_present`, `exclude_self_applied` |

---

## 12. Eklenen Dosyalar

| Dosya | Amaç |
|-------|-------|
| `healthalert_final_ai/scripts/build_retrieval_slow_index.py` | Slow (1Hz) retrieval indeksini oluşturan script |
| `backend/tests/module7/test_19_alignment_hardening.py` | 30 yeni test |
| `outputs/retrieval_slow/retrieval_index.joblib` | 1Hz NearestNeighbors indeksi |
| `outputs/retrieval_slow/retrieval_scaler.joblib` | 21 boyutlu StandardScaler |
| `outputs/retrieval_slow/retrieval_features.npy` | (1354, 21) özellik matrisi |
| `outputs/retrieval_slow/retrieval_metadata.json` | 1354 kayıt metaverisi |
| `outputs/retrieval_slow/retrieval_build_summary.json` | İndeks özeti |

---

## 13. Response Geriye Uyumluluğu

Tüm mevcut API response şemaları değişmedi:

- `DevicePacketResponse` — yeni alan YOK, mevcut alanlar aynı
- `ml_shadow_result` — `ml_skipped: False` eklendi (yeni default değer, mevcut parserlara zararsız)
- `retrieval_shadow_result` — `aligned_mode` ve `low_confidence` alanları eklendi (opsiyonel, backward compat)
- `final_risk_score` — **HİÇBİR ZAMAN** ML veya retrieval tarafından değiştirilmez

---

## 14. Test Edilen Senaryolar

### test_19 Sınıfları

| Test Sınıfı | Test Sayısı | Konu |
|-------------|-------------|-------|
| `TestMLSampleRateGate` | 4 | Sample-rate gate koşulları |
| `TestMLVitalsDim` | 5 | Vitals dim=2,3, içerik doğrulaması |
| `TestMLEMAIsolation` | 4 | Kullanıcı EMA izolasyonu |
| `TestRetrievalSampleRateGate` | 4 | 3 yollu retrieval mantığı |
| `TestSlowIndexPath` | 3 | Slow index yükleme ve sorgulama |
| `TestDemoSelfMatch` | 3 | Self-match bayrakları |
| `TestRegression` | 7 | Geriye dönük uyumluluk |

---

## 15. Çalıştırılan Komutlar ve Sonuçları

```powershell
# Slow index oluşturma (debug)
python scripts/build_retrieval_slow_index.py --max-subjects 5 --max-trials 50
# → 140 pencere, feature_dim=21, 1.2 saniye

# Slow index oluşturma (tam)
python scripts/build_retrieval_slow_index.py
# → 1354 pencere, feature_dim=21, 6.7 saniye

# Demo with self-match
python scripts/demo_retrieval_query.py --top-k 10 --exclude-self
# → Self-match exclusion applied: 10 → 7 examples

# Test 19
python -m pytest tests/module7/test_19_alignment_hardening.py -v
# → 30 passed

# Tüm Part 1-3.1 testleri
python -m pytest tests/module7/test_16..test_19 -v
# → 135 passed, 1 skipped, 0 failed
```

---

## 16. Bilinen Sınırlamalar

1. **Slow index feature dim mismatch**: Canlı buffer'dan çıkarılan özellikler her zaman 21 boyut üretmeyebilir (eksik HR/SpO2 durumunda). Bu durumda `retrieval_available=False` dönülür (fail-open).

2. **EMA warm-up**: Yeni kullanıcılar için ilk EMA durumu sıfırdan başlar; bu nedenle ilk birkaç tahmin soğuk başlangıç biasına sahip olabilir.

3. **Vitals dim auto-detection**: `_detect_vitals_dim()` model başlatılmadan önce çağrılamaz. Model yüklenememişse varsayılan 3 kullanılır.

4. **Slow index boyutu**: 1354 pencere, klinik grade güvenilirlik için yeterli değildir; sadece PoC amaçlıdır.

5. **Demo self-match**: Eşleşme tespiti yalnızca subject_id bazlıdır; iyi hizalanmış farklı deneklerden gelen gerçek yinelenen örnekler filtrelenmez.

---

## 17. Aktif Karar Hâlâ Kimden Geliyor?

**Karar: Part 1 heuristic + baseline pipeline**

ML ve retrieval sonuçları yalnızca `shadow_mode=True` ile **gözlem amaçlı** döndürülmektedir:

```
final_risk_score → SADECE heuristic/baseline logic (Part 1)
ml_shadow_result → gözlem, hiçbir zaman karar etkisi yok
retrieval_shadow_result → gözlem, hiçbir zaman karar etkisi yok
```

---

## 18. Fusion'a Geçmek İçin Kalan Şartlar

Aşağıdaki koşullar sağlandığında ML/retrieval sonuçları karar sürecine entegre edilebilir:

| # | Koşul | Durum |
|---|-------|-------|
| 1 | ML modelinin klinik veri seti üzerinde doğrulanması (F1 ≥ 0.80) | ❌ Bekliyor |
| 2 | Retrieval indeksinin en az 10.000 pencere içermesi | ❌ (şu an: 23.446 / 1.354) |
| 3 | Per-user baseline kalibrasyonunun tamamlanması (min. 24 saatlik veri) | ❌ Bekliyor |
| 4 | Klinik güvenlik incelemesi (false negative analizi) | ❌ Bekliyor |
| 5 | `final_risk_score` fusion mantığının yazılması ve test edilmesi | ❌ Bekliyor |
| 6 | `RETRIEVAL_ENABLED=True, ML_INFERENCE_ENABLED=True` prod konfigürasyonu | ❌ Bekliyor |

---

*Bu rapor otomatik olarak HealthAlert geliştirme sürecinin Part 3.1 tamamlama aşamasında oluşturulmuştur.*
