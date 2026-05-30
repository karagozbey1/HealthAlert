# exp_g_mixed_global_zscore_clipped

- strategy: Mixed global z-score plus channel clipping
- sources: uci_har, pamap2
- sensor_variant: chest
- normalization: global_train_zscore
- sampler: shuffle
- clip_after_norm: 5.0
- best_epoch: 4
- best_val_macro_f1: 0.8661
- test_macro_f1: 0.6159
- test_accuracy: 0.6691

## Per-Class Recall
- walking: 0.8415
- sitting: 0.9372
- standing: 0.2134
- lying: 0.5774

## Source Breakdown
- PAMAP2: macro_f1=0.4679, n=1502
- UCI-HAR: macro_f1=0.8239, n=1230

## Training Trace
| Epoch | Train Loss | Val Loss | Val Macro F1 |
|-------|------------|----------|--------------|
| 1 | 1.1423 | 0.8964 | 0.6985 |
| 2 | 0.6151 | 0.5598 | 0.6727 |
| 3 | 0.4335 | 0.4340 | 0.7305 |
| 4 | 0.3601 | 0.3551 | 0.8661 |
| 5 | 0.3014 | 0.3830 | 0.8484 |
| 6 | 0.2684 | 0.5333 | 0.7345 |
| 7 | 0.2662 | 0.4086 | 0.8223 |
| 8 | 0.2420 | 0.4590 | 0.7954 |
| 9 | 0.2298 | 0.3941 | 0.8406 |
| 10 | 0.2460 | 0.4404 | 0.8215 |
| 11 | 0.2079 | 0.4992 | 0.7903 |
| 12 | 0.2069 | 0.5061 | 0.7982 |
| 13 | 0.2080 | 0.4884 | 0.8415 |
| 14 | 0.2058 | 0.4380 | 0.8405 |
