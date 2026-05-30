# HealthAlert Manual Dataset Layout Status

_Generated: 2026-05-12T22:10:08.010847+00:00_

## Summary

| Status | Count |
|--------|-------|
| ready | 15 |
| empty | 4 |
| missing | 0 |
| partial | 0 |
| unsupported_vision_only | 0 |
| needs_loader_update | 0 |
| unknown_format | 0 |

## Dataset Details

| Dataset | Status | Files | Warnings |
|---------|--------|-------|----------|
| hifd | ready | 350 |  |
| weda_fall | ready | 15348 |  |
| but_ppg | ready | 27126 |  |
| sisfall | ready | 12691 |  |
| upfall | ready | 2 |  |
| umafall | ready | 1504 |  |
| unimib_shar | ready | 16 |  |
| mobiact | empty | 0 | Directory exists but contains no files |
| uci_har | ready | 64 |  |
| fallalld | empty | 0 | Directory exists but contains no files |
| bidmc | ready | 106 |  |
| ppg_dalia | ready | 78 |  |
| wesad | ready | 182 |  |
| wildppg | ready | 18 |  |
| bits2_geriatric_fall_hr | ready | 1633 |  |
| daphnet_fog | ready | 30 |  |
| pads_smartwatch_pd | empty | 1 | Only README file(s) present — dataset not yet downloaded. |
| hand_tremor_mpu9250 | ready | 2 |  |
| fallalld_sensor_only | empty | 1 | Only README file(s) present — dataset not yet downloaded. |

## Task Assignments

**activity_context:** hifd (ready), sisfall (ready), upfall (ready), unimib_shar (ready), uci_har (ready), ppg_dalia (ready), wildppg (ready), bits2_geriatric_fall_hr (ready)

**adl_detection:** hifd (ready), weda_fall (ready), upfall (ready), umafall (ready), unimib_shar (ready), uci_har (ready)

**fall_detection:** hifd (ready), weda_fall (ready), upfall (ready), umafall (ready), unimib_shar (ready), bits2_geriatric_fall_hr (ready)

**freezing_of_gait:** daphnet_fog (ready)

**gait_instability:** daphnet_fog (ready)

**movement_anomaly:** sisfall (ready), daphnet_fog (ready), hand_tremor_mpu9250 (ready)

**physiology_context:** bidmc (ready), wesad (ready)

**ppg_quality:** but_ppg (ready), bidmc (ready), ppg_dalia (ready), wesad (ready), wildppg (ready)

**tremor_context:** hand_tremor_mpu9250 (ready)

**vitals_context:** but_ppg (ready), bidmc (ready), ppg_dalia (ready), wesad (ready), wildppg (ready), bits2_geriatric_fall_hr (ready)


## Download Priority Order

### Priority 1

- **sisfall** — `ready` — http://sistemic.udea.edu.co/en/research/projects/falls/
- **unimib_shar** — `ready` — http://www.sal.disco.unimib.it/technologies/unimib-shar/
- **ppg_dalia** — `ready` — https://archive.ics.uci.edu/ml/datasets/PPG-DaLiA
- **bits2_geriatric_fall_hr** — `ready` — https://zenodo.org/records/8082667

### Priority 2

- **wesad** — `ready` — https://archive.ics.uci.edu/dataset/465/wesad
- **umafall** — `ready` — https://figshare.com/articles/dataset/UMA_ADL_FALL_Dataset_zip/4214283
- **upfall** — `ready` — https://sites.google.com/up.edu.mx/har-up/
- **daphnet_fog** — `ready` — https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait

### Priority 3

- **pads_smartwatch_pd** — `empty` — https://physionet.org/content/parkinsons-disease-smartwatch/
- **hand_tremor_mpu9250** — `ready` — https://www.kaggle.com/datasets/aaryapandya/hand-tremor-dataset-collected-using-mpu9250-sensor
- **wildppg** — `ready` — https://github.com/eth-siplab/WildPPG
- **fallalld_sensor_only** — `empty` — 

## Validation Commands

```bash
# Re-run validation
python scripts/validate_manual_dataset_layout.py

# After adding datasets, rebuild the windowed dataset
python scripts/build_multi_source_windowed_dataset.py

# Run all tests
python -m pytest healthalert_final_ai/tests/ -v --tb=short
```

_Bu rapor otomatik üretilmiştir. Değiştirmeyin._
