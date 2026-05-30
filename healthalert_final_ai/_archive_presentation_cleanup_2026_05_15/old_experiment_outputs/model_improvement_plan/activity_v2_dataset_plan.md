# Activity v2 Dataset Plan

## 1. Current Activity v0 Failure Analysis

Activity v0 is usable as a temporary context baseline, but it is not a clean activity model.

Observed behavior:

- `normal`, `instability`, and `walking` are strong
- `sitting` is weak
- `standing` is acceptable but not strong enough
- `lying` is only moderate

Current train distribution:

- `normal = 67,977`
- `instability = 34,220`
- `walking = 3,537`
- `sitting = 1,389`
- `standing = 1,502`
- `lying = 1,520`

This means `normal + instability` account for about 92.77% of train support, while true ADL classes account for about 7.23%.

The more important issue is semantic imbalance:

- `UCI-HAR` contributes the true posture/activity labels
- `SisFall` mainly contributes `normal/instability`
- `UMAFall` contributes mostly `normal`
- `UniMiB-SHAR` contributes mostly `normal`

So the current model is not learning a balanced activity taxonomy. It is learning a mixed task with strong source identity cues.

## 2. Why Balanced v1 Failed

Balanced v1 increased ADL sampling to about 35%, but performance got worse:

- macro_f1: `0.7869 -> 0.6456`
- sitting recall: `0.4862 -> 0.2385`
- standing recall: `0.7838 -> 0.1577`
- lying recall: `0.6853 -> 0.2069`

Why:

- Oversampling changed how often rare ADL windows were seen.
- It did not increase genuine ADL diversity across sources.
- It left the mixed label space intact:
  - `normal`
  - `instability`
  - true ADL classes
- It likely amplified the mismatch between UCI-HAR posture boundaries and source-heavy non-ADL windows.

Balanced v1 therefore confirms that the problem is not just frequency. It is task definition plus dataset composition.

## 3. ADL Source Audit

### Current routed datasets

From `config/hybrid_task_routing.yaml`, `activity_context` currently allows:

- `uci_har`
- `unimib_shar`
- `umafall`
- `mobiact`
- `sisfall`

### Actual final training contributors

From the accepted activity report, final splits used:

- `UMAFall`
- `SisFall`
- `UCI-HAR`
- `UniMiB-SHAR`

`MobiAct` is allowed by routing but not present in final splits.

### True ADL contributors

- `UCI-HAR`: true contributor for `walking`, `sitting`, `standing`, `lying`
- `UMAFall`: effectively contributes `normal`
- `UniMiB-SHAR`: effectively contributes `normal`
- `SisFall`: effectively contributes `normal/instability`

Conclusion:

The current ADL backbone is effectively single-source.

## 4. Pure Activity v2 Target Definition

Activity v2 should be a pure ADL model.

### Proposed classes

- `walking`
- `sitting`
- `standing`
- `lying`

### Optional future classes

- `stairs`
- `transition`

Only add optional classes if they are present across enough data and can be evaluated with stable support.

### Must exclude

- `instability`
- `fall`
- `near_fall`
- `unknown`
- `good_quality`
- `bad_quality`
- generic `normal` windows that are not real posture/activity labels

## 5. Label Mapping Plan

### UCI-HAR

- `1,2,3 -> walking`
- `4 -> sitting`
- `5 -> standing`
- `6 -> lying`

### PAMAP2 candidate mapping

- `walking -> walking`
- `sitting -> sitting`
- `standing -> standing`
- `lying -> lying`
- other labels -> exclude or park for future optional classes

### Existing source policy

- `UMAFall`: do not use for pure ADL unless raw ADL subclasses are explicitly recovered
- `UniMiB-SHAR`: do not use for pure ADL unless subclass activity labels are preserved
- `SisFall`: keep out of pure ADL if it only expresses movement anomaly rather than posture/activity
- `MobiAct`: include only after data availability and audit

## 6. Dataset Inclusion/Exclusion Plan

### Include now

- `UCI-HAR`

### Include after audit / availability

- `PAMAP2`
- `MobiAct`

### Exclude from Activity v2 training

- `UMAFall` as generic `normal`
- `UniMiB-SHAR` as generic `normal`
- `SisFall` as `instability`
- any dataset where only source-specific `normal` survives

## 7. PAMAP2 Integration Requirements

PAMAP2 is not currently wired in the repo. To add it cleanly:

1. Add `pamap2` entry in `config/datasets.yaml`
2. Add loader, likely `src/data/loaders/pamap2_loader.py`
3. Add routing entry in `config/hybrid_task_routing.yaml`
4. Define raw activity label mapping
5. Resample `100 Hz -> 50 Hz`
6. Select IMU channels compatible with the standard `(200, 6)` export
7. Preserve subject IDs for subject-aware split
8. Exclude unsupported labels from the first pure ADL version

## 8. Subject-Aware Split Plan

The repo already has subject-aware splitting in `src/data/splitting.py`.

Requirements for Activity v2:

- keep split by `subject_id` whenever possible
- keep dataset source in metadata
- produce per-source and per-subject breakdown in evaluation
- avoid random window split fallback in the final benchmark

UCI-HAR already preserves subject information in `uci_har_loader.py`.

## 9. Source-Balanced Evaluation Plan

Activity v2 must not be accepted on aggregate accuracy alone.

Required evaluation outputs:

- macro_f1
- per-class precision/recall/F1
- source breakdown
- subject-aware split confirmation
- confusion matrix

Recommended extra checks:

- leave-one-source-out evaluation if multiple sources become available
- source classifier probe to detect source shortcut risk

## 10. Training Input Format

Use:

- IMU only
- shape `(batch, 6, 200)`
- z-score normalization from train split only

No live ESP32 data in training.

## 11. Expected Output Directory

Suggested future output:

`outputs/hybrid_redesign/activity_expert_v2/`

with:

- `best_model.pt`
- `last_model.pt`
- `metrics.json`
- `training_history.json`
- `confusion_matrix.json`
- `prediction_distribution.json`
- `per_class_metrics.json`
- `source_breakdown.json`
- `imu_norm_stats.json`
- `activity_v2_report.md`

## 12. Acceptance Criteria

- macro_f1 >= 0.80
- walking recall >= 0.90
- sitting recall >= 0.75
- standing recall >= 0.75
- lying recall >= 0.75
- n_pred_cls >= 4
- subject-aware test confirmed
- source breakdown required
- no clear source-only shortcut behavior

## 13. Risks

- PAMAP2 integration may add label harmonization complexity.
- MobiAct may remain unavailable if access is not granted.
- If only UCI-HAR remains, Activity v2 may still be single-source and need careful application labeling.
- Generic `normal` windows from current sources can contaminate the task if reintroduced.

## 14. Implementation Steps

1. Create a pure ADL task definition
2. Build an ADL-only dataset inclusion list
3. Audit existing datasets for true posture labels
4. Add PAMAP2 dataset config and loader plan
5. Export pure ADL task NPZ
6. Recount class support by subject and source
7. Define source-balanced evaluation report format
8. Only then start Activity v2 training
