# Vitals Context Expert Rejection Note

Decision: **REJECT_VITALS_CONTEXT_EXPERT**

The trained checkpoint appears to separate `rest_like` and `active_like`, but it cannot be accepted as a Vitals Context Expert for the current application.

Reasons:

- `poor_signal` has zero usable train/val/test support after routing/filtering.
- `abnormal_trend` has no supervised examples in the current prepared NPZ dataset.
- The confusion matrix contains only `rest_like` and `active_like` examples.
- The apparent accuracy is misleading because the missing target classes are not represented.
- Source/domain confounding risk is high: PPG-DaLiA contributes active-like windows, while WESAD contributes rest-like windows.

Application decision:

- `best_model.pt` remains a training artifact only.
- `application_valid=false`.
- This checkpoint will not be connected to `RiskFusionEngine`.
- Current-version vitals handling will use runtime rules plus personalization instead of a Vitals ML model.

This is the safe engineering choice: we should not ship a model for classes that do not have label support.
