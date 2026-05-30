# MAX30102 BPM/SpO2 Tanı Paketi — HealthAlert
**Tarih:** 2026-05-28  
**Oluşturan:** Otomatik kod arkeoloji tarama (GitHub Copilot)  
**Amaç:** BPM 180–190 / 35–45 / 70–90 ve SpO2 70–77 gözlemlenen ölçüm sorunlarını tüm yazılım katmanlarıyla birlikte analiz etmek. Bu dosya dış AI analizine (ChatGPT vb.) verilmek üzere derlenmiştir; **hiçbir kod değişikliği yapılmamıştır.**

---

## Bölüm 1 — Proje Genel Yapısı

```
HealthAlert/
├── firmware/           # ESP32 – PlatformIO (Arduino framework)
│   ├── include/
│   │   ├── ha_config.h         ← Tüm sabitler ve eşikler
│   │   ├── ha_types.h          ← Struct ve enum tanımları
│   │   ├── ha_max30102.h       ← MAX30102 sürücüsü + BPM/SpO2 algoritması
│   │   ├── ha_acquisition.h    ← Veri toplama, motion gate, mock/real seçimi
│   │   └── ha_packet.h         ← BLE/WiFi JSON serileştirme
│   └── src/
│       └── main.cpp            ← Ana döngü, BLE gönderim zamanlayıcısı
├── mobile/             # Flutter (Dart)
│   └── lib/core/
│       ├── services/
│       │   ├── ble_device_service.dart
│       │   ├── ble_payload_parser.dart  ← JSON → BlePacket
│       │   └── transport_orchestrator.dart ← BPM yumuşatma, SpO2 tutma
│       ├── models/
│       │   └── live_status.dart        ← Uygulama veri modeli
│       └── state/
│           └── app_controller.dart     ← Durum yönetimi, BLE→UI köprüsü
│   └── lib/ui/screens/
│       ├── dashboard_screen.dart       ← Ana gösterge ekranı
│       └── live_monitor_screen.dart    ← Canlı izleme ekranı
└── backend/            # FastAPI (Python)
    ├── routers/
    │   ├── ingestion_router.py   ← POST /ingest/device-packet
    │   └── live_status_router.py ← GET /live/{user_id}
    └── services/
        ├── baseline_service.py
        └── adaptive_personalization_service.py
```

**Donanım:** ESP32-WROOM, MAX30102 (Red + IR LED), MPU6050 (IMU)  
**BLE protokolü:** Nordic UART Service (NUS) üzerinden JSON paket akışı

---

## Bölüm 2 — Firmware Yapılandırma Sabitleri (`firmware/include/ha_config.h`)

```cpp
// Örnekleme
#define SAMPLING_RATE_HZ         25       // İşleme çıktı hızı
#define PACKET_INTERVAL_MS    1000        // BLE özet paketi aralığı (1 sn)

// MAX30102 donanım ayarları
#define MAX30102_LED_BRIGHTNESS  0x1F     // 31/255 → ~6 mA (düşük parlaklık)
#define MAX30102_SAMPLE_AVG      4        // Sensör ortalaması (4 örnek/çıktı)
#define MAX30102_LED_MODE        2        // Red + IR (SpO2 modu)
#define MAX30102_SAMPLE_RATE   100        // Sensör ham hızı (100 Hz)
#define MAX30102_PULSE_WIDTH   411        // µs (en geniş → en hassas ADC)
#define MAX30102_ADC_RANGE    4096        // 18-bit ADC

// Isınma ve stabilizasyon
#define PPG_WARMUP_MS         10000       // 10 saniyelik ısınma bekleme
#define BPM_STABLE_WINDOW_MS   3000       // Kararlı BPM penceresi
#define BPM_JUMP_THRESH_BPM     20.0f    // Ani sıçrama eşiği
#define BPM_JUMP_WINDOW_MS     3000       // Sıçrama onaylama penceresi
#define SPO2_STABLE_WINDOW_MS  5000       // Kararlı SpO2 penceresi
#define SPO2_RING_SIZE            6       // SpO2 ortalama halka boyutu
#define SPO2_MAX_SPREAD_PCT       5.0f   // Maksimum SpO2 yayılımı %
#define SPO2_R_MIN               0.40f   // R oranı alt eşiği (geçerlilik kapısı)
#define SPO2_R_MAX               0.88f   // R oranı üst eşiği (geçerlilik kapısı)

// Hareket kapısı
#define MOTION_GYRO_GATE_DPS    25.0f    // °/s üzeri = hareket artefaktı
#define MOTION_ACCEL_GATE_G      0.35f   // g'den sapma > 0.35 = hareket artefaktı
```

**Önemli Gözlem:** Sensör 100 Hz'de yapılandırılmış, `SAMPLE_AVG=4` ile çıkışı 25 Hz'e düşürülmüştür. Bu nedenle her `_ppg.read()` çağrısı 1 örnek sağlar ve sinyali ~25 Hz hızında tampon belleğe ekler — ancak aşağıda açıklanan ikinci çağrı kaynağı bu varsayımı bozmaktadır.

---

## Bölüm 3 — Veri Yapıları (`firmware/include/ha_types.h`)

