# Fall Expert — Threshold Analysis Report
**Model checkpoint**: `best_model.pt` (epoch 23, val app_score=0.7902)  
**Test set**: 4,942 windows (near_fall excluded)  
**Date**: 2026-05-14  

---

## 1. Threshold Sweep

| Threshold | fall_recall | fall_precision | normal_recall | macro_f1 | FP | FN | app_score |
|-----------|-------------|----------------|---------------|----------|----|----|-----------|
| 0.25 | 0.97072 | 0.80392 | 0.88613 | 0.90607 | 380 | 47 | 0.90017 |
| 0.30 | 0.96511 | 0.81569 | 0.89512 | 0.91025 | 350 | 56 | 0.90354 |
| 0.35 | 0.95701 | 0.82095 | 0.89961 | 0.91036 | 335 | 69 | 0.90272 |
| 0.40 | 0.95389 | 0.83252 | 0.90770 | 0.91488 | 308 | 74 | 0.90687 |
| 0.45 | 0.95078 | 0.84031 | 0.91310 | 0.91752 | 290 | 79 | 0.90919 ◄ |
| 0.50 | 0.94330 | 0.84439 | 0.91639 | 0.91703 | 279 | 91 | 0.90797 |
| 0.55 | 0.93333 | 0.84824 | 0.91969 | 0.91559 | 268 | 107 | 0.90558 |
| 0.60 | 0.92586 | 0.85896 | 0.92688 | 0.91786 | 244 | 119 | 0.90729 |

---

## 2. Dataset-Source Breakdown (threshold=0.40)

| Dataset | n_total | n_fall | n_normal | fall_recall | fall_precision | normal_recall | macro_f1 | FN | FP |
|---------|---------|--------|----------|-------------|----------------|---------------|----------|----|----|
| BITS2_GERIATRIC_FALL_HR | 1,637 | 700 | 937 | 0.9229 | 0.7417 | 0.7599 | 0.8293 | 54 | 225 |
| HIFD | 446 | 140 | 306 | 0.9714 | 0.9379 | 0.9706 | 0.9665 | 4 | 9 |
| UP-Fall | 581 | 0 | 581 | 0.0000 | 0.0000 | 0.9948 | 0.4987 | 0 | 3 |
| UniMiB-SHAR | 1,786 | 619 | 1,167 | 0.9741 | 0.9541 | 0.9751 | 0.9723 | 16 | 29 |
| WEDA_FALL | 492 | 146 | 346 | 1.0000 | 0.7766 | 0.8786 | 0.9048 | 0 | 42 |

### Confusion Matrices per Dataset (threshold=0.40)

**BITS2_GERIATRIC_FALL_HR** (n=1,637)

```
              Pred Normal   Pred Fall
Act Normal           712        225
Act Fall              54        646
```

**HIFD** (n=446)

```
              Pred Normal   Pred Fall
Act Normal           297          9
Act Fall               4        136
```

**UP-Fall** (n=581)

```
              Pred Normal   Pred Fall
Act Normal           578          3
Act Fall               0          0
```

**UniMiB-SHAR** (n=1,786)

```
              Pred Normal   Pred Fall
Act Normal         1,138         29
Act Fall              16        603
```

**WEDA_FALL** (n=492)

```
              Pred Normal   Pred Fall
Act Normal           304         42
Act Fall               0        146
```


---

## 3. Error Analysis (threshold=0.40)

**Total FN (missed falls)**: 74  
**Total FP (false alarms)**: 308  

### False Negatives by Source (falls the model missed)

| Dataset | FN | Total Falls | Miss Rate |
|---------|----|-----------|-----------|
| BITS2_GERIATRIC_FALL_HR | 54 | 700 | 0.077 |
| UniMiB-SHAR | 16 | 619 | 0.026 |
| HIFD | 4 | 140 | 0.029 |
| UP-Fall | 0 | 0 | 0.000 |
| WEDA_FALL | 0 | 146 | 0.000 |

### False Positives by Source (normals misclassified as fall)

| Dataset | FP | Total Normals | FP Rate |
|---------|----|-----------|---------|
| BITS2_GERIATRIC_FALL_HR | 225 | 937 | 0.240 |
| WEDA_FALL | 42 | 346 | 0.121 |
| UniMiB-SHAR | 29 | 1,167 | 0.025 |
| HIFD | 9 | 306 | 0.029 |
| UP-Fall | 3 | 581 | 0.005 |

### FN Probability Distribution

*(These are falls where model assigned low probability — hardest misses)*

| Prob Range | Count |
|------------|-------|
| 0.00-0.10 | 29 |
| 0.10-0.20 | 18 |
| 0.20-0.30 | 9 |
| 0.30-0.40 | 18 |

### FP Probability Distribution

*(These are normals where model assigned fall probability above threshold)*

| Prob Range | Count |
|------------|-------|
| 0.40-0.50 | 29 |
| 0.50-0.60 | 35 |
| 0.60-0.70 | 49 |
| 0.70-1.00 | 195 |

---

## 4. Recommendation

**Recommended threshold**: `0.45`  
- app_score: `0.90919`  
- fall_recall: `0.95078`  
- macro_f1: `0.91752`  

*Threshold selection criteria: maximise app_score subject to fall_recall ≥ 0.70*  
