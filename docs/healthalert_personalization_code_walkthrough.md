# 1. Kısa Cevap

- Kişiselleştirme tamamen sabit tek-kural (`HR > X`) tabanlı değil; **heuristic + kullanıcıya özel istatistiksel güncelleme** birlikte kullanılıyor.
- Canlı ingest akışında **PyTorch/NN eğitimi yok**; öğrenme tarafı pencere/feedback kaydı ve export (`learning_data_service`) yapıyor.
- Sistem **adaptive/statistical personalization** yapıyor: `UserBaseline` (EMA) + `PersonalHealthProfile` + opsiyonel trend/feedback düzeltmeleri.
- Kişiyi öğrendiği veriler: `heart_rate`, `spo2`, `motion_score`, kalite/validity flag’leri, profile sayaçları.
- Kişiyi öğrenmediği veriler (bu akışta): `red_value`, `ir_value` kişiselleştirme hesaplarına girmiyor; sadece paket logunda tutuluyor.

Özet: Sistem canlıda modeli yeniden eğitmiyor; kullanıcıya özel baseline/profil tablolarını güncelliyor. Global risk kural tabanlı başlıyor, üstüne kişisel katman ekleniyor.

# 2. Ana Veri Akışı

## 2.1 Paket gelir
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyon:** `ingest_device_packet`

```python
@router.post("/device-packet", response_model=DevicePacketResponse)
async def ingest_device_packet(...):
    ...
```

Bu endpoint tüm pipeline’ın giriş noktası.

## 2.2 Device registration çözülür
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyon:** `ingest_device_packet`

```python
reg = await repos.devices.get_registration(pkt.device_id)
if reg:
    user_id = reg["user_id"]
```

Cihaz kullanıcıya eşliyse user-specific akış başlıyor; eşli değilse user pipeline atlanıyor.

## 2.3 Motion score hesaplanır
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyon:** `_compute_motion_score`

```python
def _compute_motion_score(ax, ay, az, gx, gy, gz):
    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
    accel_dev = abs(accel_mag - 1.0)
    gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
    score = min(1.0, (accel_dev * 2.0) + (gyro_mag / 50.0))
    return round(score, 3)
```

IMU/Gyro’dan normalize hareket skoru üretiliyor.

## 2.4 Global risk score hesaplanır
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyon:** `_compute_risk_score`

```python
global_risk_score = _compute_risk_score(
    pkt.heart_rate, pkt.spo2,
    pkt.hr_valid, pkt.spo2_valid, motion_score,
)
```

İlk “ham risk” burada oluşuyor.

## 2.5 Baseline service çağrılır
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyonlar:** `compute_quality_confidence`, `update_user_baseline`, `compute_personal_deviation`, `apply_baseline_adjustment`

```python
quality_info = compute_quality_confidence(...)
baseline = await update_user_baseline(..., global_risk_score=global_risk_score)
deviation = compute_personal_deviation(...)
adjustment = apply_baseline_adjustment(...)
risk_score = adjustment["final_risk_score"]
```

Kalite + kişisel baseline sapması ile global risk ayarlanıyor.

## 2.6 Adaptive personalization service çağrılır
**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyonlar:** `update_profile_from_packet`, `compute_trend_from_snapshots`, `compute_personalized_risk`

```python
profile = await adaptive_personalization_service.update_profile_from_packet(...)
trend_info = compute_trend_from_snapshots([])
personalization_result = compute_personalized_risk(...)
```

Profil güncelleniyor, personalized risk breakdown üretiliyor.

## 2.7 final_risk_score oluşur
**Dosya:** `backend/routers/ingestion_router.py`

```python
risk_score = personalization_result["final_personalized_risk"]
risk_breakdown["final_risk_score"] = risk_score
```

Pipeline’ın aşağısına giden final skor budur.

## 2.8 LiveStatus / Alert / Assistant tarafına aktarılır
**Dosya:** `backend/routers/ingestion_router.py`

