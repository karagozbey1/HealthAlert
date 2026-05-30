# Activity Expert Balanced v1 Report

## 1. Executive Summary

- Balanced training decision: **REJECT_BALANCED_MODEL**
- Sitting recall: 0.2385 (not improved)
- Lying recall: 0.2069 (not improved)
- Model accepted: NO
- PPG Quality Expert can start: NO

## 1A. Correct Python Environment Confirmation

- sys.executable: `C:\project\HealthAlert\.venv311\Scripts\python.exe`
- sys.version: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- torch.__version__: `2.9.1+cpu`
- working directory: `C:\project\HealthAlert\healthalert_final_ai`

## 2. Data Source Confirmation

- Prepared public NPZ used: YES
- Live ESP32 training used: **NO**
- User-specific fine-tuning used: **NO**
- Synthetic fallback used: **NO**
- Train NPZ: `outputs/windowed_dataset/activity_context/train.npz`
- Val NPZ: `outputs/windowed_dataset/activity_context/val.npz`
- Test NPZ: `outputs/windowed_dataset/activity_context/test.npz`

| Split | Used windows |
|---|---:|
| train | 110,145 |
| val | 25,695 |
| test | 45,906 |

## 3. Original vs Effective Training Distribution

| Class | Original count | Original % | Effective count | Effective % | Oversampling factor |
|---|---:|---:|---:|---:|---:|
| normal | 67,977 | 61.72% | 67,977 | 43.24% | 1.0000 |
| instability | 34,220 | 31.07% | 34,220 | 21.76% | 1.0000 |
| walking | 3,537 | 3.21% | 13,757 | 8.75% | 3.8895 |
| sitting | 1,389 | 1.26% | 13,757 | 8.75% | 9.9042 |
| standing | 1,502 | 1.36% | 13,757 | 8.75% | 9.1591 |
| lying | 1,520 | 1.38% | 13,757 | 8.75% | 9.0507 |

- ADL share before: 7.22%
- ADL share after: 35.00%

## 4. Sampler Configuration

- Target ADL ratio: 0.350
- Effective ADL ratio: 0.350
- Sampler type: WeightedRandomSampler(replacement=True)
- Effective epoch size: 157,225
- Augmentation enabled: YES
- Augmentation parameters: {'gaussian_noise_std': 0.015, 'time_shift_max_steps': 5, 'scale_jitter_range': [0.97, 1.03], 'gyro_noise_std': 0.01, 'applied_to': 'train split ADL classes only', 'forbidden': ['axis_rotation', 'label_changing_transforms', 'val_test_augmentation']}

## 5. Input Normalization

- Z-score normalization: YES
- Train split only: YES
- Stats path: `outputs/hybrid_redesign/activity_expert_balanced/imu_norm_stats.json`

| Channel | Mean | Std |
|---:|---:|---:|
| 0 | 0.076142 | 0.522054 |
| 1 | -41591.769531 | 41080668.000000 |
| 2 | -102887.156250 | 64951380.000000 |
| 3 | -0.000221 | 0.465296 |
| 4 | -0.000505 | 0.425093 |
| 5 | 0.000459 | 0.520195 |

## 6. Model Architecture

