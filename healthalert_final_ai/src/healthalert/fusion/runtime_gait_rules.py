from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np


def compute_runtime_gait_motion_score(imu_window: Optional[np.ndarray]) -> Dict[str, Any]:
    if imu_window is None:
        return {"score": 0.0, "features": {}, "reasons": ["imu_missing"]}

    x = np.asarray(imu_window, dtype=np.float32)
    if x.ndim != 2:
        return {"score": 0.0, "features": {}, "reasons": ["imu_invalid_shape"]}
    if x.shape[0] != 6 and x.shape[1] == 6:
        x = x.T
    if x.shape[0] != 6:
        return {"score": 0.0, "features": {}, "reasons": ["imu_invalid_channels"]}

    acc = x[:3, :]
    gyro = x[3:6, :]
    acc_mag = np.linalg.norm(acc, axis=0)
    jerk = np.diff(acc_mag, prepend=acc_mag[0])

    feats = {
        "acc_magnitude_mean": float(np.mean(acc_mag)),
        "acc_magnitude_std": float(np.std(acc_mag)),
        "acc_peak": float(np.max(np.abs(acc_mag))),
        "gyro_energy": float(np.mean(np.square(gyro))),
        "jerk_mean": float(np.mean(np.abs(jerk))),
        "jerk_std": float(np.std(jerk)),
    }
    motion_intensity = min(1.0, feats["acc_magnitude_std"] / 4.0 + feats["gyro_energy"] / 10.0)
    orientation_change_proxy = min(1.0, float(np.mean(np.abs(np.diff(gyro, axis=1)))) / 5.0)
    post_impact_low_motion = bool(feats["acc_peak"] > 2.2 and np.mean(acc_mag[-20:]) < 0.3)

    feats["motion_intensity"] = float(motion_intensity)
    feats["orientation_change_proxy"] = float(orientation_change_proxy)
    feats["post_impact_low_motion"] = post_impact_low_motion

    score = 0.0
    score += min(0.35, feats["acc_magnitude_std"] / 6.0)
    score += min(0.25, feats["gyro_energy"] / 15.0)
    score += min(0.2, feats["jerk_mean"] / 3.0)
    score += 0.1 * orientation_change_proxy
    if post_impact_low_motion:
        score += 0.2
    score = float(max(0.0, min(1.0, score)))

    reasons = []
    if score >= 0.6:
        reasons.append("motion_instability_high")
    elif score >= 0.35:
        reasons.append("motion_instability_moderate")
    else:
        reasons.append("motion_stable")

    if post_impact_low_motion:
        reasons.append("post_impact_low_motion")

    return {"score": score, "features": feats, "reasons": reasons}
