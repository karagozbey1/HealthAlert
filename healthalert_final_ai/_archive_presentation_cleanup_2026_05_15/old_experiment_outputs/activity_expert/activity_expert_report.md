# Activity Context Expert — Training Report

**Generated:** 2026-05-14  
**Output dir:** `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\activity_expert`  

---

## 1. Dataset Source Summary

| Split | Total in NPZ | Removed (source) | Removed (label) | Used |
|-------|-------------|-----------------|----------------|------|
| train | 206,143 | 67,327 | 28,671 | 110,145 |
| val   | 39,126 | 11,558 | 1,873 | 25,695 |
| test  | 78,254 | 16,887 | 15,461 | 45,906 |

**Allowed sources (per routing):** uci_har, unimib_shar, umafall, mobiact, sisfall  
**Forbidden sources removed:** ppg_dalia, wildppg, and any not in allowed list  
**Labels excluded:** fall (1), near_fall (2) — must not enter activity training  

## 2. Label Mapping

| Raw label | Name | Activity class | Index |
|-----------|------|----------------|-------|
| 0 | normal | normal | 0 |
| 3 | instability | instability | 1 |
| 10 | walking | walking | 2 |
| 11 | sitting | sitting | 3 |
| 12 | standing | standing | 4 |
| 13 | lying | lying | 5 |
| 1 | fall | **EXCLUDED** | — |
| 2 | near_fall | **EXCLUDED** | — |
| 99 | unknown (WildPPG) | **EXCLUDED** (forbidden source) | — |

## 3. Train / Val / Test Counts

- **Train:** 110,145 windows
- **Val:**   25,695 windows
- **Test:**  45,906 windows

## 4. Class Distribution

### Train

| Class | Count | % |
|-------|-------|---|
| normal | 67,977 | 61.7% |
| instability | 34,220 | 31.1% |
| walking | 3,537 | 3.2% |
| lying | 1,520 | 1.4% |
| standing | 1,502 | 1.4% |
| sitting | 1,389 | 1.3% |

### Val

| Class | Count | % |
|-------|-------|---|
| normal | 18,847 | 73.3% |
| instability | 5,782 | 22.5% |
| walking | 522 | 2.0% |
| lying | 192 | 0.7% |
| standing | 182 | 0.7% |
| sitting | 170 | 0.7% |

## 5. Model Architecture

**ActivityExpertCNN** (CNN1D + GRU + FC)  
- Input: (batch, 6, 200) — 6-channel IMU, 4s windows @ 50Hz  
- CNN: Conv1D × 3 (32→64→128 channels, k=5, MaxPool×3)  
- GRU: hidden=64, 1 layer  
- FC: 64 → 6 classes  
- Output: softmax probabilities over 6 activity classes  
- Parameters: 94,630  

## 6. Training Config

| Parameter | Value |
|-----------|-------|
| epochs | 50 |
| batch_size | 256 |
| lr | 0.0003 |
| optimizer | AdamW (weight_decay=1e-4) |
| scheduler | CosineAnnealingLR (T_max=50, eta_min=1e-5) |
| loss | CrossEntropyLoss (inverse-frequency class weights) |
| early_stopping_patience | 10 |
| device | cpu |
| seed | 42 |
| num_classes | 6 |
| input_normalization | z-score per channel (mean/std from train split) |

## 7. Best Epoch

- **Best epoch:** 31  
- **Best val macro_f1:** 0.7370  
- **Val loss at best:** 0.17273  

## 8. Best macro_f1 (val)

**0.7370**

## 9. Test Accuracy

**0.9714** (97.14%)

## 10. Test macro_f1

**0.7869**

## 11. Test weighted_f1

**0.9725**

## 12. Per-Class Precision / Recall / F1

| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| normal | 0.999 | 0.973 | 0.986 | 38,603 |
| instability | 0.863 | 0.996 | 0.925 | 6,018 |
| walking | 1.000 | 0.982 | 0.991 | 613 |
| sitting | 0.429 | 0.486 | 0.456 | 218 |
| standing | 0.763 | 0.784 | 0.773 | 222 |
| lying | 0.518 | 0.685 | 0.590 | 232 |

## 13. Confusion Matrix

Rows = actual, Columns = predicted  

| | normal | instability | walking | sitting | standing | lying |
|---|---|---|---|---|---|---|
| normal | 37555 | 950 | 0 | 96 | 2 | 0 |
| instability | 21 | 5996 | 0 | 1 | 0 | 0 |
| walking | 0 | 0 | 602 | 0 | 9 | 2 |
| sitting | 0 | 0 | 0 | 106 | 14 | 98 |
| standing | 0 | 0 | 0 | 0 | 174 | 48 |
| lying | 0 | 0 | 0 | 44 | 29 | 159 |

## 14. Prediction Distribution

| Class | Predicted count |
|-------|----------------|
| normal | 37,576 |
| instability | 6,946 |
| walking | 602 |
| sitting | 247 |
| standing | 228 |
| lying | 307 |

