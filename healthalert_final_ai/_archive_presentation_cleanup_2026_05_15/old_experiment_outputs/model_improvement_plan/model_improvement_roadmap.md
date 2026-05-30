# HealthAlert Model Improvement Roadmap

## 1. Executive Summary

This roadmap does not start new training. It explains why Activity, Vitals, and Gait did not reach application-grade quality and defines the repair work that must happen before the next training round.

The short version:

- Activity did not fail only because of class imbalance. It is mixing posture/activity labels with source-heavy `normal` and `instability` windows from datasets that do not contribute true ADL diversity.
- Vitals failed because the task definition was wrong for the available supervision and because the training input used 1400 flattened raw samples instead of true physiological features.
- Gait failed because the dataset does contain FoG labels, but the canonical mapping/export path loses them before training.

The recommended order is:

1. Gait label rescue
2. Activity v2 dataset repair and PAMAP2 audit
3. Vitals Load v2 feature export
4. New training rounds
5. RiskFusion update only after accepted checkpoints exist

## 2. Current Accepted Models

- Fall Expert Core no-UMAFall: accepted
- PPG Quality Expert: accepted

These remain the main accepted ML models for the current application version.

## 3. Current Rejected Models

- Activity Expert Balanced v1: rejected
- Vitals Context Expert: rejected
- Gait Instability Expert: rejected

Activity Expert v0 remains a temporary context baseline, not a final activity model.

## 4. Why Training Failed for Activity/Vitals/Gait

### Activity

- The current task combines:
  - source-heavy `normal`
  - `instability`
  - true ADL classes
- Final ADL supervision is effectively anchored by UCI-HAR.
- Oversampling increased exposure to weak ADL classes, but did not create new cross-source posture evidence.
- Result: the model stayed strong on `normal`, `instability`, `walking`, but became worse on `sitting`, `standing`, and `lying` under balanced sampling.

### Vitals

- The old target classes were not supported by the routed labels:
  - `poor_signal` support became 0
  - `abnormal_trend` had no supervised examples
- WESAD stress labels were folded into the shared `instability` label space instead of a vitals-specific target.
- The current `features` array is not a real vitals feature set. It is:
  - 200 x 6 IMU = 1200
  - 200 x 1 PPG = 200
  - total = 1400 flattened raw samples
- Result: the model mostly separated source/domain patterns such as `PPG-DaLiA -> active_like` and `WESAD -> rest_like`.

### Gait

- DAPHNET raw FoG information exists.
- Loader emits `freeze`.
- Canonical window label mapping does not recognize `freeze` or `pre_freeze`.
- Unrecognized labels become `unknown`.
- `unknown=99` is then excluded from export/training.
- Result: final gait train/val/test contain only `stable_gait`.

## 5. Root Cause Table

| Area | Root cause | Type |
|---|---|---|
| Activity | Mixed task definition: posture/activity plus instability plus source-heavy normal | task_definition |
| Activity | True ADL supervision mostly comes from UCI-HAR only | data_coverage |
| Activity | Oversampling changed frequency, not semantic diversity | sampling_limit |
| Vitals | Unsupported target classes (`poor_signal`, `abnormal_trend`) | label_support |
| Vitals | WESAD stress signal mapped into generic shared labels | label_mapping |
| Vitals | 1400 flat vector is not a physiological feature representation | feature_design |
| Gait | DAPHNET config, loader, and canonical mapping are inconsistent | mapping_inconsistency |
| Gait | `freeze` becomes `unknown`, then gets excluded | export_loss |

## 6. Task Trainability Matrix

See:

- [task_trainability_matrix.json](/c:/project/HealthAlert/healthalert_final_ai/outputs/hybrid_redesign/model_improvement_plan/task_trainability_matrix.json)

Operational summary:

- `fall_detection`: `TRAINABLE_NOW`
- `ppg_quality`: `TRAINABLE_NOW`
- `activity_context_current`: `TRAINABLE_WITH_NEW_DATASET`
- `activity_v2_pure_adl`: `TRAINABLE_WITH_NEW_DATASET`
- `vitals_context_current`: `SHOULD_BE_RULE_BASED_FOR_CURRENT_VERSION`
- `vitals_load_v2`: `TRAINABLE_WITH_LABEL_FIX`
- `gait_instability_current`: `TRAINABLE_WITH_LABEL_FIX`
- `tremor_context`: `NOT_TRAINABLE_CURRENT_DATA`

## 7. Activity v2 Roadmap

See:

- [activity_v2_dataset_plan.md](/c:/project/HealthAlert/healthalert_final_ai/outputs/hybrid_redesign/model_improvement_plan/activity_v2_dataset_plan.md)

Direction:

- Replace the current mixed task with a pure ADL classifier.
- Target classes:
  - `walking`
  - `sitting`
  - `standing`
  - `lying`
