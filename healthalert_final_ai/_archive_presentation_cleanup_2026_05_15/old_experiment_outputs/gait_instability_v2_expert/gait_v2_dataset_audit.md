# Gait v2 Dataset Audit

## Environment

- sys.executable: `C:\project\HealthAlert\.venv311\Scripts\python.exe`
- sys.version: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- torch.__version__: `2.9.1+cpu`
- working directory: `C:\project\HealthAlert\healthalert_final_ai`
- data_dir: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2`

## Data Source Confirmation

- Prepared public NPZ used: YES
- Synthetic fallback used: NO
- Live ESP32/MPU6050 training data used: NO
- Legacy gait_instability dataset used: NO

## NPZ Files

| Split | NPZ path | Keys | IMU shape | Model input shape | Labels shape | Unknown excluded |
|---|---|---|---|---|---|---:|
| train | `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\train.npz` | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [6258, 200, 6] | [6258, 6, 200] | [6258] | 0 |
| val | `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\val.npz` | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [1057, 200, 6] | [1057, 6, 200] | [1057] | 0 |
| test | `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\test.npz` | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [1667, 200, 6] | [1667, 6, 200] | [1667] | 0 |

## Label Mapping

| Raw label / canonical label | Final class index | Action |
|---|---|---|
| 0 / stable_movement / stable_gait | 0 | train/evaluate |
| 3 / abnormal_or_freezing_movement / unstable_gait | 1 | train/evaluate |
| other / unknown | excluded | exclude |

## Split Support

| Split | Stable count | Abnormal count | Unknown excluded | Abnormal % |
|---|---:|---:|---:|---:|
| train | 5,639 | 619 | 0 | 9.8913% |
| val | 748 | 309 | 0 | 29.2337% |
| test | 1,471 | 196 | 0 | 11.7576% |

## Subject Distribution

- Subject-aware split preserved: YES
- Train/val overlap: 0
- Train/test overlap: 0
- Val/test overlap: 0

### Train abnormal by subject

{
  "S03": 195,
  "S06": 75,
  "S07": 68,
  "S08": 117,
  "S09": 164
}

### Val abnormal by subject

{
  "S05": 309
}

### Test abnormal by subject

{
  "S01": 78,
  "S02": 118
}