- Model class: ActivityExpertCNN
- Input shape: `(batch, 6, 200)`
- Output classes: normal, instability, walking, sitting, standing, lying
- Parameter count: 94,630
- Loss: CrossEntropyLoss (unweighted; virtual balanced epoch sampling)
- Optimizer: AdamW (weight_decay=1e-4)
- LR: 0.0003
- Scheduler: CosineAnnealingLR (T_max=50, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 7. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 0.74188 | 0.45273 | 0.8988 | 0.29632 | 3 | NO | NO |
| 2 | 0.45542 | 0.53674 | 0.8985 | 0.29556 | 2 | NO | NO |
| 3 | 0.43017 | 0.58519 | 0.8978 | 0.29617 | 2 | NO | NO |
| 4 | 0.41696 | 0.60043 | 0.8982 | 0.29665 | 4 | NO | NO |
| 5 | 0.40390 | 0.55932 | 0.8989 | 0.29668 | 4 | NO | NO |
| 6 | 0.39337 | 0.41689 | 0.9050 | 0.37758 | 4 | NO | NO |
| 7 | 0.37927 | 0.49921 | 0.8989 | 0.30035 | 3 | NO | NO |
| 8 | 0.36836 | 0.35819 | 0.9119 | 0.47079 | 5 | YES | YES |
| 9 | 0.36179 | 0.39213 | 0.9134 | 0.44109 | 5 | NO | NO |
| 10 | 0.35635 | 0.38997 | 0.9115 | 0.43342 | 6 | NO | NO |
| 11 | 0.34888 | 0.46576 | 0.8998 | 0.33290 | 5 | NO | NO |
| 12 | 0.33358 | 0.47557 | 0.8998 | 0.32508 | 4 | NO | NO |
| 13 | 0.32729 | 0.33348 | 0.9168 | 0.51013 | 6 | YES | YES |
| 14 | 0.31901 | 0.29332 | 0.9213 | 0.58035 | 6 | YES | YES |
| 15 | 0.30650 | 0.29971 | 0.9198 | 0.57123 | 6 | YES | NO |
| 16 | 0.29874 | 0.31434 | 0.9206 | 0.56751 | 6 | YES | NO |
| 17 | 0.29700 | 0.28658 | 0.9222 | 0.60949 | 6 | YES | YES |
| 18 | 0.28678 | 0.31472 | 0.9193 | 0.55925 | 6 | YES | NO |
| 19 | 0.29179 | 0.29629 | 0.9213 | 0.57430 | 6 | YES | NO |
| 20 | 0.28351 | 0.28545 | 0.9223 | 0.61466 | 6 | YES | YES |
| 21 | 0.28012 | 0.31445 | 0.9197 | 0.54640 | 6 | YES | NO |
| 22 | 0.27129 | 0.33896 | 0.9162 | 0.51921 | 6 | YES | NO |
| 23 | 0.27001 | 0.30284 | 0.9200 | 0.56613 | 6 | YES | NO |
| 24 | 0.26713 | 0.33072 | 0.9170 | 0.51448 | 6 | YES | NO |
| 25 | 0.27234 | 0.32232 | 0.9180 | 0.51452 | 6 | YES | NO |
| 26 | 0.26608 | 0.31275 | 0.9191 | 0.53554 | 6 | YES | NO |
| 27 | 0.25917 | 0.33981 | 0.9147 | 0.49244 | 6 | YES | NO |
| 28 | 0.25738 | 0.35662 | 0.9155 | 0.48919 | 5 | YES | NO |
| 29 | 0.25410 | 0.29876 | 0.9206 | 0.56250 | 6 | YES | NO |
| 30 | 0.25254 | 0.36852 | 0.9147 | 0.47936 | 5 | YES | NO |

## 8. Final Test Metrics

- Accuracy: 0.9674
- Macro F1: 0.6456
- Weighted F1: 0.9647
- Macro precision: 0.9262
- Macro recall: 0.5959

## 9. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| normal | 0.9934 | 0.9758 | 0.9845 | 38,603 |
| instability | 0.8297 | 0.9963 | 0.9054 | 6,018 |
| walking | 0.9984 | 1.0000 | 0.9992 | 613 |
| sitting | 0.8814 | 0.2385 | 0.3755 | 218 |
| standing | 0.8750 | 0.1577 | 0.2672 | 222 |
| lying | 0.9796 | 0.2069 | 0.3416 | 232 |

## 10. ADL Improvement Analysis

| Class | v0 recall | Balanced v1 recall | Delta |
|---|---:|---:|---:|
| walking | 0.9821 | 1.0000 | +0.0179 |
| sitting | 0.4862 | 0.2385 | -0.2477 |
| standing | 0.7838 | 0.1577 | -0.6261 |
| lying | 0.6853 | 0.2069 | -0.4784 |
| ADL macro F1 | N/A | 0.4959 | N/A |

## 11. Confusion Matrix

Rows = actual, columns = predicted.

| Actual \ Pred | normal | instability | walking | sitting | standing | lying |
|---|---:|---:|---:|---:|---:|---:|
| normal | 37667 | 936 | 0 | 0 | 0 | 0 |
| instability | 21 | 5996 | 1 | 0 | 0 | 0 |
| walking | 0 | 0 | 613 | 0 | 0 | 0 |
| sitting | 102 | 61 | 0 | 52 | 2 | 1 |
| standing | 7 | 176 | 0 | 4 | 35 | 0 |
| lying | 120 | 58 | 0 | 3 | 3 | 48 |

- Sitting vs lying errors: 1
- Standing vs lying errors: 0
- Normal vs instability errors: normal->instability 936, instability->normal 21
- Walking errors total: 0

## 12. Prediction Distribution

| Class | True count | True % | Predicted count | Predicted % |
|---|---:|---:|---:|---:|
| normal | 38,603 | 84.09% | 37,917 | 82.60% |
| instability | 6,018 | 13.11% | 7,227 | 15.74% |
| walking | 613 | 1.34% | 614 | 1.34% |
| sitting | 218 | 0.47% | 59 | 0.13% |
| standing | 222 | 0.48% | 40 | 0.09% |
| lying | 232 | 0.51% | 49 | 0.11% |

## 13. Dataset-Source Breakdown

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| SisFall | 6,962 | 0.8624 | 0.3142 | normal:0.009, instability:0.996 |
| UCI-HAR | 1,285 | 0.5821 | 0.3307 | walking:1.000, sitting:0.238, standing:0.158, lying:0.207 |
| UMAFall | 36,492 | 1.0000 | 1.0000 | normal:1.000 |
| UniMiB-SHAR | 1,167 | 1.0000 | 1.0000 | normal:1.000 |

## 14. Collapse / Dominance Check

- Collapse: NO
- n_pred_cls: 6
- Dominant predicted class: normal
- Normal+instability prediction ratio: 0.9834
- ADL prediction ratio: 0.0166
- Dominant class crush detected: NO

## 15. Checkpoint Validity

- best_model.pt valid: YES
- Best epoch: 20
- Best validation macro_f1: 0.61466
- last_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/best_model.pt`

## 16. Comparison with Activity Expert v0

| Metric | v0 | balanced_v1 | Delta | Better/Worse |
|---|---:|---:|---:|---|
| macro_f1 | 0.7869 | 0.6456 | -0.1413 | worse |
| normal recall | 0.9729 | 0.9758 | +0.0029 | better |
| instability recall | 0.9963 | 0.9963 | +0.0000 | better |
| walking recall | 0.9821 | 1.0000 | +0.0179 | better |
| sitting recall | 0.4862 | 0.2385 | -0.2477 | worse |
| standing recall | 0.7838 | 0.1577 | -0.6261 | worse |
| lying recall | 0.6853 | 0.2069 | -0.4784 | worse |
| confusion reduction for sitting/lying | N/A | N/A | N/A | old confusion matrix unavailable |

## 17. Final Decision

**REJECT_BALANCED_MODEL**

## 18. Recommendation

- Use balanced_v1 or v0: previous v0 for now
- Can proceed to PPG Quality Expert: NO
- Another Activity iteration needed: YES
- External dataset still not needed: YES
- Architecture split still not needed: YES

*Auto-generated by train_activity_expert_balanced.py*