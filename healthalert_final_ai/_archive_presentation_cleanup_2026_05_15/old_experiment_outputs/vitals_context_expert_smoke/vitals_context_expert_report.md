# Vitals Context Expert Report

## 1. Executive Summary

- Final decision: **REJECT_RETRAIN_REQUIRED**
- Model accepted: LIMITED/NO
- Vitals context learned: PARTIAL
- Collapse detected: NO
- RiskFusionEngine use: do not use yet
- Next step: Gait only after user review

## 2. Environment Confirmation

- sys.executable: `C:\project\HealthAlert\.venv311\Scripts\python.exe`
- sys.version: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- torch.__version__: `2.9.1+cpu`
- working directory: `C:\project\HealthAlert\healthalert_final_ai`

## 3. Data Source Confirmation

- Prepared public NPZ: YES
- Synthetic: NO
- Live ESP32/MAX30102 training used: NO
- Train NPZ: `outputs/windowed_dataset/vitals_context/train.npz`
- Val NPZ: `outputs/windowed_dataset/vitals_context/val.npz`
- Test NPZ: `outputs/windowed_dataset/vitals_context/test.npz`

| Split | Samples used | Sources |
|---|---:|---|
| train | 1,600 | synthetic |
| val | 400 | synthetic |
| test | 400 | synthetic |

## 4. NPZ Structure

| Split | Keys | Features shape | PPG shape | IMU shape | Label shape | Metadata |
|---|---|---|---|---|---|---|
| train | synthetic | [1600, 1400] | None | None | [1600] | True |
| val | synthetic | [400, 1400] | None | None | [400] | True |
| test | synthetic | [400, 1400] | None | None | [400] | True |

## 5. Label Mapping

| Raw label | Label name | Final class index | Action |
|---:|---|---|---|
| 0 | normal | 0 (rest_like) | train/evaluate |
| 11 | sitting | 0 (rest_like) | train/evaluate |
| 20 | good_quality | 0 (rest_like) | train/evaluate |
| 10 | walking | 1 (active_like) | train/evaluate |
| 21 | bad_quality | 2 (poor_signal) | train/evaluate |
| 99 | unknown | excluded | exclude |

abnormal_trend has no supervised label in this NPZ and is not learned in this run.

## 6. Class Distribution

### train

Imbalance ratio: 4.82

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 738 | 46.12% |
| active_like | 709 | 44.31% |
| poor_signal | 153 | 9.56% |
| abnormal_trend | 0 | 0.00% |

### val

Imbalance ratio: 4.67

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 173 | 43.25% |
| active_like | 187 | 46.75% |
| poor_signal | 40 | 10.00% |
| abnormal_trend | 0 | 0.00% |

### test

Imbalance ratio: 4.28

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 173 | 43.25% |
| active_like | 184 | 46.00% |
| poor_signal | 43 | 10.75% |
| abnormal_trend | 0 | 0.00% |

## 7. Source Breakdown

### train

| Source | Count |
|---|---:|
| synthetic | 1,600 |

### val

| Source | Count |
|---|---:|
| synthetic | 400 |

### test

| Source | Count |
|---|---:|
| synthetic | 400 |

## 8. Input Normalization

- Method: per-feature z-score
- Stats from train split only: YES
- Path: `outputs/hybrid_redesign/vitals_context_expert/vitals_norm_stats.json`
- Input dimension: 1400

| Feature index | Mean | Std |
|---:|---:|---:|
| 0 | 0.010526 | 0.955257 |
| 1 | -0.018120 | 1.014747 |
| 2 | -0.016122 | 1.003200 |
| 3 | 0.023337 | 0.988989 |
| 4 | 0.039300 | 0.968824 |
| 5 | -0.016762 | 1.006410 |
| 6 | -0.025735 | 0.981976 |
| 7 | -0.041792 | 0.973749 |
| 8 | 0.017138 | 0.983757 |
| 9 | 0.010484 | 1.006186 |
| 10 | -0.025175 | 0.998188 |
| 11 | 0.035534 | 0.979648 |
| 12 | 0.000977 | 0.998784 |
| 13 | -0.026710 | 1.023107 |
| 14 | -0.020740 | 1.030023 |
| 15 | 0.028348 | 0.995781 |
| 16 | -0.000225 | 0.999661 |
| 17 | -0.016264 | 0.973784 |
| 18 | -0.050503 | 1.002511 |
| 19 | -0.062050 | 0.999466 |
| ... | full 1400 feature stats saved in JSON | ... |

