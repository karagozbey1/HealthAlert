# Vitals Context Expert Report

## 1. Executive Summary

- Final decision: **REJECT_VITALS_CONTEXT_EXPERT**
- Model accepted: NO
- Vitals context learned: NO - only rest/active source-correlated separation is present
- Collapse detected: NO
- RiskFusionEngine use: DO NOT CONNECT THIS CHECKPOINT
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
| train | 78,234 | PPG-DaLiA, WESAD |
| val | 7,779 | PPG-DaLiA, WESAD |
| test | 22,129 | PPG-DaLiA, WESAD |

## 4. NPZ Structure

| Split | Keys | Features shape | PPG shape | IMU shape | Label shape | Metadata |
|---|---|---|---|---|---|---|
| train | features, labels, imu, ppg, metadata | [110884, 1400] | [110884, 200, 1] | [110884, 200, 6] | [110884] | True |
| val | features, labels, imu, ppg, metadata | [14577, 1400] | [14577, 200, 1] | [14577, 200, 6] | [14577] | True |
| test | features, labels, imu, ppg, metadata | [25252, 1400] | [25252, 200, 1] | [25252, 200, 6] | [25252] | True |

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

Imbalance ratio: 1.16

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 36,291 | 46.39% |
| active_like | 41,943 | 53.61% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

### val

Imbalance ratio: 1.49

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 3,128 | 40.21% |
| active_like | 4,651 | 59.79% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

### test

Imbalance ratio: 1.73

| Class | Count | Percent |
|---|---:|---:|
| rest_like | 8,097 | 36.59% |
| active_like | 14,032 | 63.41% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

## 7. Source Breakdown

### train

| Source | Count |
|---|---:|
| PPG-DaLiA | 46,044 |
| WESAD | 32,190 |

### val

| Source | Count |
|---|---:|
| PPG-DaLiA | 4,651 |
| WESAD | 3,128 |

### test

| Source | Count |
|---|---:|
| PPG-DaLiA | 14,032 |
| WESAD | 8,097 |

## 8. Input Normalization

- Method: per-feature z-score
- Stats from train split only: YES
- Path: `outputs/hybrid_redesign/vitals_context_expert/vitals_norm_stats.json`
- Input dimension: 1400

| Feature index | Mean | Std |
|---:|---:|---:|
| 0 | -0.271753 | 28.686604 |
| 1 | -0.618113 | 18.747211 |
| 2 | 7.775841 | 21.297144 |
| 3 | 0.000000 | 0.000001 |
| 4 | 0.000000 | 0.000001 |
| 5 | 0.000000 | 0.000001 |
| 6 | -0.273892 | 28.660057 |
| 7 | -0.617497 | 18.725477 |
| 8 | 7.774989 | 21.259644 |
| 9 | 0.000000 | 0.000001 |
| 10 | 0.000000 | 0.000001 |
| 11 | 0.000000 | 0.000001 |
| 12 | -0.279360 | 28.676546 |
| 13 | -0.615922 | 18.720161 |
| 14 | 7.772864 | 21.257727 |
| 15 | 0.000000 | 0.000001 |
| 16 | 0.000000 | 0.000001 |
| 17 | 0.000000 | 0.000001 |
| 18 | -0.270787 | 28.674208 |
| 19 | -0.613287 | 18.717417 |
| ... | full 1400 feature stats saved in JSON | ... |

## 9. Model Architecture

- Model class: VitalsContextMLP
- Input shape: `(batch, 1400)`
- Output classes: rest_like, active_like, poor_signal, abnormal_trend
- Parameter count: 92,068
- Loss: CrossEntropyLoss(mild sqrt inverse class weights)
- Optimizer: AdamW(weight_decay=1e-4)
- LR: 0.0003
- Scheduler: CosineAnnealingLR(T_max=50, eta_min=1e-5)
- Checkpoint metric: validation macro_f1

## 10. Training Dynamics