- Remove:
  - `instability`
  - `fall`
  - `near_fall`
  - generic `normal`
  - `unknown`
- Add real ADL diversity, likely through PAMAP2.

## 8. Vitals Load v2 Roadmap

See:

- [vitals_load_v2_plan.md](/c:/project/HealthAlert/healthalert_final_ai/outputs/hybrid_redesign/model_improvement_plan/vitals_load_v2_plan.md)

Direction:

- Stop trying to learn `poor_signal` and `abnormal_trend` without labels.
- Redefine the task as a physiological load model:
  - `normal_load`
  - `elevated_load`
- Use WESAD stress as the main supervised target.
- Export true handcrafted PPG/HR/HRV/motion features instead of the 1400 flat raw vector.
- Keep runtime compatibility with MAX30102 + MPU6050.

## 9. Gait Label Rescue v2 Roadmap

See:

- [gait_label_rescue_plan.md](/c:/project/HealthAlert/healthalert_final_ai/outputs/hybrid_redesign/model_improvement_plan/gait_label_rescue_plan.md)

Direction:

- Rescue the labels already present in DAPHNET before adding new data.
- Introduce canonical gait labels that preserve FoG signal:
  - `stable_movement`
  - `abnormal_or_freezing_movement`

## 10. Required Dataset Additions

- PAMAP2 for Activity v2 is the strongest current candidate.
- A new FoG dataset is not the first step for gait; first fix DAPHNET label rescue.
- A new vitals dataset is not the first step for Vitals v2; first repair WESAD target mapping and feature export.

## 11. Required Code Changes

### Activity

- Add `pure_activity_v2` task definition
- Add dataset-specific inclusion/exclusion rules
- Keep subject-aware split
- Add source-balanced evaluation
- Add PAMAP2 config + loader + routing only after audit

### Vitals

- Create a vitals-specific label mapping path for WESAD
- Create a feature export path based on `src/data/feature_engineering/feature_pipeline.py`
- Stop using `features.shape == 1400` raw flat vectors for vitals training

### Gait

- Align `config/datasets.yaml` and `src/data/loaders/daphnet_fog_loader.py`
- Extend `src/data/windowing.py::assign_window_label()` to understand `freeze` and `pre_freeze`
- Recount support after export repair before training

## 12. Evaluation Strategy

- Accuracy alone is not enough.
- Macro F1 is required.
- Per-class recall is required.
- A source breakdown report is required.
- Subject-aware split must be preserved.
- Application validity must stay separate from training validity.

## 13. Acceptance Metrics

### Activity v2

- macro_f1 >= 0.80
- walking recall >= 0.90
- sitting recall >= 0.75
- standing recall >= 0.75
- lying recall >= 0.75
- n_pred_cls >= 4

### Vitals Load v2

- macro_f1 >= 0.75
- elevated_load recall >= 0.70
- normal_load recall >= 0.75
- runtime feature compatibility with MAX30102/MPU6050

### Gait v2

- abnormal support > 0 in train/val/test
- macro_f1 >= 0.75
- abnormal recall >= 0.70
- stable recall >= 0.80
- n_pred_cls >= 2

## 14. RiskFusion Impact

- Activity v2 would improve context interpretation for post-fall and low-motion scenarios.
- Vitals Load v2 would upgrade the current rule-based vitals adjustment into a supervised but runtime-compatible expert.
- Gait v2 would add real forward-risk context rather than the current rule-only motion score.

Rejected checkpoints must remain disconnected from RiskFusionEngine until new accepted checkpoints exist.

## 15. Recommended Implementation Order

1. Gait label rescue
2. Activity v2 dataset repair and PAMAP2 audit
3. Vitals Load v2 feature export and label repair
4. New training rounds:
   - Gait v2
   - Activity v2
   - Vitals Load v2
5. RiskFusionEngine update only after acceptance

## 16. What Not To Do

- Do not use live ESP32/MAX30102/MPU6050 data for training.
- Do not accept a class with support = 0.
- Do not treat training artifact validity as application validity.
- Do not use oversampling as a substitute for task repair.
- Do not connect rejected checkpoints to RiskFusionEngine.
- Do not report high accuracy as success when macro F1 and class coverage are weak.

## 17. Final Recommendation

The first model to fix should be Gait, because the failure is concrete and local: the labels exist, but the export path loses them. After that, Activity should be redesigned as a pure ADL task with better dataset support. Vitals should be rebuilt last, because its target definition and feature representation both need repair.

No new training should start until:

1. Gait label rescue support recount is complete
2. Activity v2 task definition is narrowed to pure ADL
3. PAMAP2 feasibility is documented
4. Vitals Load v2 feature export path is defined
5. Source-balanced and subject-aware evaluation criteria are locked
