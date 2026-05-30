# HealthAlert — Dataset Drop-In Loader Activation Report

**Date:** 2025-07-14  
**Task:** DATASET DROP-IN LOADER ACTIVATION  
**Scope:** `healthalert_final_ai/` sub-project  
**Outcome:** ✅ 13 READY · 2 NEEDS_LOADER_UPDATE · 4 EMPTY · 0 MISSING · 40/40 tests pass · 197,584 windows built

---

## 1. Executive Summary

All path resolution bugs were fixed, 9 dataset loaders were fully implemented or rewritten, and the windowed training dataset was successfully built from **9 active datasets** yielding **197,584 windows** (train=142,028 / val=20,626 / test=34,930) with zero test failures.

---

## 2. Validation Before / After

| Dataset | Before | After | Notes |
|---|---|---|---|
| hifd | MISSING | READY | Path resolution fix |
| weda_fall | MISSING | READY | Path resolution fix |
| but_ppg | MISSING | READY | Path resolution fix |
| sisfall | READY | READY | Loader fully rewritten for actual data |
| upfall | NEEDS_LOADER_UPDATE | READY | Full loader implementation |
| umafall | UNKNOWN_FORMAT | NEEDS_LOADER_UPDATE | Zip present, unextracted — expected |
| unimib_shar | NEEDS_LOADER_UPDATE | READY | Full CSV-based loader |
| mobiact | EMPTY | EMPTY | No data downloaded — expected |
| uci_har | READY | READY | Unchanged |
| fallalld | EMPTY | EMPTY | No data downloaded — expected |
| bidmc | READY | READY | Unchanged |
| ppg_dalia | NEEDS_LOADER_UPDATE | READY | Fixed BVP/ACC rate mismatch |
| wesad | NEEDS_LOADER_UPDATE | READY | Fixed BVP/ACC rate mismatch |
| wildppg | UNKNOWN_FORMAT | NEEDS_LOADER_UPDATE | .mat files present — loader needs scipy.io.loadmat |
| bits2_geriatric_fall_hr | NEEDS_LOADER_UPDATE | READY | Full implementation with demux logic |
| daphnet_fog | NEEDS_LOADER_UPDATE | READY | Full implementation |
| pads_smartwatch_pd | EMPTY | EMPTY | No data downloaded — expected |
| hand_tremor_mpu9250 | NEEDS_LOADER_UPDATE | READY | Full implementation |
| fallalld_sensor_only | EMPTY | EMPTY | No data downloaded — expected |

**Summary:** MISSING 3→0 · NEEDS_LOADER_UPDATE 5→2 · UNKNOWN_FORMAT 2→0 · READY 8→13

---

## 3. Root Cause Analysis: MISSING Datasets

`validate_manual_dataset_layout.py` used hardcoded path substitutions:
- `${paths.hifd_dir}` → `Data/HIFD` (wrong case and base dir)
- `${paths.weda_fall_dir}` → `Data/WEDA_FALL`
- `${paths.but_ppg_dir}` → `Data/BUT_PPG`

Actual data resides at `healthalert_final_ai/data/raw/{hifd,weda_fall,but_ppg}`.

**Fix:** Updated both `datasets.yaml` `local_path` values and the validator's path resolution block.

---

## 4. Loader Implementations

### 4.1 hand_tremor_loader.py ✅ Implemented
- Reads `hand_tremor_mpu9250_dataset.csv` (27,995 rows)
- Columns: `aX,aY,aZ,gX,gY,gZ,Result` → 6-channel IMU
- Label: `Result` 0→`normal`, 1→`instability`
- Segments by contiguous label blocks
- Tasks: `tremor_context`, `movement_anomaly`

### 4.2 daphnet_fog_loader.py ✅ Implemented
- Reads 17 `.txt` files in `dataset_fog_release/dataset/`
- Space-delimited 11-column format, 64 Hz
- Ankle (cols 1-3) + upper leg (cols 4-6) → 6-channel IMU
- Label col 10: 0=skip, 1=`normal`, 2=`freeze`→`instability`
- Tasks: `gait_instability`, `movement_anomaly`, `freezing_of_gait`

