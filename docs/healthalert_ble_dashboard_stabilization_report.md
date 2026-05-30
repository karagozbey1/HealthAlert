# HealthAlert — BLE Dashboard Stabilization Report
**Sunum Hazırlık Paketi · Tüm değişiklikler uygulandı**

---

## 1. Kısa Sonuç

Dashboard'daki dört görsel sorun tamamen düzeltildi:

| Sorun | Neden | Çözüm | Durum |
|-------|-------|-------|-------|
| HAREKET kart %0 gösteriyordu | `toLiveStatus()` içinde `motionScore: 0` hardcoded | `_computeMotionScore(accTotal, gyroTotal)` ile IMU'dan hesapla | ✅ Düzeltildi |
| RİSK SKORU kart %0 / "--" | `riskScore: 0` + `LiveValueCard.riskScore()` BLE için `'--'` döndürüyordu | `LocalRiskCalculator` servisi + kart güncellendi | ✅ Düzeltildi |
| BPM 45→60→90→105 zıplıyor | Zero-crossing algoritması gürültülü, EMA yok | Firmware EMA + 3× confirm; mobile ≥25 BPM jump rejection | ✅ Düzeltildi |
| SpO2_EST çoğunlukla "--" | `sv=0` geldiğinde anlık kayıp; buffer dolu değil | 10 saniyelik son-geçerli SpO2 retention (mobile) | ✅ Düzeltildi |

---

## 2. Değiştirilen / Oluşturulan Dosyalar

### Mobile (Flutter/Dart)

| Dosya | Değişiklik |
|-------|-----------|
| `mobile/lib/core/services/ble_payload_parser.dart` | `motionScore: _computeMotionScore(accTotal, gyroTotal)` + `_computeMotionScore()` static helper |
| `mobile/lib/core/services/local_risk_calculator.dart` | **YENİ** — BLE ölçümlerinden 0–1 risk skoru hesaplayan statik servis |
| `mobile/lib/core/models/live_status.dart` | `copyWith({heartRate, heartRateValid, spo2, spo2Valid, motionScore, riskScore, source})` eklendi |
| `mobile/lib/core/services/transport_orchestrator.dart` | `_enrichStatus()` + `_applySmoothBpm()` + SpO2 retention + LocalRiskCalculator import |
| `mobile/lib/ui/widgets/live_value_card.dart` | `riskScore` factory: BLE için `'--'` yerine hesaplanan risk + Türkçe seviye label |
| `mobile/lib/ui/screens/dashboard_screen.dart` | `_riskDisplay()`, `_motionLabel()` helper'ları; RİSK/HAREKET kart title'ları dinamik |

### Firmware (ESP32 / PlatformIO C++)

| Dosya | Değişiklik |
|-------|-----------|
| `firmware/include/ha_max30102.h` | BPM stabilizasyon state (`_stableBpm`, `_pendingBpm`, `_bpmConfirmCount`, `_bpmConfirmed`) + `_processBpm()` + finger-lost reset |
| `firmware/include/ha_acquisition.h` | `_collectReal()` içinde motion gate — yüksek hareket `hr_valid` ve `spo2_valid` bayrağını sıfırlıyor |

---

## 3. Final Dashboard Davranışı

### Dashboard Ekranı (`dashboard_screen.dart`)
- **KALP HIZI**: `heartRateValid==false` iken `'--'`; geçerliyse stabilize BPM
- **SpO2_EST**: Son 10 saniyede geçerli değer varsa gösterir, yoksa `'--'`
- **CANLI RİSK** *(BLE bağlıyken)*: Parmak yoksa `'--'`; parmak varsa `%0`–`%100` aralığında local risk
- **SAKİN / HAFİF HAREKET / HAREKETLİ / YOĞUN HAREKET** *(HAREKET kart title)*: IMU verisinden dinamik

### Canlı İzleme Ekranı (`live_monitor_screen.dart`)
- `LiveValueCard.riskScore()` artık BLE kaynağında local riski gösteriyor
- Subtitle: `Düşük / Orta / Yüksek / Kritik` veya `Parmak bekleniyor`

---

## 4. Local Runtime Risk Mantığı

`LocalRiskCalculator.calculate()` — BLE ölçümlerine dayalı, backend/model sonucu olmadığında kullanılır.

```
Parmak yok → 0.0 (hesaplama yapma)

BPM (geçerliyse):
  < 50         → +20
  50–99        → +0  (normal)
  100–119      → +10
  120–139      → +20
  ≥ 140        → +30

SpO2 (geçerliyse):
  ≥ 95         → +0  (normal)
  92–94        → +15
  88–91        → +30
  < 88         → +45

Hareket (%):
  0–19         → +0
  20–49        → +5
  50–79        → +12
  ≥ 80         → +20

Sinyal kalitesi:
  < 0.4        → +5

Sonuç = toplam / 100.0  → [0.0, 1.0]
```

**Seviye etiketleri:**
- ≤ %20 → `Düşük`
- ≤ %50 → `Orta`
- ≤ %75 → `Yüksek`
- > %75 → `Kritik`

