# HealthAlert — Model, Veri Analizi, Mock/Canlı Veri Akışı ve Sonraki Mimari Adım Analizi

> **Tarih:** 29 Nisan 2026  
> **Görev Modu:** Audit-only — Sadece inceleme ve raporlama. Kodda hiçbir değişiklik yapılmamıştır.  
> **Kapsam:** backend/, firmware/, host_bridge/, mobile/, healthalert_final_ai/, Data/, outputs/, report_bundle/

---

## BÖLÜM 1 — Executive Summary

### Projenin Model/Veri Analizi Tarafında Mevcut Durumu

HealthAlert, gerçek anlamda **katmanlı bir mimari** üzerine kurulmuştur. ML pipeline (`healthalert_final_ai/`) ile canlı backend sistemi (`backend/`) **aynı projede** olmalarına karşın şu anda **birbirinden bağımsız** çalışmaktadır. Bu durum en kritik mimari eksik olarak öne çıkmaktadır.

### Şu An Canlı Veri Nasıl Analiz Ediliyor?

**Canlı ingest yolunda ML modeli çalışmıyor.** `POST /ingest/device-packet` endpointi (`backend/routers/ingestion_router.py`) anlık paketi aldığında şu işlemler sırayla yapılmaktadır:

1. Tekrar eden paket filtresi (`_is_duplicate`)
2. Cihaz paketi veritabanına loglanır (`repos.devices.log_packet`)
3. `_compute_motion_score()` — saf heuristik: ivme sapması + jiroskop büyüklüğü
4. `_compute_risk_score()` — saf heuristik: HR/SpO2/motion eşik tabanlı ağırlıklı toplam
5. `LiveStatus` güncellenir
6. Eşik aşılırsa `AnomalyEvent` → `AlertEvent` → bildirim zinciri

Bu akışta model checkpoint'i yüklenmez, `HealthAlertPredictor` çağrılmaz, `RiskPostprocessorV2` kullanılmaz.

**Kısa yanıt:** Anlık veri analizi şu anda tamamen kural tabanlı heuristik üzerinden yapılmaktadır.

### Model Eğitimi ve Canlı Inference Arasındaki Ayrım

- **Eğitim:** `healthalert_final_ai/` altında, offline, sabit veri setleri üzerinde gerçekleştirilmiştir. 4 checkpoint üretilmiştir: `best_fall_model.pt`, `best_quality_model.pt`, `best_multitask_model.pt`, `best_final_fusion_model.pt`. Bunlar `outputs/models/` altındadır.
- **Canlı Inference:** `healthalert_final_ai/src/inference/predictor.py` → `HealthAlertPredictor` sınıfı mevcuttur ve gerçek zamanlı EMA destekli inference için tasarlanmıştır. Ancak bu sınıf backend canlı akışına **bağlanmamıştır**.
- **Köprü Kodu:** `backend/services/ai_bridge.py` → `process_ai_result()` fonksiyonu bulunmaktadır. Bu fonksiyon bir AI modelinin çıktısını backend repository katmanına aktarmak için tasarlanmıştır. `backend/routers/ingestion_router.py`'de `POST /ingest/ai-inference` endpoint'i de mevcuttur (`AIInferenceRequest` schema ile). Ancak bu endpoint dışarıdan çağrılmaktadır — backend `device-packet` ingest yolu kendin ML modeline bağlanıp çağırmaz.

### Mevcut Sistemde Kişiselleştirme Var mı?

**Hayır.** Risk eşikleri `backend/config.py`'de global sabittir:
- `RISK_CRITICAL_THRESHOLD: 0.75`
- `RISK_WARNING_THRESHOLD: 0.55`
- `RISK_WATCH_THRESHOLD: 0.30`

Veritabanında kullanıcıya özel baseline tablosu yoktur. `AppSettings` modeli yalnızca `battery_mode`, `notifications_enabled`, `sync_interval_sec`, `alert_sensitivity` gibi UI tercihlerini tutar; fizyolojik baseline değerleri içermez. Kişisel HR ortalaması, SpO2 ortalaması veya bireysel sapma analizi için hiçbir tablo, servis veya hesaplama mekanizması bulunmamaktadır.

### RAG/Benzer Örnek Getirme Mimarisi İçin Mevcut Altyapı Uygun mu?

**Uygunluk var ama eksikler kritik:** `healthalert_final_ai/src/data/feature_engineering/feature_pipeline.py` → `extract_all_handcrafted_features()` fonksiyonu ~38 boyutlu feature vektörü üretmektedir. Bu vektör, her veri seti penceresi için hesaplanmaya uygundur. `healthalert_final_ai/src/data/preprocessing/windowing.py` → `extract_windows()` fonksiyonu 200 sample (4 saniyelik) pencereler oluşturabilmektedir. **Eksik:** Üretilen vektörler için bir index (FAISS, sklearn NearestNeighbors, vb.) oluşturulup kaydedilmemiştir. Canlı pencere ile dataset penceresi arasında nearest-neighbor araması yapan hiçbir kod yoktur.

### En Büyük Eksikler

