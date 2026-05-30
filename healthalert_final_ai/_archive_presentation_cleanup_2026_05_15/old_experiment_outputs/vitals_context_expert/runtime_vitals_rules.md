# Runtime Vitals Rules

Current version: **no ML vitals model**.

The rejected Vitals Context checkpoint is not used in the application. Runtime vitals handling is rule-based and personalized.

## Required Gates

- PPG Quality Expert is required before interpreting HR, SpO2, or PPG-derived values.
- If `ppg_quality_score` indicates good quality, vitals contribution may be used.
- If PPG quality is bad or motion-artifact-like, vitals contribution is reduced or set to zero.
- If PPG is missing, vitals contribution is `0` and reason `ppg_missing` is added.

## Personalization

- HR, SpO2, and other values should be compared against the user's runtime baseline.
- No per-user ML fine-tuning is allowed.
- Baseline updates should only happen during safe, low-risk, good-quality PPG periods.

## Rest / Active Context

- Rest/active context should come from Activity Expert v0 or runtime motion level.
- Vitals alone must not infer activity context from the rejected Vitals ML checkpoint.

## Draft Contribution Formula

Inputs:

- `ppg_quality_score` in `[0, 1]`
- `personal_deviation_score` in `[0, 1]`
- `activity_or_motion_context`
- optional HR/SpO2 rule flags

Draft:

```text
if ppg_missing:
    vitals_contribution = 0
    reason = "ppg_missing"
elif ppg_quality_score < 0.50:
    vitals_contribution = 0
    reason = "ppg_quality_low_vitals_disabled"
else:
    quality_factor = ppg_quality_score
    baseline_factor = personal_deviation_score
    context_factor = lower if active_like else normal
    vitals_contribution = max_vitals_points * quality_factor * baseline_factor * context_factor
```

## Safe Fallback

- Missing PPG: vitals contribution `0`.
- Bad PPG: vitals contribution `0` or strongly reduced.
- Missing user baseline: no personalization adjustment.
- Vitals never produces `critical` by itself.
- Vitals only acts as a supporting adjustment to final risk.
