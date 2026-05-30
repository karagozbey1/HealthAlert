# HealthAlert — Dataset Bulk Download & Rebuild Report

**Tarih:** 2026-05-11  
**Oturum:** Dataset Hub Bulk Download & Windowed Dataset Rebuild

---

## 1. Amaç

Bu oturumun amacı, HealthAlert AI pipeline'ına 14 veri kümesini (Dataset Hub) entegre etmek için:

1. Tüm bağımlılıkları doğrulamak (`wfdb`, `kaggle`, `scipy`, `h5py`, `pyarrow`, `mat73`)
2. Mümkün olan veri kümelerini otomatik indirmek
3. BUT_PPG waveform yüklemeyi aktif etmek (wfdb ile)
4. `outputs/windowed_dataset` yedeğini alıp yeniden inşa etmek
5. Smoke training & 26 testi geçmek
6. Sonuçları raporlamak

---

## 2. Başlangıç Durumu

| Metrik | Değer |
|--------|-------|
| Önceki window sayısı | 1733 |
| Katkıda bulunan dataset | HIFD (927) + WEDA_FALL (806) |
| BUT_PPG durumu | 0 window (wfdb eklenmemişti) |
| BIDMC durumu | İndirilmemişti |
| UCI-HAR durumu | İndirilmemişti |
| Tüm testler | 26/26 ✓ |

---

## 3. Bağımlılık Durumu

Tüm paketler zaten kuruluydu:

| Paket | Sürüm | Durum |
|-------|-------|-------|
| wfdb | 4.3.1 | ✓ Mevcut |
| kaggle | 2.1.2 | ✓ Mevcut (kimlik bilgisi yok) |
| scipy | 1.17.1 | ✓ Mevcut |
| h5py | 3.16.0 | ✓ Mevcut |
| pyarrow | 24.0.0 | ✓ Mevcut |
| mat73 | 0.65 | ✓ Mevcut |

**Kaggle kimliği:** `~/.kaggle/kaggle.json` mevcut değil → Kaggle veri kümeleri `manual_required`.

---

## 4. Dataset Download Durumu (14 Veri Kümesi)

### Otomatik İndirildi ✓

| Dataset | Yöntem | Dosya Sayısı | Konum |
|---------|--------|-------------|-------|
| **UCI-HAR** | UCI HTTP (direct URL) | 64 dosya | `data/raw/uci_har/UCI HAR Dataset/` |
| **BIDMC-PPG-Respiration** | `wfdb.dl_database('bidmc')` | 106 dosya (53 kayıt) | `data/raw/bidmc/` |

### Zaten Mevcut ✓

| Dataset | Konum | Kayıt Sayısı |
|---------|-------|-------------|
| **HIFD** | `Data/HIFD/` | 21 özne, 349 deneme |
| **WEDA_FALL** | `Data/WEDA_FALL/` | – |
| **BUT_PPG** | `Data/BUT_PPG/` | 3888 kayıt dizini |

### Manuel İndirme Gerekiyor ✗

| Dataset | URL | Not |
|---------|-----|-----|
| SisFall | http://sistemic.udea.edu.co/en/research/projects/falls/ | Kayıt formu |
| UP-Fall | https://sites.google.com/up.edu.mx/har-up/ | CSV indirme |
| UMAFall | https://figshare.com/articles/dataset/UMAFall_Fall_Detection_Dataset/4214283 | Figshare 202 döndürüyor |
| UniMiB-SHAR | http://www.sal.disco.unimib.it/technologies/unimib-shar/ | fall_data.mat + adl_data.mat |
| FallAllD | https://falldataset.com/ | CSV |
| PPG-DaLiA | https://archive.ics.uci.edu/dataset/495/ppg+dalia | S*.pkl dosyaları |
| WESAD | https://archive.ics.uci.edu/dataset/465/wesad | S*.pkl dosyaları |
| WildPPG | https://github.com/EPiC-Lab/WildPPG | Parquet/H5 |

### İzin/Form Gerekiyor ✗