1. ML model → backend canlı ingest akışı bağlantısı yok (köprü kodu var ama bağlı değil)
2. Kişisel baseline tablosu ve kişiye özel risk kalibrasyonu yok
3. Canlı ingest yolunda sliding window buffer yok — her paket tek başına işleniyor
4. RAG/retrieval feature index dosyası yok
5. PPG kalite skoru canlı risk kararında kullanılmıyor (sadece simülasyon dışındaki AI path'te kullanılıyor)
6. Trend servisi (`backend/services/trend_service.py`) anomali geçmişini analiz ediyor ancak bu bilgi `_compute_risk_score()` fonksiyonuna geri besleme yapmıyor

### Sonraki Adım İçin En Mantıklı Teknik Yön

Mevcut mimarinin en kritik eksiği canlı ML inference bağlantısının olmaması değil, aksine **kişisel baseline**'ın olmamasıdır. Model her kullanıcıya aynı eşiklerle davranıyor; bu bitirme projesi bağlamında önce kişisel baseline MVP'nin kurulması, ardından canlı ML inference bağlantısının eklenmesi en sağlıklı sıra olacaktır.

---

## BÖLÜM 2 — Evidence Map

| Konu | Dosya yolu | Sınıf/Fonksiyon/Config | Bulgu | Not |
|---|---|---|---|---|
| Firmware sensör okuma | `firmware/src/main.cpp` | `setup()`, `loop()` | I2C SDA=21, SCL=22, 400kHz; MPU6050 + MAX30102 | FORCE_MOCK_MODE ile override edilebilir |
| Firmware mock mode | `firmware/include/ha_config.h` | `FORCE_MOCK_MODE` | `1` = her zaman mock, `0` = auto-detect | Compile-time config |
| Firmware mock senaryolar | `firmware/include/ha_mock_sensors.h` | `MockSensors`, `ScenarioProfile` | 7 senaryo: normal, elevated_hr, low_spo2, motion_instability, warning_state, critical_state, recovery_state | Sinüzoidal + gürültü |
| JSON packet format | `host_bridge/packet_schema.py` | `DevicePacketSchema` | device_id, timestamp_ms, mode, accel_x/y/z, gyro_x/y/z, red_value, ir_value, hr, spo2, signal_quality, hr_valid, spo2_valid, finger_detected, state_hint | Real/mock aynı şema |
| Backend ingest endpoint | `backend/routers/ingestion_router.py` | `POST /ingest/device-packet` | Paket alır, motion_score + risk_score hesaplar, LiveStatus günceller | ML model kullanılmıyor |
| Backend risk scoring | `backend/routers/ingestion_router.py` | `_compute_risk_score()` | HR/SpO2/motion eşik tabanlı ağırlıklı toplam | Tamamen heuristik |
| Backend motion scoring | `backend/routers/ingestion_router.py` | `_compute_motion_score()` | `accel_dev * 2.0 + gyro_mag / 50.0` | Kural tabanlı |
| Backend risk eşikleri | `backend/config.py` | `RISK_CRITICAL_THRESHOLD=0.75`, `RISK_WARNING_THRESHOLD=0.55`, `RISK_WATCH_THRESHOLD=0.30` | Global sabit, kişiselleştirme yok | Pydantic Settings |
| Backend simulation | `backend/services/simulation.py` | `SCENARIO_SEQUENCE`, `_tick_user()` | 10 senaryo, 4 saniyelik aralıklarla backend repository üzerinden işler | `start_simulation_loop` startup'ta başlatılır |
| Firestore watcher | `backend/services/firestore_watcher.py` | — | Dosya mevcut (listelendi) fakat detay okunmadı | Firestore okuma akışı için |
| Mobile live data service | `mobile/lib/core/services/live_data_service.dart` | `LiveDataService`, `start()`, `_generateDemoStatus()` | Demo modda yerel veri üretir, fetchFn ile API'dan çeker | `demoMode=true` varsayılan |
| Mobile mock demo service | `mobile/lib/core/services/mock_demo_service.dart` | `MockDemoService.initialAnomalies()` | Sabit 3 anomaly objesi döner | Demo için statik veri |
| ML model mimarisi | `healthalert_final_ai/src/models/multitask_model_v2.py` | `HealthAlertModelV2` | IMU-CRNN + PPG-CNN + VitalsMLP + HandcraftedMLP → FusionAttention → 4 head | Modality-mask destekli |
| ML veri preprocessing | `healthalert_final_ai/src/data/preprocessing/windowing.py` | `extract_windows()` | 200 sample window, 50 stride | 4s @ 50Hz |
| Feature engineering | `healthalert_final_ai/src/data/feature_engineering/feature_pipeline.py` | `extract_all_handcrafted_features()` | ~38 boyut: IMU (jerk, RMS, energy, vb.) + PPG (HR istatistikleri, SpO2) + fusion özellikler | NaN-safe, missing modality |
| Inference predictor | `healthalert_final_ai/src/inference/predictor.py` | `HealthAlertPredictor.predict()` | EMA smoothing (alpha=0.3), 4 çıktı: fall_prob, instability_prob, quality_score, risk_score | Backend'e bağlı değil |
| Risk postprocessor | `healthalert_final_ai/src/inference/risk_postprocessor_v2.py` | `RiskPostprocessorV2.process()` | fall×0.35 + instability×0.20 + vital_risk×0.25 + quality_penalty×0.20 → final_risk_level | Backend'e bağlı değil |
| AI bridge | `backend/services/ai_bridge.py` | `process_ai_result()` | AI çıktısını repo katmanına aktaran köprü | Endpoint var, auto-çağrılmıyor |
| AI inference endpoint | `backend/routers/ingestion_router.py` | `POST /ingest/ai-inference` | `AIInferenceRequest` alır, `process_ai_result()` çağırır | Dış çağrı gerektirir |
| Kişiselleştirme altyapısı | `backend/models.py` | `AppSettings`, `User` | battery_mode, notifications_enabled — fizyolojik baseline YOK | Kişisel baseline tablosu eksik |
| Trend servisi | `backend/services/trend_service.py` | `analyze_trends()` | Son 1h/24h anomali/alert sayısı, trend etiketi üretir | Risk score'a geri beslemiyor |
| HIFD dataset | `Data/HIFD/` | 21 konu × fall/non-fall/ | `.mat` dosyaları; ax,ay,az,w,x,y,z,droll,dpitch,dyaw,heart değişkenleri | 50Hz, wrist-worn IMU+PPG |
| BUT_PPG dataset | `Data/BUT_PPG/` | ~150+ kayıt | quality-hr-ann.csv + WFDB .dat/.hea | PPG kalite etiketi (0/1), HR/SpO2 |
| WEDA_FALL dataset | `Data/WEDA_FALL/dataset/` | 5Hz-50Hz alt klasörler | accel/gyro CSV; fall_timestamps.csv | 14 genç + 11 yaşlı |
| Eğitim checkpoint'leri | `outputs/models/` | `best_fall_model.pt`, `best_final_fusion_model.pt`, `best_multitask_model.pt`, `best_quality_model.pt` | Model dosyaları mevcut | Production'a bağlı değil |
| Değerlendirme sonuçları | `outputs/reports/evaluation_report.txt` | — | Fall AUC=0.9447, F1=0.7687; Instability AUC=0.9764; Quality F1=1.0 | Risk MAE=0.1466 |
| RAG/retrieval index | Hiçbir dosya | — | **Bulunamadı** | Feature index yok |
| Kişisel baseline tablosu | `backend/models.py` | — | **Bulunamadı** | UserBaseline modeli yok |
| Canlı window buffer | `backend/routers/ingestion_router.py` | — | **Bulunamadı** | Paket-başına analiz |
| Recommendation engine | `healthalert_final_ai/src/inference/recommendation_engine_v2.py` | `RecommendationEngineV2` | Dosya mevcut | Backend'e bağlı değil |
| Explainability | `healthalert_final_ai/src/inference/explainability_v2.py` | `ExplainabilityV2` | Dosya mevcut | Feature importance / attention maps |

---

## BÖLÜM 3 — Uçtan Uca Veri Akışı

### 3.1 Firmware Gerçek Sensör Akışı

**Dosya:** `firmware/src/main.cpp`, `firmware/include/ha_config.h`, `firmware/include/ha_acquisition.h`

- **MPU6050 ve MAX30102 nerede okunuyor?**  
  `AcquisitionManager::initRealSensors()` (`ha_acquisition.h`) her iki sensörü başlatır. `AcquisitionManager::collect()` her döngüde çağrılır ve `DevicePacket` döner.

- **SDA/SCL pinleri nerede tanımlı?**  
  `firmware/include/ha_config.h` → `I2C_SDA_PIN = 21`, `I2C_SCL_PIN = 22`, `I2C_FREQUENCY = 400000 Hz`

- **Sensör başlatma nasıl yapılıyor?**  
  `firmware/src/main.cpp` → `setup()`:
  1. `Wire.begin(SDA=21, SCL=22)` + `Wire.setClock(400kHz)`
  2. `i2c_scan()` ile cihaz taraması
  3. `FORCE_MOCK_MODE` kontrolü
  4. `acq.begin(useMock)` → gerçek: `acq.initRealSensors()`

- **Sensör bulunamazsa ne oluyor?**  
  `ha_acquisition.h` → `initRealSensors()` başarısız olursa `setMockMode(true)` çağrılır ve `[BOOT] All sensor inits failed → switching to MOCK.` yazdırılır. Graceful fallback.

- **DevicePacket / JSON packet hangi alanları içeriyor?**  
  `host_bridge/packet_schema.py` → `DevicePacketSchema`:  
  `device_id`, `timestamp_ms`, `mode ("real"|"mock")`, `packet_seq`, `accel_x/y/z`, `gyro_x/y/z`, `red_value`, `ir_value`, `heart_rate`, `spo2`, `signal_quality (0-1)`, `imu_ok`, `ppg_ok`, `hr_valid`, `spo2_valid`, `finger_detected`, `state_hint (≤50 char)`

- **Transport nasıl kurgulanmış?**  
  `firmware/src/main.cpp` → `TransportOrchestrator transport` nesnesi; `transport.begin()` startup'ta çağrılır. BLE primer transport; Wi-Fi fallback. USB serial: geliştirme/debug amaçlı.

---

### 3.2 Firmware Mock Veri Akışı

**Dosya:** `firmware/include/ha_mock_sensors.h`, `firmware/include/ha_config.h`

- **FORCE_MOCK_MODE var mı?**  
  Evet. `firmware/include/ha_config.h` → `#define FORCE_MOCK_MODE 1` (compile-time sabit). `1` = her zaman mock, `0` = auto-detect.

- **Mock senaryolar neler?**  
  7 senaryo (ScenarioProfile enum): `SCENARIO_NORMAL`, `ELEVATED_HR`, `LOW_SPO2`, `MOTION_INSTABILITY`, `WARNING_STATE`, `CRITICAL_STATE`, `RECOVERY_STATE`. Her biri HR merkez/genlik, SpO2, ivme, jiroskop, sinyal kalitesi ve parmak algılaması için değer profili içerir.

- **Mock veri gerçek veriyle aynı packet formatına mı dönüşüyor?**  
  Evet. `AcquisitionManager::collect()` hem gerçek hem mock sensörü `DevicePacket` yapısına dönüştürür. `mode` alanı `"mock"` olarak işaretlenir fakat tüm diğer alanlar aynı yapıdadır.

- **Mock veri hangi amaçla kullanılıyor?**  
  Gerçek donanım yokken yazılım geliştirme, entegrasyon testi ve demo sunum amacıyla kullanılır.

---

### 3.3 Backend Ingest Akışı

**Dosya:** `backend/routers/ingestion_router.py`, `backend/config.py`

- **ESP32'den gelen paket hangi endpoint'e gidiyor?**  
  `POST /ingest/device-packet` — JWT doğrulama **gerekmiyor** (cihaz paketi public endpoint).

- **Request schema nedir?**  
  `backend/schemas.py` → `DevicePacketRequest` (Pydantic v2): DevicePacketSchema alanlarının tamamı.

- **motion_score nasıl hesaplanıyor?**  
  ```python
  # backend/routers/ingestion_router.py → _compute_motion_score()
  accel_mag = sqrt(ax² + ay² + az²)
  accel_dev = abs(accel_mag - 1.0)   # 1g'den sapma
  gyro_mag  = sqrt(gx² + gy² + gz²)
  score     = min(1.0, accel_dev * 2.0 + gyro_mag / 50.0)
  ```

- **risk_score nasıl hesaplanıyor?**  
  ```python
  # backend/routers/ingestion_router.py → _compute_risk_score()
  if hr > 120: risk += 0.30
  elif hr > 100: risk += 0.15
  elif hr < 50:  risk += 0.20
  if spo2 < 90:  risk += 0.40
  elif spo2 < 94: risk += 0.20
  risk += motion * 0.20
  ```
  **Bu tamamen kural tabanlı/heuristik bir hesaptır. ML modeli kullanılmamaktadır.**

- **LiveStatus nasıl güncelleniyor?**  
  `repos.live_status.upsert(user_id, {...})` — her pakette; hr_valid/spo2_valid false ise önceki geçerli değer korunur.

- **AnomalyEvent/AlertEvent/NotificationItem/HistoryItem ne zaman oluşuyor?**  
  `severity = _risk_to_severity(risk_score)` → None değilse:
  - Her zaman: `AnomalyEvent` + `HistoryItem(anomaly)` oluşturulur
  - Severity `"warning"` veya `"critical"` ise ve aktif alert yoksa: `AlertEvent` + `HistoryItem(alert)` + fan-out bildirim

- **Bu akışta ML model kullanılıyor mu?**  
  **Hayır.** Sadece `_compute_motion_score()` ve `_compute_risk_score()` fonksiyonları; bunlar saf matematik + eşik kontrolüdür.

---

### 3.4 Backend Simulation/Mock Akışı

**Dosya:** `backend/services/simulation.py`, `backend/main.py`

- **Backend simulation nerede?**  
  `backend/services/simulation.py` → `SCENARIO_SEQUENCE` (10 senaryo listesi) + `_tick_user()` + `start_simulation_loop()`.

- **Hangi senaryolar üretiliyor?**  
  `normal` (×3) → `elevated_hr` (×2) → `warning` → `low_spo2` → `recovery` → `motion_instability` → döngü. Her senaryo için HR/SpO2/motion/risk değerleri uniform random (`_rng(lo, hi)`).

- **Simülasyon verisi gerçek endpoint üzerinden mi, yoksa service/repository üzerinden mi?**  
  Doğrudan **repository katmanı üzerinden** işleniyor (`repos.live_status.upsert`, `repos.anomalies.create`, vb.). HTTP endpoint'e paket göndermiyor. Bu mimari açıdan sağlıklı bir ayrım.

- **Alarm ve bildirim zincirini tetikliyor mu?**  
  Evet. `scenario.fires_anomaly=True` durumunda `repos.anomalies.create` + `_fan_out_notification()`. `scenario.fires_alert=True` durumunda `repos.alerts.create` + fan-out. Countdown sonunda `post_event_monitoring` → tekrar fan-out.

- **Simülasyon ne zaman çalışıyor?**  
  `backend/main.py` → `startup` event handler: `should_run_simulation()` (`config.py`) → `APP_MODE in (demo, staging)` ve `SENSOR_MODE != "real"` ise başlatılır. `backend/.env` dosyasında `AI_MODE=real` mevcut.

---

### 3.5 Firestore / Hybrid Veri Akışı

**Dosya:** `backend/config.py`, `backend/repositories/factory.py`, `backend/firebase_client.py`

- **DATA_MODE ne anlama geliyor?**  
  - `sqlite`: Tüm okuma/yazma SQLite'a gider. Yerel, basit.
  - `firebase`: Tüm okuma/yazma Firestore'a gider. Bulut.
  - `hybrid`: Okuma SQLite'tan, yazma hem SQLite hem Firestore'a. `_HybridRepo` proxy sınıfı.

- **Hybrid modda okuma ve yazma:**  
  `repositories/factory.py` → `_HybridRepo` wrapper: her `create`/`upsert`/`update` metodunda `await self._primary.*` (SQLite) + `await self._secondary.*` (Firestore). Firestore hatası sessizce loglanır, SQLite başarısı yeterli sayılır.

- **Firestore watcher neyi izliyor?**  
  `backend/services/firestore_watcher.py` dosyası mevcut; içerik tam okunmadı ancak isimden ve mimari belgelerden Firestore'daki değişiklikleri dinleyip backend'e bildirdiği anlaşılmaktadır.

- **Firestore yalnızca depo mu, yoksa aktif kaynak mı?**  
  `backend/repositories/firebase/` altındaki implmentasyon detaylarına göre hybrid modda Firestore **hem depo hem yazma hedefi**; watcher ile aktif kaynak da olabilir (mobile → Firestore → backend akışı için).

---

### 3.6 Mobile Veri Tüketimi

**Dosya:** `mobile/lib/core/services/live_data_service.dart`, `mobile/lib/core/services/mock_demo_service.dart`, `mobile/lib/core/services/api_client.dart`

- **Mobile canlı veriyi nereden alıyor?**  
  `LiveDataService.start()` içinde: `demoMode=true` ise `_generateDemoStatus()` (yerel üretim). `fetchFn` sağlanırsa API çağrısı. Prod akışında `fetchFn = api_client.getLiveStatus(userId)`.

- **Demo mod ve canlı mod farkı:**  
  Demo: `_generateDemoStatus()` → Flutter tarafında sinüzoidal + random senaryolar, API çağrısı yok.  
  Canlı: `fetchFn()` → `GET /live/{user_id}` endpoint'inden gerçek `LiveStatus` verisi.  
  **Her iki modda aynı `LiveStatus` modeli döner.** Veri yapısı aynı.

- **API client, BLE, Firestore sync servisleri:**  
  `api_client.dart` — HTTP istemcisi  
  `ble_device_service.dart` — BLE bağlantısı (ESP32'den doğrudan veri alımı)  
  `firestore_sync_service.dart` — Firestore senkronizasyonu  
  `transport_orchestrator.dart` — BLE/WiFi/API geçiş yönetimi

- **SELF/RELATIVE/DOCTOR ekranları canlı veriyi nasıl gösteriyor?**  
  `AppController` (ChangeNotifier) state yönetimi. `LiveDataService.stream` dinlenerek UI güncellenir. SELF: kendi verisini görür. RELATIVE/DOCTOR: `user_id` parametresiyle bağlı kullanıcı verisini çeker.

---

## BÖLÜM 4 — Veri Setleri ve Veri Hazırlama

### 4.1 HIFD (Heart Rate & IMU for Fall Detection)

**Konum:** `Data/HIFD/subject_01/` ... `subject_21/`  
**Yükleyici:** `healthalert_final_ai/src/data/loaders/hifd_loader.py`

- **Modaliteler:** Bilek-takılı IMU (ax, ay, az: ivme; w, x, y, z: quaternion; droll, dpitch, dyaw: açısal hız) + PPG tabanlı `heart` (HR)
- **Etiketler:**  
  - Fall: `fall1..fall6` (6 senaryo)  
  - ADL: `bed, chair, eat, hair, stair, teeth, walk, wash, write` (9 senaryo)  
  - Near-fall: `clap, cloth, shoe, zip` (4 senaryo; label=2)
- **Format:** MATLAB `.mat` dosyası; her değişken ayrı key, `(N, 1)` shape; `N` = kayıt sayısı
- **Örnekleme:** 50 Hz
- **Konu sayısı:** 21
- **Amaç:** Ana fall/ADL/near-fall sınıflandırma + HR çıkarımı

### 4.2 BUT_PPG (Brno University of Technology PPG)

**Konum:** `Data/BUT_PPG/` — ~150 kayıt klasörü + `quality-hr-ann.csv`, `subject-info.csv`  
**Yükleyici:** `healthalert_final_ai/src/data/loaders/but_ppg_loader.py`

- **Modalite:** PPG sinyali; iki format:
  - `100xxx-111xxx`: Spektrofotometrik (1 sample, 300 kanal) — spektral vektör
  - `112xxx+`: Temporal RGB PPG (300 sample, 3 kanal) — temporal sinyal
- **Etiketler:** `quality-hr-ann.csv` → `Quality (0=poor, 1=good)`, `HR (bpm)`; `subject-info.csv` → SpO2, demografik
- **Format:** WFDB `.dat/.hea`
- **Amaç:** PPG sinyal kalitesi tahmini (quality head eğitimi için)

### 4.3 WEDA_FALL (Wrist Elderly Daily Activity and Fall)

**Konum:** `Data/WEDA_FALL/dataset/` — `5Hz/`, `10Hz/`, `25Hz/`, `40Hz/`, `50Hz/` alt klasörler + `fall_timestamps.csv`  
**Yükleyici:** `healthalert_final_ai/src/data/loaders/weda_fall_loader.py`

- **Modaliteler:** Bilek IMU — `accel_x/y/z`, `gyro_x/y/z` (CSV formatında)
- **Etiketler:** `F01-F08` = fall, `D01-D11` = ADL; `fall_timestamps.csv` → start/end zaman damgaları
- **Konu:** 14 genç + 11 yaşlı = 25 kişi
- **Format:** CSV; çoklu örnekleme hızı (5-50 Hz)
- **Amaç:** Geniş yaş dağılımında fall/ADL sınıflandırma ve instability detection

### 4.4 Ortak Şema ve Ön İşleme

**Sampling Rate / Resampling:**  
`healthalert_final_ai/config/base.yaml` → `target_sr: 50`. Tüm veri setleri 50 Hz'e yeniden örneklenir. `healthalert_final_ai/src/data/preprocessing/resampling.py` bu işlemi yapar.

**Window Size / Stride:**  
`window_size: 200` (4s @ 50Hz), `window_stride: 50` (1s). `healthalert_final_ai/src/data/preprocessing/windowing.py` → `extract_windows()`.

**Subject-wise Split:**  
`healthalert_final_ai/config/data.yaml` → `70/15/15 (train/val/test)`, subject-level split. Konu sızıntısı önlenmiş.

**Normalization:**  
`healthalert_final_ai/src/data/preprocessing/normalization.py` + `scaler_pipeline.py`. Z-score normalizasyon veya MinMax, modality başına.

**Feature Engineering (~38 özellik):**  
`healthalert_final_ai/src/data/feature_engineering/feature_pipeline.py` → `extract_all_handcrafted_features()`:
- IMU özellikleri: `accel_magnitude_mean/max/std`, `accel_peak_to_peak`, `accel_variance`, `jerk_estimate_max/mean`, `movement_energy`, `posture_change_proxy`, `instability_score`, + gyro benzerleri
- PPG/vital özellikleri: HR istatistikleri, SpO2 istatistikleri, PPG kalite skoru
- Fusion özellikleri: kombinasyon metrikleri
- **Toplam: ~38 boyut**

**Veri Setleri Arasında Uyumsuzluklar:**  
- HIFD: IMU + PPG (HR). BUT_PPG: sadece PPG. WEDA_FALL: sadece IMU. → Multimodal modelde missing-modality mask (`modality_mask`) ile yönetilmiş.
- HIFD/WEDA_FALL natif 50Hz; BUT_PPG örnekleme hızı farklı (spectral/temporal) — model PPG sinyalinden ziyade quality label ve HR skalar kullanıyor.
- Etiket mapping: HIFD label `{0:ADL, 1:fall, 2:near_fall}`; WEDA_FALL `{F01-F08: fall, D01-D11: ADL}`; BUT_PPG quality `{0: poor, 1: good}`.

---

## BÖLÜM 5 — Model Mimarisi ve Eğitim Hattı

### 5.1 Model Dosyaları

- **Ana model:** `healthalert_final_ai/src/models/multitask_model_v2.py` → `HealthAlertModelV2`
- **Blocks:** `healthalert_final_ai/src/models/blocks/` → `imu_encoder.py`, `ppg_encoder.py`, `vitals_mlp.py`, `handcrafted_mlp.py`, `fusion_attention.py`, `quality_gate.py`
- **Heads:** `healthalert_final_ai/src/models/heads/` → `fall_head.py`, `instability_head.py`, `quality_head.py`, `risk_head.py`

### 5.2 Mimari Detayları

**IMU Encoder:** CRNN — 3 katman 1D CNN (kanallar: [32, 64, 128], kernel=5) + 2 katman GRU (hidden=128), dropout=0.3. Giriş: `(T=200, 6)` IMU.

**PPG Encoder:** 1D CNN — kanallar: [16, 32, 64], kernel=7, dropout=0.2. Giriş: `(T=200, 1)` PPG.

**Quality Gate:** PPG encoder çıktısını kalite skoru ile damper eder; kalite düşükse PPG modalitesi zayıflatılır.

**Vitals MLP:** `input_dim=2` (HR, SpO2) → `[32, 16]` gizli katmanlar, dropout=0.2.

**Handcrafted MLP:** ~38 boyutlu feature vektörü → MLP. **v2 ile eklenmiş.**

**Fusion Attention:** 4 head attention; 4 modality embedding'i (IMU, PPG, vitals, handcrafted) + CLS token → fused embedding. `modality_mask` ile eksik modalite öğrenilir.

**Output Heads:**
- `FallHead` → fall logit → sigmoid → fall_probability
- `InstabilityHead` → instability logit → sigmoid → instability_probability  
- `QualityHead` → quality logit → sigmoid → ppg_quality_score
- `RiskHead` → risk score (MSE hedef)

### 5.3 Eğitim Hattı

**Dosyalar:** `healthalert_final_ai/src/training/stage_trainer.py`, `trainer.py`, `losses.py`, `metrics.py`, `optim.py`, `callbacks.py`

**Çok Aşamalı Eğitim:**
- Stage 1: PPG quality (sadece quality head, BUT_PPG)
- Stage 2: Fall detection (fall head, HIFD + WEDA_FALL)
- Stage 3: Instability detection (instability head)
- Stage 4: Risk regression (risk head)
- Stage 5: Fusion (tüm başlıklar, end-to-end)

**Loss Fonksiyonları** (`healthalert_final_ai/config/train.yaml`):
- Fall: Focal Loss (weight=1.0)
- Instability: BCE + pos_weight=5.0 (weight=0.5)
- Quality: BCE + pos_weight=3.0 (weight=0.3)
- Risk: MSE (weight=0.4)

**Optimizer/Scheduler:** AdamW + Cosine Annealing LR decay, 100 epoch, batch_size=64, gradient_clip=1.0.

**Augmentation:** IMU noise, scale, time warp, mixup.

### 5.4 Değerlendirme Sonuçları

**Kaynak:** `outputs/reports/evaluation_report.txt`, `report_bundle/01_metrics/`

| Görev | Accuracy | AUC | F1 | MCC |
|---|---|---|---|---|
| Fall Detection | 0.8642 | 0.9447 | 0.7687 | 0.6863 |
| Instability | 0.9587 | 0.9764 | 0.5979 | 0.5821 |
| PPG Quality | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Risk Score | — | — | MAE=0.1466 | — |

**Checkpoint Dosyaları:** `outputs/models/` → `best_fall_model.pt`, `best_quality_model.pt`, `best_multitask_model.pt`, `best_final_fusion_model.pt`.

**Model Production'a Bağlı mı?** Hayır. Checkpointler `outputs/models/`'de duruyor; `inference.yaml` → `model_path: outputs/models/best_final_fusion_model.pt` tanımlı ama backend bu path'ten model yüklemiyor.

---

## BÖLÜM 6 — Inference ve Risk Postprocessing

### 6.1 Predictor

**Dosya:** `healthalert_final_ai/src/inference/predictor.py` → `HealthAlertPredictor`

- Model yükleme + `model.eval()`
- `predict(imu, ppg, vitals, smooth=True)`:
  - `extract_all_handcrafted_features()` çağrısı
  - Tensor hazırlama
  - `@torch.no_grad()` forward pass
  - EMA smoothing (alpha=0.3) ile `_ema_state` güncelleme
  - Döndürülen: `fall_prob`, `instability_prob`, `quality_score`, `risk_score`
- `reset()`: Yeni oturum için EMA sıfırlama

### 6.2 Risk Postprocessor

**Dosya:** `healthalert_final_ai/src/inference/risk_postprocessor_v2.py` → `RiskPostprocessorV2`

**Fusion formülü:**
```
early_risk_score = 
    fall_prob   × w_fall(0.35)
  + instability × w_instability(0.20)
  + vital_risk  × w_vital(0.25)
  + quality_penalty × w_quality(0.20)
```

- `vital_risk`: HR < 50 veya > 120 → 0.3; SpO2 < 92 → 0.4; SpO2 < 95 → 0.2
- `quality_penalty = 1.0 - quality_score`
- `final_risk_level`: normal(≤0.3) / watch(≤0.5) / warning(≤0.7) / critical(>0.7)
- `immediate_alert`: risk_score ≥ 0.85 veya fall_prob ≥ 0.9
- `reasons`: metin açıklama listesi
- `recommendations`: klinik öneri listesi

### 6.3 Recommendation Engine

**Dosya:** `healthalert_final_ai/src/inference/recommendation_engine_v2.py` — mevcut. Backend'e bağlı değil.

### 6.4 Explainability

**Dosya:** `healthalert_final_ai/src/inference/explainability_v2.py` — mevcut. Feature importance ve attention map üretimi.

### 6.5 Backend'e Bağlantı Durumu

`backend/services/ai_bridge.py` → `process_ai_result()` fonksiyonu:
- AI çıktısını (`final_risk_level`, `fall_probability`, `instability_probability`, vb.) alır
- LiveStatus günceller, AnomalyEvent/AlertEvent oluşturur, bildirim fan-out yapar
- **Bu fonksiyon `POST /ingest/ai-inference` ile dışarıdan çağrılabilir**
- **Eksik:** `/ingest/device-packet` yolu bu fonksiyonu otomatik çağırmıyor

**Entegrasyon Eksiği Nerede:**  
`ingestion_router.py` → `ingest_device_packet()` fonksiyonu heuristik risk hesabı yaptıktan sonra `process_ai_result()` çağırmıyor. Bunun için:
1. Backend'in, gelen her N paketi (200 sample = 4s) bir window oluştururken buffer tutması gerekir
2. Buffer dolunca `HealthAlertPredictor.predict()` çağrılmalı
3. Sonuç `process_ai_result()` üzerinden işlenmeli

---

## BÖLÜM 7 — Hocanın 1. Sorusu: Anlık Veri Nasıl Analiz Ediliyor?

### Teknik Gerçek: Model Her Saniye Yeniden Eğitilmez

**Model her saniye yeniden eğitilmez. Bu hem teknik hem pratik olarak yanlış olurdu.** Eğitim; HIFD, BUT_PPG ve WEDA_FALL veri setleri üzerinde, `healthalert_final_ai/src/training/stage_trainer.py` kullanılarak **offline** yapılmıştır. Ortaya çıkan checkpoint (`best_final_fusion_model.pt`) sabit bir ağırlık dosyasıdır.

### Mevcut Durum: Canlı Veri Backend'de Nasıl İşleniyor?

ESP32 her saniye `POST /ingest/device-packet` endpointine JSON paket gönderir (ya da host_bridge/ingestion_bridge.py üzerinden iletilir). Bu endpoint:

1. Paketi doğrular ve loglar
2. `_compute_motion_score()` → saf matematik (ivme sapması + jiroskop)
3. `_compute_risk_score()` → eşik tabanlı ağırlıklı toplam
4. LiveStatus günceller
5. Eşik aşılmışsa anomaly/alert/bildirim zinciri başlatır

**ML modeli bu yolda çağrılmıyor.** `HealthAlertPredictor` nesnesi oluşturulmuyor, checkpoint yüklenmiyor.

### Sliding Window Buffer Var mı?

Hayır. `ingestion_router.py`'de paket başına işlem yapılıyor. 200 sample (4s @ 50Hz) pencere oluşturmak için bir buffer mekanizması yok. Inference için en az 200 ardışık paketin biriktirilerek `HealthAlertPredictor.predict(imu, ppg, vitals)` çağrılması gerekiyor.

### Online Training Yapılıyor mu?

Hayır. Sistemde online learning veya incremental eğitim mekanizması yok. Bu doğru bir yaklaşım: üretim sistemlerde her gelen veriyle modeli güncellemek hem tehlikeli (dağılım kayması, catastrophic forgetting) hem pratik değil.

### Bir Sonraki Adımda Canlı ML Inference Nasıl Bağlanabilir?

Minimum değişiklikle:
1. `ingestion_router.py`'ye per-user in-memory ring buffer ekle (200 paket)
2. Buffer dolunca `HealthAlertPredictor.predict()` çağır
3. Sonucu `process_ai_result(repos, user_id, ai_output)` ile işle
4. Hem heuristik hem ML riski döndür (geçiş dönemi için paralel çalıştır)

**Net sonuç:**  
> "Model her saniye yeniden eğitilmez. Eğitim offline yapılır ve sabit bir checkpoint dosyasına (`best_final_fusion_model.pt`) kaydedilir. Canlıda gelen her paket doğrulanır ve loglanır. Şu anda anlık analiz saf heuristik kural tabanlıdır. ML inference bağlantısı için 4 saniyelik sliding window buffer ve `HealthAlertPredictor` entegrasyonu gereklidir."

---

## BÖLÜM 8 — Hocanın 2. Sorusu: Kişiselleştirme

### Mevcut Sistemde Kişisel Baseline Var mı?

**Hayır.** `backend/models.py` incelendiğinde 18 ORM tablosunun hiçbirinde kullanıcıya özel fizyolojik baseline alanı yoktur. `User` tablosu: email, password_hash, role, full_name, phone, birth_date. `AppSettings` tablosu: battery_mode, notifications_enabled, sync_interval_sec, alert_sensitivity gibi UI tercihleri.

### Risk Eşikleri Kullanıcıya Göre Değişiyor mu?

**Hayır.** `backend/config.py` → Pydantic Settings:
```python
RISK_CRITICAL_THRESHOLD: float = 0.75
RISK_WARNING_THRESHOLD:  float = 0.55
RISK_WATCH_THRESHOLD:    float = 0.30
```
Sabit global değerler. Tüm kullanıcılar için aynı. `.env` dosyasıyla değiştirilebilir ama yine de sistem genelinde sabit kalır.

### `AppSettings.alert_sensitivity` Ne Yapıyor?

`backend/models.py` → `alert_sensitivity` alanı mevcut fakat `ingestion_router.py`'deki `_compute_risk_score()` veya `_risk_to_severity()` bu değeri okumamaktadır. Yani mevcut durumda etki etmiyor.

### Kullanıcı Geçmiş Verisi Risk Hesaplamasına Giriyor mu?

Hayır. `trend_service.py` → `analyze_trends()` geçmiş anomali/alert sayısını sayar ve trend etiketi üretir. Ancak bu bilgi `_compute_risk_score()` fonksiyonuna **geri besleme yapmamaktadır**.

### PPG Kalitesi Risk Güveni Ayarlanıyor mu?

Hayır. `ingestion_router.py`'deki canlı ingest yolunda `signal_quality` alanı `DevicePacketLog`'a kaydedilir ancak risk hesaplamasında kullanılmaz. `RiskPostprocessorV2`'de kalite penalty var ama o ML inference yolundadır ve canlıya bağlı değil.

### Kişisel Baseline Eklemek İçin Mevcut Altyapı

`UserRelation`, `DevicePacketLog` (ham sensör geçmişi), `LiveStatus` (anlık), `HistoryItem`, `AnomalyEvent` — hepsi `user_id` foreign key'e sahip. `DevicePacketLog` tablosunda HR, SpO2, signal_quality, accel ve gyro verileri kayıtlı. **Bu tablo baseline hesaplamak için ham veri kaynağıdır.**

### Yeni UserBaseline Modeli Nasıl Olmalı?

Mevcut `backend/models.py` içinde yeni bir SQLAlchemy modeli olarak tasarlanabilir:

```python
class UserBaseline(Base):
    __tablename__ = "user_baselines"
    id              = Column(String, primary_key=True)
    user_id         = Column(String, ForeignKey("users.id"), unique=True)
    resting_hr_mean = Column(Float, default=72.0)
    resting_hr_std  = Column(Float, default=10.0)
    spo2_mean       = Column(Float, default=98.0)
    spo2_std        = Column(Float, default=1.5)
    motion_mean     = Column(Float, default=0.10)
    motion_std      = Column(Float, default=0.08)
    ppg_quality_mean= Column(Float, default=0.85)
    sample_count    = Column(Integer, default=0)
    is_ready        = Column(Boolean, default=False)  # min 300+ sample
    last_updated    = Column(DateTime)
    created_at      = Column(DateTime)
```

**Baseline hangi verilerle güncellenmeli?**
- `DevicePacketLog` tablosundan, sadece `hr_valid=True`, `spo2_valid=True`, `signal_quality > 0.5` kayıtları
- `AnomalyEvent` veya `AlertEvent` olmayan saatlerdeki kayıtlar (alarm dönemleri baseline'a dahil edilmemeli)
- Minimum 300 sample (yaklaşık 5 dakika steady-state veri) sonra `is_ready=True`

**Personal Deviation Risk Formülü:**
```
personal_deviation = 
    w_hr  × max(0, |hr - resting_hr_mean| - 2×resting_hr_std) / resting_hr_std
  + w_spo2 × max(0, (spo2_mean - spo2) / spo2_std)
  + w_motion × max(0, (motion - motion_mean - 2×motion_std) / motion_std)

final_risk = global_risk + α×personal_deviation + β×trend_risk + γ×quality_adjustment
```

**Backend'de Hangi Dosyalar Etkilenir:**
- `backend/models.py` → `UserBaseline` tablo eklenir
- `backend/schemas.py` → `UserBaselineResponse` şeması
- `backend/repositories/base.py` → `AbstractBaselineRepo` arayüzü
- `backend/repositories/sqlite/` → `SQLiteBaselineRepo` implementasyonu
- `backend/repositories/factory.py` → `RepoSet` dataclass'a `baselines` alanı
- `backend/routers/ingestion_router.py` → `_compute_risk_score()` UserBaseline okuma eklenebilir
- Yeni servis: `backend/services/baseline_service.py` → hesaplama ve güncelleme mantığı

**Mobile'da Kullanıcıya Kişiselleştirme Gösterimi:**  
Dashboard ekranında "Kişisel Normunuzdan Sapma: +12%" gibi bir widget. `AppSettings` ekranında "Benim Normum" bölümü. Notification'da "Nabzınız kişisel ortalamanızın 2.1 standart sapma üzerinde" mesajı.

---

## BÖLÜM 9 — Hocanın 3. Sorusu: RAG / ROG / Benzer Örnek Getirme Destekli Veri Eğitimi

> **Not:** Bu bölüm chatbot/asistan odağında değil; veri eğitimi, zaman serisi analizi, benzer pencere getirme ve risk analizini açıklanabilir hale getirme odağında değerlendirilmektedir.

### 9.1 Retrieval-Augmented Time-Series Risk Analysis Uygulanabilir mi?

Evet, altyapının kritik bir kısmı **hazır**:

1. **3 veri seti mevcut** ve yükleme/windowing pipeline'ı çalışıyor
2. **Feature extraction pipeline hazır:** `extract_all_handcrafted_features()` → ~38 boyutlu vektör
3. **Window extraction hazır:** `extract_windows()` → 200 sample, 50 stride
4. **Model checkpointleri mevcut:** offline eğitilmiş, değerlendirme yapılmış

**Eksik:** Veri seti pencerelerine ait pre-computed feature index dosyası yok. Canlı pencere ile dataset penceresi arasında nearest-neighbor araması yapan kod yok.

### 9.2 Feature Vector Yapısı ve Metadata

Her `(window, label)` çifti için şu metadata bileşeni oluşturulabilir:

```python
{
    "feature_vector": np.ndarray(shape=(38,)),  # extract_all_handcrafted_features()
    "dataset":        "HIFD" | "BUT_PPG" | "WEDA_FALL",
    "subject_id":     "subject_03",
    "scenario":       "fall2" | "walk" | "F04" | ...,
    "label":          0 | 1 | 2,           # ADL | fall | near_fall
    "risk_level":     "normal" | "warning" | "critical",
    "modality":       ["imu", "ppg"] | ["imu"] | ["ppg"],
    "quality_score":  float,                # BUT_PPG'den veya sinyal kalitesi
    "window_idx":     int,
    "sr":             50,
}
```

### 9.3 Vector Index Teknoloji Seçimi

| Teknoloji | Avantaj | Dezavantaj | Proje Uygunluğu |
|---|---|---|---|
| `sklearn.NearestNeighbors` | Sıfır ek bağımlılık, kolay kurulum | 10K+ vektörde yavaş | **PoC için ideal** |
| FAISS | Çok hızlı, milyonlarca vektör | C++ bağımlılığı, kurulum karmaşıklığı | Orta vadeli |
| Chroma | Metadata filtreleme, kalıcı index | Ek servis gerektirir | Ürün için uygun |
| Qdrant | En güçlü filtreleme, cloud | En fazla kurulum zahmeti | Gereksiz karmaşıklık |

**Minimum PoC için öneri:** `sklearn.NearestNeighbors` ile `.joblib` serialize edilmiş index dosyası.

### 9.4 Canlı Pencereyi Feature Space'e Dönüştürme

```python
# Canlı 200-sample window geldiğinde:
imu_window  = np.array(buffer[-200:])[:, :6]     # accel + gyro
ppg_window  = np.array(buffer[-200:])[:, 6:7]    # PPG
vitals      = np.array([hr, spo2/100, quality])

live_vec, _ = extract_all_handcrafted_features(
    accel=imu_window[:, :3],
    gyro=imu_window[:, 3:6],
    hr_signal=ppg_window[:, 0],
    spo2_signal=np.full(200, spo2),
    ppg_quality=quality,
    sr=50,
)
```

`live_vec` → `~38` boyutlu → NearestNeighbors ile top-k benzer pencere araması.

### 9.5 Top-k Benzer Pencere Getirme ve Kullanım Senaryoları

**A) Model Kararını Destekleme (Inference-time Retrieval):**
```
Canlı risk_score = 0.72 (ML model çıktısı)
Top-5 benzer pencere: [fall2(HIFD), F03(WEDA), fall4(HIFD), walk(HIFD), clap(HIFD)]
Fall oranı: 3/5 = 60% → risk skoru teyit edildi
Retrieval support score = 0.60
final_risk = 0.72 × (1 + 0.10 × retrieval_support)
```

**B) Açıklanabilirlik:**  
"Bu analiz, veritabanında 1.208 benzer hareket paterni ile karşılaştırıldı. Benzer örüntülerin %65'i düşme öncesi dönemlere karşılık geliyor."

**C) Eğitimde Hard-Negative Mining:**  
Near-fall pencerelerini fall pencerelerine yakın ama negatif label'lı olarak bulmak için retrieval kullanılabilir. Modelin zor negatiflerle eğitilerek precision artırılması.

