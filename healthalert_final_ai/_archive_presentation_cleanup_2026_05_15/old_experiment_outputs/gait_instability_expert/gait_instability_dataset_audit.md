# Gait Instability Dataset Audit

- Prepared public NPZ used: YES
- Live ESP32/MPU6050 training data used: NO
- Synthetic fallback used: NO
- IMU required: YES
- Unknown label 99 excluded

## NPZ Files

| Split | Exists | Used samples | Keys | IMU shape | Features shape | Labels shape |
|---|---|---:|---|---|---|---|
| train | True | 3,902 | features, labels, imu, ppg, metadata | [4456, 200, 6] | [4456, 1400] | [4456] |
| val | True | 2,408 | features, labels, imu, ppg, metadata | [2620, 200, 6] | [2620, 1400] | [2620] |
| test | True | 1,726 | features, labels, imu, ppg, metadata | [1819, 200, 6] | [1819, 1400] | [1819] |

## Label Mapping

| Raw label | Label name | Final class | Action |
|---:|---|---|---|
| 0 | normal | 0 (stable_gait) | train/evaluate |
| 3 | instability | 1 (unstable_gait) | train/evaluate |
| 10 | walking | 0 (stable_gait) | train/evaluate |
| 11 | sitting | 0 (stable_gait) | train/evaluate |
| 12 | standing | 0 (stable_gait) | train/evaluate |
| 13 | lying | 0 (stable_gait) | train/evaluate |
| 20 | good_quality | 0 (stable_gait) | train/evaluate |
| 21 | bad_quality | 0 (stable_gait) | train/evaluate |
| 99 | unknown | excluded | exclude |

## Split Counts

| Split | Total NPZ | Bad source removed | Label excluded | Missing IMU removed | Final used |
|---|---:|---:|---:|---:|---:|
| train | 4,456 | 0 | 554 | 0 | 3,902 |
| val | 2,620 | 0 | 212 | 0 | 2,408 |
| test | 1,819 | 0 | 93 | 0 | 1,726 |

## Train Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 3,902 | 100.00% |
| unstable_gait | 0 | 0.00% |

- Imbalance ratio: 1.00

## Train Source Distribution

| Source | Count |
|---|---:|
| DAPHNET_FOG | 3,902 |

## Val Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 2,408 | 100.00% |
| unstable_gait | 0 | 0.00% |

- Imbalance ratio: 1.00

## Val Source Distribution

| Source | Count |
|---|---:|
| DAPHNET_FOG | 2,408 |

## Test Class Distribution

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 1,726 | 100.00% |
| unstable_gait | 0 | 0.00% |

- Imbalance ratio: 1.00

## Test Source Distribution

| Source | Count |
|---|---:|
| DAPHNET_FOG | 1,726 |

## Leakage / Duplicate Check

- Train/val window overlap: 0
- Train/test window overlap: 0
- Val/test window overlap: 0