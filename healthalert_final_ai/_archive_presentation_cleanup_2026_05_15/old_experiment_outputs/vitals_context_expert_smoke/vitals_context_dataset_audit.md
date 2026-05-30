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
| train | False | 1,600 | synthetic | [1600, 1400] | None | None | [1600] |
| val | False | 400 | synthetic | [400, 1400] | None | None | [400] |
| test | False | 400 | synthetic | [400, 1400] | None | None | [400] |

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
| train | 1,600 | 0 | 0 | 0 | 1,600 |
| val | 400 | 0 | 0 | 0 | 400 |
| test | 400 | 0 | 0 | 0 | 400 |

## Train Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 738 | 46.12% |
| active_like | 709 | 44.31% |
| poor_signal | 153 | 9.56% |
| abnormal_trend | 0 | 0.00% |

## Train Source Distribution

| Source | Count |
|---|---:|
| synthetic | 1,600 |

- Sampling rate metadata: {}
- Duplicate window IDs: 0
- Unique subjects: 0
- Feature nonzero columns: 1400
- Feature zero rows: 0
- PPG missing count: 0

## Val Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 173 | 43.25% |
| active_like | 187 | 46.75% |
| poor_signal | 40 | 10.00% |
| abnormal_trend | 0 | 0.00% |

## Val Source Distribution

| Source | Count |
|---|---:|
| synthetic | 400 |

- Sampling rate metadata: {}
- Duplicate window IDs: 0
- Unique subjects: 0
- Feature nonzero columns: 1400
- Feature zero rows: 0
- PPG missing count: 0

## Test Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 173 | 43.25% |
| active_like | 184 | 46.00% |
| poor_signal | 43 | 10.75% |
| abnormal_trend | 0 | 0.00% |

## Test Source Distribution

| Source | Count |
|---|---:|
| synthetic | 400 |

- Sampling rate metadata: {}
- Duplicate window IDs: 0
- Unique subjects: 0
- Feature nonzero columns: 1400
- Feature zero rows: 0
- PPG missing count: 0

## Leakage / Duplicate Check

- Train/val window overlap: 0
- Train/test window overlap: 0
- Val/test window overlap: 0

Audit JSON: `outputs\hybrid_redesign\vitals_context_expert_smoke\vitals_context_dataset_audit.json`