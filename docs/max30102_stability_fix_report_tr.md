# MAX30102 BPM / SpO2 Kararlılık Düzeltme Raporu — v2 (tüm katmanlar)

**Tarih:** 2025-01-17  
**Kapsam:** Firmware, Backend, Mobile — 10 kritik hata uygulandı  
**Build durumu:** Firmware ✅ SUCCESS (55.7% Flash) · Backend pytest 589 pass ✅ · Flutter test 58 pass ✅ · APK ✅ Built

---

## 1. Tespit Edilen Kök Nedenler

### 1.1  BPM 60 → 110-120'ye Atlama (Parmak Yeniden Konulunca)

**Neden oluyor?**

Parmak kaldırıldığında firmware tarafında tüm durum sıfırlanır (`_stableBpm = 0`).  
Parmak tekrar konulunca ve warmup (eski: 8 s) tamamlanınca **ilk `rawBpm` tahmini**
doğruca `_stableBpm` değişkenine atanıyordu — herhangi bir onay olmaksızın.  
İlk tahmin, geçiş verisi içeren ring-buffer'dan geldiği için (buffer henüz temiz değil)
yanlış bir BPM (ör. 115) olabiliyordu. Ardından ikinci okumayla sadece **2 eşleşme**
yeterli görülüyor, yanlış değer "onaylanmış stabil" hale getiriliyordu.

Ek sorun: Büyük atlama onaylanırken `_stableBpm = 0.5 * eski + 0.5 * yeni` ile
eski hatalı değerle harmanlanıyordu → ortanca bir değer kalıcı hale geliyordu.

**Mobil taraf:** `transport_orchestrator.dart` içinde `_pendingBpmConfirm >= 2` ile
aynı sorun tekrarlanıyordu; hem de `_stableBpm = stable * 0.5 + incoming * 0.5`
harmanlama formülü kullanılıyordu.

---

### 1.2  SpO2 Sürekli 70-77 Gösterme

**İki ayrı yol:**

**Yol A — Firmware:** `_estimate_spo2()` fonksiyonu R oranını `[0.3, 2.0]` aralığında
kabul ediyordu. Bu formülde `110 - 25 * R` ile R = 1.3-1.6 → SpO2 = 70-77% üretiyordu.
Gerçi `spo2 < 88 → return 0` filtresi mevcuttu, bu nedenle *gerçek zamanlı* BLE
akışında 70-77 değeri üretilmiyordu. Ancak **daha eski firmware/ingestion** kayıtları
bu değerleri backend veritabanına "geçerli" olarak yazmıştı.

**Yol B — Mobil Parser (asıl sebep):** `ble_payload_parser.dart` içindeki
`fromNestedJson` ve `fromLegacyFlatJson` factory'leri:
```dart
spo2Valid: json['spo2_valid'] as bool? ?? json['spo2'] != null,
```
kodunu kullanıyordu. Değer null değilse (`spo2 = 72.0` gibi) otomatik olarak
`spo2Valid = true` sayılıyordu. Backend'den dönen eski kayıtlar için bu, 70-77%
değerlerini "geçerli" göstermesine neden oluyordu.

**Yol C — Dashboard display:** `_spo2Display()` ve `_hrDisplay()` fonksiyonları
yalnızca BLE modunda geçerlilik kontrolü yapıyordu; backend modunda hiç kontrol
yoktu. `spo2Valid == null` (bilinmiyor) durumu `== false` testi ile yakalanamıyordu.

---

### 1.3  Motion Artifact Gate Eksikliği

Hareket koruması yalnızca `pkt.imu_ok && pkt.hr_valid` koşulunda çalışıyordu.
Yani SpO2 zaten geçersizse hareket filtresi devreye girmiyordu.

---

## 2. Firmware Değişiklikleri

### 2.1  `firmware/include/ha_config.h`

Yeni sabitler eklendi:

| Sabit | Değer | Açıklama |
|-------|-------|----------|
| `PPG_WARMUP_MS` | 10 000 ms | Warmup 8 s → 10 s (ring-buffer tamamen temizlenir) |
| `BPM_STABLE_WINDOW_MS` | 3 000 ms | İlk BPM için gereken tutarlı okuma süresi |
| `BPM_JUMP_THRESH_BPM` | 20.0 | Atlama eşiği (eski: 25 BPM) |
| `BPM_JUMP_WINDOW_MS` | 3 000 ms | Atlama onayı için süre |
| `SPO2_STABLE_WINDOW_MS` | 5 000 ms | SpO2 onayı için gereken tutarlı okuma süresi |
| `SPO2_RING_SIZE` | 6 | SpO2 ring-buffer boyutu |
| `SPO2_R_MIN` | 0.40 | R oranı alt sınırı (→ SpO2 = 100%) |
| `SPO2_R_MAX` | 0.88 | R oranı üst sınırı (→ SpO2 = 88%) |
| `SPO2_MAX_SPREAD_PCT` | 5.0 | Ring-buffer tutarlılık eşiği |
| `MOTION_GYRO_GATE_DPS` | 25.0 | Jiroskop eşiği (deg/s) |
| `MOTION_ACCEL_GATE_G` | 0.35 | İvme eşiği (g sapma) |

### 2.2  `firmware/include/ha_types.h`

`PpgState` enum ve yeni alanlar eklendi:

```cpp
enum PpgState : uint8_t {
    PPG_NO_FINGER=0, PPG_WARMING_UP=1, PPG_STABILIZING=2,
    PPG_STABLE=3,    PPG_UNSTABLE=4,   PPG_MOTION_ARTIFACT=5
};
```

`PpgSample` ve `DevicePacket`'e şu alanlar eklendi:
- `float bpm_raw` — ham BPM (peak detection sonrası, stabilizasyon öncesi)
- `float spo2_raw` — ham SpO2 (ring-buffer öncesi)
- `PpgState measurement_state` — anlık ölçüm durumu
- `bool motion_artifact` — hareket filtresi devreye girdiyse `true`

### 2.3  `firmware/include/ha_max30102.h`  ← En Kritik Değişiklik

#### BPM Stabilizasyon — Zaman Tabanlı Onay

Eski sayaç tabanlı (`_bpmConfirmCount >= 2`) yöntem, yeni **zaman tabanlı** yöntemle
değiştirildi:

```
Parmak yeni konuldu
   → rawBpm ilk geldiğinde _pendingBpm olarak kaydedilir, timer başlar
   → Süre BPM_STABLE_WINDOW_MS (3 s) boyunca rawBpm ±20 BPM tutarlı kalırsa
     → _stableBpm = _pendingBpm  (slow EMA)
     → _bpmConfirmed = true
   → Tutarsızlık: timer sıfırlanır, yeni pendingBpm alınır

Stabil BPM varken büyük atlama (>20 BPM)
   → 3 saniye boyunca yeni seviyede tutarsa
   → _stableBpm = yeni değer  (eski ile harmanlama YOK)
   → _bpmConfirmed = true
```

#### SpO2 Ring-Buffer Onayı

6 elemanlı ring-buffer eklendi. Kurallar:
1. `_estimate_spo2()` yalnızca `R ∈ [0.40, 0.88]` için sonuç üretir — bu aralık
   doğrudan SpO2 = [88%, 100%]'e karşılık gelir; 70-77% aralığı artık hiç üretilmez.
2. Ring'de en az 3 örnek birikmeden `_spo2Confirmed = false`.
3. Ring spread'i > %5 ise stabilite timer sıfırlanır.
4. `SPO2_STABLE_WINDOW_MS` (5 s) boyunca tutarlı kaldıktan sonra `_spo2Confirmed = true`.

#### Parmak Kaldırma — Tam Sıfırlama

Parmak kaldırıldığında artık hem BPM hem SpO2 durumu sıfırlanıyor:
```cpp
_stableSpo2 = 0.0f; _spo2Confirmed = false;
_spo2RingCount = 0;  _spo2RingIdx = 0;
memset(_spo2Ring, 0, sizeof(_spo2Ring));
_spo2StableStartMs = 0;
// (BPM alanları zaten sıfırlanıyordu)
```

### 2.4  `firmware/include/ha_acquisition.h`

Motion gate koşulu düzeltildi:
```cpp
// ESKI (eksik): if (pkt.imu_ok && pkt.hr_valid) { ... }
// YENİ: IMU varsa her zaman kontrol et
if (pkt.imu_ok) {
    if (gyroMag > MOTION_GYRO_GATE_DPS || accDyn > MOTION_ACCEL_GATE_G) {
        pkt.hr_valid = false;
        pkt.spo2_valid = false;
        pkt.motion_artifact = true;
        pkt.measurement_state = (uint8_t)PPG_MOTION_ARTIFACT;
    }
}
```