**D) Kişiselleştirme Desteği:**  
Kullanıcının kendi `DevicePacketLog` geçmişinden oluşturulan feature vektörleri ayrı bir "personal index"e eklenebilir. Canlı pencere hem global dataset index'te hem de personal index'te aranır. "Senin normal hareketine benziyor" vs "Bu senin için alışılmadık bir patern" ayrımı yapılabilir.

### 9.6 Model Skoru + Retrieval Support Birleşimi

```
Karar Mantığı:
    model_risk      → HealthAlertPredictor.predict()
    retrieval_score → top_k benzer pencerelerin fall/risk etiketi ortalaması
    personal_score  → kişisel geçmişe benzerlik

final_risk = α × model_risk + β × retrieval_score + γ × personal_deviation
```

Eşikler:
- `model_risk ≥ 0.7` VE `retrieval_score ≥ 0.5` → güvenli kritik alarm
- `model_risk ≥ 0.7` FAKAT `retrieval_score < 0.2` → düşük güven, uyarı al ama yükseltme

### 9.7 Minimum Uygulanabilir PoC Planı

1. `healthalert_final_ai/scripts/build_retrieval_index.py` yaz (mevcut değil)
2. HIFD + WEDA_FALL pencerelerini feature vektörlerine dönüştür → `(N, 38)` matrix
3. `sklearn.NearestNeighbors(n_neighbors=5).fit(feature_matrix)` → `retrieval_index.joblib`
4. `healthalert_final_ai/src/inference/retrieval_engine.py` yaz
5. `HealthAlertPredictor.predict()` sonucunu retrieval ile teyit et
6. Backend `ai_bridge.py`'ye retrieval bilgisi ekle

