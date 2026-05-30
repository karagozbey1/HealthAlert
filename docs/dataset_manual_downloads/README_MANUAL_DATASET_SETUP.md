# HealthAlert — Manuel Dataset Kurulum Kılavuzu

## Amaç

Bu doküman, HealthAlert AI sistemine veri havuzu eklemek için gereken **manuel download ve klasör yapısı kurulum sürecini** açıklamaktadır. Agent dataset indirmez — veri hazırlama kullanıcıya aittir. Agent'ın rolü; klasör yapısını, loader altyapısını ve validation araçlarını hazırlamaktır.

---

## Görev Bazlı Dataset Ayrımı

| Görev | Kullanılan Datasetler |
|-------|-----------------------|
| `fall_detection` | HIFD, WEDA_FALL, SisFall, UniMiB-SHAR, UMAFall, UP-Fall, BITS2 |
| `ppg_quality` | BUT_PPG, BIDMC, PPG-DaLiA, WESAD, WildPPG |
| `vitals_context` | BUT_PPG, BIDMC, PPG-DaLiA, WESAD, BITS2 |
| `activity_context` | HIFD, WEDA_FALL, UCI-HAR, SisFall, UP-Fall, UMAFall, UniMiB-SHAR |
| `gait_instability` | Daphnet FoG, PADS, Hand Tremor |
| `tremor_context` | PADS, Hand Tremor |

---

## Klasör Yapısı

```
healthalert_final_ai/
└── data/
    └── raw/
        ├── sisfall/                      ← SisFall IMU
        ├── unimib_shar/                  ← UniMiB-SHAR .mat / CSV
        ├── ppg_dalia/                    ← PPG-DaLiA S*.pkl
        ├── bits2_geriatric_fall_hr/      ← BITS2 CSV (IMU + HR)
        ├── wesad/                        ← WESAD S*.pkl
        ├── umafall/                      ← UMAFall CSV
        ├── upfall/                       ← UP-Fall sensor CSV (NO video)
        ├── daphnet_fog/                  ← Daphnet .txt files
        ├── pads_smartwatch_pd/           ← PADS PhysioNet WFDB/CSV
        ├── hand_tremor_mpu9250/          ← MPU9250 tremor CSV
        ├── wildppg/                      ← WildPPG .parquet / .h5
        └── fallalld_sensor_only/         ← FallAllD SENSOR ONLY CSV
```

Zaten mevcut (indirilmiş):
```
        ├── hifd/              ← Data/HIFD (gerçek veri mevcut)
        ├── weda_fall/         ← Data/WEDA_FALL (gerçek veri mevcut)
        ├── but_ppg/           ← Data/BUT_PPG (gerçek veri mevcut)
        ├── bidmc/             ← data/raw/bidmc (WFDB, indirildi)
        └── uci_har/           ← data/raw/uci_har (indirildi)
```

---

## Hangi Dataset Nereye

Her dataset klasörünün içinde `README_DROP_HERE.md` dosyası bulunur. Bu dosya:
- İndirme kaynağını
- Beklenen dosya yapısını
- Task bilgilerini
- Uyarıları içerir.

---

## Öncelik Sırası

### Öncelik 1 — Yüksek etki, kolay erişim
1. **SisFall** — http://sistemic.udea.edu.co veya Kaggle mirror
2. **UniMiB-SHAR** — Kaggle mirror, `fall_data.mat` gerekli
3. **PPG-DaLiA** — UCI ML Repository, S1.pkl–S15.pkl
4. **BITS2** — Zenodo 8082667, IMU + HR + fall labels

### Öncelik 2 — Orta etki
5. **WESAD** — UCI / Kaggle, S2.pkl–S17.pkl
6. **UMAFall** — Figshare (web üzerinden manual indirme)
7. **UP-Fall** — Google Sites, YALNIZCA sensor CSV alt seti
8. **Daphnet FoG** — UCI ML Repository, S01R01.txt format

### Öncelik 3 — Düşük öncelik veya opsiyonel
9. **PADS** — PhysioNet parkinsons-disease-smartwatch
10. **Hand Tremor MPU9250** — Kaggle aaryapandya
11. **WildPPG** — GitHub ETH SIP Lab / HuggingFace (büyük: 10+ GB)
12. **FallAllD Sensor-Only** — YALNIZCA sensor CSV subset (falldataset.com RGB versiyonu KULLANILMAZ)

---

## KULLANILMAYACAK Kaynaklar

| Kaynak | Neden Reddedildi |
|--------|-----------------|
| `falldataset.com` | RGB/Depth/Kinect görüntü datasetidir, sensor time-series değildir |
| Video-only datasetler | Wearable sensor verisi içermez |
| Parkinson teşhis tabloları | Time-series IMU/PPG verisi içermez |
| Sentetik/tabular datasetler | Gerçek sensör kaydı değildir |

---

## Validation Komutu

Dataset'i indirdikten ve ilgili klasöre çıkardıktan sonra:

```bash
cd c:\project\HealthAlert\healthalert_final_ai
python scripts/validate_manual_dataset_layout.py
```

Çıktı dosyaları:
- `outputs/reports/manual_dataset_layout_status.json`
- `docs/dataset_manual_downloads/manual_dataset_layout_status.md`

---

## Build Komutu

Validation sonrası tüm mevcut datasetleri pencereleyerek NPZ üretmek için:

```bash
python scripts/build_multi_source_windowed_dataset.py
```

Çıktı: `outputs/windowed_dataset/` (train.npz, val.npz, test.npz)

---

## Test Komutu

```bash
python -m pytest healthalert_final_ai/tests/ -v --tb=short
```

Hedef: 36+ test geçmesi (26 mevcut + 10 yeni)

---

## Sık Karşılaşılan Hatalar

| Hata | Çözüm |
|------|-------|
| `status: missing` | Dataset klasörü boş veya yok. README talimatlarına göre indir. |
| `status: empty` | Klasör var ama dosya yok. ZIP'i klasör içine çıkar. |
| `status: unsupported_vision_only` | Yanlış dataset sürümü. Sensor-only subset gerekli. |
| `status: needs_loader_update` | Loader scaffold hazır, veri var. Loader implementasyonu bekleniyor. |
| `status: unknown_format` | Beklenen uzantı bulunamadı. README'deki format notlarına bak. |
| UP-Fall video dosyası | `.mp4/.avi` dosyalarını yanlışlıkla koyma. Sadece sensor CSV gerekli. |
| FallAllD RGB versiyonu | `falldataset.com` = RGB/Kinect = REDDEDİLİR. Sensor CSV subset gerekli. |

---

## Not

Kullanıcının manuel yapacağı tek işlem, dataset ziplerini ilgili
`healthalert_final_ai/data/raw/<dataset_slug>/` klasörlerine çıkarmaktır.
Tüm loader altyapısı, klasör yapısı, validation araçları ve build scripti hazırdır.
