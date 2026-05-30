# Risk Fusion Integration Report

## 1. Executive Summary
- Final integration completed for RiskFusionEngine + HybridInferenceService.
- New expert training was not started.
- Rejected models are not connected to runtime inference.
- System returns stable final outputs (0-100 score, risk level, reasons, action) without crashing on missing modalities.

## 2. Current Model Status
- Fall Expert Core no-UMAFall: ACCEPTED
- PPG Quality Expert: ACCEPTED
- Activity Expert v0: TEMPORARY_CONTEXT_BASELINE
- Activity Balanced v1: REJECTED
- Vitals Context Expert: REJECTED (runtime rules + personalization)
- Gait Instability Expert: REJECTED (runtime rule-based IMU score)
- Tremor Context: DISABLED

## 3. Accepted Models
- `outputs/hybrid_redesign/fall_expert_core_no_umafall/best_model.pt`
- `outputs/hybrid_redesign/ppg_quality_expert/best_model.pt`

## 4. Rejected Models and Why
- Vitals Context Expert: poor_signal/abnormal_trend supervised support missing.
- Gait Instability Expert: unstable support is zero, single-class collapse.
- Activity Balanced v1: macro/per-class degradation.

## 5. Runtime Rule-Based Components
- Vitals: `src/healthalert/fusion/runtime_vitals_rules.py`
- Gait/Motion: `src/healthalert/fusion/runtime_gait_rules.py`
- Both are active in `HybridInferenceService` and feed RiskFusionEngine.

## 6. Personalization Strategy
- No ML fine-tuning.
- User baseline via `UserBaselineEngine`.
- Baseline update blocked in risky periods and poor signal conditions.
- Missing baseline -> cold start mode, zero personalization boost.

## 7. RiskFusion Formula
- Inputs: fall probability, activity context, PPG quality, runtime vitals adjustment, runtime gait score, personalization, signal confidence, missing flags.
- Output score range: always clipped to 0-100.
- Risk levels: `normal`, `caution`, `high_risk`, `critical`.
- PPG missing/bad quality gates vitals contribution.
- Gait/motion does not produce critical alone.

## 8. Temporal Smoothing Rules
- Implemented in `src/healthalert/fusion/temporal_risk_smoother.py`.
- Uses EMA + persistence-based escalation/de-escalation.
- Avoids one-window critical spikes and supports user-confirmed cooldown.

## 9. HybridInferenceService Modes
- IMU-only: fall + activity + runtime gait; vitals reduced/disabled with reason.
- IMU+PPG: fall + activity + ppg quality + runtime vitals + runtime gait.
- PPG missing: no crash, `ppg_missing`, vitals contribution zero.
- Baseline missing: `cold_start_mode=true`, personalization adjustment neutral.

## 10. Missing Modality Behavior
- IMU missing: no crash, fall/gait contributions reduced to safe defaults.
- PPG missing: no crash, vitals gate closed, reason emitted.
- Baseline missing: no crash, personalization neutral.

## 11. Demo Outputs
- Script: `scripts/run_hybrid_inference_demo.py`
- Output JSON: `outputs/hybrid_redesign/inference/hybrid_inference_demo_outputs.json`
- Scenarios run:
  - `imu_only`
  - `imu_plus_ppg`
  - `ppg_missing`
  - `with_user_baseline`

## 12. Tests Run
- Command:
  - `C:\project\HealthAlert\.venv311\Scripts\python.exe -m pytest tests/test_risk_fusion_engine.py tests/test_hybrid_inference_service.py tests/test_temporal_risk_smoother.py tests/test_runtime_vitals_rules.py tests/test_runtime_gait_rules.py tests/test_model_status_config.py -q`
- Result: 12 passed, 0 failed.

## 13. Remaining Limitations
- Activity v0 is temporary and class reliability is uneven.
- No accepted gait ML model yet; runtime IMU rules are used.
- No accepted vitals ML model yet; runtime vitals rules are used.
- Demo values depend on available NPZ windows and current checkpoint behavior.

## 14. Next Steps for Mobile/Backend Integration
1. Expose `HybridInferenceService.infer()` as backend endpoint returning final JSON.
2. Add API-level schema validation for missing modalities.
3. Map `risk_level` + `recommended_action` to app UX states.
4. Persist baseline snapshots per user with safe update policy.
5. Add production telemetry for reasons distribution and gate behavior.
