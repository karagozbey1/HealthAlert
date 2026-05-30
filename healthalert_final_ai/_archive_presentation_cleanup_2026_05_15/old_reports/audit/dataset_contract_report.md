# HealthAlert Hybrid Dataset Contract Report

_Generated: 2026-05-13 20:40 UTC_

## Dataset Status Overview

| Dataset | raw | std | windowed | splits | modalities | subject-split |
|---------|-----|-----|----------|--------|------------|---------------|
| bidmc | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| bits2_geriatric_fall_hr | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| but_ppg | ✓ | ✗ | ✗ | ✗ | acc, heart, imu, metadata, ppg | ✗ |
| daphnet_fog | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| fallalld | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| fallalld_sensor_only | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| gaitpdb | ✓ | ✗ | ✗ | ✗ | metadata | ✗ |
| hand_tremor_mpu9250 | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| hifd | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| mobiact | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| pads_smartwatch_pd | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| ppg_dalia | ✓ | ✗ | ✗ | ✗ | ppg | ✗ |
| sisfall | ✓ | ✗ | ✗ | ✗ | handcrafted | ✓ |
| uci_har | ✓ | ✗ | ✗ | ✗ | acc, gyro, handcrafted, imu, metadata | ✓ |
| umafall | ✓ | ✗ | ✗ | ✗ | metadata | ✓ |
| unimib_shar | ✓ | ✗ | ✗ | ✗ | acc, imu, metadata | ✗ |
| upfall | ✓ | ✗ | ✗ | ✗ | — | ✗ |
| weda_fall | ✓ | ✗ | ✗ | ✗ | acc, gyro, imu | ✗ |
| wesad | ✓ | ✗ | ✗ | ✗ | acc, heart, imu, ppg | ✗ |
| wildppg | ✓ | ✗ | ✗ | ✗ | ppg | ✗ |

## Task Routing Compliance

| Dataset | fall_detection | activity_context | ppg_quality | vitals_context | gait_instability | tremor_context |
|---------|--------|--------|--------|--------|--------|--------|
| bidmc | forbidden | forbidden | allowed | allowed | forbidden | not_applicable |
| bits2_geriatric_fall_hr | allowed | not_applicable | forbidden | forbidden | allowed | not_applicable |
| but_ppg | forbidden | forbidden | allowed | forbidden | forbidden | not_applicable |
| daphnet_fog | forbidden | forbidden | forbidden | forbidden | allowed | not_applicable |
| fallalld | not_applicable | not_applicable | not_applicable | not_applicable | not_applicable | not_applicable |
| fallalld_sensor_only | allowed | not_applicable | forbidden | forbidden | forbidden | not_applicable |
| gaitpdb | forbidden | forbidden | forbidden | forbidden | allowed | not_applicable |
| hand_tremor_mpu9250 | forbidden | forbidden | forbidden | forbidden | forbidden | allowed (task disabled) |
| hifd | allowed | not_applicable | allowed | allowed | forbidden | not_applicable |
| mobiact | allowed | allowed | forbidden | forbidden | forbidden | not_applicable |
| pads_smartwatch_pd | forbidden | forbidden | forbidden | forbidden | allowed | not_applicable |
| ppg_dalia | forbidden | forbidden | allowed | allowed | forbidden | not_applicable |
| sisfall | not_applicable | allowed | forbidden | forbidden | allowed | not_applicable |
| uci_har | forbidden | allowed | forbidden | forbidden | forbidden | not_applicable |
| umafall | allowed | allowed | forbidden | forbidden | forbidden | not_applicable |
| unimib_shar | allowed | allowed | forbidden | forbidden | forbidden | not_applicable |
| upfall | allowed | not_applicable | forbidden | forbidden | forbidden | not_applicable |
| weda_fall | allowed | not_applicable | forbidden | forbidden | forbidden | not_applicable |
| wesad | forbidden | forbidden | allowed | allowed | forbidden | not_applicable |
| wildppg | forbidden | forbidden | allowed | allowed | forbidden | not_applicable |

## Per-Task Dataset Summary

### fall_detection
- **Enabled for training**: True
- **Primary modality**: imu
- **Allowed datasets**: umafall, upfall, weda_fall, unimib_shar, hifd, bits2_geriatric_fall_hr, mobiact, fallalld_sensor_only
- **Available (raw exists)**: bits2_geriatric_fall_hr, fallalld_sensor_only, hifd, mobiact, umafall, unimib_shar, upfall, weda_fall

### activity_context
- **Enabled for training**: True
- **Primary modality**: imu
- **Allowed datasets**: uci_har, unimib_shar, umafall, mobiact, sisfall
- **Available (raw exists)**: mobiact, sisfall, uci_har, umafall, unimib_shar

### ppg_quality
- **Enabled for training**: True
- **Primary modality**: ppg
- **Allowed datasets**: but_ppg, ppg_dalia, wildppg, wesad, bidmc, hifd
- **Available (raw exists)**: bidmc, but_ppg, hifd, ppg_dalia, wesad, wildppg

### vitals_context
- **Enabled for training**: True
- **Primary modality**: ppg_or_vitals
- **Allowed datasets**: bidmc, wesad, ppg_dalia, wildppg, hifd
- **Available (raw exists)**: bidmc, hifd, ppg_dalia, wesad, wildppg

### gait_instability
- **Enabled for training**: True
- **Primary modality**: imu
- **Allowed datasets**: daphnet_fog, gaitpdb, pads_smartwatch_pd, bits2_geriatric_fall_hr, sisfall
- **Available (raw exists)**: bits2_geriatric_fall_hr, daphnet_fog, gaitpdb, pads_smartwatch_pd, sisfall

### tremor_context
- **Enabled for training**: False
- **Reason disabled**: low_data_optional
- **Primary modality**: imu
- **Allowed datasets**: hand_tremor_mpu9250
- **Available (raw exists)**: hand_tremor_mpu9250

## Window Shape & Label Distribution (where available)

## Blocking Issues

No blocking issues detected. All enabled tasks have at least one available dataset.

---

_End of dataset contract report._
