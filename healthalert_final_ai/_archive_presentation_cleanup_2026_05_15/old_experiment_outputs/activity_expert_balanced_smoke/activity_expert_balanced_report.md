# Activity Expert Balanced v1 Report

## 1. Executive Summary

- Balanced training decision: **REJECT_BALANCED_MODEL**
- Sitting recall: 0.0526 (not improved)
- Lying recall: 0.0000 (not improved)
- Model accepted: NO
- PPG Quality Expert can start: NO

## 2. Data Source Confirmation

- Prepared public NPZ used: NO - SMOKE SYNTHETIC
- Live ESP32 training used: **NO**
- User-specific fine-tuning used: **NO**
- Synthetic fallback used: **YES, smoke mode only**
- Train NPZ: `outputs/windowed_dataset/activity_context/train.npz`
- Val NPZ: `outputs/windowed_dataset/activity_context/val.npz`
- Test NPZ: `outputs/windowed_dataset/activity_context/test.npz`

| Split | Used windows |
|---|---:|
| train | 1,600 |
| val | 400 |
| test | 400 |

## 3. Original vs Effective Training Distribution

| Class | Original count | Original % | Effective count | Effective % | Oversampling factor |
|---|---:|---:|---:|---:|---:|
| normal | 273 | 17.06% | 273 | 17.06% | 1.0000 |
| instability | 265 | 16.56% | 265 | 16.56% | 1.0000 |
| walking | 271 | 16.94% | 271 | 16.94% | 1.0000 |
| sitting | 283 | 17.69% | 283 | 17.69% | 1.0000 |
| standing | 239 | 14.94% | 239 | 14.94% | 1.0000 |
| lying | 269 | 16.81% | 269 | 16.81% | 1.0000 |

- ADL share before: 66.38%
- ADL share after: 66.38%

## 4. Sampler Configuration

- Target ADL ratio: 0.350
- Effective ADL ratio: 0.664
- Sampler type: WeightedRandomSampler(replacement=True)
- Effective epoch size: 1,600
- Augmentation enabled: NO
- Augmentation parameters: {'gaussian_noise_std': 0.015, 'time_shift_max_steps': 5, 'scale_jitter_range': [0.97, 1.03], 'gyro_noise_std': 0.01, 'applied_to': 'train split ADL classes only', 'forbidden': ['axis_rotation', 'label_changing_transforms', 'val_test_augmentation']}

## 5. Input Normalization

- Z-score normalization: YES
- Train split only: YES
- Stats path: `outputs/hybrid_redesign/activity_expert_balanced/imu_norm_stats.json`

| Channel | Mean | Std |
|---:|---:|---:|
| 0 | 0.000000 | 1.000000 |
| 1 | 0.000000 | 1.000000 |
| 2 | 0.000000 | 1.000000 |
| 3 | 0.000000 | 1.000000 |
| 4 | 0.000000 | 1.000000 |
| 5 | 0.000000 | 1.000000 |

## 6. Model Architecture

- Model class: ActivityExpertCNN
- Input shape: `(batch, 6, 200)`
- Output classes: normal, instability, walking, sitting, standing, lying
- Parameter count: 94,630
- Loss: CrossEntropyLoss (unweighted; virtual balanced epoch sampling)
- Optimizer: AdamW (weight_decay=1e-4)
- LR: 0.0003
- Scheduler: CosineAnnealingLR (T_max=2, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 7. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1.80100 | 1.79249 | 0.1800 | 0.05498 | 2 | NO | NO |
| 2 | 1.79615 | 1.79378 | 0.1925 | 0.11658 | 5 | YES | YES |

## 8. Final Test Metrics

- Accuracy: 0.1925
- Macro F1: 0.1081
- Weighted F1: 0.1184
- Macro precision: 0.1131
- Macro recall: 0.1701

## 9. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| normal | 0.1679 | 0.3770 | 0.2323 | 61 |
| instability | 0.2137 | 0.5747 | 0.3115 | 87 |
| walking | 0.1667 | 0.0164 | 0.0299 | 61 |
| sitting | 0.1304 | 0.0526 | 0.0750 | 57 |
| standing | 0.0000 | 0.0000 | 0.0000 | 61 |
| lying | 0.0000 | 0.0000 | 0.0000 | 73 |

## 10. ADL Improvement Analysis

| Class | v0 recall | Balanced v1 recall | Delta |
|---|---:|---:|---:|
| walking | 0.9821 | 0.0164 | -0.9657 |
| sitting | 0.4862 | 0.0526 | -0.4336 |
| standing | 0.7838 | 0.0000 | -0.7838 |
| lying | 0.6853 | 0.0000 | -0.6853 |
| ADL macro F1 | N/A | 0.0262 | N/A |

## 11. Confusion Matrix

Rows = actual, columns = predicted.

| Actual \ Pred | normal | instability | walking | sitting | standing | lying |
|---|---:|---:|---:|---:|---:|---:|
| normal | 23 | 30 | 2 | 6 | 0 | 0 |
| instability | 33 | 50 | 0 | 4 | 0 | 0 |
| walking | 24 | 32 | 1 | 4 | 0 | 0 |
| sitting | 20 | 34 | 0 | 3 | 0 | 0 |
| standing | 19 | 35 | 2 | 5 | 0 | 0 |
| lying | 18 | 53 | 1 | 1 | 0 | 0 |

- Sitting vs lying errors: 0
- Standing vs lying errors: 0
- Normal vs instability errors: normal->instability 30, instability->normal 33
- Walking errors total: 60

## 12. Prediction Distribution

| Class | True count | True % | Predicted count | Predicted % |
|---|---:|---:|---:|---:|
| normal | 66 | 16.50% | 137 | 34.25% |
| instability | 66 | 16.50% | 234 | 58.50% |
| walking | 66 | 16.50% | 6 | 1.50% |
| sitting | 66 | 16.50% | 23 | 5.75% |
| standing | 66 | 16.50% | 0 | 0.00% |
| lying | 66 | 16.50% | 0 | 0.00% |

## 13. Dataset-Source Breakdown

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| synthetic | 400 | 0.1925 | 0.1081 | normal:0.377, instability:0.575, walking:0.016, sitting:0.053, standing:0.000, lying:0.000 |

## 14. Collapse / Dominance Check

- Collapse: YES
- n_pred_cls: 4
- Dominant predicted class: instability
- Normal+instability prediction ratio: 0.9275
- ADL prediction ratio: 0.0725
- Dominant class crush detected: YES

## 15. Checkpoint Validity

- best_model.pt valid: YES
- Best epoch: 2
- Best validation macro_f1: 0.11658
- last_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/activity_expert_balanced/best_model.pt`

## 16. Comparison with Activity Expert v0

| Metric | v0 | balanced_v1 | Delta | Better/Worse |
|---|---:|---:|---:|---|
| macro_f1 | 0.7869 | 0.1081 | -0.6788 | worse |
| normal recall | 0.9729 | 0.3770 | -0.5959 | worse |
| instability recall | 0.9963 | 0.5747 | -0.4216 | worse |
| walking recall | 0.9821 | 0.0164 | -0.9657 | worse |
| sitting recall | 0.4862 | 0.0526 | -0.4336 | worse |
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