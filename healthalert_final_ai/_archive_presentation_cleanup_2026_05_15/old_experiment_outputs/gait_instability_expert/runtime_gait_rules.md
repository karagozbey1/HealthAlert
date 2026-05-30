# Runtime Gait Rules (Current Version)

Current version: no ML gait model.

Gait/motion instability is handled with rule-based runtime logic using IMU-derived features:
- `acc_magnitude_mean`
- `acc_magnitude_std`
- `acc_peak`
- `gyro_energy`
- `jerk_mean`
- `jerk_std`
- `motion_intensity`
- `orientation_change_proxy`
- `post_impact_low_motion`

Rules:
1. Gait/motion score must not generate a critical alert by itself.
2. Medium/high `fall_probability` combined with high gait/motion instability should increase risk.
3. Low `fall_probability` combined with stable motion should reduce risk pressure.
4. If IMU is missing, set gait contribution to `0` and append reason `imu_missing`.
5. Apply temporal smoothing to gait-related contribution before final fusion decisions.

Integration note:
- `gait_instability_model_enabled: false`
- Use runtime gait score as auxiliary input in RiskFusionEngine.
