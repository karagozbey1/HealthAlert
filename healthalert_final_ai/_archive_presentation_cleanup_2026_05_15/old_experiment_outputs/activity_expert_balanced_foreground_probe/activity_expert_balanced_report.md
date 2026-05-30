# Activity Expert Balanced v1 Report

## 1. Executive Summary

- Balanced training decision: **REJECT_BALANCED_MODEL**
- Sitting recall: 0.0000 (not improved)
- Lying recall: 0.0000 (not improved)
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
- Scheduler: CosineAnnealingLR (T_max=1, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 7. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 0.74188 | 0.45273 | 0.8988 | 0.29632 | 3 | NO | NO |

## 8. Final Test Metrics

- Accuracy: 0.9499
- Macro F1: 0.3050
- Weighted F1: 0.9396
- Macro precision: 0.2881
- Macro recall: 0.3289

## 9. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| normal | 0.9982 | 0.9737 | 0.9858 | 38,603 |
| instability | 0.7301 | 0.9998 | 0.8440 | 6,018 |
| walking | 0.0000 | 0.0000 | 0.0000 | 613 |
| sitting | 0.0000 | 0.0000 | 0.0000 | 218 |
| standing | 0.0000 | 0.0000 | 0.0000 | 222 |
| lying | 0.0000 | 0.0000 | 0.0000 | 232 |

## 10. ADL Improvement Analysis

| Class | v0 recall | Balanced v1 recall | Delta |
|---|---:|---:|---:|
| walking | 0.9821 | 0.0000 | -0.9821 |
| sitting | 0.4862 | 0.0000 | -0.4862 |
| standing | 0.7838 | 0.0000 | -0.7838 |
| lying | 0.6853 | 0.0000 | -0.6853 |
| ADL macro F1 | N/A | 0.0000 | N/A |

## 11. Confusion Matrix

Rows = actual, columns = predicted.

| Actual \ Pred | normal | instability | walking | sitting | standing | lying |
|---|---:|---:|---:|---:|---:|---:|
| normal | 37589 | 1007 | 0 | 0 | 7 | 0 |
| instability | 0 | 6017 | 0 | 0 | 1 | 0 |
| walking | 1 | 612 | 0 | 0 | 0 | 0 |
| sitting | 50 | 166 | 0 | 0 | 2 | 0 |
| standing | 5 | 217 | 0 | 0 | 0 | 0 |
| lying | 10 | 222 | 0 | 0 | 0 | 0 |

- Sitting vs lying errors: 0
- Standing vs lying errors: 0
- Normal vs instability errors: normal->instability 1,007, instability->normal 0
- Walking errors total: 613

## 12. Prediction Distribution

| Class | True count | True % | Predicted count | Predicted % |
|---|---:|---:|---:|---:|
| normal | 38,603 | 84.09% | 37,655 | 82.03% |
| instability | 6,018 | 13.11% | 8,241 | 17.95% |
| walking | 613 | 1.34% | 0 | 0.00% |
| sitting | 218 | 0.47% | 0 | 0.00% |
| standing | 222 | 0.48% | 10 | 0.02% |
| lying | 232 | 0.51% | 0 | 0.00% |

## 13. Dataset-Source Breakdown

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| SisFall | 6,962 | 0.8650 | 0.3128 | normal:0.005, instability:1.000 |
| UCI-HAR | 1,285 | 0.0000 | 0.0000 | walking:0.000, sitting:0.000, standing:0.000, lying:0.000 |
| UMAFall | 36,492 | 0.9980 | 0.3330 | normal:0.998 |
| UniMiB-SHAR | 1,167 | 0.9974 | 0.4994 | normal:0.997 |

## 14. Collapse / Dominance Check

- Collapse: YES
- n_pred_cls: 3
- Dominant predicted class: normal
- Normal+instability prediction ratio: 0.9998
- ADL prediction ratio: 0.0002
- Dominant class crush detected: YES

## 15. Checkpoint Validity

- best_model.pt valid: NO
- Best epoch: 0
- Best validation macro_f1: -1.00000
- last_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/best_model.pt`

## 16. Comparison with Activity Expert v0

| Metric | v0 | balanced_v1 | Delta | Better/Worse |
|---|---:|---:|---:|---|
| macro_f1 | 0.7869 | 0.3050 | -0.4819 | worse |
| normal recall | 0.9729 | 0.9737 | +0.0008 | better |
| instability recall | 0.9963 | 0.9998 | +0.0035 | better |
| walking recall | 0.9821 | 0.0000 | -0.9821 | worse |
| sitting recall | 0.4862 | 0.0000 | -0.4862 | worse |
| standing recall | 0.7838 | 0.0000 | -0.7838 | worse |
| lying recall | 0.6853 | 0.0000 | -0.6853 | worse |
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