---

## BÖLÜM 10 — Mevcut Eksikler

| # | Eksik | Etki | Kaynağı |
|---|---|---|---|
| 1 | **Canlı veri ML modeline bağlı değil** | Risk hesabı tamamen heuristik; modelin üstün gücü kullanılmıyor | `ingestion_router.py` → `HealthAlertPredictor` çağrısı yok |
| 2 | **Kişisel baseline tablosu yok** | Sabit eşikler herkes için yanlış alarm üretebilir | `backend/models.py` → `UserBaseline` sınıfı yok |
| 3 | **RAG/retrieval feature index yok** | Benzer pencere getirme ve açıklanabilir risk analizi yapılamıyor | `outputs/` altında `.joblib` veya `.faiss` dosyası yok |
| 4 | **Canlı ingest yolunda sliding window buffer yok** | ML inference için 200 ardışık paket gerekiyor; mevcut kod tek paket işliyor | `ingestion_router.py` → buffer mekanizması yok |
| 5 | **PPG kalite skoru risk kararında kullanılmıyor** | Düşük kaliteli PPG verisi anlık risk hesabını çarpıtıyor | `_compute_risk_score()` `signal_quality` parametresini almıyor |
| 6 | **Trend servisi risk score'a geri besleme yapmıyor** | `trend_service.py` trend etiketi üretiyor ama `_compute_risk_score()` bunu görmüyor | Servis çıktısı sadece asistan/chatbot'ta kullanılıyor |
| 7 | **`AppSettings.alert_sensitivity` etkisiz** | Kullanıcının duyarlılık ayarı risk hesaplamasına bağlı değil | `ingestion_router.py` `alert_sensitivity` okumuyor |
| 8 | **Çoğu ML inference dosyası backend'e bağlı değil** | `recommendation_engine_v2.py`, `explainability_v2.py` canlı akışa entegre değil | `healthalert_final_ai/src/inference/` izole |
| 9 | **Mock veri `mode="mock"` olarak işaretleniyor ama ayrı işlenmiyor** | Backend mock/real paketin aynı risk işleminden geçiyor; test sürecini karıştırabilir | `ingestion_router.py` `pkt.mode` değerini kontrol etmiyor |
| 10 | **WEDA_FALL çok sampling rate içeriyor (5-50Hz)** | 5Hz/10Hz verinin 50Hz'e upsample edilmesi yapay veri üretir; eğitim kalitesini etkileyebilir | `Data/WEDA_FALL/dataset/5Hz/`, `10Hz/` |
| 11 | **PPG quality AUC=1.0 → olası veri sızıntısı** | `evaluation_report.txt` quality F1=1.0; bu gerçek değil; quality label'ın feature'a sızdığı şüpheli | Sadece BUT_PPG quality label kullanımı incelenmeli |

