# Live Sensor Integration Report

## 1. Executive Summary
- Live sensor ingestion path was added without starting new model training.
- Accepted runtime stack remains unchanged: Fall Expert, PPG Quality Expert, Activity v0 helper, runtime vitals rules, runtime gait rules, personalization, RiskFusionEngine.
- Rejected models remain disabled and are not loaded.

## 2. Sensor Sample Schema
Single live sample accepted by backend:

```json
{
  "patient_id": "demo_patient_001",
  "timestamp": "2026-05-14T12:00:00Z",
  "imu": {
    "acc_x": 0.12,
    "acc_y": 0.05,
    "acc_z": 0.98,
    "gyro_x": 0.01,
    "gyro_y": -0.02,
    "gyro_z": 0.03
  },
  "ppg": {
    "ir": 12345,
    "red": 11234
  },
  "heart_rate": 82,
  "spo2": 97,
  "source": "esp32"
}
```

## 3. Window Buffer Design
- File: `src/healthalert/inference/live_window_buffer.py`
- Target IMU rate: `50 Hz`
- Window size: `4 seconds = 200 samples`
- IMU output shape: `(200, 6)`
- PPG output shape: `(200, 1)` when available
- Missing IMU channels: sample is skipped and does not advance the window
- Sparse PPG: edge fill + zero fill to keep shape stable
- No valid PPG in window: `ppg_window = None`
- Inference is not called before 200 valid IMU samples are buffered

## 4. Firebase/Backend Ingestion Path
- Active live ingestion path: `POST /api/healthalert/sensor-sample`
- FastAPI route file: `src/healthalert/api/routes/live_sensor_routes.py`
- Service file: `src/healthalert/api/services/live_sensor_ingestion_service.py`
- Firebase adapter file added as optional future hook:
  - `src/healthalert/live/firebase_sensor_adapter.py`
- Current repo has no active Firestore wiring, so backend endpoint is the default path

## 5. HybridInferenceService Connection
- When the window becomes ready, the ingestion service builds a `HybridInferenceRequest`
- It then calls `HybridInferenceAPIService.infer()`
- Final mobile-safe response schema remains stable and unchanged

## 6. Inference Event Persistence
- JSON fallback persistence added
- Directory:
  - `outputs/hybrid_redesign/live_events/`
- Files per patient:
  - `<patient_id>_events.jsonl`
  - `<patient_id>_latest.json`
- Stored fields include:
  - `patient_id`
  - `timestamp`
  - `risk`
  - `experts`
  - `personalization`
  - `missing_modalities`
  - `ui`
  - `data_mode = live`

## 7. Mobile Live Display Fields
Mobile should read:
- `patient_id`
- `timestamp`
- `risk.final_risk_score`
- `risk.risk_level`
- `risk.recommended_action`
- `risk.reasons`
- `ui.title`
- `ui.message`
- `ui.color_level`
- `ui.show_alert`
- `ui.ask_user_confirmation`

## 8. Missing Modality Behavior
- IMU present, PPG missing:
  - no crash
  - window still forms
  - inference runs
  - `ppg_missing` is returned
- IMU + PPG present:
  - full runtime path runs
- baseline missing:
  - `cold_start_mode = true`
  - personalization stays neutral
- incomplete IMU sample:
  - sample skipped
  - inference not triggered early

## 9. Tests Run
- `tests/test_live_window_buffer.py`
- `tests/test_live_sensor_ingestion.py`
- `tests/test_live_inference_pipeline.py`
- Existing API and inference tests were re-run together
- Result: `29 passed, 0 failed`

## 10. Demo Live Flow
1. ESP32 sample arrives at `POST /api/healthalert/sensor-sample`
2. Sample is validated against live sample schema
3. Patient-specific `LiveWindowBuffer` stores the sample
4. Before 200 IMU samples: backend returns `buffering`
5. At 200 IMU samples: backend triggers inference
6. Result is persisted to JSON fallback files
7. Mobile can consume the returned response immediately

## 11. Remaining Limitations
- Live path currently uses backend endpoint as the active integration path
- Firebase is not yet wired to a real project/client in this repo
- PPG raw `ir/red` is simplified into a single runtime PPG stream for inference
- Activity model is still temporary helper context quality

## 12. Next Step
- Align the payload exactly with real ESP32 firmware output
- Then connect either:
  - Firebase live stream adapter, or
  - direct backend POST from mobile/gateway layer
