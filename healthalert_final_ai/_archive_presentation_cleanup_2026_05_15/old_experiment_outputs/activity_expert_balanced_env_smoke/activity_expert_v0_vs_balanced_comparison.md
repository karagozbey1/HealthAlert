# Activity Expert v0 vs Balanced v1 Comparison

| Metric | v0 | balanced_v1 | Delta | Better/Worse |
|---|---:|---:|---:|---|
| macro_f1 | 0.7869 | 0.0595 | -0.7274 | worse |
| normal recall | 0.9729 | 0.0000 | -0.9729 | worse |
| instability recall | 0.9963 | 1.0000 | +0.0037 | better |
| walking recall | 0.9821 | 0.0000 | -0.9821 | worse |
| sitting recall | 0.4862 | 0.0000 | -0.4862 | worse |
| standing recall | 0.7838 | 0.0000 | -0.7838 | worse |
| lying recall | 0.6853 | 0.0000 | -0.6853 | worse |
| confusion reduction for sitting/lying | N/A | N/A | N/A | v0 confusion matrix not available in the provided baseline summary |

Final decision: **REJECT_BALANCED_MODEL**
Balanced report: `outputs\hybrid_redesign\activity_expert_balanced_env_smoke\activity_expert_balanced_report.md`