---

## BÖLÜM 11 — Sonraki Adım İçin Teknik Seçenekler

### A) Kişisel Baseline MVP

**Amaç:** Her kullanıcı için sakin durum fizyolojik normunu öğren ve risk kararını buna göre kalibre et.

**Faydası:**
- Yanlış alarm oranını dramatik düşürür
- Kişiye özel "bu senin için alışılmadık" mesajı üretilebilir
- Bitirme projesinde akademik özgünlük katar
- Sabah egzersiz yapan biriyle hareketsiz birini ayrıştırır

**Zorluğu:**
- `UserBaseline` tablosu, repo arayüzü ve servisi yazılmalı
- `ingestion_router.py`'ye baseline okuma + personal deviation hesabı eklenmeli
- Baseline "is_ready" kontrolü (ilk ~5 dakikaya kadar çalışmaz)
- Alarm dönemlerini baseline'dan dışlama mantığı

**Hangi dosyalar etkilenir:**
- `backend/models.py` (yeni tablo)
- `backend/schemas.py` (yeni şema)
- `backend/repositories/base.py` (yeni arayüz)
- `backend/repositories/sqlite/baseline_repo.py` (yeni implementasyon)
- `backend/repositories/factory.py` (RepoSet güncelleme)
- `backend/routers/ingestion_router.py` (_compute_risk_score güncelleme)
- `backend/services/baseline_service.py` (yeni servis)