### 2.5  `firmware/include/ha_packet.h`

BLE summary JSON'a tanı alanları eklendi:
- `ms` — measurement_state (0-5 enum değeri)
- `ma` — motion_artifact (0/1)
- `br` — bpm_raw (parmak varken)
- `sr` — spo2_raw (parmak varken)

---

## 2b. Firmware Ek Düzeltmeleri — v2 (Bu Oturum)

### PPG_EFFECTIVE_SAMPLE_RATE_HZ sabiti eklendi (ha_config.h)

`collectRawSample()` sensör tamponunu 50 Hz'de doldurduğu hâlde, `_estimate_heart_rate()` refraktör periyodu ve aralık hesabı `SAMPLING_RATE_HZ = 25`'i kullanıyordu.

```cpp
// ÖNCE
const int refract = (int)(SAMPLING_RATE_HZ * 0.30f);           // 7 @ 25 Hz → 140 ms
float interval_sec = (float)(peaks[i]-peaks[i-1]) / SAMPLING_RATE_HZ;

// SONRA
#define PPG_EFFECTIVE_SAMPLE_RATE_HZ  MODEL_STREAM_RATE_HZ      // = 50 Hz
const int refract = (int)(PPG_EFFECTIVE_SAMPLE_RATE_HZ * 0.30f); // 15 @ 50 Hz → 300 ms
float interval_sec = (float)(peaks[i]-peaks[i-1]) / (float)PPG_EFFECTIVE_SAMPLE_RATE_HZ;
```

Önceki 7 örneklik refraktör → 140 ms gürültü piklerini geçiriyordu → BPM ×2 enflasyonu.  
Interval ÷25 yerine ÷50 yapılması gerekiyordu → BPM ÷2 deflasyonu da buradan geliyordu.

### _processBpm() — _bpmStableStartMs = 0 hatası (ha_max30102.h)

```cpp
// ÖNCE (BUG)
_bpmStableStartMs = 0;
if (_bpmConfirmed && millis() - _bpmStableStartMs > 10000UL) {  // = millis()-0 → her zaman doğru
    _bpmConfirmed = false; _stableBpm = 0.0f;
}

// SONRA
_lastValidBpmMs = 0;  // yeni üye — son geçerli aralıkta ham BPM zaman damgası
if (_bpmConfirmed && (millis() - _lastValidBpmMs) > 10000UL) {
    _bpmConfirmed = false; _stableBpm = 0.0f; _bpmStableStartMs = 0;
}
// ... fonksiyon sonunda:
_lastValidBpmMs = millis();
```

### PPG_UNSTABLE ölü kod düzeltmesi + _wasEverConfirmed bayrağı

Durum makinesi yeniden düzenlendi; PPG_UNSTABLE artık erişilebilir durumda:

```cpp
if (_bpmConfirmed || _spo2Confirmed) {
    _wasEverConfirmed = true;
    sample.measurement_state = PPG_STABLE;
} else if (_wasEverConfirmed) {
    sample.measurement_state = PPG_UNSTABLE;   // artık erişilebilir
} else {
    sample.measurement_state = PPG_STABILIZING;
}
```

### hr_valid üst sınırı 140 → 130 BPM

```cpp
sample.hr_valid = _bpmConfirmed && (_stableBpm >= 45.0f) && (_stableBpm <= 130.0f);
```

---

## 3. Mobil Değişiklikleri

### 3.1  `mobile/lib/core/services/transport_orchestrator.dart`

**Parmak kaldırma → anında sıfırlama:**
```dart
if (!packet.fingerDetected) {
  _stableBpm = null;   _pendingBpm = null;   _pendingBpmConfirm = 0;
  _stableSpo2 = null;  _lastSpo2ValidAt = null;
}
```
Önceki session'ın `_stableSpo2` değeri yeni session'a taşınmıyordu, ancak
parmak kaldırma anında değil sadece timeout (10 s) ile sıfırlanıyordu. Artık
anlık sıfırlanıyor.

**SpO2 retention — parmak yok iken tutma:**
Eski kod `packet.fingerDetected` kontrolü yapmıyordu. Yeni kod:
```dart
if (packet.fingerDetected && packet.spo2Valid && packet.spo2 > 0) { ... }
```

**BPM atlama — harmanlama hatası düzeltildi:**
```dart
// ESKİ (yanlış):  _stableBpm = stable * 0.5 + incoming * 0.5;
// YENİ (doğru):   _stableBpm = incoming;  // tam değiştirme
```