## 9. Model Architecture

- Model class: VitalsContextMLP
- Input shape: `(batch, 1400)`
- Output classes: rest_like, active_like, poor_signal, abnormal_trend
- Parameter count: 92,068
- Loss: CrossEntropyLoss(mild sqrt inverse class weights)
- Optimizer: AdamW(weight_decay=1e-4)
- LR: 0.0003
- Scheduler: CosineAnnealingLR(T_max=2, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 10. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1.43180 | 1.32307 | 0.4500 | 0.27553 | 3 | YES | YES |
| 2 | 1.27315 | 1.27832 | 0.4625 | 0.29625 | 3 | YES | YES |

## 11. Final Test Metrics

- Accuracy: 0.4500
- Macro F1: 0.2946
- Weighted F1: 0.3980
- Macro precision: 0.2977
- Macro recall: 0.3309

## 12. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| rest_like | 0.4286 | 0.2428 | 0.3100 | 173 |
| active_like | 0.4646 | 0.7500 | 0.5738 | 184 |
| poor_signal | 0.0000 | 0.0000 | 0.0000 | 43 |
| abnormal_trend | 0.0000 | 0.0000 | 0.0000 | 0 |

## 13. Confusion Matrix

| Actual / Pred | rest_like | active_like | poor_signal |
|---|---:|---:|---:|
| rest_like | 42 | 129 | 2 |
| active_like | 43 | 138 | 3 |
| poor_signal | 13 | 30 | 0 |

- rest_like -> active_like errors: 129
- active_like -> rest_like errors: 43
- poor_signal learned recall: 0.0000
- abnormal_trend: no supervised examples
- unknown/no_data: label 99 excluded

## 14. Prediction Distribution

| Class | Predicted count | Predicted percent |
|---|---:|---:|
| rest_like | 98 | 24.50% |
| active_like | 297 | 74.25% |
| poor_signal | 5 | 1.25% |
| abnormal_trend | 0 | 0.00% |

## 15. Source-Level Evaluation

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| synthetic | 400 | 0.4500 | 0.2946 | rest_like:0.243, active_like:0.750, poor_signal:0.000 |

## 16. Collapse / Dominance Check

- n_pred_cls: 3
- Dominant predicted class: active_like
- Dominant ratio: 0.7425
- Single-class collapse: NO
- Majority-class crush: NO

## 17. Checkpoint Validity

- best_model.pt valid: YES
- Best epoch: 2
- Best val macro_f1: 0.29625
- last_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/best_model.pt`

## 18. Risk Fusion Integration Note

- rest_like + high HR + good PPG quality + personal deviation high can raise caution/high risk through fusion.
- active_like + high HR should be less risky than rest_like high HR.
- poor_signal reduces vitals contribution.
- abnormal_trend should add caution/high-risk context in a future labeled iteration, but must not trigger critical alone.
- Runtime must respect PPG Quality Expert output: bad/missing PPG reduces or zeros vitals contribution.

## 19. Final Decision

**REJECT_RETRAIN_REQUIRED**

## 20. Recommendation

- Gait Instability Expert can start: NO
- Vitals model binary/simple context: current run is 3 supervised contexts plus unlabeled abnormal_trend.
- Label mapping issue: abnormal_trend lacks supervised examples; unknown 99 excluded.
- Extra preprocessing: future work should add true HR/RR/SpO2 handcrafted vitals features and abnormal trend labels.
- PPG Quality integration: use accepted PPG Quality Expert at runtime to gate vitals score.
- Runtime compatibility note: this checkpoint was trained with input_dim=1400 from NPZ features.