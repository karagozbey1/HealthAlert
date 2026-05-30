# HealthAlert — Dataset Final Cleanup Before Full Training

**Tarih:** 2026-05-12  
**Proje:** HealthAlert Final AI — `healthalert_final_ai/`  
**Rapor Dosyası:** `docs/dataset_manual_downloads/healthalert_dataset_final_cleanup_before_training_report.md`

---

## 1. Amaç

Bu fazın amacı yeni model eğitmek değil; **full training öncesi veri kaynaklarının doğruluğunu, görev bazlı yönlendirmesini ve yetersiz task'ların training policy ile güvenli şekilde yönetilmesini sağlamaktır.**

Önceki build'de 3 kritik sorun belgelenmişti:

| # | Sorun | Etkisi |
|---|---|---|
| 1 | HIFD / WEDA-Fall / BUT-PPG `no_data` | 3 dataset build'e katkı sağlamıyordu |
| 2 | UCI-HAR `0 window` | 10,299 kayıt pencere üretmiyordu |
| 3 | `tremor_context` 18 pencere | Supervised training için yetersiz |

---

## 2. Başlangıç Durumu

| Metrik | Değer |
|---|---|
| Toplam pencere (önceki) | **374,942** |
| Aktif dataset | 12 |
| fall_detection | 175,526 |
| ppg_quality | 135,161 |
| vitals_context | 135,161 |
| activity_context | 309,947 |
| gait_instability | 8,895 |
| tremor_context | **18** |

---

## 3. HIFD `no_data` Analizi ve Çözümü

### Kök Neden
`datasets.yaml` içinde `local_path: data/raw/hifd` tanımlıydı. Gerçek veriler ise zip arşivinden çıkarıldıktan sonra `data/raw/hifd/HIFD/subject_01/...` altına yerleşmişti. Loader'daki `hifd_path.glob("subject_*")` ifadesi `data/raw/hifd/subject_*` arıyor, bu path mevcut değil → 0 kayıt döndürüyordu.

### Düzeltme
`datasets.yaml`'da `local_path` güncellendi:
```yaml
# Önce
local_path: data/raw/hifd
# Sonra
local_path: data/raw/hifd/HIFD
```

### Sonuç
- HIFD loader: **349 kayıt → 3,277 pencere** ✅  
- fall_detection'a katkı: 3,277 pencere  
- activity_context'e katkı: 3,277 pencere  
- HIFD modality: IMU + PPG (wrist-worn, `heart` kanalı var) — fall_detection'da her iki modalite de kabul edilebilir

---

## 4. WEDA-Fall `no_data` Analizi ve Çözümü

### Kök Neden
Veri `data/raw/weda_fall/WEDA_FALL/dataset/50Hz/` altındaydı. Config `data/raw/weda_fall` olarak tanımlıydı. Loader `weda_path / "dataset" / "50Hz"` aradığı için `data/raw/weda_fall/dataset/50Hz` bulunamıyordu.

### Düzeltme
```yaml
# Önce
local_path: data/raw/weda_fall
# Sonra
local_path: data/raw/weda_fall/WEDA_FALL
```

### Sonuç
- WEDA-Fall loader: **1,781 kayıt (700 fall, 1,081 ADL) → 7,911 pencere** ✅  
- fall_detection'a katkı: 7,911 pencere

---

## 5. BUT-PPG `no_data` Analizi ve Çözümü

### Kök Neden
İki ayrı sorun:
1. **Path sorunu:** Veri `data/raw/but_ppg/BUT_PPG/{record_id}/` altındaydı, config `data/raw/but_ppg` gösteriyordu.
2. **Label key sorunu:** BUT-PPG kayıtları `quality_label` anahtarı kullanıyor, ancak `_wrap_legacy_records` `label` ya da `scenario` anahtarını arıyordu → label_val = None → tüm pencereler "unknown" oluyor.
3. **`good_quality` mapping sorunu:** `assign_window_label()` mapping tablosunda `good_quality` tanımlanmamıştı → quality=1 kayıtları "unknown" olarak etiketleniyordu.

### Düzeltmeler
```yaml
# datasets.yaml path düzeltmesi
local_path: data/raw/but_ppg/BUT_PPG
```

```python
# but_ppg_loader.py: label key eklendi
record = {
    "quality_label": int(row["Quality"]),
    "label": int(row["Quality"]),   # <-- eklendi
    ...
}
```

```python
# windowing.py: assign_window_label mapping genişletildi
mapping = {
    ...
    "bad_quality": "bad_quality",
    "good_quality": "good_quality",   # <-- eklendi
    "walking": "walking",
    "sitting": "sitting",
    "standing": "standing",
    "lying": "lying",
    ...
}
```

