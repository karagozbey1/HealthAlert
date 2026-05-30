# exp_f_mixed_class_source_balanced

- strategy: Mixed class+source balanced sampler
- sources: uci_har, pamap2
- sensor_variant: chest
- normalization: global_train_zscore
- sampler: class_source_balanced
- clip_after_norm: None
- best_epoch: 6
- best_val_macro_f1: 0.8684
- test_macro_f1: 0.6496
- test_accuracy: 0.7108

## Per-Class Recall
- walking: 0.9672
- sitting: 0.7992
- standing: 0.3029
- lying: 0.5600

## Source Breakdown
- PAMAP2: macro_f1=0.5632, n=1502
- UCI-HAR: macro_f1=0.7716, n=1230

## Training Trace
| Epoch | Train Loss | Val Loss | Val Macro F1 |
|-------|------------|----------|--------------|
| 1 | 1.0753 | 0.8187 | 0.6042 |
| 2 | 0.6424 | 0.5509 | 0.6659 |
| 3 | 0.5071 | 0.4382 | 0.7260 |
| 4 | 0.4264 | 0.3941 | 0.8680 |
| 5 | 0.3642 | 0.3618 | 0.8682 |
| 6 | 0.3166 | 0.3821 | 0.8684 |
| 7 | 0.3083 | 0.4945 | 0.7869 |
| 8 | 0.2903 | 0.5492 | 0.7676 |
| 9 | 0.2742 | 0.5619 | 0.7804 |
| 10 | 0.2744 | 0.7502 | 0.7114 |
| 11 | 0.2665 | 0.7574 | 0.6840 |
| 12 | 0.2545 | 0.8492 | 0.6710 |
| 13 | 0.2610 | 0.7979 | 0.6747 |
| 14 | 0.2562 | 0.8028 | 0.6859 |
| 15 | 0.2502 | 0.9323 | 0.6575 |
| 16 | 0.2480 | 0.8388 | 0.6765 |