**Risk:** Orta. Database migration, baseline hazır olmadan sistem davranışı.

**Bitirme projesi için:** Çok uygun. Teknik derinliği ve akademik özgünlüğü yüksek.

---

### B) Canlı ML Inference Bağlantısı

**Amaç:** Heuristik risk hesabını ML model çıktısıyla değiştir veya tamamla.

**Faydası:**
- Modelin eğitilmiş gücünü canlı akışa taşır
- Fall detection (AUC=0.9447) gerçek zamanlı çalışır
- Proje tüm katmanı birleştirir

**Zorluğu:**
- Per-user in-memory ring buffer (200 paket)
- `HealthAlertPredictor` nesnesinin singleton olarak başlatılması
- Model checkpoint yükleme (`outputs/models/best_final_fusion_model.pt`)
- Canlı verinin aynı normalizasyon pipeline'ından geçmesi
- Async uyumluluk (PyTorch sync vs FastAPI async)
- Sistem yavaşlayabilir (GPU yoksa CPU inference ~10-50ms/pencere)

**Model checkpoint hazır mı?** Evet. `outputs/models/best_final_fusion_model.pt` mevcut.

**Backend ingest akışına nasıl bağlanır:**  
`ingestion_router.py` → buffer dolunca → thread executor ile sync `predict()` → `process_ai_result()` çağrısı.