### Sonuç
- BUT-PPG loader: **3,888 kayıt → 15,552 pencere** ✅  
- good_quality: 3,320 pencere (quality=1 × ~4 pencere/kayıt)  
- bad_quality: 12,232 pencere  
- ppg_quality ve vitals_context'e katkı: 15,552 pencere

---

## 6. UCI-HAR 0 Window Analizi ve Çözümü

### Kök Neden
UCI-HAR pre-windowed dataset: her kayıt 128 sample @ 50Hz (2.56 sn). Sliding window pipeline 4 sn = 200 sample gerektirir. `segment_timeseries_to_windows` fonksiyonu `series.shape[0] < window_samples` kontrolü yapıyor → 128 < 200 → 0 pencere döndürüyordu.

### Düzeltme
`uci_har_loader.py`'da her 128-sample pencere 200 sample'a zero-pad edildi:

```python
TARGET_SAMPLES = 200
imu_arr = np.zeros((TARGET_SAMPLES, imu_raw.shape[1]), dtype=np.float32)
imu_arr[: imu_raw.shape[0], :] = imu_raw  # zero-pad to 200
# metadata ile işaretlendi
metadata={"pre_windowed": True, "original_samples": 128, "pad_method": "zero_pad_to_200"}
```

### Sonuç
- UCI-HAR: **10,299 kayıt → 10,299 pencere** (1 kayıt = 1 pencere) ✅  
- activity_context'e katkı: 10,299 pencere  
- fall_detection'a katkı: **0** (doğru yönlendirme)  
- ppg_quality/vitals_context'e katkı: **0** (doğru yönlendirme)

---

## 7. tremor_context Veri Yetersizliği Analizi

### Kök Neden
Hand-Tremor-MPU9250 loader, CSV'deki her contiguous label segmentini ayrı bir kayıt olarak işliyordu. Çoğu segment 400 sample'dan (100Hz × 4sn) kısa olduğundan pencere üretmiyordu → toplam 18 pencere.

### Düzeltme
Loader, tüm CSV'yi TEK kayıt olarak döndürecek şekilde değiştirildi. Sliding window pipeline bu tek 27,995-satırlık kaydın tamamına uygulandı:

```python
# Öncesi: per-segment approach → 18 pencere
# Sonrası: single full-record approach
rec = StandardRecord(
    dataset_name=DATASET_NAME,
    imu_samples=imu_arr,     # (27995, 6) — tüm CSV
    labels=canonical_labels,  # per-sample labels
    metadata={"windowing_note": "sliding_window_applied_by_pipeline"},
)
```

### Sonuç: Hâlâ Yetersiz
- 27,995 sample @ 100Hz, 4s/2s window/stride → **138 pencere**
- 138 < 500 minimum eşiği → **Supervised training DISABLED**

### tremor_context Label Dağılımı (138 pencere)
| Label | Pencere | Oran |
|---|---:|---:|
| instability | 78 | 56.5% |
| normal | 60 | 43.5% |
| **Toplam** | **138** | 100% |

---

## 8. Training Policy Guard

Yetersiz veri olan görev için model head'inin körlemesine eğitilmemesi için `config/task_training_policy.yaml` oluşturuldu.

### Politika Özeti

| Görev | Durum | Pencere | Min Eşik |
|---|---|---:|---:|
| fall_detection | ✅ ENABLED | 186,714 | 10,000 |
| ppg_quality | ✅ ENABLED | 150,713 | 1,000 |
| vitals_context | ✅ ENABLED | 150,713 | 1,000 |
| activity_context | ✅ ENABLED | 323,523 | 5,000 |
| gait_instability | ✅ ENABLED | 8,895 | 1,000 |
| tremor_context | ❌ DISABLED | 138 | 500 |

**tremor_context:** `enabled_for_training: false`, `status: optional_low_data`  
Full model training bu head'i supervised loss hesabına katmaz. Yeterli veri toplandığında (`actual_windows >= 500`) `enabled_for_training: true` olarak güncellenmelidir.

---

## 9. Yeni Build Sonucu

**Komut:** `python scripts/build_multi_source_windowed_dataset.py`

| Metrik | Değer |
|---|---|
| **Toplam pencere** | **412,101** |
| Aktif dataset | **15** |
| Train pencere | 271,178 |
| Val pencere | 49,138 |
| Test pencere | 91,785 |
| Pencere süresi | 4 sn |
| Stride süresi | 2 sn |
| Hedef örnekleme | 50 Hz |

**Önceki build'e göre net artış:** 412,101 − 374,942 = **+37,159 pencere** (+9.9%)

---

## 10. Yeni Task-Specific Window Sayıları

