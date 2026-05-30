# Gait Instability v2.2 Tuning Objective (May 2026)

## Baseline v2.1 Metrics
- experiment_id: pw2.0_lr3e-04_ft0.30
- test_macro_f1: 0.7631
- stable_recall: 0.9062
- abnormal_recall: 0.7194
- abnormal_precision: 0.5054
- TP: 141
- TN: 1333
- FP: 138
- FN: 55
- application_valid: true
- decision: ACCEPT_GAIT_V2_1_EXPERT (low-weight auxiliary only)

## v2.2 Hedefi
- Abnormal/freezing precision’ı ciddi artırmak
- False positive sayısını azaltmak
- Abnormal recall 0.70 altına düşmemeli

### Minimum Kabul Kriterleri
- test_macro_f1 > 0.7631
- stable_recall ≥ 0.88
- abnormal_recall ≥ 0.70
- abnormal_precision ≥ 0.65
- n_pred_cls = 2
- Single-class collapse yok
- application_valid = true

### Güçlü Kabul Kriterleri
- test_macro_f1 ≥ 0.80
- stable_recall ≥ 0.90
- abnormal_recall ≥ 0.70
- abnormal_precision ≥ 0.70
- FP baseline’dan düşük olmalı
- FN çok artmamalı

### Threshold Seçim Stratejisi
- Threshold, validation set üzerinde seçilecek.
- Önce constraint:
  - stable_recall ≥ 0.88
  - abnormal_recall ≥ 0.70
  - abnormal_precision ≥ 0.65
- Bu constraint’i sağlayan thresholdlar içinde:
  1. macro_f1 maksimum
  2. abnormal_precision maksimum
  3. FP minimum
  4. abnormal_recall 0.70 altına düşmesin
- Eğer abnormal_precision ≥ 0.65 ve abnormal_recall ≥ 0.70 birlikte sağlanamazsa:
  - application_valid = false
  - v2.1 baseline korunur
  - RiskFusion entegrasyonu v2.1 düşük ağırlıklı auxiliary olarak kalır
  - Yeni model kullanılmaz

### Deney Aralığı
- abnormal_fraction_threshold: 0.30, 0.35, 0.40, 0.45
- pos_weight: 1.0, 1.25, 1.5, 1.75, 2.0
- learning_rate: 3e-4, 1e-4
- checkpoint selection: validation ROC-AUC primary, threshold-dependent macro_f1 checkpoint seçimi
- threshold sweep: 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70

### Raporlama (outputs/hybrid_redesign/gait_instability_v2_2_ablation/gait_v2_2_precision_recall_report.md)
- Baseline v2.1 metrikleri
- Tüm deney tablosu
- Best v2.2 experiment
- Seçilen threshold
- test macro_f1, stable recall, abnormal recall, abnormal precision, stable precision
- FP/FN/TP/TN
- Prediction distribution
- Subject-level breakdown
- application_valid true/false
- Final decision:
  A) ACCEPT_GAIT_V2_2_EXPERT
  B) KEEP_GAIT_V2_1_BASELINE
  C) REJECT_GAIT_ML_KEEP_RULE_BASED

**Not:**
Yeni model sadece baseline’dan net daha iyiyse kabul edilecek.
Abnormal precision 0.65 altındaysa veya abnormal recall 0.70 altına düşerse v2.2 kabul edilmeyecek.
RiskFusion entegrasyonu otomatik yapılmayacak.

---

# Gait Instability v2 Expert Report

## 1. Executive Summary

- Final decision: **PARTIAL_ACCEPT_LIMITED_USE**
- application_valid: **False**
- Gait abnormal/freezing learned: YES
- Collapse detected: NO
- RiskFusion integration ready: NO

## 2. Environment Confirmation

- sys.executable: `C:\project\HealthAlert\.venv311\Scripts\python.exe`
- sys.version: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- torch.__version__: `2.9.1+cpu`
- working directory: `C:\project\HealthAlert\healthalert_final_ai`
- data_dir: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2`

## 3. Data Source Confirmation

- Prepared public NPZ: YES
- Synthetic: NO
- Live ESP32/MPU6050 training used: NO
- Legacy gait_instability dataset used: NO
- Train NPZ: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\train.npz`
- Val NPZ: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\val.npz`
- Test NPZ: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2\test.npz`