```python
await repos.live_status.upsert(user_id, {"risk_score": risk_score, ...})
await repos.anomalies.create({...})
await repos.alerts.create({...})
eval_result = await care_assistant_service.evaluate_assistant_state(
    repos=repos, user_id=user_id, final_risk_score=risk_score, ...
)
```

Skor önce live status’a yazılır; severity varsa anomaly/alert zinciri ve care assistant çalışır.

# 3. Global Risk Nerede Hesaplanıyor?

**Dosya:** `backend/routers/ingestion_router.py`  
**Fonksiyon:** `_compute_risk_score`

```python
def _compute_risk_score(hr, spo2, hr_valid, spo2_valid, motion):
    risk = 0.0
    if hr_valid:
        if hr > 120: risk += 0.3
        elif hr > 100: risk += 0.15
        elif hr < 50: risk += 0.2
    if spo2_valid:
        if spo2 < 90: risk += 0.4
        elif spo2 < 94: risk += 0.2
    risk += motion * 0.2
    return round(min(1.0, risk), 3)
```

- HR, SpO2 ve motion doğrudan ağırlıklı toplanıyor.
- Bu bölüm **heuristic/kural tabanlı**.
- Bu bölüm **kişiselleştirme değil**; kişiselleştirme bundan sonra ekleniyor.

# 4. UserBaseline Kodda Nerede?

**Dosya:** `backend/models.py`  
**Model:** `UserBaseline`

```python
class UserBaseline(Base):
    __tablename__ = "user_baselines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True)
    hr_mean: Mapped[float] = mapped_column(Float, default=72.0)
    hr_std: Mapped[float] = mapped_column(Float, default=10.0)
    spo2_mean: Mapped[float] = mapped_column(Float, default=98.0)
    spo2_std: Mapped[float] = mapped_column(Float, default=1.5)
    motion_mean: Mapped[float] = mapped_column(Float, default=0.10)
    motion_std: Mapped[float] = mapped_column(Float, default=0.08)
    ppg_quality_mean: Mapped[float] = mapped_column(Float, default=0.85)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- `hr_mean/hr_std`: kullanıcının tipik nabız ortalaması ve yayılımı.
- `spo2_mean/spo2_std`: kullanıcının tipik SpO2 ortalaması ve yayılımı.
- `motion_mean/motion_std`: kullanıcının tipik hareket seviyesi.
- `ppg_quality_mean`: ortalama sinyal kalitesi.
- `sample_count`: kaç güvenilir örnekle öğrenildiği.
- `is_ready`: minimum örnek eşiği geçildi mi.
- `created_at/updated_at`: kayıt zamanları.

# 5. Baseline Nasıl Güncelleniyor?

**Dosya:** `backend/services/baseline_service.py`

## 5.1 `update_user_baseline`

```python
baseline = await repos.baselines.get_or_create(user_id)
reliable = is_reliable_for_baseline(..., global_risk_score=global_risk_score)
if not reliable:
    return baseline

alpha = settings.BASELINE_EMA_ALPHA
hr_mean = _ema(baseline["hr_mean"], hr, alpha)
hr_var = _ema_var(baseline["hr_std"] ** 2, hr, baseline["hr_mean"], alpha)
...
new_n = n + 1
is_ready = new_n >= settings.BASELINE_MIN_SAMPLES
updated = await repos.baselines.update_values(user_id, updates)
```

- Önce `get_or_create`, sonra güvenilirlik gate’i.
- Güvenilir değilse `sample_count` artmadan eski baseline döner.
- Güvenilirse EMA ile ortalama/std güncellenir.

## 5.2 `is_reliable_for_baseline`

```python
if not finger_detected: return False
if not hr_valid: return False
if not spo2_valid: return False
if not ppg_ok: return False
if signal_quality < settings.BASELINE_MIN_SIGNAL_QUALITY: return False
if hr < 35 or hr > 190: return False
if spo2 < 70 or spo2 > 100: return False
if global_risk_score >= settings.RISK_WARNING_THRESHOLD: return False
```

Baseline güncellemesi engellenen durumlar kodda açık: düşük kalite, invalid ölçüm, parmak yok, fizyolojik uç değer, yüksek risk.

## 5.3 EMA formülü

```python
def _ema(old, new, alpha):
    return alpha * new + (1.0 - alpha) * old