| Görev | Toplam | Train | Val | Test | Önceki |
|---|---:|---:|---:|---:|---:|
| `fall_detection` | **186,714** | 106,688 | 23,559 | 56,467 | 175,526 |
| `ppg_quality` | **150,713** | 110,884 | 14,577 | 25,252 | 135,161 |
| `vitals_context` | **150,713** | 110,884 | 14,577 | 25,252 | 135,161 |
| `activity_context` | **323,523** | 206,143 | 39,126 | 78,254 | 309,947 |
| `gait_instability` | **8,895** | 4,456 | 2,620 | 1,819 | 8,895 |
| `tremor_context` | **138** | 138 | 0 | 0 | 18 |

---

## 11. Dataset Bazlı Katkılar

| Dataset | Kayıt | Pencere | Durum | Değişim |
|---|---:|---:|---|---|
| **HIFD** | **349** | **3,277** | ✅ **YENİ AKTİF** | no_data → aktif |
| **WEDA-Fall** | **1,781** | **7,911** | ✅ **YENİ AKTİF** | no_data → aktif |
| **BUT-PPG** | **3,888** | **15,552** | ✅ **YENİ AKTİF** | no_data → aktif |
| SisFall | 10,318 | 55,342 | ✅ OK | değişmedi |
| UP-Fall | 917 | 4,978 | ✅ OK | değişmedi |
| UMAFall | 1,492 | 150,339 | ✅ OK | değişmedi |
| UniMiB-SHAR | 11,771 | 11,771 | ✅ OK | değişmedi |
| **UCI-HAR** | **10,299** | **10,299** | ✅ **0→10,299** | 0 window → aktif |
| BIDMC-PPG-Respiration | 53 | 12,667 | ✅ OK | değişmedi |
| PPG-DaLiA | 15 | 64,727 | ✅ OK | değişmedi |
| WESAD | 15 | 43,415 | ✅ OK | değişmedi |
| WildPPG | 48 | 14,352 | ✅ OK | değişmedi |
| BITS2-Geriatric-Fall-HR | 1,629 | 8,438 | ✅ OK | değişmedi |
| Daphnet-FoG | 17 | 8,895 | ✅ OK | değişmedi |
| **Hand-Tremor-MPU9250** | **1** | **138** | ⚠️ **18→138** | az veri; training disabled |
| MobiAct | — | 0 | ⬜ PARTIAL | veri yok |
| FallAllD | — | 0 | ⬜ PARTIAL | veri yok |
| PADS-Smartwatch-PD | — | 0 | ⬜ EMPTY | veri yok |
| FallAllD-Sensor-Only | — | 0 | ⬜ EMPTY | veri yok |

---

## 12. Label Dağılımları (Yeni)

### fall_detection
| Label | Pencere | Oran |
|---|---:|---:|
| normal | 133,282 | 71.4% |
| fall | 52,501 | 28.1% |
| near_fall | 931 | 0.5% |
| **Toplam** | **186,714** | 100% |

### ppg_quality / vitals_context
| Label | Pencere | Oran |
|---|---:|---:|
| walking | 60,626 | 40.2% |
| normal | 43,415 | 28.8% |
| unknown | 27,019 | 17.9% |
| bad_quality | 12,232 | 8.1% |
| sitting | 4,101 | 2.7% |
| **good_quality** | **3,320** | **2.2%** |
| **Toplam** | **150,713** | 100% |

> **Not:** `good_quality` etiketi önceki build'de `unknown` olarak gözüküyordu; windowing.py'daki label mapping düzeltmesiyle düzeldi.

### tremor_context
| Label | Pencere | Oran |
|---|---:|---:|
| instability | 78 | 56.5% |
| normal | 60 | 43.5% |
| **Toplam** | **138** | 100% |

---

## 13. Safety Check Sonuçları

| Kontrol | Sonuç |
|---|---|
| fall_detection: label=99 (unknown) | **0** ✅ |
| fall_detection: PPG/vitals kontaminasyonu | **0** ✅ |
| fall_detection: ppg_only pencere | **0** ✅ |
| fall_detection: WildPPG katkısı | **0** ✅ |
| fall_detection: Daphnet/Tremor katkısı | **0** ✅ |
| UCI-HAR: fall_detection'da yok | ✅ |
| UCI-HAR: activity_context'te var | **10,299** ✅ |
| BUT-PPG: fall_detection'da yok | ✅ |
| Hand-Tremor: fall_detection'da yok | ✅ |
| **Genel PASS** | **✅ PASS** |

---

## 14. Test Sonuçları

### Yeni Test Dosyası
`tests/test_dataset_final_cleanup_before_training.py` — **40 test**

