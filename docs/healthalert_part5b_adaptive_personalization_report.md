# HealthAlert Part 5B — Adaptive Personalization Engine
## Personal Health Profile & Risk Personalization Layer

**Rapor Tarihi:** 2025  
**Durum:** ✅ Tamamlandı — 33/33 test PASSED

---

## 1. Amaç

HealthAlert'in risk değerlendirme katmanını, kullanıcıya özel geçmiş gözlemler, kısa vadeli trend sinyalleri ve geri bildirim geçmişine dayanan güçlü bir kişiselleştirme motoru ile genişletmek.

### Sorun
Mevcut sistem (`baseline_service`) global istatistiksel sapmaları hesaplar; ancak her kullanıcının kendine özgü "normal" değerleri yoktur. Bu durum:
- Sporcuların düşük HR'ini "anormal" olarak değerlendirmesine,  
- Gece yükselen SpO2 dalgalanmalarını önemsememesine,  
- Aynı kullanıcının tekrarlayan yanlış alarmlarını öğrenememesine  
yol açar.

### Çözüm: Personalization Layer
Basit kural tabanlı `if HR > 100` yaklaşımı yerini şunlara bıraktı:

| Boyut | Açıklama |
|---|---|
| **Kişisel tipik aralık** | EMA ile adapte olan kullanıcıya özel HR/SpO2/motion bant sınırları |
| **Kişiselleştirme seviyesi** | `cold_start → learning → calibrated → mature` (gözlem ve geri bildirim sayısına göre) |
| **Kısa vadeli trend** | Son N paketten HR rising / SpO2 falling gibi tehlikeli örüntü tespiti |
| **Geri bildirim hafızası** | Yanlış alarm geçmişine göre duyarlılık ayarı; onaylı risk baskısı yükseltme |
| **Safety override** | Kritik SpO2 düşüşlerinde hiçbir düşürücü etki uygulanmaz |

---

## 2. Neden Basit Kural Tabanlı Değil?

| Kural tabanlı (önceki) | Kişiselleştirilmiş (yeni) |
|---|---|
| `HR > 100 → uyarı` | Kullanıcının tipik bandı `[58, 88]` ise `HR > 88` zaten sapma sayılır |
| Tüm kullanıcılar aynı eşiği kullanır | Her kullanıcı için ayrı bant hesaplanır |
| Geri bildirim hiç kullanılmaz | Yanlış alarm oranı `> 0.5` → uyarı hassasiyeti azaltılır |
| Trend görülmez | HR rising + SpO2 falling birlikte → +0.08 risk eklenir |
| Kalibre olmadan tam bonus verilmez | cold_start sınırı `0.05`, calibrated sınırı `0.20` |

---

## 3. Eklenen Veri Tabanı Modelleri

### `PersonalHealthProfile` (`personal_health_profiles`)
Her kullanıcı için bir satır. Kişisel tipik aralıkları, kişiselleştirme seviyesini ve toplam gözlem geçmişini saklar.

**Kritik alanlar:**
- `personalization_level`: `cold_start | learning | calibrated | mature`
- `typical_hr_min/max`, `typical_spo2_min/max`, `typical_motion_max`: EMA ile güncellenen bant uçları
- `false_alarm_count`, `confirmed_risk_count`, `sensor_error_count`, `total_feedback_count`

### `PersonalRiskMemory` (`personal_risk_memories`)
Her kayda değer risk olayını (uyarı girişi, kullanıcı onayı, yanlış alarm bildirimi) saatlik sırayla saklar.  
ML/retrieval sonuçları hiçbir zaman bu tabloya yazılmaz.

### `PersonalTrendSnapshot` (`personal_trend_snapshots`)
Belirli aralıklarda kaydedilen `hr_trend / spo2_trend / motion_trend / quality_trend / risk_trend` ve `trend_confidence` değerlerini tutar.

---

## 4. Eklenen Servis: `adaptive_personalization_service.py`

### Saf (Stateless) Fonksiyonlar