def _ema_var(old_var, new_val, old_mean, alpha):
    diff = new_val - old_mean
    return (1.0 - alpha) * (old_var + alpha * diff * diff)
```

## 5.4 `compute_personal_deviation`

```python
hr_z = abs(hr - baseline["hr_mean"]) / max(baseline["hr_std"], 5.0)
spo2_z = max(0.0, baseline["spo2_mean"] - spo2) / max(baseline["spo2_std"], 1.0)
motion_z = max(0.0, motion_score - baseline["motion_mean"]) / max(baseline["motion_std"], 0.05)
...
bonus = min(settings.BASELINE_PERSONAL_BONUS_MAX, hr_contrib + spo2_contrib + motion_contrib)
```

Kişisel sapma z-score’lardan `deviation_bonus` üretir.

## 5.5 `apply_baseline_adjustment`

```python
if baseline_ready:
    personal_deviation_score = deviation["deviation_bonus"]
    if confidence < 0.5 and not safety_override:
        personal_deviation_score = 0.0

final_risk_score = round(
    min(1.0, max(0.0, global_risk_score + personal_deviation_score)),
    3,
)
```

Hazır baseline varsa sapma bonusu eklenir; kalite düşükse bonus kesilir.

# 6. Quality Confidence Kodda Nasıl Var?

**Dosya:** `backend/services/baseline_service.py`  
**Fonksiyon:** `compute_quality_confidence`

```python
score = signal_quality
if not finger_detected: score *= 0.0
if not ppg_ok: score *= 0.5
if not hr_valid: score *= 0.7
if not spo2_valid: score *= 0.8
...
safety_override = spo2_valid_flag and spo2 < 88
```

- `finger_detected`: evet, en sert etki (0’a indiriyor).
- `hr_valid`: evet, kaliteyi çarpanla düşürüyor.
- `spo2_valid`: evet, kaliteyi düşürüyor.
- `signal_quality`: temel skor.
- Düşük kalite etkisi:
  - Baseline bonusu `apply_baseline_adjustment` içinde kesilebilir.
  - Learning’de training candidate kalite eşiğine göre düşebilir (`_is_training_candidate`).
  - Personalized riskte düşük kalite bonus/trend etkisini damp eder (`compute_personalized_risk`).

# 7. Adaptive Personalization Servisi Ne Yapıyor?

**Dosya:** `backend/services/adaptive_personalization_service.py`

## 7.1 `get_or_create_profile`
```python
profile = await repos.personalization.get_or_create_profile(user_id)
```
Girdi: `user_id`. Çıktı: profil dict. Final riski doğrudan hesaplamaz.

## 7.2 `update_profile_from_packet`
```python
updates["total_valid_samples"] = current_samples + 1
updates["typical_hr_min"] = _ema(...)
updates["typical_hr_max"] = _ema(...)
...
updates["personalization_level"] = _get_personalization_level(...)
return await repos.personalization.update_profile(user_id, updates)
```
Girdi: packet metrikleri + baseline. Çıktı: güncel profil. Final riski doğrudan döndürmez.

## 7.3 `compute_contextual_deviation`
```python
if hr > hr_max: hr_bonus = ...
if spo2 < spo2_min: spo2_bonus = ...
if motion_score > motion_max: motion_bonus = ...
```
Girdi: profil + anlık ölçüm. Çıktı: `deviation_bonus`. Final riske katkı verir.

## 7.4 `compute_trend_from_snapshots`
```python
if not recent_statuses or len(recent_statuses) < 3:
    return {"hr_trend":"stable", ..., "trend_confidence":0.0}
```
Girdi: son snapshot listesi. Çıktı: trend etiketleri + confidence. Tek başına final skoru set etmez.

## 7.5 `compute_trend_adjustment`
```python
if hr_trend == "rising" and spo2_trend == "falling":
    adjustment += 0.08