```
TestPathFixes                  8 passed  ← HIFD/WEDA/BUT-PPG path + katkı doğrulaması
TestUciHar                     4 passed  ← padding, metadata, routing
TestTremorContext               6 passed  ← single-record, artış, eşik, label
TestTrainingPolicyGuard        11 passed  ← policy YAML yapısı ve guard mantığı
TestSafetyChecks               7 passed  ← fall_detection güvenlik kontrolleri
TestBuildStability             4 passed  ← JSON/NPZ varlığı
```

### Regresyon Testleri (Önceki)
```
test_window_pipeline.py                   4 passed
test_dataset_hub_pipeline.py             22 passed
test_manual_dataset_dropin_preparation   14 passed
test_task_specific_window_exports        18 passed  ← 1 test güncellendi (HIFD PPG)
```

### Toplam Sonuç
```
98 passed in 4.82s
```

**Not:** `test_fall_detection_has_only_imu_modality` testi güncellendi. HIFD, fall_detection için gerçek bir IMU+PPG sensörlü dataset'tir ve `both` modality pencerelerine izin verilir. Kritik kontrol `ppg_only == 0` şartı hâlâ geçerlidir.

---

## 15. Full Training İçin Hazır / Hazır Değil Kararı

### Etkin Görevler (5/6)
| Görev | Pencere | Karar |
|---|---:|---|
| fall_detection | 186,714 | ✅ HAZIR |
| ppg_quality | 150,713 | ✅ HAZIR |
| vitals_context | 150,713 | ✅ HAZIR |
| activity_context | 323,523 | ✅ HAZIR |
| gait_instability | 8,895 | ✅ HAZIR (soft threshold) |

### Pasif Görev (1/6)
| Görev | Pencere | Karar |
|---|---:|---|
| tremor_context | 138 | ❌ TRAINING DISABLED — optional_low_data |

**tremor_context için açık uyarı:** Bu task için yeterli veri yoktur. Ana model başarısı iddiasında `tremor_context` performansı kullanılmayacaktır. `actual_windows >= 500` olduğunda `task_training_policy.yaml`'daki `enabled_for_training: true` olarak güncellenmelidir.

---

## 16. Kalan İşler

| Öncelik | Görev | Durum |
|---|---|---|
| Yüksek | Full model training başlatılması | ⏳ Bu fazdan sonra |
| Orta | MobiAct, FallAllD veri indirmesi | ⏳ Bekliyor |
| Orta | PADS-Smartwatch-PD veri indirmesi | ⏳ Bekliyor |
| Düşük | tremor_context için ek veri toplanması (MPU9250) | ⏳ Bekliyor |
| Düşük | gait_instability unknown oranını azaltma (%9.7) | ⏳ Bekliyor |
| Düşük | WildPPG sternum/head/ankle lokasyonlarından veri | İsteğe bağlı |

---

## 17. Değiştirilen / Eklenen Dosyalar

### Değiştirilen
| Dosya | Değişiklik |
|---|---|
| `config/datasets.yaml` | HIFD, WEDA_FALL, BUT_PPG `local_path` düzeltmesi |
| `src/data/loaders/uci_har_loader.py` | 128→200 zero-pad, `pre_windowed` metadata |
| `src/data/loaders/hand_tremor_loader.py` | Per-segment → single full-record approach |
| `src/data/loaders/but_ppg_loader.py` | `"label"` key eklendi |
| `src/data/windowing.py` | `assign_window_label` mapping'e `good_quality` eklendi |
| `tests/test_task_specific_window_exports.py` | `test_fall_detection_has_only_imu_modality` HIFD PPG'ye izin verir hale getirildi |

### Eklenen
| Dosya | Açıklama |
|---|---|
| `config/task_training_policy.yaml` | Full training guard — 6 görev politikası |
| `tests/test_dataset_final_cleanup_before_training.py` | 40 yeni test |

---

## 18. Verdict

| Kriter | Sonuç |
|---|---|
| HIFD no_data düzeltildi | ✅ 3,277 pencere |
| WEDA-Fall no_data düzeltildi | ✅ 7,911 pencere |
| BUT-PPG no_data düzeltildi | ✅ 15,552 pencere |
| UCI-HAR 0 window düzeltildi | ✅ 10,299 pencere |
| tremor_context artırıldı | ✅ 18 → 138 pencere |
| tremor_context training guard | ✅ DISABLED (< 500 eşiği) |
| Training policy oluşturuldu | ✅ 6 görev tanımlı |
| fall_detection güvenliği korundu | ✅ PASS |
| Toplam pencere artışı | ✅ 374,942 → **412,101** (+%9.9) |
| Test suite | ✅ **98/98 geçti** |
| Build stabilite | ✅ EMPTY/PARTIAL dataset'lar build'i bozmaz |

**Durum: PASS — Full training başlayabilir (tremor_context hariç).**

---

*Oluşturan: GitHub Copilot / HealthAlert AI Agent*  
*Kaynak kod: `healthalert_final_ai/`*