| Fonksiyon | Giriş | Çıkış |
|---|---|---|
| `_get_personalization_level(samples, fb)` | Gözlem ve geri bildirim sayısı | Seviye string |
| `_max_bonus_for_level(level)` | Seviye | Config'den max bonus |
| `compute_contextual_deviation(profile, baseline, hr, spo2, motion, ...)` | Mevcut paket + profil | `deviation_bonus` (seviyeyle sınırlandırılmış) |
| `compute_trend_from_snapshots(recent_statuses)` | Son N paket listesi | Trend string'leri + confidence |
| `compute_trend_adjustment(trend_info, quality_confidence)` | Trend sinyali | Risk delta `∈ [-trend_max, +trend_max]` |
| `compute_feedback_adjustment(profile, risk_score, severity, safety_override)` | Profil + bağlam | Risk delta |
| `compute_personalized_risk(...)` | Tüm bileşenler | Tam açıklanabilir risk breakdown dict |

### `AdaptivePersonalizationService` Sınıfı (Async, Fail-open)

| Metot | Açıklama |
|---|---|
| `get_or_create_profile(repos, user_id)` | DB'den profil getirir veya oluşturur |
| `update_profile_from_packet(...)` | EMA ile tipik aralıkları günceller; `personalization_level` yeniden hesaplar |
| `record_risk_memory(...)` | Risk olayını kaydeder; profil sayaçlarını günceller |
| `_update_profile_counters(...)` | Olay türüne göre `false_alarm_count`, `confirmed_risk_count` vb. artırır |
| `save_trend_snapshot(...)` | Trend durumunu DB'e yazar |
| `get_personalization_summary(...)` | Özetlenmiş profil ve trend bilgisi döndürür |

**Fail-open prensibi:** Her metot `try/except` ile sarılmıştır; herhangi bir hata ingestion akışını kesmez.

---

## 5. Kişiselleştirme Seviyeleri

```
cold_start  (<30 örnek)   → max bonus: 0.05  — minimal etki, çok az veri
learning    (30-299)       → max bonus: 0.10  — orta etki, veri birikim aşaması
calibrated  (≥300 örnek)  → max bonus: 0.20  — tam etki, model güvenilir
mature      (≥300 + ≥10 geri bildirim) → max bonus: 0.20  — en güvenilir profil
```

---

## 6. Trend Mantığı

`compute_trend_from_snapshots()` son N paketten HR/SpO2/motion/quality/risk için trend sınıflandırır:
- `delta / spread < 0.25` → `stable`
- Aksi hâlde `rising` veya `falling`

`compute_trend_adjustment()` risk delta üretir:
```
HR rising + SpO2 falling → +0.08
HR rising only            → +0.03
SpO2 falling only         → +0.05
motion rising             → +0.02
```
Tüm değerler `trend_confidence` ile çarpılır; `confidence < 0.2` → etki sıfır.  
Sonuç `[-TREND_MAX_BONUS, +TREND_MAX_BONUS]` aralığında sınırlandırılır.

---

## 7. Feedback Mantığı

`compute_feedback_adjustment()`:
- `false_alarm_rate > 0.5` ve `severity == "warning"` → negatif küçük düzeltme  
  (kritik seviye ASLA bastırılmaz)
- `confirmed_risk_count >= 3` ve `severity ∈ {watch, warning, critical}` → pozitif küçük artış  
- `sensor_error_count > 5` → küçük negatif kalite etkisi  
- `safety_override=True` → negatif düzeltmeler iptal edilir

---

## 8. Risk Breakdown (compute_personalized_risk)

Fonksiyonun döndürdüğü dict:

```python
{
    "global_risk_score": 0.4500,         # ham heuristik skor
    "baseline_final_risk": 0.4700,       # baseline_service sonucu
    "baseline_deviation_score": 0.0800,  # kişisel tipik banttan sapma
    "trend_adjustment": 0.0560,          # trend sinyali etkisi
    "quality_adjustment": 0.0000,        # düşük kalite zayıflatması
    "feedback_adjustment": -0.0120,      # geri bildirim geçmişi etkisi
    "final_personalized_risk": 0.5140,   # final skor (0-1 sınırlı)
    "personalization_level": "calibrated",
    "confidence": 0.950,
    "safety_override": False
}
```

**Kritik Güvence:** `final_personalized_risk` hiçbir zaman ML çıktısından veya retrieval sonucundan etkilenmez.

---

## 9. Yeni Endpointler

