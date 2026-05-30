# HealthAlert Kapsamli Proje Raporu (Turkce)

Bu rapor iki ana kisimdan olusur:
- 1) Su anki yaptiklarim (son gelistirme durumu)
- 2) Tum projede ne var, ne yapildi (uctan uca teknik envanter)

## 1) Su Anki Yaptiklarim

### 1.1 Son oturumda tamamlanan gelistirmeler (doktor ve hasta yakini erisim akisi)

Bu oturumda hedef, SELF-RELATIVE-DOCTOR rollerinin hasta canli verisi ve ozet verisine erisimini net ACL kurallariyla tamamlamakti.

Tamamlanan backend degisiklikleri:
- Yeni hasta erisim router dosyasi eklendi: [backend/routers/patients_router.py](backend/routers/patients_router.py)
- Yeni endpointler eklendi:
  - GET /patients/accessible
  - GET /patients/{patient_id}/live
  - GET /patients/{patient_id}/summary
  - GET /doctor/patients
  - GET /relative/patients
- ACL yardimcisi eklendi: can_access_patient(user, patient_id)
- Live response zenginlestirmesi yapildi:
  - [backend/schemas.py](backend/schemas.py) icinde LiveStatusResponse alanlari genisletildi
  - Yeni PatientSummaryResponse modeli eklendi
- SQLite canli veri deposu zenginlestirildi:
  - [backend/repositories/sqlite/repos.py](backend/repositories/sqlite/repos.py)
  - Son DevicePacketLog kaydindan signal_quality, hr_valid, spo2_valid, finger_present ve source bilgileri live cevabina eklendi
- Router kaydi uygulamaya baglandi:
  - [backend/main.py](backend/main.py)

Tamamlanan mobil degisiklikleri:
- API istemcisine yeni metodlar eklendi:
  - [mobile/lib/core/services/api_client.dart](mobile/lib/core/services/api_client.dart)
  - getMe, getAccessiblePatients, getPatientSummary, getPatientLive, getDoctorPatients, getRelativePatients
- Monitore edilen kullanici yukleme akisi iyilestirildi:
  - [mobile/lib/core/state/app_controller.dart](mobile/lib/core/state/app_controller.dart)
  - Once /patients/accessible deneniyor, hata olursa mevcut /link-codes/relations fallback akisi calisiyor
- Hasta canli veri cekme akisinda uyumluluk genisletildi:
  - Once /patients/{id}/live deneniyor, gerekirse /live/{id} fallback'i kullaniyor

### 1.2 Dogrulama ve test sonuclari

Backend tarafinda dogrulanan noktalar:
- Yeni endpointler route listesinde aktif
- Demo kullanicilarla login basarili (doctor@demo.com, relative@demo.com, self@demo.com)
- /patients/accessible doktor, relative ve self rollerinde beklenen sekilde sonuc donduruyor
- /patients/{id}/live ve /patients/{id}/summary doktor tarafinda calisiyor
- Yetkisiz erisimde 403 donuyor (ACL dogrulandi)
- Role-ozel endpointlerde rol korumasi aktif (doctor/relative endpoint ayrimi)

Mobil tarafinda dogrulanan noktalar:
- Degisen dosyalarda analizde derleme hatasi yok
- ApiException tarafinda const kaynakli iki hata duzeltildi
- Kalan bulgular warning/info seviyesinde (genel kod tabani kaynakli)

### 1.3 Cihaz/Firmware konfigu hakkinda ozel not (ha_config.h)

Aktif secimdeki [firmware/include/ha_config.h](firmware/include/ha_config.h) dosyasi, cihazin tum runtime davranisini merkezi olarak tanimliyor.

Kritik konfigurasyon alanlari:
- Kimlik ve versiyon:
  - FW_VERSION, FW_NAME, HA_DEVICE_ID, HA_PATIENT_ID
- Sensor ve ornekleme:
  - I2C pin/frekans, SAMPLING_RATE_HZ, PACKET_INTERVAL_MS
- BLE model akisi:
  - BLE_MODEL_STREAM_ENABLED, MODEL_STREAM_RATE_HZ, MODEL_WINDOW_SIZE, MODEL_WINDOW_DURATION_MS
- Sensor guvenilirlik ve zaman asimi:
  - SENSOR_INIT_RETRIES, SENSOR_INIT_RETRY_MS, SENSOR_READ_TIMEOUT_MS
- MAX30102 ve MPU6050 low-level parametreleri:
  - LED parlakligi, sample rate, pulse width, ADC range, accel/gyro range
- BLE servis ve karakteristik UUID'leri:
  - BLE_SERVICE_UUID, BLE_TELEMETRY_CHAR_UUID, BLE_RAW_SAMPLE_CHARACTERISTIC_UUID vb.
- Wi-Fi fallback parametreleri:
  - WIFI_SSID, WIFI_PASS, WIFI_BACKEND_URL, timeout/reconnect ayarlari
- Transport modu:
  - TRANSPORT_MODE

