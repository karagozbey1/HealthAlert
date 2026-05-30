# Activity v2 Pure ADL Detailed Report

Generated: 2026-05-15
Decision: REVIEW_ACTIVITY_V2_PURE_ADL

## 1. Executive Summary
- Objective: train a contamination-free 4-class Activity v2 expert for walking / sitting / standing / lying.
- Usable sources in this run: PAMAP2, UCI-HAR.
- Final split sizes: train=9569, val=1974, test=2732.
- Best validation macro_f1: 0.8970 at epoch 31.
- Final test macro_f1: 0.6490; acceptance threshold: 0.7000.
- Decision rationale: review required because the test macro_f1 stayed below the 0.70 target despite strong validation performance.

## 2. Scope and Label Contract
- Target labels: walking, sitting, standing, lying.
- Excluded from Activity v2: generic normal / instability / fall style labels and any dataset that collapses ADL subclasses.
- Split coverage complete: True.
- PAMAP2 integration note: PAMAP2 raw path exists and is integrated into the pure ADL builder.

## 3. Dataset Audit
| Dataset | Status | Raw Present | Records | Subjects | Pure Label Support | Feasible Now | Notes |
|---------|--------|-------------|---------|----------|--------------------|--------------|-------|
| UCI-HAR | ok | True | 10299 | 30 | {"standing": 1906, "sitting": 1777, "lying": 1944, "walking": 4672} | True | Provides all four target labels with preserved subject IDs. |
| MobiAct | partial | True | 0 | 0 | {} | False | Could provide pure ADL via activity_code metadata, but current raw data is missing in repo. |
| PAMAP2 | ok | True | 32 | 8 | {"lying": 8, "sitting": 8, "standing": 8, "walking": 8} | True | Parser recovers lying/sitting/standing/walking segments from Protocol files. |
| UniMiB-SHAR | ok | True | 11771 | 11771 | {} | False | ADL windows are collapsed to normal; subclasses are not preserved. |
| UMAFall | ok | True | 1492 | 19 | {} | False | ADL is exposed only as normal; sitting/standing/lying subclasses are absent. |
| SisFall | ok | True | 10318 | 469 | {} | False | Current repo copy is instability/normal oriented, not clean ADL context. |

## 4. Final Export Summary
| Split | Windows | Unique Subjects | Sources | Labels |
|-------|---------|-----------------|---------|--------|
| train | 9569 | 26 | {"UCI-HAR": 7590, "PAMAP2": 1979} | {"standing": 1854, "sitting": 1791, "lying": 1919, "walking": 4005} |
| val | 1974 | 5 | {"UCI-HAR": 1479, "PAMAP2": 495} | {"standing": 407, "sitting": 422, "lying": 400, "walking": 745} |
| test | 2732 | 7 | {"UCI-HAR": 1230, "PAMAP2": 1502} | {"standing": 581, "sitting": 478, "lying": 575, "walking": 1098} |

### Source Window Totals
| Source | Label Counts |
|--------|--------------|
| UCI-HAR | {"standing": 1906, "sitting": 1777, "lying": 1944, "walking": 4672} |
| PAMAP2 | {"lying": 950, "sitting": 914, "standing": 936, "walking": 1176} |

## 5. Training Setup
- Model: ActivityExpertCNN (CNN1D + GRU), parameters=94500
- Input shape: (batch, 6, 200)
- Loss: CrossEntropyLoss
- Optimizer: AdamW
- Scheduler: CosineAnnealingLR
- Class weights: {"walking": 0.75, "sitting": 1.1953, "standing": 1.1547, "lying": 1.1155}
- Normalization: z-score per channel from train split only; stats saved in imu_norm_stats.json.
- Training time: 214.8 sec

## 6. Overall Results
- Best epoch: 31
- Best validation macro_f1: 0.8970
- Validation loss at best epoch: 0.3085
- Test accuracy: 0.6951
- Test macro_f1: 0.6490
- Test weighted_f1: 0.7055

## 7. Per-Class Test Metrics
| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| walking | 0.999 | 0.857 | 0.923 | 1,098 |
| sitting | 0.393 | 0.776 | 0.521 | 478 |
| standing | 0.673 | 0.365 | 0.473 | 581 |
| lying | 0.708 | 0.652 | 0.679 | 575 |

## 8. Source-Level Test Breakdown
| Source | n | Macro F1 |
|--------|---|----------|
| PAMAP2 | 1502 | 0.5419 |
| UCI-HAR | 1230 | 0.7991 |

## 9. Prediction Distribution
| Class | Predicted Count |
|-------|-----------------|
| walking | 942 |
| sitting | 945 |
| standing | 315 |
| lying | 530 |

## 10. Test Confusion Matrix
Rows = actual, columns = predicted.

| Actual \ Pred | walking | sitting | standing | lying |
|---------------|---|---|---|---|
| walking | 941 | 6 | 9 | 142 |
| sitting | 1 | 371 | 93 | 13 |
| standing | 0 | 369 | 212 | 0 |
| lying | 0 | 199 | 1 | 375 |