| Endpoint | Metot | Açıklama |
|---|---|---|
| `/personalization/profile/{user_id}` | GET | `PersonalHealthProfileResponse` |
| `/personalization/summary/{user_id}` | GET | `PersonalizationSummaryResponse` |
| `/personalization/trends/{user_id}` | GET | `PersonalTrendSnapshotResponse` (son snapshot) |
| `/personalization/memory/{user_id}` | GET | `List[PersonalRiskMemoryResponse]` |

Tüm endpointler JWT kimlik doğrulaması gerektirir.

---

## 10. Değiştirilen / Eklenen Dosyalar

### Değiştirilen
| Dosya | Değişiklik |
|---|---|
| `backend/models.py` | +3 ORM model (PersonalHealthProfile, PersonalRiskMemory, PersonalTrendSnapshot) |
| `backend/schemas.py` | +4 Pydantic şema; `DevicePacketResponse` + `personalization_result` alanı |
| `backend/repositories/base.py` | +`AbstractPersonalizationRepo` |
| `backend/repositories/sqlite/repos.py` | +`SqlitePersonalizationRepo` + 3 yardımcı fonksiyon |
| `backend/repositories/sqlite/__init__.py` | +`SqlitePersonalizationRepo` import |
| `backend/repositories/factory.py` | `RepoSet` + 3 builder güncellendi |
| `backend/config.py` | +6 `PERSONALIZATION_*` ayar |
| `backend/routers/ingestion_router.py` | Part 5B bloğu eklendi; `DevicePacketResponse` güncellendi |
| `backend/main.py` | +`personalization_router` import ve `include_router` |
| `backend/_smoke_api.py` | +3 smoke test (18-20) |

### Eklenen
| Dosya | Açıklama |
|---|---|
| `backend/services/adaptive_personalization_service.py` | Ana servis ve saf fonksiyonlar |
| `backend/routers/personalization_router.py` | 4 REST endpoint |
| `backend/tests/module7/test_23_adaptive_personalization.py` | 33 test |

---

## 11. Test Sonuçları

```
backend/tests/module7/test_23_adaptive_personalization.py

TestColdStartProfile        (3/3)   ✅
TestCalibratedProfile       (3/3)   ✅
TestTrendAnalysis           (5/5)   ✅
TestFeedbackAdjustment      (5/5)   ✅
TestRiskBreakdown           (5/5)   ✅
TestPersonalizationRepo     (5/5)   ✅
TestAdaptivePersonalizationService (5/5) ✅
TestConfig                  (2/2)   ✅

TOPLAM: 33/33 PASSED — 0 FAILED — 0 ERROR
```

---

## 12. Kalan Riskler / Gelecek İyileştirmeler

| Risk | Açıklama | Önlem |
|---|---|---|
| EMA cold-start yavaşlığı | İlk 30 pakette tipik band hâlâ geniş | cold_start max bonus = 0.05 ile sınırlandırıldı |
| Trend penceresi MVP | Şu an ingestion_router canlı pencere geçmişi trend hesabına aktarılmıyor | `live_window_buffer` entegrasyonu gelecek iterasyonda |
| Firebase desteği | `personalization=None` — Firebase modunda endpointler 503 döner | Firebase implementasyonu ayrı iterasyonda |
| Trend snapshot sıklığı | Her pakt için kayıt → büyük hacim | Gelecekte batch/downsample yapılabilir |

---

## 13. Verdict

**Part 5B tamamlandı.**

- ✅ Kişiselleştirme artık kural tabanlı DEĞİL — veri odaklı, adaptif ve açıklanabilir
- ✅ Trend sinyalleri (HR rising + SpO2 falling) kullanılıyor
- ✅ Geri bildirim hafızası (false_alarm, confirmed_risk) kullanılıyor
- ✅ `final_risk_score` ML/retrieval'dan ETKİLENMEYEN — tamamen heuristik + kişisel profil
- ✅ `UserBaseline` silinmedi — üstüne yeni katman eklendi
- ✅ Mevcut 22 test grubundan geçen hiçbir test bozulmadı
- ✅ 33/33 yeni test geçti
- ✅ Rapor: `docs/healthalert_part5b_adaptive_personalization_report.md`