## 15. Dataset-Source Breakdown

| Source | n | macro_f1 |
|--------|---|----------|
| UMAFall | 36,492 | 0.333 |
| SisFall | 6,962 | 0.236 |
| UCI-HAR | 1,285 | 0.734 |
| UniMiB-SHAR | 1,167 | 0.500 |

## 16. Failure Cases / Weak Classes

No classes with recall < 0.40. All classes are reasonably well-covered.

## 17. Activity Expert Acceptance

**Accepted: YES**

Acceptance criteria:
- Test macro_f1 ≥ 0.55: ✓ (0.7869)
- Test accuracy ≥ 0.60: ✓ (0.9714)
- ≥ 3 classes with recall > 0.30: ✓ (6 classes)

## 18. Proceed to PPG Quality Expert

**YES — Activity Expert accepted, PPG Quality Expert training can proceed.**

---

*Note: Activity Expert does NOT generate health alarms. It provides movement*
*context to RiskFusionEngine (e.g., high fall_prob + lying → stronger risk signal).*

---

## 19. Normal/Instability Dominance Analysis

- **normal + instability**: 102,197 windows (92.8% of train)
- **walking + sitting + standing + lying**: 7,948 windows (7.2% of train)

⚠ **SEVERE IMBALANCE**: dominant classes are 92.8% of train. ADL minority classes at high risk of being crushed. Class weights applied to compensate (see training config).

**Test prediction distribution (dominant classes):**
- normal predicted: 37,576 (81.9% of all predictions)
- instability predicted: 6,946 (15.1%)
- normal+instability total: 44,522 (97.0%)

🔴 **DOMINANT CLASS CRUSH CONFIRMED**: Model predicted normal/instability 97.0% of the time — rare ADL classes were NOT learned.

## 20. Model Collapse Detection

- Epochs with n_pred_cls=1 (single-class collapse): **0 / 41**
- First epoch predicting ≥ 2 classes: **1**

🟢 **No collapse**: Model maintained multi-class predictions throughout training.

| Epoch | n_pred_cls | checkpoint_valid | val_macro_f1 |
|-------|-----------|-----------------|--------------|
|   1 |          6 | ✓                | 0.4353 |
|   2 |          6 | ✓                | 0.4714 |
|   3 |          5 | ✓                | 0.4722 |
|   4 |          6 | ✓                | 0.5487 |
|   5 |          6 | ✓                | 0.5750 |
|   6 |          6 | ✓                | 0.5196 |
|   7 |          6 | ✓                | 0.5569 |
|   8 |          6 | ✓                | 0.4951 |
|   9 |          6 | ✓                | 0.6113 |
|  10 |          6 | ✓                | 0.5689 |
|  11 |          6 | ✓                | 0.6091 |
|  12 |          6 | ✓                | 0.4386 |
|  13 |          6 | ✓                | 0.6466 |
|  14 |          6 | ✓                | 0.6464 |
|  15 |          6 | ✓                | 0.5947 |
| ... (26 more epochs) | | | |

## 21. ADL Class Learning Assessment

*(walking / sitting / standing / lying — source: UCI-HAR only)*

| Class | Precision | Recall | F1 | Support | Status |
|-------|-----------|--------|----|---------|--------|
| walking | 1.000 | 0.982 | 0.991 | 613 | 🟢 LEARNED |
| sitting | 0.429 | 0.486 | 0.456 | 218 | 🟢 LEARNED |
| standing | 0.763 | 0.784 | 0.773 | 222 | 🟢 LEARNED |
| lying | 0.518 | 0.685 | 0.590 | 232 | 🟢 LEARNED |

🟢 **All 4 ADL classes LEARNED** (recall ≥ 0.30). Single-model approach viable.

## 22. Checkpoint Validity

- Valid checkpoints (checkpoint_valid=True): **41 / 41**
- best_model.pt saved: **YES — epoch 31**
- best_val_macro_f1: **0.7370**

✓ best_model.pt saved at epoch 31 with val_macro_f1=0.7370.

## 23. Data Source Confirmation

- **Trained on real prepared public dataset NPZ: YES**
- NPZ directory: `outputs/windowed_dataset/activity_context/`
- Keys used: `imu` (N, 200, 6) — 4s windows, 6-channel IMU, 50Hz
- `features` key (flattened N×1400): NOT used
- `ppg` key: NOT used
- Fall (label=1) and near_fall (label=2): EXCLUDED before training
- Forbidden sources (PPG-DaLiA, WildPPG): EXCLUDED via routing

✓ Real public dataset NPZ files were used. No synthetic data. No live ESP32 sensor data used (inference only, per project rules).

## 24. Split Architecture Recommendation

**Recommendation: KEEP single Activity Expert model.**

- ADL classes learned: 4/4 (recall ≥ 0.30): walking, sitting, standing, lying
- Single-model approach is viable with current architecture.
- Monitor ADL recall in production; consider split if recall degrades.

---

*This report was auto-generated by train_activity_expert.py*