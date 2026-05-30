# Gait v2.2 Precision/Recall Report

## 1. Executive Summary

- Overall decision: **KEEP_GAIT_V2_1_BASELINE**
- RiskFusion integration now: **NO**
- User approval required before any future integration: **YES**
- Best v2.2 experiment: **ft0.35_pw1.25_lr3e-04**
- Selected threshold: **0.05**
- test_macro_f1: **0.7416**
- stable_recall: **0.8601**
- abnormal_recall: **0.9119**
- abnormal_precision: **0.4073**
- application_valid: **False**

## 2. Baseline v2.1 Metrics

- experiment_id: pw2.0_lr3e-04_ft0.30
- frac_threshold: 0.3
- pos_weight: 2.0
- lr: 0.0003
- selected_threshold: 0.1
- test_macro_f1: 0.7631
- stable_recall: 0.9062
- abnormal_recall: 0.7194
- abnormal_precision: 0.5054
- TP/TN/FP/FN: 141 / 1333 / 138 / 55
- application_valid: True
- decision: ACCEPT_GAIT_V2_1_EXPERT

## 3. v2.2 Goal

- Improve abnormal/freezing precision while keeping abnormal_recall >= 0.70.
- Keep stable_recall >= 0.88 and beat baseline test_macro_f1=0.7631.
- Reduce or at least not materially worsen FP relative to baseline FP=138.

## 4. Dataset Variants

| frac_threshold | dataset_dir | report_dir | built |
|---|---|---|---|
| 0.30 | C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2_ft0.30 | C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_label_rescue_ft0.30 | YES |
| 0.35 | C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2_ft0.35 | C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_label_rescue_ft0.35 | YES |
| 0.40 | C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2_ft0.40 | C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_label_rescue_ft0.40 | YES |
| 0.45 | C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2_ft0.45 | C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_label_rescue_ft0.45 | YES |

## 5. Support Recount by Fraction Threshold

| frac_threshold | train_stable | train_abnormal | val_stable | val_abnormal | test_stable | test_abnormal | train_abnormal_pct | val_abnormal_pct | test_abnormal_pct | unknown_excluded_train | unknown_excluded_val | unknown_excluded_test |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.30 | 5688 | 570 | 766 | 291 | 1496 | 171 | 9.1083% | 27.5307% | 10.2579% | 4202 | 586 | 1188 |
| 0.35 | 5723 | 535 | 778 | 279 | 1508 | 159 | 8.5491% | 26.3955% | 9.5381% | 4202 | 586 | 1188 |
| 0.40 | 5738 | 520 | 789 | 268 | 1512 | 155 | 8.3094% | 25.3548% | 9.2981% | 4202 | 586 | 1188 |
| 0.45 | 5764 | 494 | 803 | 254 | 1521 | 146 | 7.8939% | 24.0303% | 8.7582% | 4202 | 586 | 1188 |

## 6. Ablation Grid

- frac_threshold: 0.30, 0.35, 0.40, 0.45
- pos_weight: 1.0, 1.25, 1.5, 1.75, 2.0
- lr: 3e-4, 1e-4
- checkpoint metric: validation ROC-AUC

## 7. Threshold Selection Policy

- Primary validation constraint: stable_recall >= 0.88, abnormal_recall >= 0.70, abnormal_precision >= 0.65.
- Among valid thresholds: maximize macro_f1, then abnormal_precision, then minimize FP, while keeping abnormal_recall >= 0.70.
- If no threshold satisfies precision>=0.65 and recall>=0.70 together, a secondary threshold is recorded but application_valid stays false.

## 8. Results Table

