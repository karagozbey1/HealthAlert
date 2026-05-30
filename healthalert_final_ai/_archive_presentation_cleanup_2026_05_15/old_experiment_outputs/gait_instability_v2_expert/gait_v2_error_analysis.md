# Gait v2 Error Analysis Report

## 1. Overview

- Checkpoint: `C:\project\HealthAlert\healthalert_final_ai\outputs\hybrid_redesign\gait_instability_v2_expert\best_model.pt`
- Dataset: DAPHNET_FOG (gait_instability_v2)
- All analysis on test split unless noted otherwise.
- Threshold analysis (section 4) done on validation set.

## 2. Probability Distribution

### Stable true samples — predicted abnormal probability

- N stable true: 1,471
- Mean prob: 0.2464
- Median prob: 0.2393
- P25 / P75: 0.0768 / 0.3433
- P10 / P90: 0.0631 / 0.463

| Prob range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 385 | 0.2617 |
| [0.10, 0.20) | 163 | 0.1108 |
| [0.20, 0.30) | 443 | 0.3012 |
| [0.30, 0.40) | 240 | 0.1632 |
| [0.40, 0.50) | 147 | 0.0999 |
| [0.50, 0.60) | 89 | 0.0605 |
| [0.60, 0.70) | 4 | 0.0027 |
| [0.70, 0.80) | 0 | 0.0000 |
| [0.80, 0.90) | 0 | 0.0000 |
| [0.90, 1.00) | 0 | 0.0000 |

### Abnormal true samples — predicted abnormal probability

- N abnormal true: 196
- Mean prob: 0.3499
- Median prob: 0.3281
- P25 / P75: 0.2517 / 0.4358
- P10 / P90: 0.2086 / 0.5239

| Prob range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 0 | 0.0000 |
| [0.10, 0.20) | 15 | 0.0765 |
| [0.20, 0.30) | 65 | 0.3316 |
| [0.30, 0.40) | 49 | 0.2500 |
| [0.40, 0.50) | 39 | 0.1990 |
| [0.50, 0.60) | 26 | 0.1327 |
| [0.60, 0.70) | 2 | 0.0102 |
| [0.70, 0.80) | 0 | 0.0000 |
| [0.80, 0.90) | 0 | 0.0000 |
| [0.90, 1.00) | 0 | 0.0000 |

### Overlap region (false positive risk at different thresholds)

- FP rate at threshold=0.20: 0.6275
- FP rate at threshold=0.30: 0.3263
- FP rate at threshold=0.40: 0.1632
- FP rate at threshold=0.50: 0.0632

## 3. False Positive Analysis (test set, threshold=0.20)

- Total stable windows: 1,471
- False positives: 923 (62.75%)
- FP predicted prob mean: 0.3349
- FP predicted prob median: 0.3066
- FP predicted prob P25/P75: 0.2474 / 0.4095
- FP abnormal_fraction mean: 0.0037
- FP abnormal_fraction median: 0.0

### FP Subject distribution

| Subject | FP count |
|---|---:|
| S01 | 557 |
| S02 | 366 |

### FP Recording distribution

| Recording | FP count |
|---|---:|
| S01_R01 | 401 |
| S01_R02 | 156 |
| S02_R01 | 118 |
| S02_R02 | 248 |

### FP abnormal_fraction histogram

| AF range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 906 | 0.9816 |
| [0.10, 0.20) | 17 | 0.0184 |
| [0.20, 0.30) | 0 | 0.0000 |
| [0.30, 0.40) | 0 | 0.0000 |
| [0.40, 0.50) | 0 | 0.0000 |
| [0.50, 0.60) | 0 | 0.0000 |
| [0.60, 0.70) | 0 | 0.0000 |
| [0.70, 0.80) | 0 | 0.0000 |
| [0.80, 0.90) | 0 | 0.0000 |
| [0.90, 1.00) | 0 | 0.0000 |

## 4. False Negative Analysis (test set, threshold=0.20)

- Total abnormal windows: 196
- False negatives: 15 (7.65%)
- FN predicted prob mean: 0.1754
- FN predicted prob median: 0.1794
- FN predicted prob P25/P75: 0.1664 / 0.1852
- FN abnormal_fraction mean: 0.6693
- FN abnormal_fraction median: 0.6602

### FN Subject distribution

| Subject | FN count |
|---|---:|
| S01 | 12 |
| S02 | 3 |

### FN abnormal_fraction histogram

| AF range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 0 | 0.0000 |
| [0.10, 0.20) | 0 | 0.0000 |
| [0.20, 0.30) | 2 | 0.1333 |
| [0.30, 0.40) | 1 | 0.0667 |
| [0.40, 0.50) | 1 | 0.0667 |
| [0.50, 0.60) | 2 | 0.1333 |
| [0.60, 0.70) | 2 | 0.1333 |
| [0.70, 0.80) | 2 | 0.1333 |
| [0.80, 0.90) | 0 | 0.0000 |
| [0.90, 1.00) | 5 | 0.3333 |

## 5. Threshold Sensitivity (validation set)

Constraint objective: stable_recall >= 0.75 AND abnormal_recall >= 0.60

| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN | Meets constraint |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0.1 | 0.0361 | 1.0 | 0.3 | 0.2656 | 721 | 0 | no |
| 0.15 | 0.1404 | 0.9709 | 0.3181 | 0.3614 | 643 | 9 | no |
| 0.2 | 0.4318 | 0.7832 | 0.3628 | 0.5318 | 425 | 67 | no |
| 0.25 | 0.5495 | 0.6472 | 0.3724 | 0.5605 | 337 | 109 | no |
| 0.3 | 0.6791 | 0.4628 | 0.3734 | 0.5639 | 240 | 166 | no |
| 0.35 | 0.7406 | 0.2718 | 0.3022 | 0.5059 | 194 | 225 | no |
| 0.4 | 0.7807 | 0.1424 | 0.2115 | 0.4508 | 164 | 265 | no |
| 0.45 | 0.8142 | 0.0615 | 0.1203 | 0.4104 | 139 | 290 | no |
| 0.5 | 0.8449 | 0.0324 | 0.0794 | 0.3994 | 116 | 299 | no |
| 0.55 | 0.9505 | 0.0032 | 0.0263 | 0.4053 | 37 | 308 | no |
| 0.6 | 0.9973 | 0.0 | 0.0 | 0.4138 | 2 | 309 | no |
| 0.7 | 1.0 | 0.0 | 0.0 | 0.4144 | 0 | 309 | no |

### Threshold sensitivity (test set, for reference only)

| Threshold | stable recall | abnormal recall | abnormal precision | macro_f1 | FP | FN |
|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | 0.2617 | 1.0 | 0.1529 | 0.34 | 1086 | 0 |
| 0.15 | 0.2712 | 0.9949 | 0.1539 | 0.3465 | 1072 | 1 |
| 0.2 | 0.3725 | 0.9235 | 0.1639 | 0.4087 | 923 | 15 |
| 0.25 | 0.5411 | 0.75 | 0.1788 | 0.4881 | 675 | 49 |
| 0.3 | 0.6737 | 0.5918 | 0.1946 | 0.5363 | 480 | 80 |
| 0.35 | 0.7559 | 0.4388 | 0.1933 | 0.5471 | 359 | 110 |
| 0.4 | 0.8368 | 0.3418 | 0.2182 | 0.568 | 240 | 129 |
| 0.45 | 0.8824 | 0.2143 | 0.1953 | 0.5463 | 173 | 154 |
| 0.5 | 0.9368 | 0.1429 | 0.2314 | 0.5451 | 93 | 168 |
| 0.55 | 0.9782 | 0.0663 | 0.2889 | 0.5192 | 32 | 183 |
| 0.6 | 0.9973 | 0.0102 | 0.3333 | 0.4783 | 4 | 194 |
| 0.7 | 1.0 | 0.0 | 0.0 | 0.4688 | 0 | 196 |

## 6. Abnormal Fraction Analysis

### Train split abnormal windows

- N abnormal windows in train: 619
- Mean abnormal_fraction: 0.7648
- Median abnormal_fraction: 0.9648
- Min / Max: 0.2031 / 1.0
- P10 / P25 / P75 / P90: 0.3195 / 0.5352 / 1.0 / 1.0

| AF range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 0 | 0.0000 |
| [0.10, 0.20) | 0 | 0.0000 |
| [0.20, 0.30) | 49 | 0.0792 |
| [0.30, 0.40) | 50 | 0.0808 |
| [0.40, 0.50) | 38 | 0.0614 |
| [0.50, 0.60) | 55 | 0.0889 |
| [0.60, 0.70) | 50 | 0.0808 |
| [0.70, 0.80) | 34 | 0.0549 |
| [0.80, 0.90) | 18 | 0.0291 |
| [0.90, 1.00) | 325 | 0.5250 |

### Purity threshold analysis (how many abnormal train windows survive at each AF threshold)

| AF threshold | Kept | Dropped | Kept fraction |
|---|---:|---:|---:|
| >= 0.0 | 619 | 0 | 1.0000 |
| >= 0.1 | 619 | 0 | 1.0000 |
| >= 0.2 | 619 | 0 | 1.0000 |
| >= 0.3 | 570 | 49 | 0.9208 |
| >= 0.4 | 520 | 99 | 0.8401 |
| >= 0.5 | 482 | 137 | 0.7787 |

### Test split abnormal windows

- N abnormal windows in test: 196
- Mean abnormal_fraction: 0.7097
- Median abnormal_fraction: 0.75

| AF range | Count | Fraction |
|---|---:|---:|
| [0.00, 0.10) | 0 | 0.0000 |
| [0.10, 0.20) | 0 | 0.0000 |
| [0.20, 0.30) | 25 | 0.1276 |
| [0.30, 0.40) | 16 | 0.0816 |
| [0.40, 0.50) | 16 | 0.0816 |
| [0.50, 0.60) | 14 | 0.0714 |
| [0.60, 0.70) | 17 | 0.0867 |
| [0.70, 0.80) | 17 | 0.0867 |
| [0.80, 0.90) | 9 | 0.0459 |
| [0.90, 1.00) | 82 | 0.4184 |

## 7. Key Findings and Implications for Ablation

### Root cause hypothesis

- The model was trained with pos_weight_cap=5.0, which strongly penalised stable predictions.
- Val loss exploded from epoch 2 (2.59) onwards, indicating the model overfit to the high pos_weight signal.
- Best checkpoint was epoch 2 (val macro_f1=0.3994) — very early, model barely learned.
- At threshold=0.20, 62.7% of stable windows are falsely classified as abnormal (923/1471).

### Ablation priorities

1. **Reduce pos_weight_cap**: Test 1.0, 2.0, 3.0 to reduce FP explosion.
2. **Lower LR (1e-4)**: Slower training may prevent val loss explosion.
3. **Purity filtering**: Higher abnormal_fraction_threshold may give cleaner signal.
4. **Threshold re-selection**: Use constraint stable>=0.75, abnormal>=0.60 on val.

### DAPHNET single-source risk

- All data is from one dataset (DAPHNET_FOG).
- Subject-aware split ensures no leakage but generalisation to other datasets is unknown.
- Val (S05 only) and test (S01, S02) have different subject characteristics than train.
