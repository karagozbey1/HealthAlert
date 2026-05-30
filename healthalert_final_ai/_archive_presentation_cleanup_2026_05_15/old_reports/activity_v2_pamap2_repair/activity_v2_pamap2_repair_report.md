# Activity v2.1 PAMAP2 Repair Report

## 1. Executive Summary
- Current failed combined checkpoint macro_f1: 0.6490.
- Best repair experiment: exp_h_mixed_sensor_ankle (Mixed sensor variant ankle).
- Best repaired combined macro_f1: 0.7935.
- Final decision: KEEP_UCI_ONLY_ACTIVITY_V2_BASELINE.

## 2. Current UCI-only Baseline
- experiment_id: exp_a_uci_only_baseline
- test_macro_f1: 0.8826
- test_accuracy: 0.9047

## 3. Failed UCI-HAR + PAMAP2 Result
- current combined macro_f1: 0.6490
- current UCI-HAR macro_f1: 0.7991
- current PAMAP2 macro_f1: 0.5419

## 4. Source-Level Error Analysis
- main posture confusion in PAMAP2 is concentrated in: S107, S102, S108
- UCI-HAR standing recall under current failed model: 0.3676
- PAMAP2 standing recall under current failed model: 0.3634

## 5. PAMAP2 Sensor/Label Audit
- Label mapping is internally consistent; no direct label inversion was found.
- The main gap is sensor-location mismatch and source distribution mismatch, not a loader crash or missing class problem.

## 6. Normalization Ablation
- exp_c_mixed_global_zscore: macro_f1=0.7217
- exp_d_mixed_per_window_zscore: macro_f1=0.7695
- exp_g_mixed_global_zscore_clipped: macro_f1=0.6159

## 7. Source-Balanced Training Results
- exp_e_mixed_source_balanced: combined=0.5775, UCI=0.6397, PAMAP2=0.5286
- exp_f_mixed_class_source_balanced: combined=0.6496, UCI=0.7716, PAMAP2=0.5632

## 8. PAMAP2-only Result
- experiment_id: exp_b_pamap2_only_baseline
- test_macro_f1: 0.5786
- per-class recall: {"walking": 0.9481, "sitting": 0.7035, "standing": 0.0343, "lying": 0.7189}

## 9. Best Experiment
- experiment_id: exp_h_mixed_sensor_ankle
- strategy: Mixed sensor variant ankle
- combined macro_f1: 0.7935
- UCI-HAR macro_f1: 0.8773
- PAMAP2 macro_f1: 0.7392

## 10. Comparison Against UCI-only Baseline
- UCI-only macro_f1: 0.8826
- Best multisource macro_f1: 0.7935
- Gap vs UCI-only: -0.0891

## 11. Final Decision
- Decision: KEEP_UCI_ONLY_ACTIVITY_V2_BASELINE
- Multisource acceptance met: False

## 12. Recommendation
- Keep UCI-only baseline unless a later source can close the remaining cross-domain gap.
- Use MobiAct or a more waist-aligned ADL source if multisource Activity v2 is still required.
