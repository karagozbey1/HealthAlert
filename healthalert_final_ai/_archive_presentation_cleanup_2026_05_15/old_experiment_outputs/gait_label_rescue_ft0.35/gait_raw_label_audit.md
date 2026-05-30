# Gait Raw Label Audit

## Summary

- Raw DAPHNET files scanned: 17
- Raw label counts: {0: 777052, 1: 1030050, 2: 110785}
- Loader label counts: {'unannotated': 777052, 'normal': 1030050, 'freeze': 110785}
- pre_freeze present in raw files: False
- freeze present in raw files: True
- label 0 meaning selected: unannotated_ignore_for_gait_fraction_not_normal

## Config vs Loader

- datasets.yaml mapping before fix: {'0': 'normal', '1': 'pre_freeze', '2': 'freeze'}
- datasets.yaml mapping after fix: {'0': 'unannotated', '1': 'normal', '2': 'freeze'}
- loader mapping after fix: {'0': 'unannotated', '1': 'normal', '2': 'freeze'}

## Notes

- Current local raw files contain labels 0, 1, and 2 only.
- There is no separate pre_freeze raw label in the local raw files.
- Label 0 is treated as unannotated and preserved in the timeline.