| Split | Samples used | Sources |
|---|---:|---|
| train | 6,258 | DAPHNET_FOG |
| val | 1,057 | DAPHNET_FOG |
| test | 1,667 | DAPHNET_FOG |

## 4. Dataset Audit

| Split | Keys | IMU shape | Label shape | Metadata | Unknown excluded | abnormal_fraction field |
|---|---|---|---|---|---:|---|
| train | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [6258, 200, 6] | [6258] | True | 0 | True |
| val | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [1057, 200, 6] | [1057] | True | 0 | True |
| test | features, imu, labels, metadata, ppg, recording_id, source, subject_id | [1667, 200, 6] | [1667] | True | 0 | True |

## 5. Label Mapping

| Raw/canonical label | Final class index | Action |
|---|---|---|
| 0 / stable_movement / stable_gait | 0 | train/evaluate |
| 3 / abnormal_or_freezing_movement / unstable_gait | 1 | train/evaluate |
| other / unknown | excluded | exclude |

## 6. Class Distribution

| Split | stable count | abnormal/freezing count | unknown excluded | abnormal % |
|---|---:|---:|---:|---:|
| train | 5,639 | 619 | 0 | 9.8913% |
| val | 748 | 309 | 0 | 29.2337% |
| test | 1,471 | 196 | 0 | 11.7576% |

## 7. Subject/Recording Breakdown

- Subject-aware split preserved: YES
- Train/val overlap: 0
- Train/test overlap: 0
- Val/test overlap: 0

- Train abnormal by subject: {"S03": 195, "S06": 75, "S07": 68, "S08": 117, "S09": 164}
- Val abnormal by subject: {"S05": 309}
- Test abnormal by subject: {"S01": 78, "S02": 118}

## 8. Input Normalization