...
adjustment *= confidence
```
Girdi: trend bilgisi. Çıktı: risk delta. Final riske eklenir.

## 7.6 `compute_feedback_adjustment`
```python
false_alarm_rate = false_alarm_count / total_fb
if false_alarm_rate > 0.5 and severity == "warning":
    adjustment -= ...
if confirmed_risk_count >= 3:
    adjustment += ...
```
Girdi: profile sayaçları. Çıktı: feedback delta. Final riske eklenir.

## 7.7 `compute_personalized_risk`
```python
baseline_final = baseline_result.get("final_risk_score", global_risk_score)
deviation = compute_contextual_deviation(...)
trend_adjustment = compute_trend_adjustment(...)
feedback_adjustment = compute_feedback_adjustment(...)
raw_personalized = baseline_final + baseline_deviation_score + trend_adjustment + feedback_adjustment
final_personalized_risk = round(max(0.0, min(1.0, raw_personalized)), 4)
```
Girdi: global risk + baseline sonucu + profil + trend + quality.  
Çıktı: `final_personalized_risk` dahil breakdown.  
**Evet, final_risk_score’u downstream’de bu değer değiştiriyor.**

## 7.8 `record_risk_memory`
```python
result = await repos.personalization.add_risk_memory(data)
await self._update_profile_counters(repos, user_id, event_type)
```
Girdi: event/risk. Çıktı: risk memory kaydı.  
Profil feedback sayaçlarını artırma logic’i burada var.

# 8. PersonalHealthProfile Kodda Nasıl?

**Dosya:** `backend/models.py`  
**Model:** `PersonalHealthProfile`

```python
class PersonalHealthProfile(Base):
    __tablename__ = "personal_health_profiles"
    baseline_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    personalization_level: Mapped[str] = mapped_column(String(20), nullable=False, default="cold_start")
    total_valid_samples: Mapped[int] = mapped_column(Integer, default=0)
    total_feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    false_alarm_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    sensor_error_count: Mapped[int] = mapped_column(Integer, default=0)
    typical_hr_min: Mapped[float] = mapped_column(Float, default=55.0)
    typical_hr_max: Mapped[float] = mapped_column(Float, default=100.0)
    typical_spo2_min: Mapped[float] = mapped_column(Float, default=95.0)
    typical_spo2_max: Mapped[float] = mapped_column(Float, default=100.0)
    typical_motion_min: Mapped[float] = mapped_column(Float, default=0.0)
    typical_motion_max: Mapped[float] = mapped_column(Float, default=0.5)
```

Bu tablo `UserBaseline`’dan daha zengin kişisel profil katmanı: tipik aralıklar + feedback geçmiş sayaçları.

# 9. Personalization Level Nasıl Hesaplanıyor?

**Dosya:** `backend/services/adaptive_personalization_service.py`  
**Fonksiyon:** `_get_personalization_level`

```python
_COLD_START_MAX_SAMPLES = 30
_LEARNING_MAX_SAMPLES = 300
_MATURE_MIN_FEEDBACK = 10

def _get_personalization_level(total_valid_samples, total_feedback_count):
    if total_valid_samples < 30: return "cold_start"
    if total_valid_samples < 300: return "learning"
    if total_feedback_count >= 10: return "mature"
    return "calibrated"
```

- `cold_start`: `< 30` sample
- `learning`: `30..299` sample
- `calibrated`: `>= 300` sample ve feedback `< 10`
- `mature`: `>= 300` sample ve feedback `>= 10`
- Feedback sayısı mature’a geçişi etkiliyor.
- Seviye, bonus tavanlarını sınırlar (`_max_bonus_for_level`).

Test doğrulaması:

```python
assert _get_personalization_level(29, 100) == "cold_start"
assert _get_personalization_level(30, 0) == "learning"
assert _get_personalization_level(300, 0) == "calibrated"
assert _get_personalization_level(300, 10) == "mature"
```

# 10. Trend Kodu Gerçekten Canlıda Kullanılıyor mu?

Evet trend fonksiyonları var, ama ingest’te şu an gerçek son N snapshot beslenmiyor:

```python
# ingestion_router.py
trend_info = compute_trend_from_snapshots([])
```

Trend fonksiyonu da boş/az listede şunu döndürüyor:

```python
if not recent_statuses or len(recent_statuses) < 3:
    return {..., "trend_confidence": 0.0}
