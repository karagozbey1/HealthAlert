# Gait Label Rescue Plan

## 1. Current Gait Failure Analysis

The rejected gait model did not fail because of optimization instability. It failed because the positive class disappeared before training.

Observed final support:

- train: `stable_gait = 3902`, `unstable_gait = 0`
- val: `stable_gait = 2408`, `unstable_gait = 0`
- test: `stable_gait = 1726`, `unstable_gait = 0`

This makes binary training impossible.

## 2. DAPHNET Label Mapping Inconsistency

There are three inconsistent representations of DAPHNET labels in the repo:

### `config/datasets.yaml`

- `0 -> normal`
- `1 -> pre_freeze`
- `2 -> freeze`

### `src/data/loaders/daphnet_fog_loader.py`

- `0 -> None`
- `1 -> normal`
- `2 -> freeze`

### `src/data/windowing.py::assign_window_label()`

- understands `normal`, `fall`, `near_fall`, `instability`, `walking`, `sitting`, `standing`, `lying`, `good_quality`, `bad_quality`, `unknown`
- does not understand `freeze`
- does not understand `pre_freeze`

This is the core inconsistency.

## 3. Where Freeze Labels Are Lost

Current chain:

1. DAPHNET loader emits `freeze`
2. `assign_window_label()` does not recognize `freeze`
3. unrecognized label becomes `unknown`
4. export maps `unknown -> 99`
5. gait training excludes `99`

So the FoG signal is not absent in raw data. It is being erased by the canonical mapping/export path.

## 4. Required Code Changes

### Minimal repair set

1. Align DAPHNET config and loader semantics
2. Extend canonical label mapping in `src/data/windowing.py`
3. Decide whether `pre_freeze` stays separate or folds into binary abnormal movement
4. Re-export gait task NPZ
5. Recount support before any training

### Safe first implementation

- map `freeze -> abnormal_or_freezing_movement`
- map `pre_freeze -> abnormal_or_freezing_movement`
- keep `unknown` only for truly unmapped labels

## 5. New Canonical Labels

### Recommended v2.0 target

Binary:

- `stable_movement`
- `abnormal_or_freezing_movement`

### Why binary first

- likely better support
- simpler acceptance criteria
- easier integration into RiskFusion
- avoids sparse 3-class failure on first rescue

## 6. Window Label Aggregation Strategy

Current windowing uses majority label inside the window.

For FoG rescue, define an explicit rule:

- if any `freeze` proportion exceeds a threshold, label the window abnormal
- if `pre_freeze` is present and binary mode is used, label abnormal
- otherwise label stable

Recommended first threshold:

- if `freeze` or `pre_freeze` occupies at least 20-30% of the window, mark abnormal

This threshold must be documented in the future export script/report.

## 7. Export Plan

After mapping repair:

- rebuild `outputs/windowed_dataset/gait_instability/`
- include metadata fields:
  - original raw label summary
  - window abnormal fraction
  - dataset name
  - subject id
  - recording id

Do not train yet. First produce a support recount.

## 8. Support Recount Plan

After label rescue, audit:

1. train abnormal support
2. val abnormal support
3. test abnormal support
4. subject distribution of abnormal windows
5. proportion of windows changed from `unknown` to abnormal

This recount is the go/no-go gate for Gait v2 training.

## 9. Training Plan After Label Rescue

Suggested future model:

- IMU CNN1D or current gait CNN

Training rules:

- IMU only
- z-score from train split only
- macro F1 primary metric
- collapse guard active
- no application_valid unless both classes have support

## 10. Acceptance Criteria

- train/val/test abnormal support > 0
- n_pred_cls >= 2
- abnormal recall >= 0.70
- stable recall >= 0.80
- macro_f1 >= 0.75
- `best_model.pt` only usable if `application_valid=true`

## 11. Risks

- DAPHNET may still have sparse abnormal coverage after rescue.
- Majority-window labeling may wash out short freeze events if the threshold is too strict.
- Subject count is limited, so source diversity remains narrow even after rescue.

## 12. Implementation Steps

1. Audit current DAPHNET raw labels and window label fractions
2. Align config and loader definitions
3. Extend canonical mapping for `freeze` and `pre_freeze`
4. Decide binary versus 3-class export
5. Rebuild gait task NPZ
6. Produce support recount report
7. Only if support is present, start Gait v2 training
