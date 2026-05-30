# Activity v2 Pure ADL Dataset Audit

Decision: READY_FOR_ACTIVITY_V2_DATASET_BUILD

## Key Findings
- Current activity_context export is contaminated by generic normal/instability sources and is not suitable for pure ADL training.
- Usable pure ADL sources available now: PAMAP2, UCI-HAR.
- UCI-HAR preserves walking/sitting/standing/lying labels end-to-end and remains the active training source in the current repo snapshot.
- MobiAct loader is integrated for pure ADL, but the raw folder is empty in this repo snapshot.
- PAMAP2 raw path exists and is integrated into the pure ADL builder.

## Dataset Feasibility

### UCI-HAR
- status: ok
- raw_path_exists: True
- n_records: 10299
- n_unique_subjects: 30
- pure_label_support: {"standing": 1906, "sitting": 1777, "lying": 1944, "walking": 4672}
- pure_label_missing: []
- note: Provides all four target labels with preserved subject IDs.

### MobiAct
- status: partial
- raw_path_exists: True
- n_records: 0
- n_unique_subjects: 0
- pure_label_support: {}
- pure_label_missing: ["walking", "sitting", "standing", "lying"]
- note: Could provide pure ADL via activity_code metadata, but current raw data is missing in repo.
- error: No CSV files found under C:\project\HealthAlert\healthalert_final_ai\data\raw\mobiact

### PAMAP2
- status: ok
- raw_path_exists: True
- n_records: 32
- n_unique_subjects: 8
- pure_label_support: {"lying": 8, "sitting": 8, "standing": 8, "walking": 8}
- pure_label_missing: []
- note: Parser recovers lying/sitting/standing/walking segments from Protocol files.

### UniMiB-SHAR
- status: ok
- raw_path_exists: True
- n_records: 11771
- n_unique_subjects: 11771
- pure_label_support: {}
- pure_label_missing: ["walking", "sitting", "standing", "lying"]
- note: ADL windows are collapsed to normal; subclasses are not preserved.

### UMAFall
- status: ok
- raw_path_exists: True
- n_records: 1492
- n_unique_subjects: 19
- pure_label_support: {}
- pure_label_missing: ["walking", "sitting", "standing", "lying"]
- note: ADL is exposed only as normal; sitting/standing/lying subclasses are absent.

### SisFall
- status: ok
- raw_path_exists: True
- n_records: 10318
- n_unique_subjects: 469
- pure_label_support: {}
- pure_label_missing: ["walking", "sitting", "standing", "lying"]
- note: Current repo copy is instability/normal oriented, not clean ADL context.

## PAMAP2
- present_in_config: True
- raw_path_exists: True
- feasibility: PAMAP2 raw path exists and is integrated into the pure ADL builder.
