# Gait Label Rescue Implementation Report

## 1. Executive Summary

- Decision: **READY_FOR_GAIT_V2_TRAINING**
- Reason: abnormal/freezing support exists in train, val, and test after label rescue
- New dataset path: `C:\project\HealthAlert\healthalert_final_ai\outputs\windowed_dataset\gait_instability_v2`

## 2. Previous Failure Summary

- Previous gait training had zero unstable support in train/val/test.
- The failure root cause was label loss before training, not optimizer behavior.

## 3. Raw DAPHNET Label Audit

- Raw label counts: {0: 777052, 1: 1030050, 2: 110785}
- Loader label counts after fix: {'unannotated': 777052, 'normal': 1030050, 'freeze': 110785}

## 4. Config vs Loader Mapping Comparison

- datasets.yaml corrected to `0=unannotated, 1=normal, 2=freeze`.
- daphnet_fog_loader now preserves the full raw timeline instead of dropping label 0 rows.

## 5. Windowing Mapping Fix

- `assign_window_label()` now understands `freeze`, `pre_freeze`, `stable_movement`, and `abnormal_or_freezing_movement`.
- gait-specific aggregation runs before generic canonical fallback.

## 6. Window Label Aggregation Rule

- abnormal_fraction_threshold = 0.20
- if freeze/pre_freeze fraction >= 0.20 -> abnormal_or_freezing_movement
- else if stable labels dominate informative samples -> stable_movement
- else -> unknown

## 7. Export Changes

- New export directory created: `outputs/windowed_dataset/gait_instability_v2/`
- Existing `gait_instability/` directory was not modified.

## 8. Unknown Rescue Results

- Legacy unknown windows: 6871
- Rescued abnormal windows: 1124
- Rescued from legacy unknown: 860
- Remaining unknown windows: 5976

## 9. Gait v2 Support Recount

- train: stable=5639, abnormal=619, unknown_excluded=4202
- val: stable=748, abnormal=309, unknown_excluded=586
- test: stable=1471, abnormal=196, unknown_excluded=1188

## 10. Subject/Recording Distribution

- Train abnormal by subject: {'S03': 195, 'S06': 75, 'S07': 68, 'S08': 117, 'S09': 164}
- Val abnormal by subject: {'S05': 309}
- Test abnormal by subject: {'S01': 78, 'S02': 118}

## 11. Go/No-Go Decision

**READY_FOR_GAIT_V2_TRAINING**

## 12. Files Changed

- config/datasets.yaml
- config/hybrid_task_routing.yaml
- src/data/loaders/daphnet_fog_loader.py
- src/data/windowing.py
- scripts/build_gait_instability_v2_dataset.py

## 13. Risks

- DAPHNET is still a single-source gait dataset.
- The abnormal fraction threshold may need tuning after first supervised training.
- pre_freeze is not present in current local raw files, so the rescue currently targets freeze directly.

## 14. Next Step

- If the decision is READY_FOR_GAIT_V2_TRAINING, the next step is a gated training prompt using `outputs/windowed_dataset/gait_instability_v2/` only.
- If the decision is NEED_SPLIT_REPAIR, adjust split strategy without introducing leakage.