- Method: per-channel z-score
- Train stats only: YES
- imu_norm_stats path: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_instability_v2_expert\imu_norm_stats.json`

| Channel | Mean | Std |
|---:|---:|---:|
| 0 | -60.051781 | 534.134583 |
| 1 | 999.613953 | 333.938080 |
| 2 | 218.349243 | 302.453186 |
| 3 | -90.283012 | 551.608826 |
| 4 | 724.920288 | 377.866760 |
| 5 | 143.691864 | 279.927490 |

## 9. Model Architecture

- Model class: `GaitInstabilityExpertCNN`
- Input shape: `(batch, 6, 200)`
- Output classes: stable_gait, abnormal_or_freezing_movement
- Parameter count: 94,305
- Loss: `BCEWithLogitsLoss`
- pos_weight: `5.0000`
- pos_weight_cap: `5.00`
- Optimizer: `AdamW(weight_decay=1e-4)`
- lr: `0.0003`
- Scheduler: `CosineAnnealingLR(T_max=50, eta_min=1e-5)`
- Checkpoint metric: validation macro_f1

## 10. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | stable recall | abnormal recall | n_pred_cls | checkpoint_valid | best saved |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 0.89516 | 1.88391 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 2 | 0.69557 | 2.59094 | 0.6074 | 0.39940 | 0.8449 | 0.0324 | 2 | YES | YES |
| 3 | 0.56810 | 4.94015 | 0.7067 | 0.41719 | 0.9973 | 0.0032 | 2 | NO | NO |
| 4 | 0.49785 | 6.32399 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 5 | 0.45226 | 6.83826 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 6 | 0.39954 | 6.43477 | 0.7152 | 0.44149 | 1.0000 | 0.0259 | 2 | NO | NO |
| 7 | 0.39030 | 6.72043 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 8 | 0.39261 | 7.00202 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 9 | 0.37365 | 6.67174 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 10 | 0.34564 | 7.05962 | 0.7077 | 0.41440 | 1.0000 | 0.0000 | 1 | NO | NO |
| 11 | 0.35319 | 7.04347 | 0.7124 | 0.43445 | 0.9987 | 0.0194 | 2 | NO | NO |
| 12 | 0.32751 | 6.87034 | 0.7181 | 0.45412 | 0.9987 | 0.0388 | 2 | NO | NO |

## 11. Final Test Metrics

- Threshold used for final test metrics: `0.20`
- Accuracy: 0.4373
- Macro F1: 0.4087
- Weighted F1: 0.5082
- Macro precision: 0.5687
- Macro recall: 0.6480
- ROC-AUC: 0.7040
- PR-AUC: 0.2112

## 12. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| stable_gait | 0.9734 | 0.3725 | 0.5388 | 1,471 |
| abnormal_or_freezing_movement | 0.1639 | 0.9235 | 0.2785 | 196 |

## 13. Confusion Matrix

| Actual / Pred | stable_gait | abnormal_or_freezing_movement |
|---|---:|---:|
| stable_gait | 548 | 923 |
| abnormal_or_freezing_movement | 15 | 181 |

- abnormal -> stable false negatives: 15
- stable -> abnormal false positives: 923

## 14. Prediction Distribution

| Class | Predicted count | Predicted % | True count | True % |
|---|---:|---:|---:|---:|
| stable_gait | 563 | 33.77% | 1,471 | 88.24% |
| abnormal_or_freezing_movement | 1,104 | 66.23% | 196 | 11.76% |

## 15. Threshold Analysis

- Threshold recommendation is selected on validation sweep, not test.
- application_score = 100 * (0.45 * macro_f1 + 0.35 * abnormal_recall + 0.20 * stable_recall)

| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN | application_score |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 0.4318 | 0.7832 | 0.3628 | 0.5318 | 425 | 67 | 59.98 |
| 0.30 | 0.6791 | 0.4628 | 0.3734 | 0.5639 | 240 | 166 | 55.16 |
| 0.40 | 0.7807 | 0.1424 | 0.2115 | 0.4508 | 164 | 265 | 40.88 |
| 0.50 | 0.8449 | 0.0324 | 0.0794 | 0.3994 | 116 | 299 | 36.00 |
| 0.60 | 0.9973 | 0.0000 | 0.0000 | 0.4138 | 2 | 309 | 38.57 |
| 0.70 | 1.0000 | 0.0000 | 0.0000 | 0.4144 | 0 | 309 | 38.65 |

- Recommended threshold: **0.20**

## 16. Source/Subject Evaluation

### Source-level

| Source | Samples | Accuracy | Macro F1 | stable recall | abnormal recall |
|---|---:|---:|---:|---:|---:|
| DAPHNET_FOG | 1,667 | 0.4373 | 0.4087 | 0.3725 | 0.9235 |

### Subject-level (test)

| Subject | Samples | Stable support | Abnormal support | Macro F1 | stable recall | abnormal recall |
|---|---:|---:|---:|---:|---:|---:|
| S01 | 956 | 878 | 78 | 0.3592 | 0.3656 | 0.8462 |
| S02 | 711 | 593 | 118 | 0.4678 | 0.3828 | 0.9746 |

## 17. Collapse / Dominance Check

- n_pred_cls: 2
- Dominant predicted class: abnormal_or_freezing_movement
- Dominant ratio: 0.6623
- Single-class collapse: NO
- Majority-class crush: NO

## 18. Checkpoint Validity

- best_model.pt valid: YES
- application_valid: NO
- best epoch: 2
- best val macro_f1: 0.39940
- best_model.pt path: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_instability_v2_expert\best_model.pt`
- last_model.pt path: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_instability_v2_expert\last_model.pt`

## 19. RiskFusion Integration Note

- Model remains disabled at runtime.
- Rule-based gait handling should continue.
- Do not connect this checkpoint to RiskFusionEngine yet.

## 20. Final Decision

**PARTIAL_ACCEPT_LIMITED_USE**

## 21. Recommendation

- RiskFusionEngine connection now: NO
- Recommended threshold: 0.20
- pos_weight tuning needed: likely worth another pass after review
- DAPHNET single-source risk should still be acknowledged.
- Activity v2 can proceed independently; no need to block it on gait unless another gait iteration is explicitly desired.