```

Sonuç: Trend altyapısı kodda var ama canlı pipeline şu an boş liste ile çağırdığı için trend etkisi pratikte `0` kalıyor.

# 11. Feedback Kişiselleştirmeye Nasıl Giriyor?

## 11.1 Kullanıcı “İyiyim / Yanlış alarm / Yardıma ihtiyacım var” akışı
**Dosya:** `backend/routers/assistant_router.py`

```python
@router.post("/ack")
async def post_assistant_ack(body: AssistantAckRequest, ...):
    result = await care_assistant_service.handle_user_ack(...)
```

`response` değerleri `ok`, `not_ok`, `false_alarm`.

## 11.2 Care assistant feedback yazımı
**Dosya:** `backend/services/care_assistant_service.py`

```python
if repos.personalization is not None:
    await repos.personalization.add_risk_memory({... "event_type": event_type, ...})
```

Bu yol `PersonalRiskMemory` tablosuna yazıyor.

## 11.3 Learning feedback yazımı
**Dosya:** `backend/routers/learning_router.py` + `backend/services/learning_data_service.py`

```python
saved = await learning_data_service.attach_feedback(...)
...
saved = await repos.learning.create_feedback(feedback_data)
```

Bu yol `UserFeedbackEvent` tablosuna yazıyor.

## 11.4 Kritik gözlem: Adaptive feedback sayaçları gerçekten besleniyor mu?

`compute_feedback_adjustment`, profile sayaçlarını okuyor:

```python
false_alarm_count = profile.get("false_alarm_count", 0)
confirmed_risk_count = profile.get("confirmed_risk_count", 0)
total_fb = profile.get("total_feedback_count", 0)
```

Sayaç artırma kodu `record_risk_memory()` içinde:

```python
await self._update_profile_counters(repos, user_id, event_type)
```

Ama üretim akışında bu metod çağrısı yok (yalnız testte var). `care_assistant_service._record_feedback` doğrudan `add_risk_memory` çağırıyor, profile sayaçlarını artırmıyor.  
Dolayısıyla feedback verisi belleğe/loglara giriyor, fakat feedback-tabanlı risk düzeltmesi için kullanılan profile sayaçları mevcut akışta sınırlı besleniyor.

Ek not: `_record_feedback` içinde `UserFeedbackEvent(...)` objesi oluşturuluyor ama DB’ye `add/flush` edilmediği için bu blok kendi başına kalıcı yazım yapmıyor.

# 12. final_risk_score Tam Olarak Nerede Oluşuyor?

**Dosya:** `backend/routers/ingestion_router.py`  
`risk_score` adım adım şu şekilde oluşuyor:

```python
global_risk_score = _compute_risk_score(...)

quality_info = compute_quality_confidence(...)
baseline = await update_user_baseline(..., global_risk_score=global_risk_score)
deviation = compute_personal_deviation(...)
adjustment = apply_baseline_adjustment(
    global_risk_score=global_risk_score,
    deviation=deviation,
    quality_info=quality_info,
    baseline_ready=baseline_ready,
    alert_sensitivity=alert_sensitivity,
)
risk_score = adjustment["final_risk_score"]

profile = await adaptive_personalization_service.update_profile_from_packet(...)
trend_info = compute_trend_from_snapshots([])
personalization_result = compute_personalized_risk(
    global_risk_score=global_risk_score,
    baseline_result=adjustment,
    profile=profile,
    trend_info=trend_info,
    quality_info=quality_info,
    ...
)
risk_score = personalization_result["final_personalized_risk"]
```

Sonrasında bu `risk_score`:
- `LiveStatus.risk_score` olarak yazılır,
- severity hesaplarında kullanılır,
- anomaly/alert/assistant akışına taşınır.

Yani final değer iki katmanda oluşuyor:
1. **Baseline-adjusted risk** (`adjustment["final_risk_score"]`)
2. **Personalized final risk** (`personalization_result["final_personalized_risk"]`)
