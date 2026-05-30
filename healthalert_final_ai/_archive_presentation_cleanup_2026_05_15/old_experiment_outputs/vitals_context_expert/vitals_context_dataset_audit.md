# Vitals Context Dataset Audit

- Prepared public NPZ used: YES
- Live ESP32/MAX30102 training data used: NO
- Synthetic fallback used: NO
- Feature source: NPZ `features` array
- Unknown label 99: excluded
- abnormal_trend: no supervised label in current NPZ
- PPG Quality relation: training uses dataset labels/features; RiskFusion uses PPG Quality Expert inference at runtime

## NPZ Files

| Split | Exists | Used samples | Keys | Features shape | PPG shape | IMU shape | Labels shape |
|---|---|---:|---|---|---|---|---|
| train | True | 78,234 | features, labels, imu, ppg, metadata | [110884, 1400] | [110884, 200, 1] | [110884, 200, 6] | [110884] |
| val | True | 7,779 | features, labels, imu, ppg, metadata | [14577, 1400] | [14577, 200, 1] | [14577, 200, 6] | [14577] |
| test | True | 22,129 | features, labels, imu, ppg, metadata | [25252, 1400] | [25252, 200, 1] | [25252, 200, 6] | [25252] |

## Label Mapping

| Raw label | Label name | Final class | Action |
|---:|---|---|---|
| 0 | normal | 0 (rest_like) | train/evaluate |
| 11 | sitting | 0 (rest_like) | train/evaluate |
| 20 | good_quality | 0 (rest_like) | train/evaluate |
| 10 | walking | 1 (active_like) | train/evaluate |
| 21 | bad_quality | 2 (poor_signal) | train/evaluate |
| 99 | unknown | excluded | exclude |

## Split Counts

| Split | Total NPZ | Bad source removed | Label/unknown excluded | Missing vitals removed | Final used |
|---|---:|---:|---:|---:|---:|
| train | 110,884 | 21,886 | 10,764 | 0 | 78,234 |
| val | 14,577 | 3,210 | 3,588 | 0 | 7,779 |
| test | 25,252 | 3,123 | 0 | 0 | 22,129 |

## Train Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 36,291 | 46.39% |
| active_like | 41,943 | 53.61% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

## Train Source Distribution

| Source | Count |
|---|---:|
| PPG-DaLiA | 46,044 |
| WESAD | 32,190 |

- Sampling rate metadata: {'unknown': 78234}
- Duplicate window IDs: 0
- Unique subjects: 22
- Feature nonzero columns: 800
- Feature zero rows: 0
- PPG missing count: 0

## Val Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 3,128 | 40.21% |
| active_like | 4,651 | 59.79% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

## Val Source Distribution

| Source | Count |
|---|---:|
| PPG-DaLiA | 4,651 |
| WESAD | 3,128 |

- Sampling rate metadata: {'unknown': 7779}
- Duplicate window IDs: 0
- Unique subjects: 2
- Feature nonzero columns: 800
- Feature zero rows: 0
- PPG missing count: 0

## Test Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 8,097 | 36.59% |
| active_like | 14,032 | 63.41% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

## Test Source Distribution

| Source | Count |
|---|---:|
| PPG-DaLiA | 14,032 |
| WESAD | 8,097 |

- Sampling rate metadata: {'unknown': 22129}
- Duplicate window IDs: 0
- Unique subjects: 6
- Feature nonzero columns: 800
- Feature zero rows: 0
- PPG missing count: 0

## Leakage / Duplicate Check

- Train/val window overlap: 0
- Train/test window overlap: 0
- Val/test window overlap: 0

Audit JSON: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\vitals_context_expert\vitals_context_dataset_audit.json`