| experiment_id | frac_threshold | pos_weight | lr | best_epoch | best_val_auc | selected_threshold | test_macro_f1 | stable_recall | abnormal_recall | abnormal_precision | stable_precision | FP | FN | TP | TN | application_valid | decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| ft0.35_pw1.25_lr3e-04 | 0.35 | 1.25 | 3e-04 | 30 | 0.82416 | 0.05 | 0.7416 | 0.8601 | 0.9119 | 0.4073 | 0.9893 | 211 | 14 | 145 | 1297 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.35_pw1.0_lr1e-04 | 0.35 | 1.00 | 1e-04 | 26 | 0.74852 | 0.05 | 0.7159 | 0.8966 | 0.6667 | 0.4046 | 0.9623 | 156 | 53 | 106 | 1352 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.30_pw1.25_lr3e-04 | 0.30 | 1.25 | 3e-04 | 24 | 0.81373 | 0.05 | 0.7225 | 0.8476 | 0.8538 | 0.3904 | 0.9807 | 228 | 25 | 146 | 1268 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.40_pw2.0_lr3e-04 | 0.40 | 2.00 | 3e-04 | 30 | 0.81159 | 0.05 | 0.7300 | 0.8558 | 0.8968 | 0.3894 | 0.9878 | 218 | 16 | 139 | 1294 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.40_pw1.25_lr3e-04 | 0.40 | 1.25 | 3e-04 | 30 | 0.83141 | 0.05 | 0.7276 | 0.8565 | 0.8839 | 0.3870 | 0.9863 | 217 | 18 | 137 | 1295 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.40_pw1.75_lr3e-04 | 0.40 | 1.75 | 3e-04 | 30 | 0.81496 | 0.05 | 0.7270 | 0.8545 | 0.8903 | 0.3855 | 0.9870 | 220 | 17 | 138 | 1292 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.30_pw1.5_lr3e-04 | 0.30 | 1.50 | 3e-04 | 24 | 0.80967 | 0.05 | 0.7188 | 0.8396 | 0.8713 | 0.3830 | 0.9828 | 240 | 22 | 149 | 1256 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.35_pw1.75_lr3e-04 | 0.35 | 1.75 | 3e-04 | 30 | 0.80964 | 0.05 | 0.7245 | 0.8442 | 0.9119 | 0.3816 | 0.9891 | 235 | 14 | 145 | 1273 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.35_pw1.5_lr3e-04 | 0.35 | 1.50 | 3e-04 | 30 | 0.82301 | 0.05 | 0.7231 | 0.8428 | 0.9119 | 0.3796 | 0.9891 | 237 | 14 | 145 | 1271 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.40_pw1.5_lr3e-04 | 0.40 | 1.50 | 3e-04 | 30 | 0.82144 | 0.05 | 0.7210 | 0.8459 | 0.9032 | 0.3753 | 0.9884 | 233 | 15 | 140 | 1279 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.35_pw2.0_lr3e-04 | 0.35 | 2.00 | 3e-04 | 30 | 0.80718 | 0.05 | 0.7154 | 0.8309 | 0.9308 | 0.3672 | 0.9913 | 255 | 11 | 148 | 1253 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.30_pw2.0_lr3e-04 | 0.30 | 2.00 | 3e-04 | 24 | 0.80193 | 0.05 | 0.7003 | 0.8175 | 0.8830 | 0.3561 | 0.9839 | 273 | 20 | 151 | 1223 | false | KEEP_GAIT_V2_1_BASELINE |
| ft0.30_pw1.75_lr3e-04 | 0.30 | 1.75 | 3e-04 | 16 | 0.80832 | 0.05 | 0.6475 | 0.7614 | 0.8655 | 0.2931 | 0.9802 | 357 | 23 | 148 | 1139 | false | KEEP_GAIT_V2_1_BASELINE |

## 9. Best Experiment

- experiment_id: **ft0.35_pw1.25_lr3e-04**
- frac_threshold: 0.35
- pos_weight: 1.25
- lr: 3e-04
- selected_threshold: 0.05
- best_epoch: 30
- best_val_auc: 0.82416
- application_valid: False
- decision: KEEP_GAIT_V2_1_BASELINE

## 10. Test Metrics

- test_macro_f1: 0.7416
- test_accuracy: 0.8650
- stable_precision: 0.9893
- stable_recall: 0.8601
- stable_f1: 0.9202
- abnormal_precision: 0.4073
- abnormal_recall: 0.9119
- abnormal_f1: 0.5631
- ROC-AUC: 0.9394
- PR-AUC: 0.6119

## 11. Confusion Matrix

| Actual / Pred | stable_gait | abnormal_or_freezing_movement |
|---|---:|---:|
| stable_gait | 1297 | 211 |
| abnormal_or_freezing_movement | 14 | 145 |

## 12. Precision/Recall Tradeoff

- Baseline abnormal_precision -> v2.2 best: 0.5054 -> 0.4073
- Baseline abnormal_recall -> v2.2 best: 0.7194 -> 0.9119
- Baseline FP -> v2.2 best: 138 -> 211
- Baseline macro_f1 -> v2.2 best: 0.7631 -> 0.7416

## 13. Subject-Level Evaluation

| Subject | Samples | Stable support | Abnormal support | Stable precision | Stable recall | Abnormal precision | Abnormal recall | Macro F1 | TP | TN | FP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S01 | 956 | 898 | 58 | 0.9919 | 0.8163 | 0.2396 | 0.8966 | 0.6369 | 52 | 733 | 165 | 6 |
| S02 | 711 | 610 | 101 | 0.9860 | 0.9246 | 0.6691 | 0.9208 | 0.8647 | 93 | 564 | 46 | 8 |

## 14. Application Validity

- threshold constraints met on validation: False
- n_pred_cls: 2
- single_class_collapse: False
- application_valid: False

## 15. Final Decision

**KEEP_GAIT_V2_1_BASELINE**

## 16. RiskFusion Recommendation

- Automatic integration: NO
- User approval required before any future integration: YES
- Integration mode if later approved: low-weight auxiliary only

## 17. Files Changed

- scripts/build_gait_instability_v2_dataset.py
- scripts/run_gait_v2_2_precision_ablation.py
- C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_instability_v2_2_ablation\gait_v2_2_precision_recall_report.md

## 18. Next Step

- Keep v2.1 baseline as the accepted auxiliary gait model.
- Continue with Activity v2 work; do not auto-integrate new gait model.