Operasyonel etkisi:
- Bu dosya BLE-odakli canli veri akisinda performans, paket ritmi, model pencereleme ve baglanti davranisini dogrudan belirler.
- Uretim/demo gecisleri icin en kritik firmware ayar noktasi burasidir.

### 1.4 Calisma agacindaki guncel degisiklik gorunumu (genis kapsam)

Depoda sadece bu oturumdaki degisiklikler degil, daha genis bir aktif calisma seti bulunuyor. Guncel degisiklikler backend, firmware, mobile ve AI klasorlerine yayilmis durumda.

One cikan degisiklik yogunlugu:
- Backend: config, models, schemas, repositories, model window ve yeni patients router
- Firmware: ana include basliklari, transport ve main akisi
- Mobile: app config, BLE servisleri, transport orchestrator, dashboard ve canli ekran bilesenleri
- AI: script arsivleme/temizlik, yeni rapor ve test dosyalari

Bu nedenle raporun ikinci bolumu, tum projeyi moduller halinde eksiksiz envanter mantigiyla listeler.

---

## 2) Tum Projede Ne Var, Ne Yapildi (Eksiksiz Teknik Envanter)

## 2.1 Projenin amaci ve kapsami

HealthAlert; dusme/instabilite riski, nabiz-SpO2 ve hareket verilerini toplayan, rol bazli paylasan, uca uca bir saglik izleme platformudur.

Temel roller:
- SELF: kendi verisini gorur
- RELATIVE: bagli oldugu SELF kullanicilarini gorur
- DOCTOR: bagli oldugu SELF kullanicilarini gorur, klinik not/izleme akisina katilir

## 2.2 Uca uca sistem mimarisi

Uretim odakli hedef akis:
- ESP32 Firmware
- BLE ile mobil uygulama
- Mobil tarafindan backend/Firebase senkronizasyonu
- FastAPI backend uzerinde risk-anomali-alert isleme
- Gerekirse AI pipeline ile ileri analiz ve raporlama

Gelistirme/debug akisinda:
- host_bridge araclari ile serial veya replay uzerinden paket enjeksiyonu

## 2.3 Klasor bazli tam envanter

### Kok dizin (proje seviyesi)
- [backend](backend): FastAPI servis katmani, veritabani, ACL, repository pattern
- [mobile](mobile): Flutter istemci, rol bazli ekranlar, durum yonetimi
- [firmware](firmware): ESP32 PlatformIO firmware, sensor ve BLE/Wi-Fi transport
- [host_bridge](host_bridge): serial okuyucu, ingestion bridge, mock emitter, replay araclari
- [healthalert_final_ai](healthalert_final_ai): egitim, degerlendirme, veri hazirlama, raporlama
- [docs](docs): teknik raporlar, dataset ve stabilizasyon dokumanlari
- [Data](Data): ham/islenmis veri havuzlari
- [outputs](outputs): modeller, loglar, rapor ciktilari
- [report_bundle](report_bundle): ozet, metrik, figur, confusion matrix ve konfigurasyon paketleri
- [reports](reports): model ve rapor artefaktlari
- [src](src): legacy veya deneysel egitim scriptleri

## 2.4 Backend detaylari (FastAPI + SQLAlchemy + Repository Pattern)

Ana dosyalar:
- [backend/main.py](backend/main.py): uygulama bootstrap, router kayitlari, startup akislar
- [backend/models.py](backend/models.py): ORM tablolari
- [backend/schemas.py](backend/schemas.py): request/response kontratlari
- [backend/database.py](backend/database.py): async DB baglantisi
- [backend/config.py](backend/config.py): ortam ayarlari
- [backend/seed.py](backend/seed.py): demo kullanici, iliski ve cihaz kayit tohumlamasi

Router katmani (onecikan):
- Auth, user, link code, live, ingestion, alerts, anomalies, history, notifications, settings, clinical notes, model window
- Yeni eklenen hasta erisim katmani:
  - [backend/routers/patients_router.py](backend/routers/patients_router.py)

Repository yapisi:
- [backend/repositories/base.py](backend/repositories/base.py): soyut sozlesmeler
- [backend/repositories/sqlite](backend/repositories/sqlite): SQLite uygulamalari
- [backend/repositories/firebase](backend/repositories/firebase): Firebase uygulamalari
- [backend/repositories/factory.py](backend/repositories/factory.py): sqlite/firebase/hybrid secimi

Durum:
- RBAC ve iliski tabanli ACL aktif
- SELF-RELATIVE-DOCTOR akisinda canli veri erisimi endpoint seviyesinde dogrulandi
- Demo veri ve cihaz mapping tohumlamasi mevcut

## 2.5 Mobile detaylari (Flutter)

Ana yapi:
- [mobile/lib/main.dart](mobile/lib/main.dart): rol bazli ana yonlendirme
- [mobile/lib/core/state/app_controller.dart](mobile/lib/core/state/app_controller.dart): uygulama merkezi state
- [mobile/lib/core/services/api_client.dart](mobile/lib/core/services/api_client.dart): backend baglantisi
- [mobile/lib/core/services/transport_orchestrator.dart](mobile/lib/core/services/transport_orchestrator.dart): BLE/transport akisi
- [mobile/lib/core/services/ble_device_service.dart](mobile/lib/core/services/ble_device_service.dart): cihaz baglantisi