**Bitirme projesi için:** Uygun ama dikkatli implementasyon gerektirir. Sync/async karışımı ve buffer yönetimi hata riski taşır.

---

### C) Retrieval / RAG PoC

**Amaç:** 3 veri setinden feature index oluştur; canlı pencere için top-k benzer örnek getir; risk kararını destekle ve açıkla.

**Faydası:**
- Akademik özgünlük çok yüksek ("Retrieval-Augmented Time-Series Risk Analysis")
- Açıklanabilir AI kapsamına giriyor
- 3 veri setinin birleşik kullanımı için güçlü motivasyon
- Model kararını hem destekler hem yorumlar

**Zorluğu:**
- Index build script yazılmalı
- Feature vector normalize edilmeli (train/test time uyumu)
- Retrieval engine servis olarak backend'e entegre edilmeli
- Index dosyası (~10-50MB) sunucu başlangıcında yüklenmeli

**3 veri setinden feature index nasıl kurulur:**
1. Tüm pencereleri `extract_windows()` ile oluştur
2. Her pencere için `extract_all_handcrafted_features()` çağır
3. `(N, 38)` matrix oluştur + metadata array
4. `sklearn.NearestNeighbors.fit(matrix)` → `retrieval_index.joblib`

**Canlı pencere ile top-k similar search:**
```python
live_vec = extract_all_handcrafted_features(...)
distances, indices = nn.kneighbors([live_vec])
similar_metadata = [metadata[i] for i in indices[0]]
retrieval_score = mean([m["label"] == "fall" for m in similar_metadata])
```

