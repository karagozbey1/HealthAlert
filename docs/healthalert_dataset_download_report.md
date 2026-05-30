# HealthAlert Dataset Download Report

**Tarih:** 2026-05-11T10:41:07.683022+00:00  
**Dry run:** False  

---

## Download Durumu Özeti

| Durum | Sayı | Dataset'ler |
|-------|------|-------------|
| ✅ Zaten Mevcut | 0 | — |
| ⬇️ İndirildi | 1 | UCI-HAR |
| ⚠️ Kısmi | 0 | — |
| 📋 Manuel | 10 | HIFD, WEDA_FALL, SisFall, UP-Fall, UMAFall, UniMiB-SHAR, FallAllD, PPG-DaLiA, WESAD, WildPPG |
| 📧 İstek Gerekli | 1 | MobiAct |
| ❌ Başarısız | 2 | BUT_PPG, BIDMC-PPG-Respiration |
| 🔴 Bağımlılık Eksik | 0 | — |

---

## Dataset Detayları

| Dataset | Tip | Durum | Detay |
|---------|-----|-------|-------|
| HIFD | direct | manual_required | direct URL set but no auto-downloader implemented for hifd |
| WEDA_FALL | direct | manual_required | direct URL set but no auto-downloader implemented for weda_fall |
| BUT_PPG | physionet | failed | 404 Error: Not Found for url: https://physionet.org/content/butpvdb/ |
| SisFall | manual | manual_required | Download from http://sistemic.udea.edu.co/en/research/projects/falls/ – extract to data/raw/sisfall/ |
| UP-Fall | manual | manual_required | Download from https://sites.google.com/up.edu.mx/har-up/ – extract to data/raw/upfall/ |
| UMAFall | manual | manual_required | If auto-download failed: https://figshare.com/articles/dataset/UMAFall_Fall_Detection_Dataset/4214283 – extract to data/raw/umafall/ |
| UniMiB-SHAR | manual | manual_required | Download from http://www.sal.disco.unimib.it/technologies/unimib-shar/ – need fall_data.mat + adl_data.mat → data/raw/unimib_shar/ |
| MobiAct | request_required | request_required | Request at https://bmi.teicrete.gr/index.php/research/mobifall – form required, free for research |
| UCI-HAR | direct | downloaded | 2 files extracted |
| FallAllD | manual | manual_required | Download from https://falldataset.com/ – extract to data/raw/fallalld/ |
| BIDMC-PPG-Respiration | physionet | failed | 404 Error: Not Found for url: https://physionet.org/content/bidmc/1.0.0/1.0.0/ |
| PPG-DaLiA | manual | manual_required | Download from https://archive.ics.uci.edu/dataset/495/ppg+dalia – extract S*.pkl files to data/raw/ppg_dalia/ |
| WESAD | manual | manual_required | Download from https://archive.ics.uci.edu/dataset/465/wesad – extract S*.pkl to data/raw/wesad/ |
| WildPPG | manual | manual_required | Clone https://github.com/EPiC-Lab/WildPPG or download parquet/h5 files → data/raw/wildppg/ |

---

## Loader Validation

| Dataset | Loader OK | Kayıt Sayısı | Detay |
|---------|-----------|--------------|-------|
| HIFD | ❌ | — | no data files |
| WEDA_FALL | ❌ | — | no data files |
| BUT_PPG | ❌ | — | no data files |
| SisFall | ❌ | — | no data files |
| UP-Fall | ❌ | — | no data files |
| UMAFall | ❌ | — | no data files |
| UniMiB-SHAR | ❌ | — | no data files |
| MobiAct | ❌ | — | no data files |
| UCI-HAR | ❌ | — | loader returned status=missing, errors=['Dataset path not found: data/raw/uci_har'] |
| FallAllD | ❌ | — | no data files |
| BIDMC-PPG-Respiration | ❌ | — | no data files |
| PPG-DaLiA | ❌ | — | no data files |
| WESAD | ❌ | — | no data files |
| WildPPG | ❌ | — | no data files |

---

## Manuel İndirme Talimatları

### HIFD
- **URL:** https://github.com/kaist-avelab/HIFD
- **Talimat:** direct URL set but no auto-downloader implemented for hifd
- **Hedef klasör:** `C:\project\HealthAlert\Data\${PATHS.HIFD}`

### WEDA_FALL
- **URL:** https://github.com/weda-fall/WEDA-FALL
- **Talimat:** direct URL set but no auto-downloader implemented for weda_fall
- **Hedef klasör:** `C:\project\HealthAlert\Data\${PATHS.WEDA_FALL}`

### BUT_PPG
- **URL:** https://physionet.org/content/butpvdb/1.0.0/
- **Talimat:** 404 Error: Not Found for url: https://physionet.org/content/butpvdb/
- **Hedef klasör:** `C:\project\HealthAlert\Data\${PATHS.BUT_PPG}`

### SisFall
- **URL:** http://sistemic.udea.edu.co/en/research/projects/falls/
- **Talimat:** Download from http://sistemic.udea.edu.co/en/research/projects/falls/ – extract to data/raw/sisfall/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\sisfall`

### UP-Fall
- **URL:** https://sites.google.com/up.edu.mx/har-up/
- **Talimat:** Download from https://sites.google.com/up.edu.mx/har-up/ – extract to data/raw/upfall/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\upfall`

### UMAFall
- **URL:** https://figshare.com/articles/dataset/UMAFall_Fall_Detection_Dataset/4214283
- **Talimat:** If auto-download failed: https://figshare.com/articles/dataset/UMAFall_Fall_Detection_Dataset/4214283 – extract to data/raw/umafall/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\umafall`

### UniMiB-SHAR
- **URL:** http://www.sal.disco.unimib.it/technologies/unimib-shar/
- **Talimat:** Download from http://www.sal.disco.unimib.it/technologies/unimib-shar/ – need fall_data.mat + adl_data.mat → data/raw/unimib_shar/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\unimib_shar`

### MobiAct
- **URL:** https://bmi.teicrete.gr/index.php/research/mobifall
- **Talimat:** Request at https://bmi.teicrete.gr/index.php/research/mobifall – form required, free for research
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\mobiact`

### FallAllD
- **URL:** https://falldataset.com/
- **Talimat:** Download from https://falldataset.com/ – extract to data/raw/fallalld/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\fallalld`

### BIDMC-PPG-Respiration
- **URL:** https://physionet.org/content/bidmc/1.0.0/
- **Talimat:** 404 Error: Not Found for url: https://physionet.org/content/bidmc/1.0.0/1.0.0/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\bidmc`

### PPG-DaLiA
- **URL:** https://archive.ics.uci.edu/dataset/495/ppg+dalia
- **Talimat:** Download from https://archive.ics.uci.edu/dataset/495/ppg+dalia – extract S*.pkl files to data/raw/ppg_dalia/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\ppg_dalia`

### WESAD
- **URL:** https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detection
- **Talimat:** Download from https://archive.ics.uci.edu/dataset/465/wesad – extract S*.pkl to data/raw/wesad/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\wesad`

### WildPPG
- **URL:** https://github.com/EPiC-Lab/WildPPG
- **Talimat:** Clone https://github.com/EPiC-Lab/WildPPG or download parquet/h5 files → data/raw/wildppg/
- **Hedef klasör:** `C:\project\HealthAlert\healthalert_final_ai\data\raw\wildppg`