UI katmani:
- Doktor, yakin ve SELF icin ayrik ekran konteynerleri
- Dashboard, canli monitor, bildirim, gecmis ve ayarlar ekranlari

Durum:
- Rol tabanli ekran ayrimi uygulanmis
- Monitored user listesi artik hasta-erisim endpointleriyle daha temiz akiyor
- Geriye donuk uyumluluk icin fallback akis korunuyor

## 2.6 Firmware detaylari (ESP32 + PlatformIO)

Ana dosyalar:
- [firmware/platformio.ini](firmware/platformio.ini): kart, framework, kutuphaneler
- [firmware/src/main.cpp](firmware/src/main.cpp): cihaz dongusu, sensor toplama, paket cikisi
- [firmware/include/ha_config.h](firmware/include/ha_config.h): merkezi cihaz konfigu
- [firmware/include/ha_packet.h](firmware/include/ha_packet.h): paket serilestirme
- [firmware/include/ha_types.h](firmware/include/ha_types.h): veri yapilari
- [firmware/include/ha_acquisition.h](firmware/include/ha_acquisition.h): sensor toplama yonetimi
- [firmware/include/ha_ble.h](firmware/include/ha_ble.h): BLE transport katmani
- [firmware/include/ha_wifi_transport.h](firmware/include/ha_wifi_transport.h): Wi-Fi fallback

Durum:
- BLE ana yol, Wi-Fi fallback prensibi korunuyor
- Sensor mock/real gecis ve debug komut altyapisi mevcut
- Konfigurasyon parametreleri proje hedefiyle uyumlu

## 2.7 Host Bridge detaylari

Araclar:
- [host_bridge/serial_reader.py](host_bridge/serial_reader.py): serial paket kaydi
- [host_bridge/ingestion_bridge.py](host_bridge/ingestion_bridge.py): serial to backend forward
- [host_bridge/mock_serial_emitter.py](host_bridge/mock_serial_emitter.py): test paket uretimi
- [host_bridge/replay_tool.py](host_bridge/replay_tool.py): kayitli veriyi yeniden oynatma
- [host_bridge/packet_schema.py](host_bridge/packet_schema.py): ortak paket semasi

Durum:
- Gelistirme/test ortami icin kritik debug katmani
- Uretim yolunun yerine gecen degil, destekleyici arac seti

## 2.8 AI/ML katmani detaylari

Ana yapi:
- [healthalert_final_ai/config](healthalert_final_ai/config): base, data, train, inference
- [healthalert_final_ai/src](healthalert_final_ai/src): data/model/training/inference modulleri
- [healthalert_final_ai/scripts](healthalert_final_ai/scripts): egitim/degerlendirme araclari
- [healthalert_final_ai/tests](healthalert_final_ai/tests): test kapsami
- [healthalert_final_ai/reports](healthalert_final_ai/reports): model ve deney raporlari

Durum:
- Cok gorevli modelleme, risk birlestirme ve ozel veri boru hatti mevcut
- Arsiv temizligi ve sunum odakli duzenlemeler aktif calisma halinde
- Activity v2 notu: saf ADL derlemesi su an UCI-HAR merkezli, bazi kaynaklar eksik/ayiklanmis

## 2.9 Veri, cikti ve raporlama katmani

One cikan klasorler:
- [Data](Data): veri havuzlari
- [outputs](outputs): model/log/cikti havuzu
- [report_bundle](report_bundle): metrik/figur/konfig paketleri
- [docs](docs): proje raporlari ve dataset surec dokumanlari

Bu katman, deney tekrarlanabilirligi ve sunum hazirligi acisindan kritik rol oynar.

## 2.10 Guvenlik ve yetkilendirme resmi

Kimlik dogrulama:
- JWT tabanli auth

Yetkilendirme:
- Rol tabanli kontroller + iliski tabanli ACL
- Yetkisiz hasta verisi erisimlerinde 403

Bu model, doktor/yakin izleme ihtiyacini karsilarken SELF gizliligini koruyacak sekilde uygulanmistir.

## 2.11 Demo ve calistirma hazirligi

Demo kullanicilar:
- self@demo.com / demo1234
- relative@demo.com / demo1234
- doctor@demo.com / demo1234

Demo akisinin beklenen sonucu:
- Doktor ve yakin, bagli SELF kullanicinin canli ve ozet verisini gorebilir
- SELF yalnizca kendi verisini gorur
- Yetkisiz veri denemeleri 403 ile engellenir

## 2.12 Sonuc

Proje; backend, mobile, firmware, host bridge ve AI katmanlariyla birlikte tam bir uca uca saglik izleme platformu haline gelmistir.

Son oturumda yapilan rol bazli hasta erisim gelistirmeleri, mevcut mimariyi bozmadan sisteme eklenmis; endpoint seviyesi ACL, mobil istemci uyarlamasi ve canli dogrulamalarla birlikte isletime alinmistir.