**Bitirme projesi için minimum uygulanabilir mi?** Evet, `sklearn.NearestNeighbors` ile ~100 satır kodda PoC kurulabilir. Tam entegrasyon (Chroma/FAISS + backend servis) daha fazla iş.

---

## BÖLÜM 12 — Önerilen Yol Haritası

### Kısa Vadeli Plan (Öncelik Sırası)

**Adım 1 — Canlı risk akışını netleştir**  
- `ingestion_router.py`'de `pkt.mode="mock"` ise simülasyon olarak işaretle
- `AppSettings.alert_sensitivity`'i `_risk_to_severity()` eşiğine bağla (düşük riskli değişiklik)

**Adım 2 — Kişisel Baseline MVP tasarla**  
- `UserBaseline` tablosunu `backend/models.py`'ye ekle
- `baseline_service.py`: `DevicePacketLog`'dan sakin dönem ortalaması hesapla
- `ingestion_router.py`'de baseline_ready=True ise `personal_deviation` ekle

**Adım 3 — Canlı sensör paketlerini backend'e stabil ilet**  
- `host_bridge/ingestion_bridge.py` retry mekanizması zaten var
- Firmware `FORCE_MOCK_MODE=0` ile gerçek sensör denemesi yap
- JWT token yönetimini otomatikleştir

**Adım 4 — Baseline + trend + global risk birleşimi**  
- `trend_service.analyze_trends()` sonucunu `_compute_risk_score()`'a parametre olarak ekle
- `final_risk = global_risk + personal_deviation + trend_adjustment`

**Adım 5 — RAG/retrieval için küçük PoC hazırla**  
- HIFD + WEDA_FALL için feature index oluştur
- Demo script: canlı pencere → top-5 benzer örnek → konsol çıktısı

### Orta Vadeli Plan

**Adım 1 — ML inference backend'e bağla**  
- Per-user ring buffer (collections.deque, maxlen=200) `ingestion_router.py`'ye ekle
- `asyncio.get_event_loop().run_in_executor()` ile PyTorch inference
- Heuristik + ML paralel çalıştır, sonuçları karşılaştır

**Adım 2 — HIFD/BUT_PPG/WEDA_FALL feature index oluştur**  
- `scripts/build_retrieval_index.py` yaz
- `sklearn.NearestNeighbors` → `retrieval_index.joblib`
- Metadata array (dataset, subject, label, quality)

**Adım 3 — Model risk + retrieval support + personal baseline birleşimi**  
- `process_ai_result()` parametrelerine `retrieval_support` ekle
- `final_risk = ML_model × 0.6 + retrieval_score × 0.2 + personal_deviation × 0.2`

**Adım 4 — Metrikler çıkar**  
- Heuristik vs ML inference: false positive oranı karşılaştırması
- Kişisel baseline ile yanlış alarm azalması ölçümü
- Retrieval support güven artışı analizi

---

## BÖLÜM 13 — Hocaya Verilecek Teknik Cevap Taslakları

### 1. Anlık Veri Analizi

> "ESP32 her saniye bir JSON paket gönderiyor ve backend bu paketi `/ingest/device-packet` endpoint'inde alıyor. Canlı sistemde model **her saniye yeniden eğitilmez** — bu hem teknik olarak imkânsız hem de yanlış olurdu. Model, HIFD, BUT_PPG ve WEDA_FALL veri setleri üzerinde **offline** eğitilmiş ve `best_final_fusion_model.pt` checkpoint dosyasına kaydedilmiştir. Şu anda canlı akışta ML modeli değil; HR/SpO2/motion eşik tabanlı **kural tabanlı heuristik** çalışmaktadır. ML inference bağlantısı için gerekli altyapı (checkpoint, predictor, ai_bridge) hazır ama 200 ardışık paketi biriktiren sliding window buffer ile bağlantı kurulmamıştır. Bir sonraki adımda bu buffer mekanizması ve `HealthAlertPredictor` entegrasyonu tamamlanacaktır."

### 2. Kişiselleştirme

> "Mevcut sistemde tüm kullanıcılar için aynı global eşikler geçerlidir (kritik: 0.75, uyarı: 0.55, izlem: 0.30 — `backend/config.py`). Sabit eşikler güvenlik alt sınırı olarak korunacak; asıl karar mekanizması **kişiye özel baseline ve sapma analizi** ile kalibre edilecektir. Her kullanıcı için `UserBaseline` tablosu oluşturularak dinlenme HR ortalaması/standart sapması, SpO2 normu ve hareket normu kaydedilecek. Risk hesabı `global_risk + personal_deviation + trend_risk` olarak yeniden tanımlanacak. Bu şekilde saate 140 nabızla koşan aktif bir kullanıcı ile hareketsiz bir yaşlı için aynı 'normal nabız: 140 bpm' durumu farklı risk skorları üretecek."

### 3. RAG / Retrieval-Augmented Time-Series Risk Analysis

> "3 veri seti (HIFD, BUT_PPG, WEDA_FALL) kullanıldığı için **Retrieval-Augmented Time-Series Risk Analysis** mimarisi uygulanabilir. Her veri seti 4 saniyelik (200 sample @ 50Hz) pencerelere ayrılacak ve mevcut `extract_all_handcrafted_features()` fonksiyonu (~38 boyut) ile özellik vektörlerine dönüştürülecektir. Bu vektörler dataset, subject_id, label, risk_level ve quality_score metadata'sıyla birlikte bir `sklearn.NearestNeighbors` indexine kaydedilecek. Canlıdan gelen her 4 saniyelik pencere aynı feature pipeline'ından geçirilerek top-k benzer tarihsel pencereler bulunacak. Model risk skoru + retrieval support + kişisel geçmiş benzerliği birleşiminden `final_risk` üretilecektir. Bu yaklaşım hem modelin kararını destekler hem de 'bu alarm için 1.247 benzer örüntüden %73'ü düşme öncesi döneme işaret ediyor' gibi açıklanabilir risk analizi sunar."

---

## SON NOT: Bir Sonraki Adım Kararı

> **"Bu projenin mevcut haline göre önce hangisini yapmak daha mantıklı: Kişisel Baseline MVP mi, Canlı ML Inference bağlantısı mı, Retrieval/RAG PoC mi?"**

### Öneri: **A) Kişisel Baseline MVP önce yapılmalı.**

**Gerekçe:**

1. **Temel gereksinim bağımsızlığı:** Kişisel baseline, ML modeline bağımlı değildir. Mevcut heuristik risk hesabı üzerinde bile çalışır. `_compute_risk_score()` fonksiyonuna ek parametre olarak eklenebilir.

2. **Pratik değer hemen görünür:** Demo sırasında "Nabzınız kişisel normunuzun 2.1 standart sapma üzerinde" mesajı akademik değerlendirme açısından çok güçlü bir kanıt.

3. **ML inference bağlantısını kolaylaştırır:** ML model canlıya bağlandığında kişisel baseline zaten hazır olursa fusion (ML_risk + personal_deviation) direkt uygulanabilir.

4. **Retrieval/RAG PoC için zemin hazırlar:** Personal index (kullanıcının kendi geçmişi) zaten baseline altyapısıyla doğal örtüşür.

5. **Risk düzeyi düşük:** Mevcut canlı akışı bozmayan ek tablo + servis. Hata olsa bile heuristik çalışmaya devam eder.

**Sıralama:**
```
1. Kişisel Baseline MVP  (2-3 günlük iş)
2. Canlı ML Inference bağlantısı  (3-4 günlük iş; ring buffer + async executor)  
3. Retrieval/RAG PoC  (2-3 günlük iş; sklearn NearestNeighbors + build script)
```

---

*Bu rapor yalnızca analiz amaçlıdır. Kodda hiçbir değişiklik yapılmamıştır.*