```cpp
// PPG durum makinesi
enum PpgState : uint8_t {
    PPG_NO_FINGER       = 0,
    PPG_WARMING_UP      = 1,
    PPG_STABILIZING     = 2,
    PPG_STABLE          = 3,
    PPG_UNSTABLE        = 4,   // ← Kodda ÖLÇÜM NOKTASINA ULAŞILMIYOR (bkz. Bölüm 9)
    PPG_MOTION_ARTIFACT = 5,
};

struct PpgSample {
    float    bpm_raw;           // Ham BPM tahmini
    float    spo2_raw;          // Ham SpO2 tahmini
    float    signal_quality;    // 0.0–1.0
    bool     finger_detected;
    bool     hr_valid;          // Onaylanmış, aralık içinde
    bool     spo2_valid;        // Onaylanmış, aralık içinde
    bool     motion_artifact;
    uint8_t  measurement_state; // PpgState enum değeri
};

struct DevicePacket {
    float    heart_rate;        // BPM (hr_valid=false ise 0)
    float    spo2;              // % (spo2_valid=false ise 0)
    float    signal_quality;
    bool     finger_detected;
    bool     hr_valid;
    bool     spo2_valid;
    bool     motion_artifact;
    uint8_t  measurement_state;
    // + IMU ve raw ADC alanları
};
```

---

## Bölüm 4 — MAX30102 Algoritması (`firmware/include/ha_max30102.h`)

### 4.1 — Sinyal Kalitesi Hesabı (`_computeSignalQuality`)

```cpp
// Varyasyon katsayısı (CV) tabanlı kalite puanı
float cv = sqrt(var_sum / n) / mean;
if (cv < 0.001f) return 0.05f;  // Düz çizgi (parmak yok)
if (cv < 0.004f) return 0.35f;  // Zayıf sinyal
if (cv < 0.020f) return 0.85f;  // İyi sinyal
if (cv < 0.050f) return 0.55f;  // Biraz hareket
if (cv < 0.120f) return 0.25f;  // Hareket artefaktı
return 0.08f;                   // Ağır gürültü
```

### 4.2 — BPM Tepe Tespiti (`_processBpm`)

```cpp
// Eşik ve refraktör periyot
float thresh = mean + ac_range * 0.35f;
int   refract_samples = (int)(SAMPLING_RATE_HZ * 0.30f);  // = 7 örnek @ 25 Hz
                                                            // = 3.5 örnek @ 50 Hz efektif hız
```

Tepe tespiti → arası örnekler → BPM:
```
bpm_raw = 60.0f * SAMPLING_RATE_HZ / interval_samples
```

BPM geçerlilik penceresi:
```cpp
if (bpm_raw < 45.0f || bpm_raw > 200.0f) {
    // SORUNLU KISIM — aşağıya bakın
    _bpmStableStartMs = 0;                              // ← 0'a sıfırla
    if (millis() - _bpmStableStartMs > 10000UL) {       // ← millis() - 0 HEMEN > 10000!
        _bpmConfirmed = false;                           // ← Kararlı BPM'i anında sil
        _stableBpm = 0.0f;
    }
} else {
    // Aralık içindeyse: 3 saniyelik kararlılık penceresi birikmesi
}
```

`hr_valid` son filtresi:
```cpp
hr_valid = _bpmConfirmed && (_stableBpm >= 45.0f) && (_stableBpm <= 140.0f);
// NOT: bpm_raw 141–200 arasındaysa hr_valid=false olur ama _bpmConfirmed=true kalabilir
```

### 4.3 — SpO2 Hesabı (`_estimate_spo2`)

```cpp
// R oranı (RMS AC/DC yöntemi)
float ac_red_rms = sqrt(ac_red_sq_sum / n);
float ac_ir_rms  = sqrt(ac_ir_sq_sum  / n);
float R = (ac_red_rms / dc_red) / (ac_ir_rms / dc_ir);

// R kapısı
if (R < SPO2_R_MIN || R > SPO2_R_MAX) return;  // [0.40, 0.88]

// Empirical SpO2 formülü
float spo2 = 110.0f - 25.0f * R;
// R=0.40 → SpO2=100, R=0.88 → SpO2=88 (minimum çıktı ~88%)
```

**SpO2 halka ortalaması ve yayılım filtresi:**
```cpp
// SPO2_RING_SIZE=6 örnek, SPO2_MAX_SPREAD_PCT=5.0
if (spread_pct > SPO2_MAX_SPREAD_PCT) {
    _spo2Confirmed = false;
    _spo2Valid = false;
}
```

### 4.4 — İkili R Hesabı (`_estimate_ppg_features` vs `_estimate_spo2`)

```cpp
// _estimate_ppg_features: Tepe-tepe AC kullanır → rr alanı (BLE paketiyle gönderilir)
float r_peak_to_peak = (ac_red_pp / dc_red) / (ac_ir_pp / dc_ir);

// _estimate_spo2: RMS AC kullanır → SpO2 formülüne girer
float R_rms = (ac_red_rms / dc_red) / (ac_ir_rms / dc_ir);
```