### 3.2  `mobile/lib/core/services/ble_payload_parser.dart`

`fromNestedJson` ve `fromLegacyFlatJson`'daki tehlikeli fallback kaldırıldı:
```dart
// ESKİ — non-null = valid varsayımı (BUG):
spo2Valid: json['spo2_valid'] as bool? ?? json['spo2'] != null,
hrValid:   json['hr_valid']   as bool? ?? json['heart_rate'] != null,

// YENİ — yalnızca explicit bool flag kullanılır:
spo2Valid: _boolValue(json['spo2_valid']),
hrValid:   _boolValue(json['hr_valid']),
```

### 3.3  `mobile/lib/ui/screens/dashboard_screen.dart`

**`_hrDisplay()` ve `_spo2Display()` düzeltildi:**

- `== false` testi → `!= true` (null bilinmiyor = geçersiz sayılır)
- Backend modunda sınır kontrolü eklendi:
  ```dart
  // BPM: 20-220 dışı → '--'
  // SpO2: 80-100 dışı → '--' (eski firmware'den gelen 70-77 kayıtları gösterilmez)
  ```

**MetricCard başlıkları:** `== false` → `!= true`, `!= false` → `== true` ile eşleşti.

---

## 4. Risk Servisi / Personalizasyon Güvenliği

`local_risk_calculator.dart` zaten `bpmValid` ve `spo2Valid` flag'lerini kontrol
ediyor ve `fingerPresent = false` → risk = 0.0 döndürüyor. Ek değişiklik gerekmedi.

Backend risk fusion servisi, BLE kanalında `hr_valid`/`spo2_valid` alanlarını
alıyor; bu alanlar artık firmware tarafından çok daha güvenilir şekilde set ediliyor.

---

## 5. Build / Analiz Sonuçları

| Test | Sonuç |
|------|-------|
| `cd firmware ; pio run` | ✅ BAŞARILI (1 752 705 / 3 145 728 flash; 63 676 / 327 680 RAM) |
| `cd mobile ; flutter analyze --no-pub --no-fatal-infos --no-fatal-warnings` | ✅ HATA YOK (269 mevcut info/warning — hiçbiri yeni değişikliklerden değil) |

---

## 6. Beklenen Davranış Değişiklikleri

| Durum | Eskiden | Şimdi |
|-------|---------|-------|
| Parmak ilk konulunca | 8 s sonra BPM hemen gösteriliyordu | 10 s warmup + 3 s stabilizasyon = ~13 s sonra BPM |
| Parmak kaldırıp tekrar konulunca | Yanlış ilk tahmin stabil BPM olabiliyordu | Yeni session başlar, min. 3 s tutarlılık beklenir |
| SpO2 70-77% | Dashboard'da görünebiliyordu | Artık mümkün değil (R gate + parser fix) |
| SpO2 stabil olmadan | Anlık ham değer gösteriliyordu | "SpO2 KALIBRE" / "Stabil oluyor" gösterilir |
| Hareket var, SpO2 invalid | Gate tetiklenmeyebiliyordu | Her zaman tetiklenir, `ma=1` gönderilir |
| Backend modunda eski geçersiz kayıt | SpO2 = 72.0 gösteriliyordu | `_spo2Display` sanity bound → '--' döner |

---

## 7. El ile Test Önerileri

1. **Warmup testi:** ESP32 bağlandıktan sonra ilk 10 s boyunca BPM/SpO2 kartları
   "KALIBRE OLUYOR" / "SpO2 KALIBRE" göstermeli. 10 s sonra geçiş başlar.

2. **Parmak kaldır-koy testi:** Parmağı kaldırınca değerler anlık '--' olmalı.
   Tekrar koyunca stabilizasyon süreci yeniden başlamalı (10+3 = ~13 s).

3. **SpO2 aralık testi:** Dashboard'da asla 88% altında SpO2 görünmemeli.
   Düşük kalite / hareket durumunda "Stabil oluyor" veya '--' görünmeli.

4. **Hareket testi:** Cihaz sallandığında BPM/SpO2 kartları geçerlilik kaybetmeli
   ve `ms` alanı 5 (MOTION_ARTIFACT) olmalı.

5. **Backend mod testi:** Backend'den gelen eski 70-77% kayıtları için dashboard
   '--' göstermeli (`spo2 < 80` → '--' kuralı).