> **Not:** Bu klinik bir araç değildir. Backend/model sonucu varsa o her zaman önceliklidir.

---

## 5. Hareket Skoru Mantığı

`ble_payload_parser.dart` → `_computeMotionScore(accTotal, gyroTotal)`:

```dart
final accDynamic = (accTotal - 1.0).abs();  // 1.0g = durağan
return ((accDynamic * 90.0) + (gyroTotal * 4.0)).clamp(0.0, 100.0) / 100.0;
```

- `at` (acc toplam) ESP32'den g biriminde gelir. Durağan ≈ 1.0 g.
- `gt` (gyro toplam) °/s biriminde gelir.
- Sonuç 0.0–1.0 (dashboard'da `× 100 → %` olarak gösterilir).

**Dashboard title mapping:**
| Değer | Title |
|-------|-------|
| < %15 | SAKİN |
| %15–44 | HAFİF HAREKET |
| %45–74 | HAREKETLİ |
| ≥ %75 | YOĞUN HAREKET |

---

## 6. BPM Stabilizasyonu

### Firmware (ha_max30102.h — `_processBpm()`)
1. Geçersiz ham BPM (< 30 veya > 220) → stable güncellenmez, confirm sıfırlanır
2. İlk geçerli okuma → `_stableBpm = rawBpm`
3. Sonraki okumalar:
   - Fark ≤ 25 BPM → EMA: `stable = 0.7 × stable + 0.3 × raw`
   - Fark > 25 BPM → 3 ardışık benzer okuma bekle, sonra kabul et
4. Parmak kaybolduğunda → tüm state sıfırlanır

### Mobile (transport_orchestrator.dart — `_applySmoothBpm()`)
- Firmware EMA'ya ek ikinci filtre katmanı
- ≥ 25 BPM zıplama için 2 ardışık confirm gerekir
- Confirm tamamlanana kadar son stable BPM gösterilmeye devam eder

---

## 7. SpO2_EST Stabilizasyonu

`transport_orchestrator.dart` → `_enrichStatus()`:

```dart
if (packet.spo2Valid && packet.spo2 > 0) {
  _stableSpo2 = packet.spo2;   // güncelle + zamanı kaydet
  _lastSpo2ValidAt = DateTime.now();
} else if (_stableSpo2 != null &&
           DateTime.now().difference(_lastSpo2ValidAt!).inSeconds < 10) {
  // Son 10 saniyedeki geçerli değeri tut
  spo2Valid = true;  // UI'da göster
} else {
  spo2Valid = false; // '--'
}
```

Etkisi: Firmware'den `sv=0` geldiğinde SpO2 anında `'--'`'a düşmez; 10 saniye önceki son geçerli değer tutulur.

---

## 8. Firmware Motion Gate

`ha_acquisition.h` → `_collectReal()`, PPG okumalarından sonra:

```cpp
if (pkt.imu_ok && pkt.hr_valid) {
    float gyroMag = sqrtf(gx*gx + gy*gy + gz*gz);  // °/s
    float accDyn  = fabsf(accMag - 1.0f);           // g'den sapma
    if (gyroMag > 15.0f || accDyn > 0.4f) {
        pkt.hr_valid   = false;
        pkt.spo2_valid = false;
    }
}
```

Yüksek hareket sırasında BPM/SpO2 geçersiz işaretlenir → mobile'da `'--'` gösterilir. Bu hareket skoru hesaplamayı etkilemez.

---

## 9. Build Sonuçları

### Flutter Analyze
```
flutter analyze --no-pub
→ 0 error  (269 warning/info — tamamı pre-existing)
```

### PlatformIO Firmware
```
pio run
→ [SUCCESS] Took 24.76 seconds
   RAM: 19.4% used | Flash: 55.7% used
```

---

## 10. APK Build Komutu

```bash
cd mobile
flutter build apk --debug \
  --dart-define=BACKEND_URL=http://10.194.197.145:8000
```

Release APK için `--debug` yerine `--release` kullanın.

---

## 11. Sunum Test Talimatı

1. **APK yükle** → telefona kur
2. **ESP32'yi çalıştır** → BLE iletişimi başlat
3. **Parmağı sensöre koy** → 2-3 saniye bekle
4. Dashboard'da kontrol et:
   - **HAREKET** kart: IMU'ya göre `SAKİN` / `HAFİF HAREKET` vb.
   - **CANLI RİSK** kart: `%0` değil, gerçek bir değer (ör. `%12`, seviye `Düşük`)
   - **KALP HIZI**: Stabilize BPM; hareket sırasında `'--'`
   - **SpO2_EST**: Son 10 saniyede ölçüm varsa gösterir
5. **Hareketi test et** (cihazı sallamak):
   - HAREKET title `HAREKETLİ` veya `YOĞUN HAREKET` olmalı
   - BPM kart `'--'` veya son stable değer göstermeli
6. **BLE kesilirse** → state sıfırlanır, yeniden bağlandığında temiz başlar
