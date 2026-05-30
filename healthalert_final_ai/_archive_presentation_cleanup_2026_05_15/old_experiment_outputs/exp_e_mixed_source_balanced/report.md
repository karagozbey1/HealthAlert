# exp_e_mixed_source_balanced

- strategy: Mixed source-balanced sampler
- sources: uci_har, pamap2
- sensor_variant: chest
- normalization: global_train_zscore
- sampler: source_balanced
- clip_after_norm: None
- best_epoch: 2
- best_val_macro_f1: 0.6624
- test_macro_f1: 0.5775
- test_accuracy: 0.6471

## Per-Class Recall
- walking: 0.7914
- sitting: 0.9247
- standing: 0.0138
- lying: 0.7809

## Source Breakdown
- PAMAP2: macro_f1=0.5286, n=1502
- UCI-HAR: macro_f1=0.6397, n=1230

## Training Trace
| Epoch | Train Loss | Val Loss | Val Macro F1 |
|-------|------------|----------|--------------|
| 1 | 1.0826 | 0.8281 | 0.6358 |
| 2 | 0.6245 | 0.5385 | 0.6624 |
| 3 | 0.4772 | 0.5395 | 0.6497 |
| 4 | 0.4134 | 0.4941 | 0.6433 |
| 5 | 0.3735 | 0.5358 | 0.6393 |
| 6 | 0.3409 | 0.6270 | 0.6168 |
| 7 | 0.3248 | 0.8598 | 0.5758 |
| 8 | 0.3060 | 0.7892 | 0.6179 |
| 9 | 0.2898 | 0.9836 | 0.6308 |
| 10 | 0.2819 | 0.9637 | 0.6432 |
| 11 | 0.2784 | 0.9443 | 0.6202 |
| 12 | 0.2650 | 1.0483 | 0.5977 |
