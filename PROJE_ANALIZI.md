# HealthAlert — Kapsamlı Proje Analizi

> Hazırlanan bu doküman, projenin her klasörünü, her dosyasını ve her dosyanın içindeki kodun ne işe yaradığını akademik bir sunum için detaylı şekilde açıklamaktadır.

---

## İÇİNDEKİLER

1. [Projeye Genel Bakış](#1-projeye-genel-bakış)
2. [Sistem Mimarisi ve Veri Akışı](#2-sistem-mimarisi-ve-veri-akışı)
3. [Kök Dizin Dosyaları](#3-kök-dizin-dosyaları)
4. [backend/ — FastAPI Sunucu](#4-backend--fastapi-sunucu)
5. [firmware/ — ESP32 Gömülü Yazılım](#5-firmware--esp32-gömülü-yazılım)
6. [host_bridge/ — Geliştirici Araçları](#6-host_bridge--geliştirici-araçları)
7. [mobile/ — Flutter Mobil Uygulama](#7-mobile--flutter-mobil-uygulama)
8. [healthalert_final_ai/ — Makine Öğrenmesi Boru Hattı](#8-healthalert_final_ai--makine-öğrenmesi-boru-hattı)
9. [Data/ — Veri Setleri](#9-data--veri-setleri)
10. [outputs/ ve report_bundle/ — Çıktılar](#10-outputs-ve-report_bundle--çıktılar)
11. [Temel Tasarım Kalıpları](#11-temel-tasarım-kalıpları)
12. [Kullanılan Teknoloji Yığını](#12-kullanılan-teknoloji-yığını)
13. [Rol Tabanlı Erişim Kontrolü](#13-rol-tabanlı-erişim-kontrolü)
14. [Güvenlik Tasarımı](#14-güvenlik-tasarımı)

---

## 1. Projeye Genel Bakış

**HealthAlert**, gerçek zamanlı sağlık izleme ve düşme tespiti yapan, uçtan uca çalışan bir platform sistemidir. Sistem; gömülü donanım (ESP32 mikrodenetleyici), mobil uygulama (Flutter), bulut destekli bir sunucu (FastAPI + Firebase) ve yapay zeka tabanlı bir çıkarım motoru (PyTorch) olmak üzere dört ana katmandan oluşmaktadır.

### Sistemin Temel Amacı

| Hedef | Açıklama |
|---|---|
| **Gerçek Zamanlı İzleme** | Kalp atış hızı (HR), kan oksijen satürasyonu (SpO2), ivme ve jiroskop verilerinin sürekli takibi |
| **Düşme Tespiti** | Makine öğrenmesi modeli ile anlık düşme ve dengesizlik tespiti |
| **Alarm Yönetimi** | Anormal değerlerde otomatik uyarı üretimi ve zincir bildirimi |
| **Çok Kullanıcılı Erişim** | SELF (hasta), RELATIVE (yakın), DOCTOR (doktor) rol hiyerarşisi |
| **Klinik Entegrasyon** | Doktorların hasta notları ekleyebileceği bir klinik not sistemi |

### Kullanıcı Rolleri

```
SELF (Hasta)
  → Kendi sağlık verilerini görür
  → Alarmları TAMAM veya ACİL olarak yanıtlar
  → Bağlantı kodu oluşturarak yakın/doktora erişim izni verir

RELATIVE (Yakın)
  → Bağlı olduğu hastanın verilerini izler
  → Anlık durum ve alarm bildirimlerini alır

DOCTOR (Doktor)
  → Tam hasta verisi erişimi + klinik not yazabilme
  → Birden fazla hasta izleme yetkisi
```

---

## 2. Sistem Mimarisi ve Veri Akışı

### Üretim Ortamı Veri Akışı

```
┌─────────────────────────────────────────────────┐
│              ESP32 Firmware (Gömülü)            │
│  MPU6050 (IMU) + MAX30102 (PPG) sensörleri      │
│  → JSON paket üretir, BLE/Wi-Fi ile iletir      │
└───────────────────┬─────────────────────────────┘
                    │ BLE (birincil) / Wi-Fi (yedek)
                    ▼
┌─────────────────────────────────────────────────┐
│          Flutter Mobil Uygulama                 │
│  BLE alıcısı + Transport Orchestrator           │
│  → Firebase/Firestore'a bulut senkronizasyonu   │
└───────────────────┬─────────────────────────────┘
                    │ Firebase / Firestore
                    ▼
┌─────────────────────────────────────────────────┐
│          FastAPI Backend (Python)               │
│  Repository katmanı (SQLite/Firebase/Hybrid)    │
│  Servisler: Anomali → Alarm → Bildirim          │
│  LLM Sağlık Asistanı (OpenAI uyumlu API)       │
└───────────────────┬─────────────────────────────┘
                    │ Çıkarım sonuçları
                    ▼
┌─────────────────────────────────────────────────┐
│       ML Çıkarım Motoru (PyTorch)               │
│  4 Başlıklı Model: Düşme / Dengesizlik /        │
│  PPG Kalitesi / Risk Skoru                      │
└─────────────────────────────────────────────────┘
```

### Geliştirme Ortamı Veri Akışı (Yalnızca Geliştirme/Debug)

```
ESP32 → USB Seri Port → host_bridge/ araçları → POST /ingest/device-packet
```

> **Not:** USB/seri bağlantı üretim ortamında kullanılmaz; yalnızca firmware geliştirme ve hata ayıklama içindir.

---

## 3. Kök Dizin Dosyaları

```
HealthAlert/
├── requirements.txt          # Kök seviye Python bağımlılıkları
├── README.ME                 # Boş, henüz doldurulmamış
├── generate_report_bundle.py # Rapor paketleme betiği
└── chat_body.json            # LLM sohbet test verisi
```

### `requirements.txt`
Veri bilimi çalışmaları için temel Python kütüphanelerini içerir:
- `numpy`, `scipy`: Sayısal hesaplama
- `matplotlib`: Veri görselleştirme
- `scikit-learn`: Makine öğrenmesi yardımcıları
- `torch`: PyTorch derin öğrenme çatısı

### `generate_report_bundle.py`
ML eğitim çıktılarını (metrikler, karışıklık matrisleri, eğri grafikleri, model kontrol noktaları) tek bir arşiv paketinde toplamak için kullanılan yardımcı betiktir. `report_bundle/` klasörü altına klasörlenmiş çıktı üretir.

---

## 4. backend/ — FastAPI Sunucu

Backend, Python ile yazılmış, asenkron mimariye sahip bir REST API sunucusudur. Veri depolama için SQLite (yerel), Firebase Firestore (bulut) veya ikisinin karma modunu destekler. LLM tabanlı sağlık asistanı entegrasyonu da bu katmanda yer alır.

```
backend/
├── main.py                    # Uygulama giriş noktası
├── config.py                  # Ortam değişkenleri ve ayarlar
├── database.py                # Asenkron SQLAlchemy motoru
├── auth.py                    # JWT + Bcrypt yardımcıları
├── models.py                  # 14 SQLAlchemy ORM tablosu
├── schemas.py                 # Pydantic istek/yanıt modelleri
├── firebase_client.py         # Firebase Admin SDK başlatıcı
├── seed.py                    # Demo verisi tohumlayıcı
├── repositories/              # Veri erişim katmanı (Repository Pattern)
├── routers/                   # HTTP endpoint'leri (12 yönlendirici)
└── services/                  # İş mantığı servisleri
```

---

### 4.1 `main.py` — Uygulama Giriş Noktası

```python
# Çalıştırma komutu:
uvicorn main:app --reload --port 8000
```

**Ne yapar?**
- `FastAPI()` uygulamasını oluşturur ve tüm CORS politikalarını ayarlar (demo için tüm kaynaklara izin verilir).
- Aşağıdaki 12 yönlendiriciyi kayıt eder:
  `auth`, `users`, `link_codes`, `live_status`, `anomalies`, `alerts`, `history`, `notifications`, `clinical_notes`, `settings`, `ingestion`, `assistant`
- Uygulama başlarken sırayla şunları çalıştırır:
  1. `init_db()` → Tüm veritabanı tablolarını oluşturur
  2. `init_firebase()` → Firebase bağlantısını başlatır
  3. `seed_demo_data()` → Demo kullanıcılarını oluşturur (ilk çalışmada)
  4. `start_simulation_loop()` → Simülasyon motorunu arka planda başlatır
- `GET /health` endpoint'i sunucu sağlık kontrolü için kullanılır.

---

### 4.2 `config.py` — Ortam Ayarları

Pydantic `BaseSettings` kullanılarak `.env` dosyasından veya ortam değişkenlerinden okunan ayarları yönetir.

| Ayar | Açıklama | Varsayılan |
|---|---|---|
| `SECRET_KEY` | JWT imzalama anahtarı | Gerekli |
| `ALGORITHM` | JWT algoritması | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token geçerlilik süresi | 7 gün |
| `DATABASE_URL` | SQLite bağlantı dizesi | `sqlite+aiosqlite:///healthalert.db` |
| `DATA_MODE` | Depolama modu | `sqlite` / `firebase` / `hybrid` |
| `SIMULATION_INTERVAL_SECONDS` | Simülasyon döngü hızı | `4.0` saniye |
| `LINK_CODE_EXPIRE_HOURS` | Bağlantı kodu geçerliliği | `48` saat |
| `LLM_API_KEY` | LLM sağlayıcı API anahtarı | Opsiyonel |
| `LLM_BASE_URL` | LLM API adresi | `https://api.openai.com/v1` |
| `LLM_MODEL` | Kullanılan dil modeli | `gpt-4o-mini` |

---

### 4.3 `database.py` — Veritabanı Altyapısı

- `aiosqlite` sürücüsü üzerinden `AsyncEngine` oluşturur (asenkron I/O).
- `AsyncSessionLocal` fabrikası; her HTTP isteği için izole bir veritabanı oturumu sağlar.
- `Base` sınıfı tüm ORM modellerinin türediği `DeclarativeBase`'dir.
- `get_db()` fonksiyonu FastAPI bağımlılık enjeksiyonu ile çalışır; her istek için yeni bir oturum açar ve istek bittikten sonra otomatik kapatır.
- `init_db()` başlangıçta `Base.metadata.create_all()` çağrısı yaparak tabloları oluşturur.

---

### 4.4 `auth.py` — Kimlik Doğrulama Yardımcıları

Üç temel işlev sağlar:

```python
verify_password(plain, hashed)  # bcrypt karşılaştırması
hash_password(plain)            # bcrypt hashleme
create_access_token(data, expires_delta)  # JWT üretimi
decode_token(token)             # JWT doğrulama ve payload döndürme
```

JWT payload'u içinde `sub` (kullanıcı ID) ve `exp` (son geçerlilik tarihi) bulunur.

---

### 4.5 `models.py` — Veritabanı Tabloları (14 Tablo)

Tüm tablolar SQLAlchemy ORM ile tanımlanmıştır ve `asyncio` uyumludur.

| # | Tablo | İçeriği |
|---|---|---|
| 1 | **User** | E-posta, şifre hash, rol (SELF/RELATIVE/DOCTOR), tam ad, telefon, doğum tarihi |
| 2 | **LinkCode** | 6 haneli bağlantı kodu, oluşturan kullanıcı, son kullanım tarihi, kalan kullanım hakkı |
| 3 | **UserRelation** | Hasta ↔ Yakın/Doktor bağlantısı, aktif/pasif durumu |
| 4 | **LiveStatus** | Son canlı ölçüm: HR, SpO2, hareket skoru, risk skoru, senaryo, zaman damgası |
| 5 | **DevicePacketLog** | Ham ESP32 paket geçmişi: ivme, jiroskop, PPG ham değerleri |
| 6 | **DeviceRegistration** | Cihaz ID → Kullanıcı ID eşlemesi |
| 7 | **AnomalyEvent** | Anormallik kaydı: metrik adı, değer, eşik, önem derecesi |
| 8 | **AlertEvent** | Aktif alarm: geri sayım süresi, öneriler, durum (ACTIVE/OKAY/EMERGENCY/RESOLVED) |
| 9 | **PostEventSession** | Alarm sonrası izleme oturumu |
| 10 | **HistoryItem** | Zaman damgalı olay günlüğü girişleri |
| 11 | **NotificationItem** | Kullanıcıya gönderilen bildirimler (okundu bayrağı) |
| 12 | **ClinicalNote** | Doktor → Hasta klinik notları |
| 13 | **AppSettings** | Kullanıcı tercihleri: batarya modu, bildirim ayarları |
| 14 | **SimulationState** | Her SELF kullanıcısı için simülasyon senaryo takibi |

---

### 4.6 `schemas.py` — Pydantic Şemaları

HTTP istek ve yanıt modellerini tanımlar. Pydantic v2 kullanılmıştır ve tüm modeller `from_attributes=True` ile ORM nesnelerinden doğrudan oluşturulabilir.

Başlıca şema grupları:
- **Auth**: `RegisterRequest`, `LoginRequest`, `TokenResponse`
- **User**: `UserResponse`, `UpdateProfileRequest`
- **LinkCode**: `LinkCodeResponse`, `RedeemCodeRequest`, `RedeemCodeResponse`
- **Live/Anomaly/Alert/History/Notification**: Her biri için karşılıklı istek/yanıt çiftleri
- **Device**: `DevicePacketRequest` (ESP32'den gelen paketler), `DeviceRegistrationRequest`
- **Assistant**: `AssistantSummaryResponse`, `TrendAnalysisResponse`

---

### 4.7 `firebase_client.py` — Firebase Entegrasyonu

- `DATA_MODE` ayarına göre Firebase Admin SDK'yı koşullu olarak başlatır.
- Servis hesabı JSON dosyasını (`healthalertsystem-2776a-firebase-adminsdk-...json`) okur.
- `get_firestore_client()` yardımcısı ile Firestore bağlantısı döndürür.
- Kimlik bilgisi hatası durumunda sessizce SQLite moduna geri döner (graceful fallback).

---

### 4.8 `seed.py` — Demo Veri Tohumlayıcı

Uygulama ilk çalıştırıldığında otomatik olarak demo ortamı hazırlar:

1. 3 demo kullanıcı oluşturur:
   - `demo@demo.com` → SELF rolü (hasta)
   - `relative@demo.com` → RELATIVE rolü (yakın)
   - `doctor@demo.com` → DOCTOR rolü (doktor)
   - Tüm şifreler: `demo1234`
2. Kullanıcılar arasında `UserRelation` bağlantıları kurar.
3. Başlangıç geçmişi, anormallik kayıtları ve bildirimleri ekler.
4. `AppSettings` ve `SimulationState` kayıtları oluşturur.

---

### 4.9 `repositories/` — Repository Soyutlama Katmanı

Bu klasör, **Repository Pattern** tasarım kalıbını uygular. Amaç: veri kaynağı (SQLite, Firebase veya her ikisi) değişse bile üst katmanların (router, service) etkilenmemesidir.

```
repositories/
├── __init__.py
├── base.py       # 13 soyut temel sınıf (Abstract Base Classes)
├── factory.py    # Doğru implementasyonu döndüren fabrika fonksiyon
├── firebase/     # Firestore implementasyonları
└── sqlite/       # SQLite implementasyonları
```

#### `repositories/base.py`
13 soyut sınıf tanımlar; her biri bir veri varlığına karşılık gelir:
`AbstractUserRepo`, `AbstractLinkCodeRepo`, `AbstractRelationRepo`, `AbstractLiveStatusRepo`, `AbstractAnomalyRepo`, `AbstractAlertRepo`, `AbstractPostEventRepo`, `AbstractHistoryRepo`, `AbstractNotificationRepo`, `AbstractClinicalNoteRepo`, `AbstractSettingsRepo`, `AbstractSimulationStateRepo`, `AbstractDeviceRepo`

Tüm metodlar `async` tanımlanmıştır ve `Dict[str, Any]` döndürür — bu sayede JSON uyumlu veri transferi sağlanır.

#### `repositories/factory.py`
- `RepoSet` dataclass'ı: 13 repo alanını tek bir nesnede toplar.
- `get_repos(db, mode)` fabrika fonksiyonu: `DATA_MODE` ayarına göre doğru implementasyon setini döndürür.
- `_HybridRepo` proxy sınıfı: Okuma işlemlerini SQLite'tan, yazma işlemlerini hem SQLite hem Firestore'a yönlendirir.

```
DATA_MODE = "sqlite"   → Yalnızca SQLite
DATA_MODE = "firebase" → Yalnızca Firestore
DATA_MODE = "hybrid"   → Okuma: SQLite | Yazma: SQLite + Firestore
```

---

### 4.10 `routers/` — HTTP Endpoint'leri

Her yönlendirici dosyası belirli bir işlevsel alanı kapsar.

#### `auth_router.py`
| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/auth/register` | Yeni hesap oluşturma (rol zorunlu) |
| POST | `/auth/login` | JWT token üretimi |

#### `users_router.py`
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/users/me` | Mevcut kullanıcı profili |
| PUT | `/users/me` | Profil güncelleme |
| GET | `/users/{user_id}` | Başka kullanıcının profili |

#### `link_codes_router.py`
Bağlantı kodu sistemi: Bir hasta (SELF), 6 haneli kod üretir. Yakın veya doktor bu kodu girerek hastaya bağlanır.

| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/link-codes/generate` | 6 haneli kod üret (RELATIVE/DOCTOR) |
| GET | `/link-codes/mine` | Kendi aktif kodlarını listele |
| DELETE | `/link-codes/{code_id}` | Kodu iptal et |
| POST | `/link-codes/redeem` | Kodu kullanarak bağlantı kur |

#### `live_status_router.py`
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/live/{user_id}` | Son HR/SpO2/hareket/risk değerleri |

#### `alerts_router.py`
Alarm yaşam döngüsünü yönetir.

| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/alerts` | Kullanıcının alarmları |
| GET | `/alerts/active` | Aktif alarm (SELF) |
| GET | `/alerts/{user_id}/for-linked` | Bağlı hastanın alarmlari (ACL kontrollü) |
| PUT | `/alerts/{alert_id}/respond` | OKAY veya EMERGENCY geçişi + bildirim fan-out |

#### `anomalies_router.py`
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/anomalies` | Kullanıcının anormallikleri |
| GET | `/anomalies/{user_id}` | Bağlı hastanın anormallikleri |

#### `history_router.py`, `notifications_router.py`, `settings_router.py`
Sırasıyla olay geçmişi, bildirimler ve uygulama ayarları için CRUD endpoint'leri sağlar.

#### `clinical_notes_router.py`
| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/clinical-notes` | Not oluştur (yalnızca DOCTOR) |
| GET | `/clinical-notes/{patient_id}` | Notları getir |
| PUT | `/clinical-notes/{note_id}` | Notu güncelle |
| DELETE | `/clinical-notes/{note_id}` | Notu sil |

#### `ingestion_router.py`
ESP32 cihazından gelen ham sensör paketlerini işler.

| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/ingest/device-packet` | ESP32 paketini al, hareket/risk skoru hesapla, LiveStatus güncelle |
| POST | `/ingest/register-device` | Cihaz ID'yi kullanıcıya bağla |
| GET | `/ingest/device-status/{device_id}` | Cihaz kayıt durumunu kontrol et |

**Risk hesaplama mantığı:**
```
motion_score = ivme_sapması + jiroskop_büyüklüğü
risk_score   = HR_anomalisi × 0.4 + SpO2_anomalisi × 0.4 + motion_score × 0.2
```

#### `assistant_router.py`
LLM tabanlı sağlık asistanı endpoint'leri. OpenAI, Azure OpenAI, Ollama veya herhangi bir OpenAI uyumlu API ile çalışır.

| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/assistant/summary` | Kullanıcı/hasta için AI özeti üretir |
| GET | `/assistant/alert-explanation/{alert_id}` | Alarm açıklaması oluşturur |
| GET | `/assistant/daily-summary` | Günlük sağlık özeti |
| GET | `/assistant/trends` | Trend analizi |

#### `deps.py` — Bağımlılık Enjeksiyonu
- `OAuth2PasswordBearer` ile `Authorization: Bearer <token>` başlığını çözer.
- `get_current_user(token)` → Token'ı doğrular, kullanıcıyı veritabanından çeker.
- `get_repo_set(db)` → `DATA_MODE`'a göre doğru `RepoSet`'i enjekte eder.

---

### 4.11 `services/` — İş Mantığı Servisleri

```
services/
├── ai_bridge.py          # ML sonuçlarını backend'e bağlayan köprü
├── alert_service.py      # Alarm durum makinesi geçiş mantığı
├── assistant_service.py  # LLM asistan sorgu üretimi
├── chat_service.py       # Sohbet geçmişi yönetimi
├── context_builder.py    # LLM için hasta bağlam metni oluşturucu
├── firestore_watcher.py  # Firestore değişiklik dinleyicisi
├── llm_client.py         # Provider-agnostik LLM HTTP istemcisi
├── notification.py       # Bildirim fan-out (tüm bağlı kullanıcılara)
├── prompt_templates.py   # LLM sistem/kullanıcı prompt şablonları
├── push_service.py       # FCM push bildirim gönderici
├── simulation.py         # Canlı veri simülasyon motoru
└── trend_service.py      # Vitals trend hesaplama servisi
```

#### `simulation.py` — Simülasyon Motoru
Demo ortamı için gerçek donanım olmadan canlı veri üretir. Arka planda asenkron bir döngü olarak çalışır.

**10 Senaryo Dizisi:**

| Senaryo | HR Aralığı | SpO2 | Tetikleyici |
|---|---|---|---|
| normal | 62–72 bpm | %97–99 | Yok |
| elevated_hr | 95–115 bpm | %96–97 | Anormallik uyarısı |
| warning | 118–130 bpm | %96 | Alarm (warning) |
| normal | 62–72 bpm | %97–99 | Yok (iyileşme) |
| low_spo2 | 70–80 bpm | %88–91 | Kritik anormallik + alarm |
| recovery | 70–80 bpm | %93–95 | Yok |
| normal | 62–72 bpm | %97–99 | Yok |
| motion_instability | 70–80 bpm | %96–98 | Yüksek jiroskop → anormallik |
| normal | 62–72 bpm | %97–99 | Yok |
| normal | 62–72 bpm | %97–99 | Yok |

Her tetikleyici senaryo: `AnomalyEvent` oluşturur → `AlertEvent` açar → tüm bağlı yakın/doktorlara `NotificationItem` gönderir.

#### `ai_bridge.py` — AI Köprüsü
ML çıkarım motorunun ürettiği yapılandırılmış sonucu (`RiskPostprocessorV2` çıktısı) backend repository katmanına bağlar:
- Risk seviyesini `AnomalyEvent`'e dönüştürür
- `AlertEvent` açar
- `LiveStatus`'u günceller
- Fan-out bildirimi tetikler

#### `llm_client.py` — LLM İstemcisi
Sağlayıcıdan bağımsız, asenkron, yeniden deneme mantığına sahip HTTP tabanlı LLM istemcisi. OpenAI, Azure OpenAI, Ollama, LM Studio, Together AI gibi tüm OpenAI uyumlu API'lerle çalışır. `LLM_API_KEY` ortam değişkeni ayarlanmamışsa sessizce devre dışı kalır.

#### `alert_service.py` — Alarm Durum Makinesi
```
normal → watch → warning → critical
         ↓           ↓          ↓
       OKAY      OKAY/EMERGENCY  EMERGENCY
         ↓           ↓          ↓
    post_event → resolved ← post_event
```

#### `notification.py` — Bildirim Fan-Out
`notify_linked_users()`: Bir hastanın tüm aktif `UserRelation` bağlantılarını bulur (RELATIVE ve DOCTOR rolleri) ve her birine `NotificationItem` oluşturur.

---

## 5. firmware/ — ESP32 Gömülü Yazılım

PlatformIO ile derlenen, Arduino framework üzerine kurulu C++ yazılımıdır. Gerçek sensör donanımı yoksa tam işlevli bir mock (simüle) modda çalışır.

```
firmware/
├── platformio.ini     # PlatformIO derleme ve kütüphane yapılandırması
├── src/
│   └── main.cpp       # ESP32 giriş noktası (setup + loop)
└── include/           # C++ başlık dosyaları (modüler mimari)
    ├── ha_config.h        # Merkezi yapılandırma sabitleri
    ├── ha_types.h         # Veri yapıları (struct tanımları)
    ├── ha_acquisition.h   # Sensör soyutlama katmanı
    ├── ha_mock_sensors.h  # Mock sensör motoru (7 senaryo)
    ├── ha_mpu6050.h       # MPU6050 IMU sürücüsü
    ├── ha_max30102.h      # MAX30102 PPG sürücüsü
    ├── ha_packet.h        # JSON paket formatlayıcı
    ├── ha_serial_cmd.h    # Seri port komut arayüzü
    ├── ha_ble.h           # BLE iletişim katmanı
    ├── ha_transport.h     # Transport yöneticisi (BLE/Wi-Fi)
    ├── ha_wifi_transport.h# Wi-Fi transport katmanı
    └── ha_i2c_scan.h      # I2C cihaz tarama yardımcısı
```

### `platformio.ini`
```ini
[env:esp32dev]
platform  = espressif32
board     = esp32dev
framework = arduino
monitor_speed  = 115200
upload_speed   = 921600
lib_deps:
  sparkfun/SparkFun MAX3010x ...  # PPG sensör kütüphanesi
  electroniccats/MPU6050          # IMU sensör kütüphanesi
  bblanchon/ArduinoJson v7.0.4    # JSON serileştirme
```

### `src/main.cpp`
ESP32 giriş noktasıdır. `setup()` ve `loop()` fonksiyonlarını içerir:

**`setup()` aşamaları:**
1. Seri port başlatma (115200 baud) ve başlık mesajı
2. I2C veri yolu başlatma (SDA=21, SCL=22, 400kHz)
3. I2C tarama ile donanım tespiti → Sensör bulunamazsa mock mod devreye girer
4. `AcquisitionManager` ve `SerialCmd` nesneleri başlatılır

**`loop()` aşamaları:**
1. Seri komutları işle (`SerialCmd.process()`)
2. Paket topla (`AcquisitionManager.collect()`)
3. JSON satırı oluştur (`toJsonLine()`)
4. Seri porta gönder (sonradan BLE/Wi-Fi'ya aktarılır)
5. Mod geçiş bayrakları kontrol edilir (mock ↔ gerçek)

### `include/ha_config.h` — Merkezi Yapılandırma
```cpp
#define FW_VERSION        "1.0.0"
#define HA_DEVICE_ID      "ha_device_001"
#define SDA_PIN           21
#define SCL_PIN           22
#define I2C_FREQ          400000    // 400kHz Fast Mode
#define SAMPLING_RATE_HZ  25        // 25 Hz örnekleme
#define PACKET_INTERVAL_MS 1000     // 1 paket/saniye
#define FORCE_MOCK_MODE   1         // 1=her zaman mock, 0=otomatik
#define SERIAL_BAUD       115200
```

### `include/ha_types.h` — Veri Yapıları
Üç temel struct tanımlanmıştır:

```cpp
struct ImuSample {
    float accel_x, accel_y, accel_z;  // m/s²
    float gyro_x, gyro_y, gyro_z;     // °/s
    bool  valid;
};

struct PpgSample {
    uint32_t red_value, ir_value;  // Ham ADC değerleri
    float    heart_rate, spo2;     // Hesaplanan değerler
    float    signal_quality;       // 0.0 – 1.0
    bool     finger_detected, hr_valid, spo2_valid, ppg_ok;
};

struct DevicePacket {
    // ImuSample + PpgSample + metadata alanları
    char     device_id[65];
    uint32_t timestamp_ms, packet_seq;
    char     mode[8];        // "real" veya "mock"
    char     state_hint[51]; // Senaryo ipucu
    bool     imu_ok, ppg_ok;
};
```

### `include/ha_acquisition.h` — Sensör Soyutlama
`AcquisitionManager` sınıfı, gerçek ve mock sensörler üzerinde tek bir arayüz sağlar:

```cpp
class AcquisitionManager {
    void begin(bool useMock);      // Başlatma
    DevicePacket collect();        // Tek çağrı ile tam paket al
    void setMockMode(bool mock);   // Çalışma anında mod değiştir
    void reinitSensors();          // Seri komutla yeniden başlat
    SensorStatus getStatus();      // IMU/PPG durumu
};
```

### `include/ha_mock_sensors.h` — Mock Sensör Motoru
7 senaryo tanımlar ve her biri için gerçekçi sinüzoidal veri üretir:

| Senaryo | HR | SpO2 | IMU |
|---|---|---|---|
| NORMAL | 70 bpm ± 5 | %98 | Minimal |
| ELEVATED_HR | 105 bpm ± 10 | %96 | Orta |
| LOW_SPO2 | 75 bpm ± 5 | %89 ± 1 | Minimal |
| MOTION_INSTABILITY | 80 bpm ± 5 | %97 | Yüksek jiroskop |
| WARNING_STATE | 120 bpm ± 8 | %96 | Orta |
| CRITICAL_STATE | 140 bpm ± 5 | %85 ± 2 | Yüksek |
| RECOVERY_STATE | 85 bpm ± 5 | %94 ± 1 | Azalan |

Senaryolar arası geçişlerde **50-tick kademeli blend** ile keskin değişimler önlenir.

### `include/ha_mpu6050.h` ve `include/ha_max30102.h`
Her iki dosya kendi sensörlerinin I2C sürücüsünü kapsüller:
- `begin()`: Sensörü başlatır, adres yoksa hata döner
- `read()`: Örnek okur ve ilgili struct'ı doldurur
- Zaman aşımında otomatik yeniden başlatma (`reinit on timeout`)
- `ha_config.h`'dan I2C adresi okur (MPU6050: `0x68`, MAX30102: `0x57`)

### `include/ha_packet.h` — JSON Paket Formatlayıcı
`ArduinoJson` kütüphanesi ile `DevicePacket`'i şu formata dönüştürür:
```json
{"device_id":"ha_device_001","timestamp_ms":12345,"mode":"mock",
 "packet_seq":42,"accel_x":0.01,"accel_y":0.02,"accel_z":9.81,
 "gyro_x":0.1,"gyro_y":0.05,"gyro_z":0.02,
 "red_value":80000,"ir_value":90000,
 "heart_rate":72.5,"spo2":98.2,"signal_quality":0.95,
 "imu_ok":true,"ppg_ok":true,"hr_valid":true,"spo2_valid":true,
 "finger_detected":true,"state_hint":"normal"}
```

### `include/ha_serial_cmd.h` — Seri Komut Arayüzü
Geliştirici debug komutlarını işler:
- `help` → Mevcut komutları listeler
- `mock` / `real` → Mod geçişi
- `restart_sensors` → Sensörleri yeniden başlatır
- `scenario <name>` → Mock senaryoyu dinamik olarak değiştirir

### `include/ha_ble.h` ve `include/ha_transport.h`
- BLE (Bluetooth Low Energy) üzerinden JSON paketleri gönderir
- `TransportManager`: Önce BLE'yi dener; başarısız olursa Wi-Fi'ya geçer (otomatik yedekleme)

---

## 6. host_bridge/ — Geliştirici Araçları

Bu klasör **yalnızca geliştirme ve debug** içindir. Üretim ortamında kullanılmaz. ESP32'yi USB seri porta bağlayıp verileri yakalamak veya backend'e iletmek için kullanılır.

```
host_bridge/
├── serial_reader.py       # USB seri portu dinleyici + kayıt
├── ingestion_bridge.py    # Seri port → Backend HTTP köprüsü
├── mock_serial_emitter.py # Mock paket üreticisi (donanımsız test)
├── replay_tool.py         # Kaydedilmiş paketleri tekrar oynatır
├── packet_schema.py       # Pydantic paket doğrulama şeması
└── requirements.txt       # pyserial, requests, pydantic, click
```

### `serial_reader.py`
ESP32'nin USB seri portundan JSON satırı paketleri okur ve diske kaydeder.

**CLI seçenekleri:**
```bash
python serial_reader.py --port COM3 --output capture.jsonl --format jsonl
python serial_reader.py --port /dev/ttyUSB0 --format csv --quiet
```

İçindeki `PacketWriter` sınıfı hem JSONL hem CSV formatını destekler. Her paket `packet_schema.py` ile doğrulanır.

### `ingestion_bridge.py`
Seri porttan okunan paketleri doğrudan backend API'sine HTTP POST ile iletir.

```bash
python ingestion_bridge.py \
  --port COM3 \
  --backend http://localhost:8000 \
  --token <JWT_TOKEN>
```

- Başarısız POST'lar yeniden deneme kuyruğuna alınır
- `requests.Session()` ile kalıcı bağlantı yönetimi

### `mock_serial_emitter.py`
Gerçek donanım olmadan mock paket üretir; stdout'a JSON satırları yazar. Diğer araçlarla pipe edilebilir.

```bash
# Tek senaryo, 0.5 saniye aralıkla, 100 paket:
python mock_serial_emitter.py --scenario elevated_hr --interval 0.5 --count 100

# Tüm senaryoları otomatik döngüyle, her birinden 30 paket:
python mock_serial_emitter.py --cycle --cycle-packets 30
```

### `replay_tool.py`
Daha önce `serial_reader.py` ile kaydedilmiş JSONL veya CSV dosyasını alır ve backend'e gerçek zamanlı oynatar.

```bash
python replay_tool.py \
  --file capture.jsonl \
  --backend http://localhost:8000 \
  --token <JWT_TOKEN> \
  --speed 2.0  # 2 kat hızlı oynat
```

`--dry-run` ile yalnızca veri doğrulaması yapılabilir, gerçekte gönderim yapılmaz.

### `packet_schema.py`
Firmware, host bridge ve backend arasında **ortak doğrulama** şeması sağlar. Pydantic v2 modeli:

```python
class DevicePacketSchema(BaseModel):
    device_id: str          # 1-64 karakter
    timestamp_ms: int       # ≥ 0
    mode: Literal["real", "mock"]
    packet_seq: int         # ≥ 0
    accel_x/y/z: float
    gyro_x/y/z: float
    red_value: int          # ≥ 0 (ham PPG)
    ir_value: int           # ≥ 0 (ham PPG)
    heart_rate: float
    spo2: float
    signal_quality: float   # 0.0 – 1.0
    imu_ok: bool
    ppg_ok: bool
    hr_valid: bool
    spo2_valid: bool
    finger_detected: bool
    state_hint: str         # ≤ 50 karakter
```

---

## 7. mobile/ — Flutter Mobil Uygulama

Flutter ile yazılmış çok platformlu (iOS/Android) mobil uygulamadır. Durum yönetimi için `ChangeNotifier` tabanlı `AppController` ve `InheritedNotifier` tabanlı `AppScope` kullanılır. Veri katmanı soyutlandığından gerçek Firebase entegrasyonu hazırlanmıştır.

```
mobile/lib/
├── main.dart               # Uygulama başlatma ve tema ayarı
├── firebase_options.dart   # Firebase yapılandırma seçenekleri
├── core/                   # İş mantığı katmanı
│   ├── config/             # Uygulama sabit değerleri ve tema
│   ├── firebase/           # Firestore eşleme placeholder'ları
│   ├── models/             # Domain varlık sınıfları (14 model)
│   ├── repositories/       # Arayüzler + mock implementasyonlar
│   ├── services/           # Servisler (durum makinesi, BLE, LLM)
│   └── state/              # AppController, AppScope, başlatma
└── ui/
    ├── screens/            # Tüm ekranlar (rol tabanlı)
    ├── theme/              # AppTheme sabitleri
    └── widgets/            # Yeniden kullanılabilir widget'lar
```

### `lib/main.dart`
- `WidgetsFlutterBinding.ensureInitialized()` ile Flutter başlatılır
- Firebase initialize edilir
- `AppController` oluşturulur ve `AppScope` ile sarılır
- `MaterialApp` oluşturularak `LoginScreen`'e yönlendirilir

---

### `lib/core/models/` — Domain Varlık Sınıfları

Flutter tarafındaki veri modelleri. Backend şemaları ile birebir eşlenir:

| Dosya | Model | İçeriği |
|---|---|---|
| `user_profile.dart` | `UserProfile` | Kullanıcı bilgileri, rol enum'u |
| `alert_event.dart` | `AlertEvent` | Alarm verisi, durum, geri sayım |
| `anomaly_event.dart` | `AnomalyEvent` | Anormallik verisi, önem derecesi |
| `live_status.dart` | `LiveStatus` | HR, SpO2, hareket, risk skoru |
| `history_item.dart` | `HistoryItem` | Zaman damgalı olay |
| `notification_item.dart` | `NotificationItem` | Bildirim, okundu bayrağı |
| `clinical_note.dart` | `ClinicalNote` | Doktor notu |
| `link_code.dart` | `LinkCode` | Bağlantı kodu verisi |
| `app_settings.dart` | `AppSettings` | Kullanıcı tercihleri |
| `enums.dart` | `UserRole`, `AlertStatus`, vb. | Tüm enum tanımları |
| `battery_profile.dart` | `BatteryProfile` | Batarya modu ayarları |
| `device_state.dart` | `DeviceState` | Cihaz bağlantı durumu |
| `emergency_contact.dart` | `EmergencyContact` | Acil iletişim |
| `user_relation.dart` | `UserRelation` | Kullanıcı bağlantı kaydı |

---

### `lib/core/services/` — Servisler

| Dosya | Açıklama |
|---|---|
| `alert_state_machine.dart` | Alarm durum geçişlerini yönetir (normal→watch→warning→critical) |
| `api_client.dart` | Backend REST API için HTTP istemcisi |
| `ble_device_service.dart` | ESP32 ile BLE bağlantısı ve paket okuma |
| `chat_service.dart` | LLM sohbet geçmişi ve API iletişimi |
| `firestore_sync_service.dart` | Firestore gerçek zamanlı senkronizasyon |
| `health_assistant_service.dart` | Sağlık asistanı sorgu yönetimi |
| `live_data_service.dart` | Canlı veri akışı yönetimi |
| `mock_demo_service.dart` | Demo senaryo simülatörü |
| `recommendation_service.dart` | Risk seviyesine göre öneri üretimi |
| `transport_orchestrator.dart` | BLE/Wi-Fi/Firebase transport yöneticisi |

---

### `lib/ui/screens/` — Ekranlar

Ekranlar **rol bazında** ayrılmıştır:

#### Ortak Ekranlar
| Ekran | Açıklama |
|---|---|
| `login_screen.dart` | Giriş ve kayıt akışı |
| `register_screen.dart` | Yeni hesap oluşturma |
| `dashboard_screen.dart` | Genel gösterge panosu |
| `alert_screen.dart` | Aktif alarm görüntüleme ve yanıtlama |
| `history_screen.dart` | Olay geçmişi |
| `notifications_screen.dart` | Bildirimler |
| `settings_screen.dart` | Uygulama ayarları |
| `profile_screen.dart` | Profil görüntüleme ve düzenleme |
| `live_monitor_screen.dart` | Canlı vitals izleme |
| `health_status_screen.dart` | Sağlık durumu özeti |
| `health_assistant_screen.dart` | LLM sağlık asistanı sohbet arayüzü |
| `post_event_monitor_screen.dart` | Alarm sonrası izleme |
| `battery_optimization_screen.dart` | Batarya modu seçimi |

#### SELF (Hasta) Ekranları — `screens/self/`
| Ekran | Açıklama |
|---|---|
| `generate_code_screen.dart` | Bağlantı kodu oluşturma |
| `redeem_code_screen.dart` | Kodu sisteme girme |
| `linked_people_screen.dart` | Bağlı kişileri listeleme |
| `history_detail_screen.dart` | Olay detay görünümü |

#### RELATIVE (Yakın) Ekranları — `screens/relative/`
| Ekran | Açıklama |
|---|---|
| `relative_dashboard_screen.dart` | Yakın gösterge panosu |
| `monitored_user_live_screen.dart` | İzlenen hastanın canlı verisi |
| `relative_alerts_screen.dart` | Bağlı hastanın alarmlari |
| `relative_history_screen.dart` | Hasta geçmişi |
| `relative_generate_code_screen.dart` | Bağlantı kodu oluşturma |

#### DOCTOR (Doktor) Ekranları — `screens/doctor/`
| Ekran | Açıklama |
|---|---|
| `doctor_dashboard_screen.dart` | Doktor gösterge panosu |
| `doctor_overview_screen.dart` | Tüm hastaların özeti |
| `patient_detail_screen.dart` | Hasta detay görünümü |
| `clinical_notes_screen.dart` | Klinik not ekleme/görüntüleme |
| `doctor_alerts_screen.dart` | Hasta alarmları |

---

## 8. healthalert_final_ai/ — Makine Öğrenmesi Boru Hattı

PyTorch tabanlı, çok görevli (multi-task) düşme tespiti ve sağlık risk değerlendirme ML sistemidir. 4 paralel çıktı başlığı içerir ve çok aşamalı eğitim stratejisi uygular.

```
healthalert_final_ai/
├── pyproject.toml         # Python paketi yapılandırması
├── requirements.txt       # ML bağımlılıkları
├── config/
│   ├── base.yaml          # Yollar, örnekleme hızı, eşikler
│   ├── data.yaml          # Veri seti yapılandırmaları
│   ├── train.yaml         # Model ve eğitim hiperparametreleri
│   └── inference.yaml     # Streaming çıkarım ayarları
├── src/
│   ├── data/              # Veri yükleme ve ön işleme
│   ├── models/            # Model mimarisi
│   ├── training/          # Eğitim döngüsü ve kayıp fonksiyonları
│   ├── inference/         # Çıkarım ve risk postprocessing
│   ├── simulation/        # Sentetik veri üretimi
│   └── utils/             # Yardımcı araçlar
├── scripts/               # CLI betikleri
├── tests/                 # Testler
└── outputs/               # Model çıktıları ve raporlar
```

---

### 8.1 `config/` — YAML Yapılandırmaları

#### `base.yaml`
```yaml
signal:
  target_sr: 50          # 50 Hz hedef örnekleme hızı
  window_size: 200        # 4 saniyelik pencere (200 örnek @ 50Hz)
  stride: 50              # Pencere kaydırma adımı

risk_thresholds:
  hr_low: 50              # bpm - bradikardi alt sınırı
  hr_high: 120            # bpm - taşikardi üst sınırı
  spo2_critical: 92       # % - kritik hipoksi eşiği
  fall_prob: 0.5          # Düşme karar eşiği
  instability_prob: 0.4   # Dengesizlik karar eşiği
```

#### `data.yaml`
3 veri seti yapılandırmasını içerir:
- **HIFD**: 21 denekten bilek üstü IMU+PPG, `.mat` format, 3 sınıf (fall/adl/near_fall)
- **BUT_PPG**: PPG kalite anotasyonları ve HR/SpO2 gerçek değerleri (WFDB format)
- **WEDA_FALL**: 25 denek (14 genç + 11 yaşlı), CSV 50Hz, IMU-only düşme/ADL

Bölme stratejisi: **%70 eğitim / %15 doğrulama / %15 test** — **konu bazlı** (aynı kişi iki sette olmaz → veri sızıntısı yok).

#### `train.yaml`
Model mimarisi ve eğitim hiperparametreleri:

```yaml
model:
  imu_encoder:   # CRNN: 3-katlı CNN + 2-katlı GRU
    cnn_channels: [32, 64, 128]
    rnn_hidden: 128
    rnn_layers: 2
  ppg_encoder:   # 1D CNN
    channels: [16, 32, 64]
  vitals_mlp:    # 2 → 32 → 16 boyutlar
  fusion:        # 4-başlıklı dikkat mekanizması (Attention)
  quality_gate:  # Eşik tabanlı PPG kalite filtresi

loss_weights:
  fall: 1.0          # Focal Loss
  instability: 0.5   # Binary Cross-Entropy + pos_weight=5.0
  quality: 0.3       # Binary Cross-Entropy + pos_weight=3.0
  risk: 0.4          # Mean Squared Error

optimizer: AdamW
scheduler: CosineAnnealingLR
epochs: 100
batch_size: 64
gradient_clip: 1.0
```

#### `inference.yaml`
Streaming (akış) çıkarım için:
```yaml
streaming:
  buffer_size: 200   # 200 örnek tampon
  stride: 100        # %50 örtüşme
  ema_alpha: 0.3     # Üstel hareketli ortalama yumuşatma

risk_levels:
  watch: 0.5         # İzle
  warning: 0.7       # Uyarı
  critical: 1.0      # Kritik

fusion_weights:
  fall: 0.35
  instability: 0.20
  vital_risk: 0.25
  ppg_quality_penalty: 0.20
```

---

### 8.2 `src/data/` — Veri Katmanı

```
src/data/
├── base_dataset.py       # Temel çok-modal veri seti sınıfı
├── column_schema.py      # Birleşik sütun tanımları (tüm veri setleri için)
├── dataset_registry.py   # Veri seti kataloğu
├── loaders/
│   ├── hifd_loader.py    # HIFD .mat dosya yükleyici
│   ├── but_ppg_loader.py # BUT_PPG WFDB format yükleyici
│   └── weda_loader.py    # WEDA_FALL CSV yükleyici
├── preprocessing/
│   ├── resampling.py     # Örnekleme hızı dönüşümü (50Hz hedef)
│   ├── windowing.py      # Kayan pencere segmentasyonu
│   ├── gravity.py        # İvmemetre'den yerçekimi bileşeni çıkarma
│   └── normalization.py  # Özellik normalizasyonu
└── feature_engineering/
    └── handcrafted.py    # RMS, enerji, frekans alanı özellikleri
```

**`column_schema.py`:** Tüm veri setlerini ortak bir sütun isim uzayına eşler → farklı kaynaklardan gelen veriler aynı model girişine beslenebilir.

**`loaders/hifd_loader.py`:** Robüst `.mat` (MATLAB) dosya ayrıştırıcısı; hem açık anahtar hem de geri dönüş matris yorumlamayı destekler. Klasör adından etiket çıkarır (fall vs adl).

---

### 8.3 `src/models/` — Model Mimarisi

```
src/models/
├── multitask_model.py    # V1 model (referans)
├── multitask_model_v2.py # Son versiyon: 4 çıktı başlığı
├── blocks/
│   ├── cnn_block.py      # 1D evrişimsel blok
│   ├── rnn_block.py      # GRU yinelemeli blok
│   ├── attention.py      # Çok-başlıklı dikkat mekanizması
│   └── fusion.py         # Modal füzyon katmanı
└── heads/
    ├── fall_head.py         # İkili sınıflandırma (düşme/düşmeme)
    ├── instability_head.py  # İkili sınıflandırma (dengesizlik)
    ├── quality_head.py      # PPG kalite tahmini
    └── risk_head.py         # Sürekli risk skoru regresyon
```

**`multitask_model_v2.py` — Ana Model:**

```
IMU Girişi (6 kanal: accel_xyz + gyro_xyz)
    → CNN Blokları (32→64→128 filtre) + GRU (128 gizli)
    → IMU Temsili (128 boyut)

PPG Girişi (kırmızı + IR)
    → 1D CNN (16→32→64 filtre)
    → PPG Temsili (64 boyut)
    → Kalite Kapısı: signal_quality < eşik → sıfırla (attenuation)

Vitals Girişi (HR, SpO2)
    → MLP (2 → 32 → 16)
    → Vitals Temsili (16 boyut)

Tüm Temsiller → 4-Başlıklı Dikkat Füzyonu
    ↓
Paralel Çıktı Başlıkları:
    fall_head       → P(düşme)    ∈ [0,1]
    instability_head → P(dengesizlik) ∈ [0,1]
    quality_head    → P(iyi PPG kalitesi) ∈ [0,1]
    risk_head       → Risk skoru ∈ [0,1]
```

---

### 8.4 `src/training/` — Eğitim Altyapısı

```
src/training/
├── stage_trainer.py  # Çok aşamalı eğitim orchestrator
├── trainer.py        # Tek aşama eğitim döngüsü
├── losses.py         # Kayıp fonksiyonları
├── metrics.py        # Özel metrikler
├── optim.py          # Optimizer/Scheduler kurulumu
└── callbacks.py      # Early stopping, model kayıt
```

**`stage_trainer.py` — 5 Aşamalı Eğitim:**

| Aşama | Eğitilen Bileşen | Kayıp |
|---|---|---|
| 1 - Kalite | PPG encoder + quality_head | BCE |
| 2 - Düşme | IMU encoder + fall_head | Focal Loss |
| 3 - Dengesizlik | IMU encoder + instability_head | BCE |
| 4 - Risk | Vitals MLP + risk_head | MSE |
| 5 - Füzyon | Tüm model uçtan uca | Ağırlıklı toplam |

**`losses.py`:**
- `FocalLoss`: Sınıf dengesizliğine karşı, `(1-p)^γ` ağırlıklandırması
- `WeightedBCELoss`: Pozitif sınıf ağırlığı destekli BCE
- `MultiTaskLoss`: Dört kaybı `train.yaml` ağırlıklarıyla birleştirir

**Veri Artırma (`augmentation`):**
- IMU gürültü enjeksiyonu
- Ölçek bozma
- Zaman bükme (time warp)
- Mixup (iki örnek arası enterpolasyon)

---

### 8.5 `src/inference/` — Çıkarım Motoru

```
src/inference/
├── predictor.py                  # Model yükleme + batch çıkarım
├── risk_postprocessor_v2.py      # Ham skorlar → risk seviyeleri
├── recommendation_engine_v2.py   # Risk seviyesine göre klinik öneriler
└── explainability_v2.py          # Özellik önemi / dikkat haritaları
```

**`risk_postprocessor_v2.py`:**
Ham model çıktılarını yorumlanabilir risk seviyelerine dönüştürür:
```
composite_risk = fall_prob×0.35 + instability_prob×0.20 +
                 vital_risk×0.25 + (1-ppg_quality)×0.20

composite_risk ≥ 0.70 → CRITICAL
composite_risk ≥ 0.50 → WARNING
composite_risk ≥ 0.30 → WATCH
Aksi halde          → NORMAL
```

EMA (Üstel Hareketli Ortalama) ile pencere-pencere titre aşmaları azaltılır.

**`recommendation_engine_v2.py`:**
Risk seviyesine göre klinik yönerge tabanlı öneriler üretir:
- `NORMAL`: Rutin izleme devam et
- `WATCH`: HR ve SpO2'yi takip et, aktiviteyi azalt
- `WARNING`: Yatay pozisyon al, yakınları bilgilendir
- `CRITICAL`: 112'yi ara, hasta hemen yardım çağırsın

---

### 8.6 `scripts/` — CLI Betikleri

| Betik | Kullanım |
|---|---|
| `run_train.py` | `--stage` argümanıyla belirli aşamayı eğit |
| `run_eval.py` | Test seti değerlendirmesi: metrikler, karışıklık matrisi, AUC |
| `run_infer_demo.py` | 6 sentetik senaryo (normal→kritik) ile demo çıkarımı |
| `inspect_datasets.py` | Veri seti dağılımı ve istatistik analizi |

---

### 8.7 `tests/`

```
tests/
├── test_core.py   # Veri yükleyici, model ileri geçiş, postprocessor testleri
└── test_v2.py     # V2 model, füzyon başlıkları, senaryo testleri
```

---

## 9. Data/ — Veri Setleri

```
Data/
├── BUT_PPG/       # PPG kalite ve HR/SpO2 doğruluk veri seti
├── HIFD/          # Ana IMU+PPG düşme tespiti veri seti
└── WEDA_FALL/     # IMU-only düşme + ADL veri seti
```

### BUT_PPG (PPG Quality Dataset)
- **Format:** WFDB (PhysioNet uyumlu)
- **İçerik:** PPG sinyal kalitesi etiketleri (0/1), HR ve SpO2 gerçek değerleri
- **Kullanım:** Model 4. başlığı (PPG quality head) eğitimi

### HIFD (Human IMU Fall Dataset)
- **Özellik:** Bilek-üstü giyilebilir cihaz, IMU + PPG
- **Denekler:** 21 kişi
- **Senaryolar:** Düşme (fall), Günlük aktivite (ADL), Düşme öncesi (near_fall)
- **Format:** `.mat` (MATLAB)
- **Etiketleme:** Klasör adından otomatik (fall/ vs adl/)
- **Kullanım:** Birincil eğitim verisi (düşme + dengesizlik başlıkları)

### WEDA_FALL
- **Özellik:** Yalnızca IMU, 50Hz
- **Denekler:** 25 kişi (14 genç F01–F08 + 11 yaşlı D01–D11)
- **Format:** CSV
- **Kullanım:** Tamamlayıcı veri, özellikle yaşlı popülasyon için genelleme

---

## 10. outputs/ ve report_bundle/ — Çıktılar

```
outputs/
├── logs/        # Eğitim/değerlendirme günlükleri
├── models/      # Kaydedilen model ağırlıkları (.pt dosyaları)
└── reports/     # Değerlendirme rapor dosyaları

report_bundle/
├── 00_summary/            # Özet metrikleri
├── 01_metrics/            # Detaylı metrik tabloları
├── 02_figures/            # Eğitim grafikleri
├── 03_confusion_matrices/ # Karışıklık matrisi görüntüleri
├── 04_curves/             # ROC, PR eğrileri
├── 05_predictions/        # Tahmin-gerçek karşılaştırmaları
├── 06_checkpoints_info/   # Model kontrol noktası bilgileri
├── 07_data_split/         # Eğitim/doğrulama/test bölme detayları
├── 08_report_text/        # Otomatik üretilen metin raporları
└── 09_configs_used/       # Kullanılan yapılandırma dosyaları
```

`reports/best_model.pt`: En iyi performans gösteren model ağırlıkları (gerçek PyTorch checkpoint dosyası).

---

## 11. Temel Tasarım Kalıpları

### 11.1 Repository Pattern (Backend)
Backend'in en kritik mimarik kararı: tüm veri erişimi soyut arayüzler üzerinden yapılır.

```
Router/Service katmanı  →  AbstractXxxRepo (Arayüz)
                              ↙         ↘
                    SQLiteXxxRepo    FirestoreXxxRepo
```

**Avantaj:** DATA_MODE'u değiştirmek yeterli; router veya servis kodu hiç değişmez.

### 11.2 Hybrid Mod (Local-First)
```
Okuma → SQLite (hızlı, offline uyumlu)
Yazma → SQLite + Firestore (her ikisine birden)
```
Firestore yazma hatalarında sessiz loglama; lokal veri bütünlüğü korunur.

### 11.3 Alarm Durum Makinesi
```
          ┌─────────────────────────────────────────────┐
          │                 Sensör Verisi                │
          └─────────────────────┬───────────────────────┘
                                │
    ┌─────────┐            ┌────▼────┐           ┌──────────┐
    │  normal │──eşik aşım→│  watch  │──kötüleşme→│ warning  │
    └─────────┘            └────┬────┘           └────┬─────┘
                                │ TAMAM               │ kötüleşme
                           ┌────▼─────┐          ┌────▼──────┐
                           │post_event│          │  critical │
                           └────┬─────┘          └────┬──────┘
                                │                     │ ACİL
                           ┌────▼─────┐          ┌────▼──────┐
                           │ resolved │          │ emergency │
                           └──────────┘          └───────────┘
```

### 11.4 Simülasyon Motoru
Gerçek donanım olmadan tam sistem demosu yapılabilmesi için tasarlanmıştır:
- Backend startup'ta arka planda asenkron döngü başlar
- Her SELF kullanıcısı için bağımsız senaryo takibi
- Eşik aşımlarında otomatik anomali/alarm/bildirim zincirleme

### 11.5 Çok Görevli Öğrenme (Multi-Task Learning)
Tek model, dört paralel hedefi aynı anda optimize eder:
- **Paylaşılan temsil**: IMU encoder ve PPG encoder her iki görev tarafından da kullanılır → **transfer öğrenme** etkisi
- **Kalite kapısı**: Düşük kaliteli PPG sinyali diğer başlıkları olumsuz etkilememesi için `quality_head` ile attenüe edilir
- **Aşamalı eğitim**: Önce basit görevler (kalite, sonra düşme), en son füzyon → yakınsama daha stabil

### 11.6 BLE-First Transport
```
BLE (birincil) → başarısız → Wi-Fi (otomatik yedek)
```
`TransportOrchestrator` bu geçişi hem Flutter (Dart) hem firmware (C++) tarafında uygular.

---

## 12. Kullanılan Teknoloji Yığını

### Backend
| Teknoloji | Versiyon | Kullanım Amacı |
|---|---|---|
| FastAPI | 0.109.2 | REST API çatısı |
| SQLAlchemy | 2.0.25 | Asenkron ORM |
| aiosqlite | 0.19.0 | Asenkron SQLite sürücüsü |
| Pydantic | 2.5.3 | Veri doğrulama ve şema |
| python-jose | 3.3.0 | JWT token yönetimi |
| passlib + bcrypt | 1.7.4 | Şifre hashleme |
| firebase-admin | ≥6.4.0 | Firebase/Firestore entegrasyonu |
| httpx | — | LLM API çağrıları (asenkron) |
| uvicorn | 0.27.1 | ASGI sunucu |

### Mobil
| Teknoloji | Kullanım Amacı |
|---|---|
| Flutter / Dart | Çok platformlu mobil uygulama |
| google_fonts | Tipografi |
| fl_chart | Grafik ve veri görselleştirme |
| percent_indicator | SpO2/HR göstergesi |
| glassmorphism | Cam efekti UI |
| http | REST API bağlantısı |
| shared_preferences | Yerel veri saklama |
| firebase_core / cloud_firestore | Bulut senkronizasyon |

### Firmware
| Teknoloji | Kullanım Amacı |
|---|---|
| ESP32 (Espressif) | Mikrodenetleyici |
| PlatformIO + Arduino | Derleme çatısı |
| SparkFun MAX3010x | MAX30102 PPG kütüphanesi |
| electroniccats/MPU6050 | IMU kütüphanesi |
| ArduinoJson v7 | JSON serileştirme |

### ML / Veri Bilimi
| Teknoloji | Kullanım Amacı |
|---|---|
| PyTorch ≥2.0 | Derin öğrenme motoru |
| numpy, scipy | Sayısal hesaplama |
| pandas | Veri işleme |
| scikit-learn | Metrikler, bölme |
| omegaconf | YAML yapılandırma |
| wfdb | PhysioNet/WFDB veri okuma |
| matplotlib, seaborn | Görselleştirme |
| h5py | HDF5 dosya desteği |

---

## 13. Rol Tabanlı Erişim Kontrolü

Her HTTP isteği `deps.py` içindeki `get_current_user()` dependency ile doğrulanır. Yetki kontrolleri router seviyesinde uygulanır:

| Endpoint Grubu | SELF | RELATIVE | DOCTOR |
|---|---|---|---|
| `/live/{user_id}` | Kendi | Bağlı hasta | Bağlı hasta |
| `/alerts/active` | ✅ | ❌ | ❌ |
| `/alerts/{uid}/for-linked` | ❌ | ✅ (ACL) | ✅ (ACL) |
| `/clinical-notes` POST | ❌ | ❌ | ✅ |
| `/link-codes/generate` | ✅ | ✅ | ✅ |
| `/link-codes/redeem` | ✅ | ✅ | ✅ |
| `/settings` | Kendi | Kendi | Kendi |

**ACL Kontrolü:** Bir kullanıcı başkasının verisine erişmeden önce `UserRelation` tablosunda aktif bir bağlantı aranır:
```python
link = await repos.relations.find_active_link(target_id, current_user.id)
if link is None:
    raise HTTPException(status_code=403, detail="Yetkisiz erişim")
```

---

## 14. Güvenlik Tasarımı

| Güvenlik Katmanı | Uygulama |
|---|---|
| **Kimlik Doğrulama** | JWT (HS256, 7 günlük geçerlilik) |
| **Şifre Depolama** | bcrypt hashing (salt içerir) |
| **Yetkilendirme** | Her endpoint'te rol + ACL kontrolü |
| **Servis Hesabı** | Firebase Admin SDK kimlik bilgileri ortam değişkeninden |
| **Token Doğrulama** | Her istekte `decode_token()` ile exp kontrolü |
| **Veri Doğrulama** | Tüm giriş verileri Pydantic şemaları ile doğrulanır |

---

## Özet

HealthAlert, aşağıdaki beş bileşeni entegre eden, uçtan uca çalışan bir sağlık izleme platformudur:

| Bileşen | Teknoloji | Durum |
|---|---|---|
| **ESP32 Firmware** | C++ / PlatformIO | Donanım hazır, mock mod tam fonksiyonel |
| **FastAPI Backend** | Python / FastAPI + SQLAlchemy | Tamamlandı, LLM asistanı entegre |
| **Flutter Mobile** | Dart / Flutter | Yazılım prototipi, Firebase hazır |
| **ML Pipeline** | PyTorch 4-başlıklı model | Eğitim boru hattı tamamlandı |
| **Host Bridge** | Python araçları | Tüm araçlar (reader, emitter, bridge, replay) fonksiyonel |

Sistemin en önemli mimari kararları şunlardır:
1. **Repository Pattern** ile veri kaynağı değişkenliğine karşı izolasyon
2. **Çok görevli öğrenme** ile tek modelden 4 farklı sağlık çıktısı
3. **BLE-first transport** ile düşük gecikmeli cihaz → telefon iletişimi
4. **Hibrit mod** ile çevrimdışı güvenilirlik ve bulut senkronizasyonu
5. **Simülasyon motoru** ile gerçek donanımsız tam sistem demosu