| Dataset | URL |
|---------|-----|
| MobiAct | https://bmi.teicrete.gr/index.php/research/mobifall |

### PhysioNet Slug Sorunu (Çözüldü)

BIDMC'nin `wfdb.dl_database()` ile doğru slug'u `'bidmc'` (sürüm son ek olmadan). `'bidmc/1.0.0'` → 404 hata verir.

---

## 5. Loader Düzeltmeleri

### BUT_PPG — Waveform Yükleme Aktifleştirildi

`loader_registry.py`'de `_load_but_ppg` fonksiyonu güncellendi:

```python
def _load_but_ppg(cfg, path):
    try:
        import wfdb
        waveforms_available = True
    except ImportError:
        waveforms_available = False
    raw = load_all_records(path, load_waveforms=waveforms_available)
    return _wrap_legacy_records("BUT_PPG", raw, cfg)
```

Her kayıt `wfdb.rdrecord()` ile 300-örnek PPG dizi döndürüyor.

### BIDMC — Dosya Deseni Düzeltmesi

`bidmc_loader.py`'de `bidmc_*.hea` → `bidmc*.hea` düzeltildi (gerçek dosya adları: `bidmc01.hea`, `bidmc02.hea`, ...).

### UCI-HAR — İç İçe ZIP Yapısı

UCI HAR indirmesi dıştaki zip içinde `UCI HAR Dataset.names` + `UCI HAR Dataset.zip` (iç zip) içeriyor. İç zip `UCI HAR Dataset/train` + `UCI HAR Dataset/test` dizin yapısına çıkarılıyor. Loader bu yapıyı zaten destekliyor.

---

## 6. Window Build Sonuçları

### Rebuild Komutu

```bash
python scripts/build_multi_source_windowed_dataset.py --max-records-per-dataset 100
```

Yedek: `outputs/windowed_dataset_backup_20260511_135331/`

### Dataset Katkıları