| Epoch | Train loss | Val loss | Val accuracy | Val macro_f1 | n_pred_cls | Checkpoint valid | Best saved |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 0.33046 | 0.05371 | 1.0000 | 0.66667 | 2 | YES | YES |
| 2 | 0.18040 | 0.03177 | 1.0000 | 0.66667 | 2 | YES | NO |
| 3 | 0.16309 | 0.02404 | 1.0000 | 0.66667 | 2 | YES | NO |
| 4 | 0.15629 | 0.02154 | 1.0000 | 0.66667 | 2 | YES | NO |
| 5 | 0.15321 | 0.01776 | 1.0000 | 0.66667 | 2 | YES | NO |
| 6 | 0.15072 | 0.02243 | 1.0000 | 0.66667 | 2 | YES | NO |
| 7 | 0.14879 | 0.01746 | 1.0000 | 0.66667 | 2 | YES | NO |
| 8 | 0.14749 | 0.02482 | 1.0000 | 0.66667 | 2 | YES | NO |
| 9 | 0.14658 | 0.02259 | 1.0000 | 0.66667 | 2 | YES | NO |
| 10 | 0.14504 | 0.02062 | 1.0000 | 0.66667 | 2 | YES | NO |
| 11 | 0.14507 | 0.01923 | 1.0000 | 0.66667 | 2 | YES | NO |

## 11. Final Test Metrics

- Accuracy: 1.0000
- Macro F1: 0.6666
- Weighted F1: 1.0000
- Macro precision: 0.6666
- Macro recall: 0.6666

## 12. Per-Class Metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| rest_like | 1.0000 | 0.9999 | 0.9999 | 8,097 |
| active_like | 0.9999 | 1.0000 | 1.0000 | 14,032 |
| poor_signal | 0.0000 | 0.0000 | 0.0000 | 0 |
| abnormal_trend | 0.0000 | 0.0000 | 0.0000 | 0 |

## 13. Confusion Matrix

| Actual / Pred | rest_like | active_like | poor_signal |
|---|---:|---:|---:|
| rest_like | 8096 | 1 | 0 |
| active_like | 0 | 14032 | 0 |
| poor_signal | 0 | 0 | 0 |

- rest_like -> active_like errors: 1
- active_like -> rest_like errors: 0
- poor_signal learned recall: 0.0000
- abnormal_trend: no supervised examples
- unknown/no_data: label 99 excluded

## 14. Prediction Distribution

| Class | Predicted count | Predicted percent |
|---|---:|---:|
| rest_like | 8,096 | 36.59% |
| active_like | 14,033 | 63.41% |
| poor_signal | 0 | 0.00% |
| abnormal_trend | 0 | 0.00% |

## 15. Source-Level Evaluation

| Source | Samples | Accuracy | Macro F1 | Available class recall |
|---|---:|---:|---:|---|
| PPG-DaLiA | 14,032 | 1.0000 | 0.3333 | active_like:1.000 |
| WESAD | 8,097 | 0.9999 | 0.3333 | rest_like:1.000 |

## 16. Collapse / Dominance Check

- n_pred_cls: 2
- Dominant predicted class: active_like
- Dominant ratio: 0.6341
- Single-class collapse: NO
- Majority-class crush: NO

## 17. Checkpoint Validity

- best_model.pt valid: YES
- Best epoch: 1
- Best val macro_f1: 0.66667
- last_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/last_model.pt`
- best_model.pt path: `outputs/hybrid_redesign/vitals_context_expert/best_model.pt`

## 18. Risk Fusion Integration Note

- rest_like + high HR + good PPG quality + personal deviation high can raise caution/high risk through fusion.
- active_like + high HR should be less risky than rest_like high HR.
- poor_signal reduces vitals contribution.
- abnormal_trend should add caution/high-risk context in a future labeled iteration, but must not trigger critical alone.
- Runtime must respect PPG Quality Expert output: bad/missing PPG reduces or zeros vitals contribution.

## 19. Final Decision

**REJECT_VITALS_CONTEXT_EXPERT**

Application validity override: **application_valid=false**. The checkpoint can be valid as a training artifact, but it is invalid for application/RiskFusionEngine use because poor_signal has zero train/val/test support, abnormal_trend has no supervised examples, and the apparent rest/active performance is likely source/domain confounded.

## 20. Recommendation

- Gait Instability Expert can start: YES, after Vitals rejection artifacts are recorded.
- Vitals ML model: disabled for current application version.
- Runtime vitals strategy: rule-based + personalization, gated by accepted PPG Quality Expert.
- Label mapping issue: poor_signal has zero usable support after routing, abnormal_trend lacks supervised examples, unknown 99 excluded.
- Extra preprocessing: future work should add true HR/RR/SpO2 handcrafted vitals features, poor_signal labels, and abnormal trend labels.
- PPG Quality integration: use accepted PPG Quality Expert at runtime to gate rule-based vitals contribution.
- Runtime compatibility note: this rejected checkpoint must not be wired into HybridInferenceService/RiskFusionEngine.
