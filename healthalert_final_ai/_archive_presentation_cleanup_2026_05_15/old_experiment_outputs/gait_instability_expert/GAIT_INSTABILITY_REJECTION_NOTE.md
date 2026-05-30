# GAIT Instability Expert Rejection Note

Final decision: `REJECT_GAIT_INSTABILITY_EXPERT`

Reason summary:
- `unstable_gait` support is zero in train/val/test after filtering.
- The model cannot learn stable vs unstable separation without supervised unstable examples.
- Reported `accuracy=1.0` is misleading because only stable class is present.
- `n_pred_cls=1` indicates single-class collapse.
- `best_model.pt` is not valid for deployment and must not be loaded by application services.

Current version policy:
- Gait ML model is disabled.
- RiskFusionEngine and HybridInferenceService must not connect this checkpoint.
- Gait contribution is handled with runtime rule-based IMU scoring until labeled unstable data is available.
