# Vitals Load v2 Plan

## 1. Current Vitals Failure Analysis

The rejected Vitals Context task failed for structural reasons, not because the optimizer or epoch count was weak.

Main failures:

- `poor_signal` had zero support after routing/filtering
- `abnormal_trend` had no supervised examples
- aggregate accuracy reached `1.0`, but macro F1 stayed `0.6666`
- source breakdown strongly suggests source/domain separation:
  - `PPG-DaLiA -> active_like`
  - `WESAD -> rest_like`

That means the old task definition is not trainable as-is.

## 2. Why 1400 Flat Features Are Not True Vitals Features

The current `features` vector used in `train_vitals_context_expert.py` is not a physiological feature vector.

It is produced by `scripts/build_multi_source_windowed_dataset.py` as:

- `200 x 6 IMU = 1200`
- `200 x 1 PPG = 200`
- total `1400`

This is just flattened raw window data after resampling/padding.

That representation can be useful for a raw multimodal model, but it is not a vitals-specific feature design and it does not reflect the task we claimed to train.

## 3. WESAD Label Mapping Repair

Current WESAD mapping in `config/datasets.yaml`:

- `1 -> normal`
- `2 -> instability`
- `3 -> instability`
- `4 -> normal`

This shared label-space mapping is acceptable for a broad multimodal export, but it is not suitable for a dedicated vitals task.

### Proposed WESAD-specific Vitals Load mapping

- `baseline -> normal_load`
- `stress -> elevated_load`
- `amusement -> exclude` for v2.0, or optional future third class
- `meditation -> normal_load` or exclude based on support audit

Key principle:

Do not force WESAD stress into the generic `instability` label family for this expert.

## 4. Proposed Target Classes

### Primary recommendation

Binary model:

- `normal_load`
- `elevated_load`

### Why binary first

- better label clarity
- easier runtime explanation
- less source fragmentation
- more compatible with MAX30102 + MPU6050 runtime signals

## 5. Feature Engineering Plan

Use the existing handcrafted extraction path in:

- `src/data/feature_engineering/feature_pipeline.py`
- `src/data/feature_engineering/ppg_features.py`

### Candidate feature groups

- HR estimate / provided HR
- `hr_mean`
- `hr_std`
- `hr_slope`
- `hr_delta`
- `hr_variability_proxy`
- `hr_cv`
- `current_spo2`
- `spo2_mean`
- `spo2_min`
- `spo2_std`
- `spo2_slope`
- `spo2_drop_amount`
- `low_spo2_duration_proxy`
- `ppg_quality_aggregate`
- `reliability_proxy`
- motion intensity
- instability score
- posture change proxy
- fusion features such as:
  - `hr_high_and_rising`
  - `spo2_low_and_falling`
  - `motion_instability_with_vitals`
  - `combined_risk_pattern`

### Important rule

For Vitals Load v2, the exported training features should be these engineered features, not the 1400 raw flattened vector.

## 6. PPG Quality Gate Strategy

The accepted PPG Quality Expert remains the runtime reliability gate.

### Training-time strategy

Options:

1. Exclude low-quality windows from Vitals Load training
2. Keep them but tag them for auxiliary analysis

Recommended first version:

- exclude clearly bad-quality windows from the main supervised training set
- keep a side audit of how many windows were removed

### Runtime strategy

- `good_quality`: vitals contribution allowed
- `bad_quality`: vitals contribution reduced or zeroed
- missing PPG: vitals contribution zero

## 7. Runtime Sensor Compatibility

This is critical.

WESAD includes sensors that do not exist in the target runtime stack, such as EDA and temperature. If those dominate the model, the result will not be deployable with MAX30102 + MPU6050.

### Therefore

Vitals Load v2 should use features derived primarily from:

- PPG
- HR / HR proxy
- SpO2 when available
- IMU motion context

Avoid making the core model depend on:

- EDA
- chest-only physiology
- sensors not available in runtime

## 8. Dataset Export Plan

Create a dedicated task-specific export for Vitals Load v2:

- do not reuse the old `vitals_context` target directly
- export engineered features
- keep source metadata
- keep subject metadata
- keep quality flags

Suggested future path:

`outputs/windowed_dataset/vitals_load_v2/`

Required fields:

- `features`
- `labels`
- optional raw `ppg`
- optional raw `imu`
- `metadata`

## 9. Training Plan

Suggested future model:

- feature-based MLP

Why:

- aligns with physiological feature semantics
- easier to inspect
- less likely to overfit source wave-shape patterns

Training rules:

- subject-aware split when possible
- train normalization stats only
- source breakdown mandatory
- macro F1 as primary metric
- binary confusion matrix required

## 10. Acceptance Criteria

- macro_f1 >= 0.75
- elevated_load recall >= 0.70
- normal_load recall >= 0.75
- source-confounding check passed
- subject/source split reported
- runtime feature compatibility confirmed for MAX30102/MPU6050
- application_valid only if the runtime-compatible feature subset was actually used

## 11. Risks

- WESAD may still carry strong source identity if combined naively with other datasets.
- HR and SpO2 availability differ across sources.
- Quality-based filtering may reduce support.
- If feature export mixes incompatible sensors, the model may look good offline and still fail at runtime.

## 12. Implementation Steps

1. Define a new Vitals Load task and binary target
2. Create WESAD-specific target mapping for that task
3. Build an engineered feature export path
4. Audit runtime-available versus runtime-unavailable feature columns
5. Add quality gating policy for training windows
6. Export new NPZ with metadata and source labels
7. Recount support and source balance
8. Only then start Vitals Load v2 training