## 11. Activity v0 Comparison
- v0 overall macro_f1: 0.7869
- v2 pure ADL macro_f1: 0.6490
- note: v0 was trained on contaminated mixed activity_context data, so its overall macro_f1 is not directly comparable to pure ADL v2.

| ADL Class | v0 Recall | v2 Recall | Delta |
|-----------|-----------|-----------|-------|
| walking | 0.9821 | 0.8570 | -0.1250 |
| sitting | 0.4862 | 0.7762 | +0.2899 |
| standing | 0.7838 | 0.3649 | -0.4189 |
| lying | 0.6853 | 0.6522 | -0.0332 |

## 12. Interpretation
- Strongest class by recall: walking (0.8570).
- Weakest class by recall: standing (0.3649).
- Source gap in macro_f1: 0.2572.
- UCI-HAR source macro_f1: 0.7991
- PAMAP2 source macro_f1: 0.5419
- Interpretation: current multi-source merge is not stable enough for acceptance; validation stayed high but test performance dropped because source behaviour is uneven.

## 13. Decision
- Decision: REVIEW_ACTIVITY_V2_PURE_ADL
- Acceptance threshold used here: test macro_f1 >= 0.70.
- Result: 0.6490
- MobiAct status: loader integrated, but raw CSV files are still absent from the repo.
- PAMAP2 status: raw data successfully integrated and included in this run.

## 14. Training Config
- epochs: 50
- batch_size: 256
- lr: 0.0003
- weight_decay: 0.0001
- patience: 10
- device: cpu
- seed: 42
- loss: CrossEntropyLoss
- optimizer: AdamW
- scheduler: CosineAnnealingLR
- checkpoint_metric: validation macro_f1
- dataset_dir: C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\activity_v2_pure_adl
- class_weights: {'walking': 0.75, 'sitting': 1.1953, 'standing': 1.1547, 'lying': 1.1155}

## 15. Validation Trace
| Epoch | Train Loss | Val Loss | Val Macro F1 | Checkpoint |
|-------|------------|----------|--------------|------------|
| 1 | 1.1250 | 0.8960 | 0.5943 | yes |
| 2 | 0.6111 | 0.4781 | 0.7944 | yes |
| 3 | 0.4256 | 0.4102 | 0.6888 | yes |
| 4 | 0.3770 | 0.3642 | 0.8546 | yes |
| 5 | 0.3173 | 0.3533 | 0.8528 | yes |
| 6 | 0.2981 | 0.3070 | 0.8755 | yes |
| 7 | 0.2761 | 0.3462 | 0.8640 | yes |
| 8 | 0.2495 | 0.3747 | 0.8656 | yes |
| 9 | 0.2249 | 0.3872 | 0.8340 | yes |
| 10 | 0.2197 | 0.3653 | 0.8651 | yes |
| 11 | 0.2220 | 0.3789 | 0.8577 | yes |
| 12 | 0.2272 | 0.4348 | 0.8543 | yes |
| 13 | 0.2014 | 0.3613 | 0.8864 | yes |
| 14 | 0.2411 | 0.3436 | 0.8741 | yes |
| 15 | 0.2176 | 0.3443 | 0.8719 | yes |
| 16 | 0.1945 | 0.3422 | 0.8917 | yes |
| 17 | 0.2294 | 0.3151 | 0.8940 | yes |
| 18 | 0.1959 | 0.3664 | 0.8740 | yes |
| 19 | 0.1937 | 0.3125 | 0.8871 | yes |
| 20 | 0.1925 | 0.3306 | 0.8829 | yes |
| 21 | 0.1931 | 0.3347 | 0.8789 | yes |
| 22 | 0.1822 | 0.3342 | 0.8949 | yes |
| 23 | 0.1728 | 0.3364 | 0.8769 | yes |
| 24 | 0.1748 | 0.3797 | 0.8509 | yes |
| 25 | 0.1750 | 0.3572 | 0.8778 | yes |
| 26 | 0.1724 | 0.3315 | 0.8776 | yes |
| 27 | 0.1776 | 0.3135 | 0.8947 | yes |
| 28 | 0.1696 | 0.3271 | 0.8746 | yes |
| 29 | 0.1681 | 0.3261 | 0.8833 | yes |
| 30 | 0.1706 | 0.3660 | 0.8654 | yes |
| 31 | 0.1735 | 0.3085 | 0.8970 | yes |
| 32 | 0.1689 | 0.3223 | 0.8853 | yes |
| 33 | 0.1575 | 0.3179 | 0.8878 | yes |
| 34 | 0.1650 | 0.3319 | 0.8768 | yes |
| 35 | 0.1629 | 0.3748 | 0.8668 | yes |
| 36 | 0.1625 | 0.3418 | 0.8740 | yes |
| 37 | 0.1553 | 0.3397 | 0.8733 | yes |
| 38 | 0.1600 | 0.3301 | 0.8798 | yes |
| 39 | 0.1612 | 0.3391 | 0.8772 | yes |
| 40 | 0.1579 | 0.3471 | 0.8731 | yes |
| 41 | 0.1602 | 0.3351 | 0.8769 | yes |
