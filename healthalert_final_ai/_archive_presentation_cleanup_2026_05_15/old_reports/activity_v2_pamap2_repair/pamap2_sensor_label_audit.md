# PAMAP2 Sensor / Label Audit

## Loader Facts
- Current loader supports `chest`, `hand`, and `ankle` variants via `pamap2_sensor_variant`.
- The current mixed baseline used `chest_acc6_x/y/z + chest_gyro_x/y/z`.
- No unit conversion is applied in the PAMAP2 loader; raw numeric values are passed through as provided by PAMAP2 files.
- 100 Hz -> 50 Hz happens in shared window normalization via linear interpolation to 200 samples over 4 seconds.
- Label mapping is explicit and consistent in both config and loader: 1=lying, 2=sitting, 3=standing, 4=walking.
- Segments are formed by contiguous runs of the same activity_id inside each subject protocol file.

## Sensor Placement Audit
- UCI-HAR source is smartphone-on-waist and uses total acceleration plus gyroscope.
- PAMAP2 chest is central-body but not waist-mounted; frame/orientation and wearing dynamics still differ from UCI-HAR.
- PAMAP2 hand and ankle are farther from the runtime body location implied by UCI-HAR and are expected to increase domain gap further.

## Runtime Comparison
| Variant | Combined Macro F1 | UCI-HAR Macro F1 | PAMAP2 Macro F1 | Notes |
|---------|-------------------|------------------|-----------------|-------|
| chest | 0.7096 | 0.8355 | 0.6266 | closest central-body option |
| hand | 0.7558 | 0.8466 | 0.6933 | larger location mismatch vs UCI-HAR waist smartphone |
| ankle | 0.7935 | 0.8773 | 0.7392 | larger location mismatch vs UCI-HAR waist smartphone |

## Conclusion
- Best runtime variant in this repair run: ankle.
- If even the best PAMAP2 variant remains far below UCI-only baseline, the issue is broader than label-map correctness and points to source mismatch.
- The current evidence does not show a broken label mapping; the bigger risk is sensor placement / motion-domain mismatch.
