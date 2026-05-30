# Gait Instability Expert Report

## 1. Executive Summary

- Final decision: **REJECT_GAIT_INSTABILITY_EXPERT**
- Model accepted: LIMITED/NO
- Gait instability learned: NO - unstable class has zero support
- Collapse detected: YES
- RiskFusionEngine use: do not use

## 2. Environment Confirmation

- sys.executable: `C:\project\HealthAlert\.venv311\Scripts\python.exe`
- sys.version: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- torch.__version__: `2.9.1+cpu`
- working directory: `C:\project\HealthAlert\healthalert_final_ai`

## 3. Data Source Confirmation

- Prepared public NPZ: YES
- Synthetic: NO
- Live ESP32/MPU6050 training used: NO
- Train NPZ: `outputs/windowed_dataset/gait_instability/train.npz`
- Val NPZ: `outputs/windowed_dataset/gait_instability/val.npz`
- Test NPZ: `outputs/windowed_dataset/gait_instability/test.npz`

| Split | Samples used | Sources |
|---|---:|---|
| train | 3,902 | DAPHNET_FOG |
| val | 2,408 | DAPHNET_FOG |
| test | 1,726 | DAPHNET_FOG |

## 4. NPZ Structure

| Split | Keys | IMU shape | Features shape | Metadata | Label shape |
|---|---|---|---|---|---|
| train | features, labels, imu, ppg, metadata | [4456, 200, 6] | [4456, 1400] | True | [4456] |
| val | features, labels, imu, ppg, metadata | [2620, 200, 6] | [2620, 1400] | True | [2620] |
| test | features, labels, imu, ppg, metadata | [1819, 200, 6] | [1819, 1400] | True | [1819] |

## 5. Label Mapping

| Raw label | Label name | Final class index | Action |
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

## 6. Class Distribution

### train

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 3,902 | 100.00% |
| unstable_gait | 0 | 0.00% |

### val

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 2,408 | 100.00% |
| unstable_gait | 0 | 0.00% |

### test

| Class | Count | Percent |
|---|---:|---:|
| stable_gait | 1,726 | 100.00% |
| unstable_gait | 0 | 0.00% |

## 7. Source Breakdown

### train

| Source | Count | Label support |
|---|---:|---|
| DAPHNET_FOG | 3,902 | see audit JSON |

### val

| Source | Count | Label support |
|---|---:|---|
| DAPHNET_FOG | 2,408 | see audit JSON |

### test

| Source | Count | Label support |
|---|---:|---|
| DAPHNET_FOG | 1,726 | see audit JSON |

## 8. Input Normalization

- Method: per-channel z-score
- Train stats only: YES
- Path: `outputs/hybrid_redesign/gait_instability_expert/imu_norm_stats.json`

| Channel | Mean | Std |
|---:|---:|---:|
| 0 | -38.346657 | 447.919861 |
| 1 | 998.885681 | 295.395264 |
| 2 | 256.948883 | 277.416718 |
| 3 | -48.153091 | 593.842651 |
| 4 | 735.049255 | 387.391571 |
| 5 | 125.671204 | 261.875671 |

## 9. Model Architecture

- Model class: GaitInstabilityExpertCNN
- Input shape: `(batch, 6, 200)`
- Output classes: stable_gait, unstable_gait
- Parameter count: 94,305
- Loss: BCEWithLogitsLoss(pos_weight=3.0000)
- Optimizer: AdamW(weight_decay=1e-4)
- LR: 0.0003
- Scheduler: CosineAnnealingLR(T_max=50, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 10. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 0.57234 | 0.55105 | 1.0000 | 0.50000 | 1 | NO | NO |
| 2 | 0.28558 | 0.20791 | 1.0000 | 0.50000 | 1 | NO | NO |
| 3 | 0.09855 | 0.05670 | 1.0000 | 0.50000 | 1 | NO | NO |
| 4 | 0.03458 | 0.01979 | 1.0000 | 0.50000 | 1 | NO | NO |
| 5 | 0.01664 | 0.01057 | 1.0000 | 0.50000 | 1 | NO | NO |
| 6 | 0.01008 | 0.00698 | 1.0000 | 0.50000 | 1 | NO | NO |
| 7 | 0.00746 | 0.00512 | 1.0000 | 0.50000 | 1 | NO | NO |
| 8 | 0.00573 | 0.00399 | 1.0000 | 0.50000 | 1 | NO | NO |
| 9 | 0.00456 | 0.00320 | 1.0000 | 0.50000 | 1 | NO | NO |
| 10 | 0.00380 | 0.00266 | 1.0000 | 0.50000 | 1 | NO | NO |

## 11. Final Test Metrics

- Accuracy: 1.0000
- Macro F1: 0.5000
- Weighted F1: 1.0000
- Macro precision: 0.5000
- Macro recall: 0.5000

## 12. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| stable_gait | 1.0000 | 1.0000 | 1.0000 | 1,726 |
| unstable_gait | 0.0000 | 0.0000 | 0.0000 | 0 |

## 13. Confusion Matrix

| Actual / Pred | stable_gait | unstable_gait |
|---|---:|---:|
| stable_gait | 1726 | 0 |
| unstable_gait | 0 | 0 |

- unstable -> stable errors: 0
- stable -> unstable errors: 0

## 14. Prediction Distribution

| Class | Predicted count | Predicted percent |
|---|---:|---:|
| stable_gait | 1,726 | 100.00% |
| unstable_gait | 0 | 0.00% |

## 15. Source-Level Evaluation

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| DAPHNET_FOG | 1,726 | 1.0000 | 0.5000 | stable_gait:1.000 |

## 16. Collapse / Dominance Check

- n_pred_cls: 1
- Dominant predicted class: stable_gait
- Dominant ratio: 1.0000
- Single-class collapse: YES
- Majority-class crush: YES

## 17. Checkpoint Validity

- best_model.pt valid: NO
- application_valid: false
- Best epoch: 0
- Best val macro_f1: N/A
- last_model.pt path: `outputs/hybrid_redesign/gait_instability_expert/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/gait_instability_expert/best_model.pt`

## 18. Risk Fusion Integration Note

- high gait_instability_score + medium fall_probability should increase risk.
- high gait_instability_score alone should not trigger critical.
- stable gait + low fall_probability should reduce risk pressure.
- gait score should be used with temporal smoothing.

## 19. Final Decision

**REJECT_GAIT_INSTABILITY_EXPERT**

## 20. Recommendation

- RiskFusion integration now: NO
- Gait model usable: LIMITED/NO
- Preprocessing need: add unstable-labeled gait windows if currently absent.
- Dataset/source issue: current split may not include instability labels.
