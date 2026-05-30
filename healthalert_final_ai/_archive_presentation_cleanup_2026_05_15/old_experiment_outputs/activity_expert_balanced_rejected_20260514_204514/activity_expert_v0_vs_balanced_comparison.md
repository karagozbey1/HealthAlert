# Activity Expert v0 vs Balanced v1 Comparison

| Metric | v0 | balanced_v1 | Delta | Better/Worse |
|---|---:|---:|---:|---|
| macro_f1 | 0.7869 | 0.6456 | -0.1413 | worse |
| normal recall | 0.9729 | 0.9758 | +0.0029 | better |
| instability recall | 0.9963 | 0.9963 | +0.0000 | better |
| walking recall | 0.9821 | 1.0000 | +0.0179 | better |
| sitting recall | 0.4862 | 0.2385 | -0.2477 | worse |
| standing recall | 0.7838 | 0.1577 | -0.6261 | worse |
| lying recall | 0.6853 | 0.2069 | -0.4784 | worse |
| confusion reduction for sitting/lying | N/A | N/A | N/A | v0 confusion matrix not available in the provided baseline summary |

Final decision: **REJECT_BALANCED_MODEL**
Balanced report: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\activity_expert_balanced\activity_expert_balanced_report.md`