Her iki `R` değeri de pakete yazılıyor ancak farklı algoritmalar kullanıyor. `rr` alanı tanısal izleme için gönderilse de SpO2 hesabıyla tutarsız.

---

## Bölüm 5 — Veri Toplama ve Hareket Kapısı (`firmware/include/ha_acquisition.h`)

```cpp
// _collectReal() içinde hareket kapısı
void _collectReal(RawSensorSample& out) {
    _ppg.read(out.ppg);          // ← PPG tamponuna 1 örnek ekle

    // IMU verisi
    float gyroMag  = sqrt(gx*gx + gy*gy + gz*gz);
    float accMag   = sqrt(ax*ax + ay*ay + az*az);
    float accDyn   = (accMag > 1.0f) ? (accMag - 1.0f) : (1.0f - accMag);

    bool motionDetected = (gyroMag > MOTION_GYRO_GATE_DPS) ||   // 25 dps
                          (accDyn  > MOTION_ACCEL_GATE_G);      // 0.35g

    if (motionDetected) {
        out.ppg.hr_valid    = false;
        out.ppg.spo2_valid  = false;
        out.ppg.motion_artifact = true;
        out.ppg.measurement_state = PPG_MOTION_ARTIFACT;
    }
}
```

**IMU yoksa hareket kapısı atlanıyor:**
```cpp
if (!_imuOk) {
    // Hareket kapısı uygulanmaz → BPM/SpO2 hareket sırasında da geçer
}
```

---

## Bölüm 6 — Ana Döngü ve Zamanlama (`firmware/src/main.cpp`)

```cpp
// BLE özet paketi: Her 1000 ms
if (millis() - _lastSummaryMs >= SUMMARY_PACKET_INTERVAL_MS) {   // 1000 ms
    sendBleSummaryPacket();
    _lastSummaryMs = millis();
}

// Ham model akışı: Her 20 ms (50 Hz)
if (millis() - _lastModelStreamMs >= (1000 / MODEL_STREAM_RATE_HZ)) {  // 20 ms
    collectRawSample();   // ← _collectReal() çağırır → _ppg.read() çağırır
    _lastModelStreamMs = millis();
}
```

**KRİTİK ZAMANLAMA SORUNU:**
- `collectRawSample()` 50 Hz'de çağrılıyor → `_ppg.read()` 50 Hz'de çağrılıyor
- PPG halka tamponuna (`PPG_BUF_SIZE=100`) her 20 ms'de 1 örnek ekleniyor
- Ancak BPM algoritması 25 Hz (`SAMPLING_RATE_HZ=25`) varsayıyor
- Sonuç: Tampon 25 Hz'in 2 katı hızda dolduruluyor → BPM hesabında kullanılan örnekler arası mesafe yanlış

---

## Bölüm 7 — BLE Paket Formatı (`firmware/include/ha_packet.h`)

### 7.1 — BLE Özet Paketi (Short JSON)

```json
{
  "t":   1748440123456,   // Zaman damgası (ms)
  "fp":  1,               // finger_present (0/1)
  "bpm": 72.5,            // hr_valid=false → null
  "bv":  1,               // bpm_valid (0/1)
  "spo2e": 97.0,          // spo2_valid=false → null
  "sv":  1,               // spo2_valid (0/1)
  "q":   85,              // signal_quality × 100 (0–100 integer)
  "ir":  85432,           // IR ham ADC
  "red": 72108,           // Red ham ADC
  "pi":  0.82,            // perfusion_index
  "rr":  0.61,            // R ratio (peak-to-peak yöntemi)
  "ms":  3,               // measurement_state (PpgState enum)
  "ma":  0,               // motion_artifact (0/1)
  "br":  72.5,            // bpm_raw (ham, doğrulanmamış)
  "sr":  96.8,            // spo2_raw (ham, doğrulanmamış)
  "ax":  0.01, "ay": -0.03, "az": 1.00,   // İvme (g)
  "gx":  1.2,  "gy":  0.8,  "gz": -0.5,  // Jiroskop (dps)
  "at":  0.05,            // acc_total dinamik sapma
  "gt":  1.7              // gyro_total büyüklüğü (dps)
}
```