| Dataset | Kayıt | Window | Modality |
|---------|-------|--------|----------|
| HIFD | 100 (349'dan) | 927 | IMU + PPG |
| WEDA_FALL | 100 | 806 | IMU only |
| BUT_PPG | 100 (3888'den) | 400 | PPG only |
| BIDMC | 53 (tümü) | 12,667 | PPG only |
| UCI-HAR | 100 yüklendi | **0** | IMU only† |
| Diğer 9 | – | 0 | – |
| **TOPLAM** | – | **14,800** | – |

†UCI-HAR kayıtları 128 örneklik önceden segmentlenmiş windows; 4s×50Hz=200 örneklik pencere eşiğinin altında kalıyor.

### Label Dağılımı

| Label | Sayı | % |
|-------|------|---|
| normal (0) | 1,259 | 8.5% |
| fall (1) | 210 | 1.4% |
| near_fall (2) | 264 | 1.8% |
| unknown (99) | 13,067 | 88.3% |

> ⚠️ BIDMC bir PPG/solunum veri kümesidir; düşme etiketi yoktur. 13,067 window `label=99` (unknown) alıyor. Bu windows PPG kalite/fizyoloji modelleri için değerli ama düşme sınıflandırması için etiket yoktur.

### Split (Özneye Göre)

| Split | Özne | Window |
|-------|------|--------|
| Train | 66 | 10,790 |
| Val | 14 | 1,555 |
| Test | 15 | 2,455 |

Özellik vektörü: `1400 float32` (200×6 IMU + 200×1 PPG), eksik modalite sıfır dolgulu.

---

## 7. Smoke Training Sonuçları

Smoke training, train setinin ilk 256 örneğini kullanır (stratifiye olmayan). Örneklem içinde labels 0/1/2 bulunduğundan eğitim çalıştı.

| Metrik | Val | Test |
|--------|-----|------|
| Accuracy | 36.7% | 41.4% |
| Precision | 36.7% | 41.7% |
| Recall | 39.2% | 42.7% |
| F1 | 36.3% | 41.2% |

Sınıf bazlı recall (test): normal=38.1%, fall=40.0%, near_fall=50.0%

> Smoke training bir baseline LinearLogisticRegression modeli eğitir; düşük metrikler beklenen. Üretim için daha güçlü modeller gerekiyor.

**Düzeltilen bug:** `datetime.utcnow()` deprecation warning → `datetime.now(timezone.utc)` olarak güncellendi.

---

## 8. Test Sonuçları

```
26 passed in 1.47s   ✓
```

Tüm 26 test başarılı:
- `test_window_pipeline.py` — 4 test
- `test_dataset_hub_pipeline.py` — 22 test

---

## 9. UCI-HAR 0 Window Sorunu

UCI-HAR pre-segmented windows kullanır (128 örnek / 2.56 saniye @ 50Hz). Build script'in sliding window mantığı minimum 4s×50Hz=200 örnek gerektirir. 128 < 200 olduğundan pencere üretilemiyor.

**Çözüm seçenekleri:**
1. UCI-HAR için özel loader: Her kayıt zaten bir pencere → direkt feature vector oluştur (200'e zero-pad veya tekrar-örnekle)
2. `--window-sec 2` seçeneğiyle rebuild (100 örnek < 128 olur, çalışır)
3. UCI-HAR loader'ını `DatasetLoadResult` dönerken kayıtları pre-windowed olarak işaretle

---

## 10. Kalan Manuel İşler

Aşağıdaki veri kümelerini kendiniz indirip belirlenen dizine çıkarın:

```
data/raw/sisfall/      → SA*/SE* klasör yapısı
data/raw/upfall/       → CSV dosyaları
data/raw/umafall/      → CSV dosyaları (Figshare manual)
data/raw/unimib_shar/  → fall_data.mat + adl_data.mat
data/raw/fallalld/     → CSV veya pkl dosyaları
data/raw/ppg_dalia/    → S*.pkl dosyaları
data/raw/wesad/        → S*.pkl dosyaları
data/raw/wildppg/      → .parquet veya .h5 dosyaları
data/raw/mobiact/      → form ile talep (serbest akademik)
```

İndirdikten sonra:
```bash
python scripts/build_multi_source_windowed_dataset.py
python scripts/train_window_model.py --dataset-dir outputs/windowed_dataset --output-dir outputs/models --smoke
```

---

## 11. Sonraki Adımlar

1. **UCI-HAR window sorunu:** Pre-segmented loader desteği ekle
2. **BIDMC etiket stratejisi:** BIDMC windows için `ppg_quality` / `vitals_context` görevi tanımla; düşme sınıflandırmasından ayır
3. **Label 99 filtresi:** Smoke training için label≠99 filtresi veya stratifiye örnekleme ekle
4. **Üretim eğitimi:** `--max-records-per-dataset` kısıtı olmadan tüm HIFD + WEDA_FALL + BUT_PPG (3888 kayıt) + BIDMC (53 kayıt) ile eğit
5. **Manuel dataset indirme:** Yukarıdaki 9 dataset indirilirse toplam window sayısı tahmin: ~50,000+

---

## 12. Verdict

| Kategori | Değer |
|----------|-------|
| Otomatik indirilen | 2/14 (UCI-HAR + BIDMC) |
| Zaten mevcut | 3/14 (HIFD + WEDA_FALL + BUT_PPG) |
| Manuel gerekiyor | 9/14 |
| Window pencere sayısı: önce → sonra | **1,733 → 14,800** (+754%) |
| Katkıda bulunan dataset | 3 → **4** (HIFD + WEDA_FALL + BUT_PPG + BIDMC) |
| Smoke training | ✓ Exit 0 |
| 26 test | ✓ 26/26 |
| Yedek | `outputs/windowed_dataset_backup_20260511_135331/` |

**SONUÇ:** Dataset Hub entegrasyonu KISMEN başarılı. Toplam window sayısı 14,800'e çıktı (%754 artış), 4 dataset aktif, smoke training ve tüm testler geçiyor. 9 dataset manuel indirme gerektiriyor.
