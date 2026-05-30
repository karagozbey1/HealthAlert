# HealthAlert Final Presentation README

## 1. Proje nasil calistirilir?

Backend runtime final kabul edilen model yollarini `config/hybrid_runtime_config.yaml` dosyasindan okur. Yeni egitim baslatmadan, mevcut accepted artifact'ler ile API/live pipeline calistirilir.

## 2. Backend komutu

```powershell
C:\project\HealthAlert\.venv311\Scripts\python.exe -m uvicorn src.healthalert.api.app:app --host 0.0.0.0 --port 18765
```

## 3. Endpoint

`POST /api/healthalert/sensor-sample`

## 4. Final accepted models

- Fall: `outputs/hybrid_redesign/fall_expert_core_no_umafall/best_model.pt`
- PPG quality: `outputs/hybrid_redesign/ppg_quality_expert/best_model.pt`
- Activity: `outputs/hybrid_redesign/activity_expert_v2_uci_only/best_model.pt`
- Gait auxiliary: `outputs/hybrid_redesign/gait_instability_v2_ablation/pw2.0_lr3e-04_ft0.30/best_model.pt`

Norm stats:

- `outputs/hybrid_redesign/fall_expert_core_no_umafall/imu_norm_stats.json`
- `outputs/hybrid_redesign/ppg_quality_expert/ppg_norm_stats.json`
- `outputs/hybrid_redesign/activity_expert_v2_uci_only/imu_norm_stats.json`
- `outputs/hybrid_redesign/gait_instability_v2_ablation/pw2.0_lr3e-04_ft0.30/imu_norm_stats.json`

## 5. Runtime disabled models

- `activity_v0`
- `activity_balanced_v1`
- `activity_v2_pamap2_mixed`
- `gait_v2_2`
- `old_gait_instability`
- `vitals_context_expert`
- `vitals_context_model`
- `tremor_context`

## 6. Demo output paths

- `outputs/hybrid_redesign/live_stream/`
- `outputs/hybrid_redesign/live_stream/live_stream_demo_outputs.json`
- `outputs/hybrid_redesign/live_stream/live_inference_events.jsonl`
- `outputs/hybrid_redesign/live_stream/{patient_id}_latest.json`
- `outputs/hybrid_redesign/final_runtime/final_hybrid_inference_demo_outputs.json`

Final raporlar:

- `outputs/hybrid_redesign/final_runtime/final_runtime_readiness_report.md`
- `outputs/hybrid_redesign/live_stream/final_live_demo_readiness_report.md`
- `outputs/hybrid_redesign/live_stream/endpoint_live_test_report.md`
- `outputs/hybrid_redesign/live_stream/esp32_payload_compatibility_report.md`
- `outputs/hybrid_redesign/mobile_backend_integration/mobile_risk_screen_binding.md`

## 7. ESP32 firmware config notlari

Firmware dosyalari repo kokundeki `../firmware/` altindadir:

- `../firmware/include/ha_config.h`
- `../firmware/include/ha_packet.h`
- `../firmware/include/ha_transport.h`
- `../firmware/include/ha_wifi_transport.h`
- `../firmware/src/main.cpp`

`ha_config.h` icinde demo varsayilanlari:

- `HA_PATIENT_ID`: `demo_patient_001`
- `MODEL_WINDOW_SIZE`: `200`
- `MODEL_WINDOW_DURATION_MS`: `4000`
- `TRANSPORT_MODE`: `0`
- `FORCE_MOCK_MODE`: `1`
- `WIFI_BACKEND_URL`: demo agina gore guncellenebilir

## 8. Mobilin okuyacagi latest JSON path

Varsayilan demo hasta icin:

`outputs/hybrid_redesign/live_stream/demo_patient_001_latest.json`

Genel format:

`outputs/hybrid_redesign/live_stream/{patient_id}_latest.json`

## 9. Sinirlamalar

- Klinik teshis degildir.
- Activity modeli UCI-HAR-only single-source baseline olarak kabul edildi.
- Gait modeli low-weight auxiliary katkidir; standalone kritik karar vermez.
- Firebase credentials yoksa JSON fallback kullanilir.