**Geçersiz ölçüm durumunda:**
- `hr_valid=false` → `"bpm": null` (JSON'da null olarak gönderilir)
- `spo2_valid=false` → `"spo2e": null`
- `"bv": 0` ve `"sv": 0` geçersizliği açıkça işaretler

---

## Bölüm 8 — Mobile BLE Ayrıştırıcı (`mobile/lib/core/services/ble_payload_parser.dart`)

### 8.1 — Paket Yönlendirme Mantığı

```dart
static BlePacket fromJson(Map<String, dynamic> json) {
  // Short format: BLE özet paketleri
  if (json.containsKey('t') || json.containsKey('bpm') || json.containsKey('spo2e')) {
    return BlePacket.fromShortJson(json);
  }
  // Nested format: Eski sunucu yanıtları
  else if (json.containsKey('ppg') || json.containsKey('vitals')) {
    return BlePacket.fromNestedJson(json);
  }
  // Legacy flat format
  else {
    return BlePacket.fromLegacyFlatJson(json);
  }
}
```

### 8.2 — Short Format Ayrıştırması (Mevcut BLE paketleri için geçerli)

```dart
static BlePacket fromShortJson(Map<String, dynamic> json) {
  return BlePacket(
    heartRate:   (json['bpm'] as num?)?.toDouble(),
    spo2:        (json['spo2e'] as num?)?.toDouble(),
    hrValid:     _boolValue(json['bv']),        // 0/1 → false/true
    spo2Valid:   _boolValue(json['sv']),
    fingerPresent: _boolValue(json['fp']),
    signalQuality: (json['q'] as num?)?.toDouble()?.let((v) => v / 100.0),
    // Tanısal alanlar
    bpmRaw:     (json['br'] as num?)?.toDouble(),
    spo2Raw:    (json['sr'] as num?)?.toDouble(),
    measurementState: json['ms'] as int?,
    motionArtifact: _boolValue(json['ma']),
    irValue:    (json['ir'] as num?)?.toInt(),
    redValue:   (json['red'] as num?)?.toInt(),
    accTotal:   (json['at'] as num?)?.toDouble(),
    gyroTotal:  (json['gt'] as num?)?.toDouble(),
  );
}
```

### 8.3 — Legacy Flat Format Hatası

```dart
static BlePacket fromLegacyFlatJson(Map<String, dynamic> json) {
  return BlePacket(
    heartRate:   (json['heart_rate'] as num?)?.toDouble(),
    hrValid:     _boolValue(json['hr_valid']),   // ← BUG: 'bv' alanını OKUMAZ
    spo2Valid:   _boolValue(json['spo2_valid']), // ← BUG: 'sv' alanını OKUMAZ
    // ...
  );
}
```

Eğer bir paket `bv`/`sv` anahtarlarına sahip ama `t`/`bpm`/`spo2e` yoksa, bu yol seçilir ve geçerlilik bayrakları kaybolur.

### 8.4 — `toLiveStatus` Geçerlilik Maskesi

```dart
LiveStatus toLiveStatus() {
  return LiveStatus(
    heartRate: hrValid == true ? heartRate : 0,   // geçersizse 0 göster
    spo2:      spo2Valid == true ? spo2 : 0,       // geçersizse 0 göster
    heartRateValid: hrValid,
    spo2Valid: spo2Valid,
    // ...
  );
}
```

---

## Bölüm 9 — Ölü Kod: `PPG_UNSTABLE` Erişilemeyen Dal

`ha_max30102.h` içindeki `measurement_state` belirleme mantığı:

```cpp
if (_fingerDetected == false) {
    out.measurement_state = PPG_NO_FINGER;
} else if (_ppgState == PPG_WARMING_UP) {
    out.measurement_state = PPG_WARMING_UP;
} else if (_ppgState == PPG_STABILIZING) {
    out.measurement_state = PPG_STABILIZING;
} else if (_bpmConfirmed || _spo2Confirmed) {
    out.measurement_state = PPG_STABLE;
} else {
    // Bu dal ASLA erişilemiyor çünkü:
    // 1. PPG_NO_FINGER → ilk dal yakalar
    // 2. PPG_WARMING_UP → ikinci dal yakalar
    // 3. PPG_STABILIZING → üçüncü dal yakalar
    // 4. _bpmConfirmed=false && _spo2Confirmed=false → buraya ulaşır
    //    ama bu SADECE ilk stabilizasyon sırasında olur → aslında PPG_STABILIZING olmalı
    out.measurement_state = PPG_UNSTABLE;   // ← Hiçbir zaman gönderilmez
}
```

Mobil uygulama `ms=4` (PPG_UNSTABLE) için özel gösterim kodu içermez çünkü firmware bunu asla göndermez.

---

## Bölüm 10 — Mobile Veri Modeli (`mobile/lib/core/models/live_status.dart`)

### 10.1 — `fromJson` Varsayılan Değer Sorunları

```dart
factory LiveStatus.fromJson(Map<String, dynamic> json) {
  return LiveStatus(
    heartRate:      (json['heart_rate'] as num?)?.toDouble() ?? 72,   // ← Null → 72 BPM
    spo2:           (json['spo2'] as num?)?.toDouble() ?? 98,         // ← Null → %98
    heartRateValid: json['hr_valid'] as bool? ?? json['bpm_valid'] as bool?,
    spo2Valid:      json['spo2_valid'] as bool?,
    // ...
  );
}
```

Backend `heart_rate: null` döndürürse mobil `72 BPM` gösterir — bu gerçekçi görünen sahte veri üretir.

### 10.2 — `heartRateValid` / `spo2Valid` null Davranışı

```dart
// heartRateValid ve spo2Valid null olabilir
// null = "bilinmiyor" — ama UI bunu farklı yorumluyor
```

---

## Bölüm 11 — Transport Orchestrator BPM/SpO2 İşleme (`mobile/lib/core/services/transport_orchestrator.dart`)

### 11.1 — BPM EMA Yumuşatması

```dart
// α = 0.3 — Üstel hareketli ortalama
double _applySmoothBpm(double newBpm) {
  if (_stableBpm == null) {
    _stableBpm = newBpm;
    return newBpm;
  }
  // Ani sıçrama: > 25 BPM → 2 ardışık onay gerektirir
  if ((newBpm - _stableBpm!).abs() > 25.0) {
    if (_pendingJump != null && (newBpm - _pendingJump!).abs() < 15.0) {
      _stableBpm = newBpm;    // Sıçramayı onayla
      _pendingJump = null;
    } else {
      _pendingJump = newBpm;  // İlk onay — eski değeri koru
      return _stableBpm!;
    }
  } else {
    _stableBpm = _stableBpm! * (1 - 0.3) + newBpm * 0.3;
    _pendingJump = null;
  }
  return _stableBpm!;
}
```

**Çift yumuşatma sorunu:** Firmware BPM'i 3 saniyelik pencerede kendisi kararlı hale getirip `bv=1` gönderiyor. Mobil uygulama bunun üzerine EMA α=0.3 uyguluyor → çift yumuşatma. Firmware hatalı bir `bv=1` gönderirse mobil de bunu karıştırmaya başlar.

### 11.2 — SpO2 Tutma Penceresi

```dart
// 10 saniye boyunca son geçerli SpO2'yi göster
if (_lastSpo2ValidAt != null &&
    DateTime.now().difference(_lastSpo2ValidAt!) < Duration(seconds: 10) &&
    _fingerPresent == true) {
  return _stableSpo2;   // Eski değeri göster
}
```

Parmak yerinden alındığında `_stableSpo2 = null` sıfırlanıyor ✓

### 11.3 — Mobil Hareket Skoru Hesabı (Deadband filtreli)

```dart
double _computeMotionScore(BlePacket packet) {
  double accDynamic  = max(0, (packet.accTotal ?? 0) - 0.05);
  double gyroDynamic = max(0, (packet.gyroTotal ?? 0) - 15.0);
  // Normalleştirme + birleştirme
  return min(1.0, (accDynamic * 2.0) + (gyroDynamic / 50.0));
}
```

---

## Bölüm 12 — Mobil UI Gösterim Mantığı

### 12.1 — Dashboard (`mobile/lib/ui/screens/dashboard_screen.dart`)

```dart
String get _hrDisplay {
  final live = _latestLive;
  if (live == null) return '--';
  if (live.source == 'ble') {
    if (live.fingerPresent != true) return '--';
    if (live.heartRateValid != true) return 'Stabil oluyor';  // BLE + parmak var + geçersiz
    final hr = live.heartRate ?? 0;
    if (hr < 20 || hr > 220) return '--';   // Akılcı sınır kontrolü
    return '${hr.toStringAsFixed(0)} BPM';
  }
  if (live.heartRateValid == false) return '--';
  final hr = live.heartRate ?? 0;
  if (hr < 20 || hr > 220) return '--';
  return '${hr.toStringAsFixed(0)} BPM';
}

String get _spo2Display {
  // ... benzer mantık
  // BLE + parmak var + !spo2Valid → 'Stabil oluyor'
  // Backend spo2Valid==false → '--'
  // Aralık dışı [80, 100] → '--'
}
```

**Metrik kart başlığı:**
```dart
// BLE + parmak var + !hrValid → "KALIBRE OLUYOR" gösterilir
title: (isBle && fingerPresent && !hrValid) ? 'KALIBRE OLUYOR' : 'KALP ATIŞI'
```

### 12.2 — Live Monitor (`mobile/lib/ui/screens/live_monitor_screen.dart`)

```dart
Widget _buildBleMeasurementDetails(LiveStatus live, String transportLabel) {
  final hrValid   = live.heartRateValid == false ? 'Gecersiz' : 'Valid';
  //                                              ↑ BUG: null → 'Valid' olarak gösterilir
  //                                              Doğrusu: null → 'Bilinmiyor' olmalı
  final spo2Valid = live.spo2Valid == false ? 'Gecersiz' : 'Valid';
  //                                         ↑ Aynı bug
}
```

`heartRateValid == null` durumunda (bilinmiyor/veri yok) "Valid" etiketi gösterilir — yanıltıcı.

---

## Bölüm 13 — Local Risk Hesaplayıcı (`mobile/lib/core/services/local_risk_calculator.dart`)

```dart
double calculate(LiveStatus live) {
  if (live.fingerPresent != true) return 0.0;  // Parmak yoksa risk 0

  double risk = 0.0;
  final bpmValid  = live.heartRateValid == true;
  final spo2Valid = live.spo2Valid == true;

  if (bpmValid) {
    final hr = live.heartRate ?? 0;
    if (hr >= 50 && hr <= 99)  risk += 0.0;
    else if (hr >= 100 && hr <= 119) risk += 0.10;
    else if (hr >= 120 && hr <= 139) risk += 0.20;
    else if (hr < 50)  risk += 0.20;
    else               risk += 0.30;  // ≥ 140
  }

  if (spo2Valid) {
    final spo2 = live.spo2 ?? 100;
    if (spo2 >= 95)           risk += 0.0;
    else if (spo2 >= 92)      risk += 0.15;
    else if (spo2 >= 88)      risk += 0.30;
    else                      risk += 0.45;  // < 88 (firmware R-kapısı engeller)
  }

  return risk.clamp(0.0, 1.0);
}
```

SpO2 < 88 için risk puanı var ama firmware R-kapısı (`R > 0.88 → SpO2 < 88`) bu değerlerin üretilmesini engeller.

---

## Bölüm 14 — Backend Veri İşleme (`backend/routers/ingestion_router.py`)

### 14.1 — Live Status Kayıt Mantığı (GEÇERSİZ ÖLÇÜM SAKLAMA)

```python
# hr_valid=False durumunda önceki değeri kullan
hr_display  = pkt.heart_rate if pkt.hr_valid  else (existing["heart_rate"] if existing else 72.0)
spo2_display = pkt.spo2       if pkt.spo2_valid else (existing["spo2"]       if existing else 98.0)

# Aralık sınırlaması
hr_display   = max(20.0, min(250.0, hr_display))
spo2_display = max(50.0, min(100.0, spo2_display))

await repos.live_status.upsert(user_id, {
    "heart_rate": hr_display,
    "spo2":       spo2_display,
    # ...
})
```

**Not:** `heart_rate` veya `spo2` alanı daima sayısal değerle kaydediliyor — backend canlı durumu asla `null` içermiyor. Ancak `hr_valid` / `spo2_valid` alanları kaydedilmediği görülüyor: `upsert` sözlüğünde bu bayraklar yok.

### 14.2 — Backend Risk Hesabı

```python
def _compute_risk_score(hr, spo2, hr_valid, spo2_valid, motion):
    risk = 0.0
    if hr_valid:
        if hr > 120: risk += 0.30
        elif hr > 100: risk += 0.15
        elif hr < 50: risk += 0.20
    if spo2_valid:
        if spo2 < 90: risk += 0.40
        elif spo2 < 94: risk += 0.20
    risk += motion * 0.20
    return round(min(1.0, risk), 3)
```

### 14.3 — Baseline Güvenilirlik Filtresi (`backend/services/baseline_service.py`)

```python
def is_reliable_for_baseline(...) -> bool:
    if hr < 35 or hr > 190: return False   # 180-190 BPM değerleri baseline günceller!
    if spo2 < 70 or spo2 > 100: return False
    # ...
```

**Not:** Firmware'in gönderdiği yanlış `bv=1` paketiyle birlikte BPM=185 gelirse (`hr_valid=True` ile) ve sinyal kalitesi yüksekse, bu değer baseline'ı günceller.

---

## Bölüm 15 — Derleme ve Test Özeti

### 15.1 — Firmware (PlatformIO)

```
✅ BUILD BAŞARILI
RAM:   19.4% (63676 / 327680 bytes)
Flash: 55.7% (1752705 / 3145728 bytes)
Platform: Espressif 32 (6.13.0), ESP32 240MHz
Kütüphaneler: SparkFun MAX3010x 1.1.2, ArduinoJson 7.4.3
Süre: 3.95 saniye
```

### 15.2 — Flutter Analiz

```
270 issue bulundu (0 hata, tümü uyarı/bilgi düzeyinde)
Dikkat çekici uyarılar:
- core/state/app_controller.dart:534 — unused local variable 'role'
- main.dart:83 — unreachable_switch_default
```

### 15.3 — Flutter Test

```
58 geçti, 4 başarısız
Başarısız testler:
- app_controller_flow_test.dart: mock login persists authenticated session
- extended_coverage_test.dart: anomaly creates unread notification
Hata türü: UnimplementedError: initialize() has not been implemented
(Mock servis initialize() uygulaması eksik)
```

### 15.4 — Backend Pytest

```
589 geçti, 43 başarısız, 1 atlandı, 17 hata
Önemli başarısızlıklar:
- test_23_adaptive_personalization.py: personalization_disabled_returns_baseline
- test_26_model_window_pipeline.py: sample_rate_1hz_marks_model_not_ready
- test_09_integration.py / test_12_final_closure.py: SQLite repo ayarları
```

---

## Bölüm 16 — Şüpheli Noktalar (Hata Analizi)

### 🔴 KRİTİK — Bug #1: `_bpmStableStartMs = 0` Mantık Hatası

**Dosya:** `firmware/include/ha_max30102.h`, `_processBpm()` fonksiyonu

**Sorun:**
```cpp
if (bpm_raw < 45.0f || bpm_raw > 200.0f) {
    _bpmStableStartMs = 0;                          // 1. Sayacı sıfırla
    if (millis() - _bpmStableStartMs > 10000UL) {   // 2. millis() - 0 ≈ millis() > 10000
        // Cihaz açıldıktan 10 saniye sonra bu koşul DAIMA DOĞRUDUR
        _bpmConfirmed = false;                       // 3. Onaylanmış BPM'i anında sil
        _stableBpm = 0.0f;
    }
}
```

**Etki:** Tek bir gürültülü tepe → aralık dışı BPM (örn. 201) → `_bpmConfirmed=false` ve `_stableBpm=0` anında. Kullanıcı sakin oturmuş olsa bile stabilizasyon sıfırlanır.

**Gözlemlenen semptom:** BPM 70–90 → kısa gürültü → `bv=0` → "Stabil oluyor" → yeniden stabilizasyon döngüsü. Bu, tutarsız ölçüm gösterimiyle uyumlu.

---

### 🔴 KRİTİK — Bug #2: 50 Hz Ring Buffer Beslemesi (25 Hz Algoritma Varsayımı ile Uyumsuzluk)

**Dosya:** `firmware/src/main.cpp` + `firmware/include/ha_acquisition.h`

**Sorun:**
```
Model akış döngüsü: 50 Hz → collectRawSample() → _ppg.read() → ring buffer +1 örnek
BPM algoritması: interval_samples / SAMPLING_RATE_HZ(=25) kullanıyor

Etki:
  Gerçek örnekleme: 50 Hz (ring buffer görüşü)
  Algoritma varsayımı: 25 Hz
  
  İki tepe arası 50 örnek @ 50 Hz → gerçek 1 saniye
  Algoritma yorumu: 50 / 25 = 2 saniye → BPM = 60/2 = 30 (çok düşük)
  
  İki tepe arası 25 örnek @ 50 Hz → gerçek 0.5 saniye
  Algoritma yorumu: 25 / 25 = 1 saniye → BPM = 60 (doğru görünür ama şans eseri)
  
  İki tepe arası 12 örnek @ 50 Hz → gerçek 0.24 saniye
  Algoritma yorumu: 12 / 25 = 0.48 saniye → BPM = 125 (aslında BPM=250!)
```

**Ek etki — refraktör periyot:**
```
Refraktör = SAMPLING_RATE_HZ * 0.30 = 7 örnek
Gerçek hız 50 Hz'de → 7 örnek = 140 ms koruma (minimum fyzyolojik tepe arası = 300 ms @ 200 BPM)
Gürültü tepeleri 140-299 ms arayla kabul edilebilir hale geliyor → sahte çift tepeler
```

**Gözlemlenen semptomlara bağlantı:**
- BPM 180–190: Refraktörün yarısı ile yanlış ölçülen arka arkaya tepeler → BPM ≈ 2×gerçek
- BPM 35–45: Çift sayılan örnekler → interval 2×beklenen → BPM yarı olarak hesaplanıyor
- Her ikisi de aynı kök nedenden (50 Hz vs 25 Hz uyumsuzluğu) kaynaklanıyor

---

### 🟡 ORTA — Sorun #3: SpO2 70–77 Değerleri

**Dosya:** `firmware/include/ha_max30102.h`

**Analiz:**
```
Firmware R-kapısı: R ∈ [0.40, 0.88]
SpO2 = 110 - 25×R
  R=0.40 → SpO2=100 (maksimum)
  R=0.88 → SpO2=88  (minimum)

Teorik olarak firmware'in üretebileceği minimum SpO2 = 88%
SpO2 70–77 değerleri mevcut firmware'den GELEMEMELİDİR.
```

**Olası kaynaklar:**
1. Önceki firmware versiyonu (R-kapısı olmadan) kaydedilmiş backend veri
2. Backend ingestion_router'da `spo2_display = max(50.0, min(100.0, spo2_display))` — 50% alt limitine kadar herhangi bir değer saklanıyor
3. Demo/mock veri jeneratörü bu değerleri üretiyor
4. Tamamen farklı bir veri kaynağı (el ile girilmiş / test verisi)

---

### 🟡 ORTA — Sorun #4: Backend Live Status `hr_valid`/`spo2_valid` Saklamaması

**Dosya:** `backend/routers/ingestion_router.py`, satır ~305

**Sorun:**
```python
await repos.live_status.upsert(user_id, {
    "heart_rate": hr_display,
    "spo2":       spo2_display,
    "motion_score": motion_score,
    "risk_score": risk_score,
    "scenario":   pkt.state_hint or "normal",
    "timestamp":  datetime.utcnow(),
    # ← hr_valid, spo2_valid, finger_detected SAKLANMIYOR
})
```

Mobil uygulama `/live/{user_id}` yanıtında `hr_valid`/`spo2_valid` görmez → `LiveStatus.fromJson` bu alanları `null` olarak alır → `heartRateValid == null`.

**Bağlantı:** `live_monitor_screen.dart`'taki `heartRateValid == null → 'Valid'` hatası bu durumu aktive eder.

---

### 🟡 ORTA — Sorun #5: `LiveStatus.fromJson` Varsayılan Değerleri

**Dosya:** `mobile/lib/core/models/live_status.dart`

```dart
heartRate: (json['heart_rate'] as num?)?.toDouble() ?? 72,
spo2:      (json['spo2'] as num?)?.toDouble() ?? 98,
```

Backend `null` döndürdüğünde (ilk bağlantı, veri yok) → 72 BPM ve %98 SpO2 gösterilir. Bu değerler fizyolojik olarak makul göründüğünden kullanıcıyı yanıltabilir.

---

### 🟡 ORTA — Sorun #6: `fromLegacyFlatJson` `bv`/`sv` Alanlarını Okumaz

**Dosya:** `mobile/lib/core/services/ble_payload_parser.dart`

Legacy format seçilirse `hrValid` ve `spo2Valid` her zaman `null` olur (BLE paketinde `bv=1` olsa bile).

---

### 🟢 DÜŞÜK — Sorun #7: İkili R Hesabı Tutarsızlığı

**Dosya:** `firmware/include/ha_max30102.h`

`rr` alanı (tepe-tepe yöntemi) BLE paketiyle gönderilir; SpO2 hesabı (RMS yöntemi) farklı bir R kullanır. Tanısal izlemede bu iki değer arasındaki fark kafa karıştırıcı olabilir.

---

### 🟢 DÜŞÜK — Sorun #8: PPG_UNSTABLE Erişilemeyen Dal

**Dosya:** `firmware/include/ha_max30102.h`

`measurement_state = PPG_UNSTABLE` hiçbir zaman atanmıyor. Bu durum, stabilizasyon bilgisinin eksik iletilmesine yol açıyor — mobil "Stabil oluyor" mesajını yalnızca `hrValid != true` kontrolüyle gösteriyor, gerçek durum makinesi bilgisi kullanılmıyor.

---

## Bölüm 17 — Özet Tablo

| # | Önem | Bileşen | Sorun | Gözlemlenen Semptom |
|---|------|---------|-------|---------------------|
| 1 | 🔴 Kritik | `ha_max30102.h` | `_bpmStableStartMs=0` → `millis()-0>10000` her zaman doğru → herhangi bir aralık dışı ham BPM anında `_bpmConfirmed=false` yapıyor | BPM 70–90 arası tutarsız gösterim, sık "Stabil oluyor" |
| 2 | 🔴 Kritik | `main.cpp` + `ha_max30102.h` | Ring buffer 50 Hz'de besleniyor, BPM algoritması 25 Hz varsayıyor; refraktör periyot 7 örnek yerine 3.5 gerçek örneğe karşılık geliyor | BPM 180–190 (aşırı düşük interval) veya BPM 35–45 (aşırı yüksek interval) |
| 3 | 🟡 Orta | `ha_max30102.h` | SpO2 R-kapısı [0.40, 0.88] → minimum üretilebilir SpO2 = 88% | SpO2 70–77 mevcut firmware'den kaynaklanamaz; eski veri veya mock |
| 4 | 🟡 Orta | `ingestion_router.py` | `live_status.upsert()` `hr_valid`/`spo2_valid` alanlarını saklamıyor | Backend modunda geçerlilik bilgisi kayboluyor |
| 5 | 🟡 Orta | `live_status.dart` | `fromJson` varsayılanları: `heart_rate ?? 72`, `spo2 ?? 98` | Veri olmadığında fizyolojik görünen sahte değerler |
| 6 | 🟡 Orta | `live_monitor_screen.dart` | `heartRateValid == null` → "Valid" etiketli gösterim | Bilinmiyor durumu yanlış işaretleniyor |
| 7 | 🟡 Orta | `ble_payload_parser.dart` | `fromLegacyFlatJson` `bv`/`sv` okumaz | Legacy paketlerde geçerlilik bilgisi kaybolabilir |
| 8 | 🟢 Düşük | `ha_max30102.h` | `PPG_UNSTABLE` (ms=4) hiçbir zaman atanmıyor | Stabilizasyon durumu doğru iletilemiyor |
| 9 | 🟢 Düşük | `ha_max30102.h` | `rr` (tepe-tepe R) ile SpO2 R (RMS) iki farklı hesap | Tanısal log karışıklığı |
| 10 | 🟢 Düşük | `ha_acquisition.h` | IMU bağlı değilse hareket kapısı atlanıyor | IMU arızasında hareket artefaktları geçiyor |

---

## Bölüm 17 Ek — Düzeltme Öncelikleri

**Önce düzeltilmesi önerilen (firmware):**

1. **Bug #2 (50 Hz sorunu)** — `collectRawSample()` döngüsünü BPM algoritmasından ayır: Ya model akış hızını 25 Hz'e indir, ya da BPM algoritmasına efektif örnekleme hızını doğru parametre olarak geç (`ACTUAL_SAMPLING_RATE_HZ = 50`).

2. **Bug #1 (`_bpmStableStartMs` sıfırlama)** — `_bpmStableStartMs = millis()` olarak değiştir (0 değil). Zaman sayacını sıfırlayıp hemen kontrol etmek ters mantık.

**Sonra düzeltilmesi önerilen (mobile/backend):**

3. **`ingestion_router.py`** — `upsert` sözlüğüne `hr_valid`, `spo2_valid`, `finger_detected` alanlarını ekle.

4. **`live_status.dart`** — `fromJson` varsayılanlarını kaldır; `heartRate` ve `spo2` nullable bırak.

5. **`live_monitor_screen.dart`** — `heartRateValid == null` durumunu `'Bilinmiyor'` olarak göster.

---

*Bu dosya sadece tanı amaçlıdır. Hiçbir kaynak dosyası değiştirilmemiştir.*  
*Oluşturma tarihi: 2026-05-28 — HealthAlert projesi için MAX30102 ölçüm hata analizi*