### 4.3 bits2_loader.py ✅ Implemented
- 1,629 CSV files in `fall_detection_data/Dataset/{fall,adl}/userN/`
- Sensor type demultiplexed from `Unnamed: 5` column
- `acc` rows → IMU xyz; `gyro` rows → IMU xyz; `hrt` rows → heart rate
- Label from directory path: `fall/`→`fall`, `adl/`→`normal`
- Tasks: `fall_detection`, `activity_context`

### 4.4 sisfall_loader.py ✅ Rewritten
- Actual data is **movement disorder assessment** (Parkinson's/tremor), NOT standard SisFall falls
- Reads `movement/timeseries/{id}_{activity}_{side}.txt` (7-col, 100 Hz)
- Subject labels from `preprocessed/file_list.csv`: 0=Healthy→`normal`, 1/2=disorder→`instability`
- Tasks: `movement_anomaly`, `activity_context` — **NOT fall_detection**
- `datasets.yaml` config updated to reflect actual content

### 4.5 upfall_loader.py ✅ Implemented
- Single CSV "UP-Fall sensor CSV.csv" with 2-row header (47 columns)
- Skips first 2 header rows; uses wrist IMU at cols 29-34
- Tag 1-5→`fall`, 6-11→`normal`, 20=transition (skipped)
- Groups by Subject; segments by contiguous Tag value
- Tasks: `fall_detection`, `adl_detection`, `activity_context`

### 4.6 unimib_shar_loader.py ✅ Implemented
- Reads `unimib_train.csv`, `unimib_val.csv`, `unimib_test.csv`
- Columns: `ID, t, ax, ay, az, label, mag`; 151 samples/window → padded to 200
- Labels 1-9→`normal` (ADL), 10-17→`fall`
- Falls back to `.npy` arrays in `UniMiB/` sub-directory
- Tasks: `fall_detection`, `adl_detection`, `activity_context`

### 4.7 ppg_dalia_loader.py ✅ Fixed
- Loads S1-S15 `.pkl` files; wrist `BVP` at 64 Hz, `ACC` at 32 Hz
- ACC upsampled 2× by repeating to match BVP rate → 6-channel IMU (acc + zero gyro)
- Dominant activity label from `activity` array at 4 Hz
- Tasks: `ppg_quality`, `activity_context`, `vitals_context` — **NOT fall_detection**

### 4.8 wesad_loader.py ✅ Fixed
- Loads S10-S17 `.pkl` files; wrist `BVP` at 64 Hz, `ACC` at 32 Hz
- ACC upsampled 2× by repeating; EDA preserved separately
- Dominant stress label from chest label array (700 Hz): 1→`normal`, 2→`instability`, 3/4→`normal`
- Tasks: `physiology_context`, `vitals_context`, `ppg_quality` — **NOT fall_detection**

---

## 5. Datasets Requiring No Action

| Dataset | Status | Reason |
|---|---|---|
| umafall | NEEDS_LOADER_UPDATE | `.zip` files present but not extracted — manual step required |
| wildppg | NEEDS_LOADER_UPDATE | `.mat` files present; loader needs `scipy.io.loadmat` integration |
| mobiact | EMPTY | Data not yet downloaded — optional, non-blocking |
| fallalld | EMPTY | Data not yet downloaded — optional, non-blocking |
| pads_smartwatch_pd | EMPTY | Data not yet downloaded — optional, non-blocking |
| fallalld_sensor_only | EMPTY | Data not yet downloaded — optional, non-blocking |

---

## 6. Task Routing Constraints (Verified)

All loaders enforce correct task routing:

| Constraint | Status |
|---|---|
| `fall_detection` label ≠ 99 (unknown) | ✅ No loader assigns unknown to fall_detection tasks |
| PPG/vitals datasets not in fall_detection | ✅ ppg_dalia, wesad, but_ppg, bidmc exclude fall_detection |
| Parkinson/gait/tremor not in fall_detection | ✅ sisfall, daphnet_fog, hand_tremor exclude fall_detection |

---

## 7. Config Changes (datasets.yaml)

| Change | Detail |
|---|---|
| `hifd.local_path` | `${paths.hifd_dir}` → `data/raw/hifd` |
| `weda_fall.local_path` | `${paths.weda_fall_dir}` → `data/raw/weda_fall` |
| `but_ppg.local_path` | `${paths.but_ppg_dir}` → `data/raw/but_ppg` |
| `sisfall` group, tasks, label_mapping | Rewritten to match actual Parkinson's assessment data |
| `umafall.accepted_extensions` | Added `.zip` |
| `wildppg.accepted_extensions` | Added `.mat` |
| `loader_status` | Set to `active` for 8 datasets |

---

## 8. Build Results

```
Total windows:     197,584
Train split:       142,028 windows
Val split:          20,626 windows
Test split:         34,930 windows
Feature shape:     (N, 1400)  [200 samples × 7 channels]
Active datasets:   9
```

**Datasets contributing windows:**
- SisFall (movement disorder)
- UP-Fall
- UniMiB-SHAR
- UCI-HAR
- PPG-DaLiA
- WESAD
- BITS2-Geriatric-Fall-HR
- Daphnet-FoG
- Hand-Tremor-MPU9250

---

## 9. Test Results

```
40 passed in 13.27s
```

All test modules passed:
- `test_window_pipeline.py` — 4/4
- `test_dataset_hub_pipeline.py` — 26/26
- `test_manual_dataset_dropin_preparation.py` — 10/10

---

## 10. Bug Fixes

| File | Bug | Fix |
|---|---|---|
| `validate_manual_dataset_layout.py` | Wrong path substitution for hifd/weda_fall/but_ppg | Corrected string replacements + added regex fallback |
| `ppg_dalia_loader.py` | `imu_samples` silently dropped due to size mismatch check | Upsample 32 Hz ACC to 64 Hz by repetition |
| `wesad_loader.py` | Same ACC/BVP size mismatch | Same fix + correct label downsampling |
| `pads_smartwatch_pd_loader.py` | `from data.standard_schema import ...` | Fixed to `from src.data.standard_schema import ...` |
| `fallalld_sensor_loader.py` | Same wrong import | Same fix |
| Multiple loaders | Old scaffold code appended after new implementation (Python syntax error) | Truncated files to correct boundary |

---

## 11. Remaining Work (Non-Blocking)

| Item | Priority | Notes |
|---|---|---|
| Extract `umafall.zip` | Medium | Contents: accelerometer CSV files; loader scaffold ready |
| Implement `wildppg_loader.py` using `scipy.io.loadmat` | Medium | `.mat` files present |
| Download mobiact, fallalld, pads_smartwatch_pd | Low | Optional additional training data |
| Install `wfdb` package for BIDMC loader | Low | `pip install wfdb` |

---

## 12. Files Modified

| File | Change |
|---|---|
| `config/datasets.yaml` | Path fixes, sisfall rewrite, status updates, accepted_extensions |
| `scripts/validate_manual_dataset_layout.py` | Path resolution block fix |
| `src/data/loaders/hand_tremor_loader.py` | Full implementation |
| `src/data/loaders/daphnet_fog_loader.py` | Full implementation |
| `src/data/loaders/bits2_loader.py` | Full implementation with sensor demux |
| `src/data/loaders/sisfall_loader.py` | Complete rewrite for actual data format |
| `src/data/loaders/upfall_loader.py` | Full implementation for single-file format |
| `src/data/loaders/unimib_shar_loader.py` | Full implementation for CSV format |
| `src/data/loaders/ppg_dalia_loader.py` | BVP/ACC rate mismatch fix |
| `src/data/loaders/wesad_loader.py` | BVP/ACC rate mismatch fix |
| `src/data/loaders/pads_smartwatch_pd_loader.py` | Import path fix |
| `src/data/loaders/fallalld_sensor_loader.py` | Import path fix |
