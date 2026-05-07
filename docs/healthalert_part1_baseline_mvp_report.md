# HealthAlert — Part 1: Personal Baseline MVP + Quality-aware Heuristic Risk

**Tarih:** 29 Nisan 2026  
**Durum:** Tamamlandı  
**Kapsam:** Kontrollü Mimari Geliştirme — Görev 1

---

## 1. Amaç

Mevcut `/ingest/device-packet` heuristik risk akışını bozmadan, kullanıcıya özel kişisel baseline ve PPG kalite farkındalığı eklemek. Bu görev ML inference, RAG, büyük Flutter değişikliği veya firmware transport değişikliği içermemektedir.

---

## 2. Önceki Canlı Risk Akışı

```
packet validation
→ duplicate check
→ DevicePacketLog
→ motion_score  (_compute_motion_score)
→ heuristic risk_score  (_compute_risk_score)
→ LiveStatus upsert  (risk_score = global heuristik)
→ severity  (_risk_to_severity — sabit eşikler)
→ AnomalyEvent / AlertEvent / HistoryItem / NotificationItem
```

---

## 3. Yeni Baseline-Aware Risk Akışı

```
packet validation
→ duplicate check
→ DevicePacketLog
→ motion_score
→ global_risk_score  (heuristik — değişmedi)
→ [BASELINE_ENABLED=True]
    → AppSettings.alert_sensitivity çekme
    → compute_quality_confidence()
    → update_user_baseline()  (EMA, güvenilirlik kapısı)
    → compute_personal_deviation()
    → apply_baseline_adjustment()  → final_risk_score
→ LiveStatus upsert  (risk_score = final_risk_score)
→ severity  (_risk_to_severity — alert_sensitivity eşik kayması)
→ AnomalyEvent / AlertEvent / HistoryItem / NotificationItem
→ DevicePacketResponse  (+ opsiyonel risk_breakdown)
```

`BASELINE_ENABLED=False` ise akış tamamen eski gibi çalışır.

---

## 4. Değiştirilen Dosyalar

| Dosya | Değişiklik |
|-------|-----------|
| `backend/config.py` | `BASELINE_ENABLED`, `BASELINE_MIN_SAMPLES`, `BASELINE_EMA_ALPHA`, `BASELINE_MIN_SIGNAL_QUALITY`, `BASELINE_ALLOW_MOCK_DATA`, `BASELINE_PERSONAL_BONUS_MAX` eklendi |
| `backend/models.py` | `UserBaseline` ORM modeli eklendi; `AppSettings.alert_sensitivity` alanı eklendi |
| `backend/schemas.py` | `SettingsResponse` ve `SettingsUpdate`'e `alert_sensitivity` alanı eklendi; `DevicePacketResponse`'a `risk_breakdown` opsiyonel alanı eklendi; `UserBaselineResponse`, `BaselineStatusResponse`, `RiskBreakdownResponse` eklendi |
| `backend/repositories/base.py` | `AbstractBaselineRepo` soyut sınıfı eklendi |
| `backend/repositories/sqlite/repos.py` | `UserBaseline` import, `AbstractBaselineRepo` import, `_baseline_to_dict` helper, `SqliteBaselineRepo` sınıfı eklendi; `_settings_to_dict` içine `alert_sensitivity` eklendi |
| `backend/repositories/sqlite/__init__.py` | `SqliteBaselineRepo` export'u eklendi |
| `backend/repositories/firebase/repos.py` | `AbstractBaselineRepo` import, `FirebaseBaselineRepo` sınıfı eklendi |
| `backend/repositories/firebase/__init__.py` | `FirebaseBaselineRepo` export'u eklendi |
| `backend/repositories/factory.py` | `RepoSet.baselines` alanı eklendi; `_build_sqlite`, `_build_firebase`, `_build_hybrid` güncellendi |
| `backend/routers/ingestion_router.py` | `baseline_service` importları eklendi; `_risk_to_severity` `sensitivity_offset` parametresi aldı; ana handler baseline akışı entegre edildi |
| `backend/routers/settings_router.py` | `alert_sensitivity` güncelleme desteği eklendi |
| `backend/tests/module7/test_04_factory.py` | `TestRepoSetFields` içinde beklenen field seti `baselines` içerecek şekilde güncellendi |

---

## 5. Eklenen Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `backend/services/baseline_service.py` | Baseline mantığının tamamı: güvenilirlik kapısı, EMA güncelleme, personal deviation, quality confidence, risk adjustment |
| `backend/tests/module7/test_16_baseline_mvp.py` | 36 test senaryosu |
| `docs/healthalert_part1_baseline_mvp_report.md` | Bu rapor |

---

## 6. UserBaseline Tablo Açıklaması

**Tablo adı:** `user_baselines`

| Alan | Tip | Varsayılan | Açıklama |
|------|-----|-----------|----------|
| `id` | str (UUID) | uuid4() | Primary key |
| `user_id` | str (FK → users.id) | — | Unique, indexed |
| `hr_mean` | float | 72.0 | EMA ile güncellenen ortalama kalp hızı |
| `hr_std` | float | 10.0 | EMA variance kökü; min clamp 5.0 |
| `spo2_mean` | float | 98.0 | EMA ile güncellenen ortalama SpO2 |
| `spo2_std` | float | 1.5 | EMA variance kökü; min clamp 1.0 |
| `motion_mean` | float | 0.10 | EMA ile güncellenen ortalama hareket skoru |
| `motion_std` | float | 0.08 | EMA variance kökü; min clamp 0.05 |
| `ppg_quality_mean` | float | 0.85 | EMA ile güncellenen sinyal kalitesi ortalaması |
| `sample_count` | int | 0 | Dahil edilen güvenilir paket sayısı |
| `is_ready` | bool | False | `sample_count >= BASELINE_MIN_SAMPLES` (varsayılan 300) |
| `created_at` | datetime | utcnow | İlk oluşturulma zamanı |
| `updated_at` | datetime | utcnow | Son güncelleme zamanı |
| `last_updated` | datetime (nullable) | None | Son başarılı baseline update zamanı |

---

## 7. Repository / Factory Entegrasyonu

### AbstractBaselineRepo
`backend/repositories/base.py` içinde dört metot tanımlandı:
- `get_by_user_id(user_id)` → mevcut baseline dict veya None
- `create_for_user(user_id)` → varsayılan değerlerle yeni baseline
- `get_or_create(user_id)` → varsa getir, yoksa oluştur
- `update_values(user_id, values)` → partial update

### SqliteBaselineRepo
`_baseline_to_dict` helper fonksiyonu ile ORM ↔ dict dönüşümü yapılır. `get_or_create` idempotent'tir — duplicate oluşturulmaz.

### FirebaseBaselineRepo
Firestore koleksiyonu: `user_baselines`. `user_id` alanı üzerinden `FieldFilter` kullanılır.

### Hybrid Mode Kararı
Hybrid modda `baselines` alanı **SQLite primary** olarak çalışır (`_build_hybrid` içinde `baselines=sq.baselines`). Firestore'a baseline yazımı bu görevde eklenmemiştir.

**Gerekçe:** Baseline, yüksek-frekanslı (her paket) write işlemi gerektirir. Firestore'a her paket için async write denemesi, Firestore gecikmeleri durumunda ingestion akışını yavaşlatabilir. Hybrid modda baseline'ın SQLite'ta kaldığı kabul edilebilir çünkü:
- Baseline yalnızca risk kalibrasyon amaçlıdır, kritik klinik veri değildir.
- Firestore yazımı Part 2'de incremental olarak eklenebilir (arka plan task + fallback).

---

## 8. Baseline Güncelleme Kuralları

### Dahil Edilmeyecek Paketler
Aşağıdaki koşullardan herhangi biri sağlanırsa paket baseline'a dahil edilmez:
- `BASELINE_ENABLED = False`
- `mode == "mock"` ve `BASELINE_ALLOW_MOCK_DATA == False`
- `finger_detected == False`
- `hr_valid == False`
- `spo2_valid == False`
- `ppg_ok == False`
- `signal_quality < BASELINE_MIN_SIGNAL_QUALITY` (0.50)
- `HR < 35` veya `HR > 190`
- `SpO2 < 70` veya `SpO2 > 100`
- `global_risk_score >= RISK_WARNING_THRESHOLD` (0.55)

Not: `imu_ok == False` ise yalnızca motion baseline güncellenmez; HR/SpO2/quality baseline güncellemesi devam eder.

### EMA Güncelleme

```
alpha = BASELINE_EMA_ALPHA  # 0.02

new_mean = alpha * new_value + (1 - alpha) * old_mean
new_var  = (1 - alpha) * (old_var + alpha * (new_value - old_mean)^2)
new_std  = max(clamp_min, sqrt(new_var))
```

Clamp değerleri: `hr_std ≥ 5.0`, `spo2_std ≥ 1.0`, `motion_std ≥ 0.05`

### is_ready
`sample_count >= BASELINE_MIN_SAMPLES (300)` olduğunda `is_ready = True` set edilir.

---

## 9. Mock Verinin Baseline'a Dahil Edilip Edilmediği

**Varsayılan:** Mock verisi baseline'a dahil edilmez (`BASELINE_ALLOW_MOCK_DATA = False`).

Demo/test ortamları için `BASELINE_ALLOW_MOCK_DATA=True` env değişkeni set edilerek simülasyon paketlerinin de baseline'a katkı yapması sağlanabilir.

Bu karar `.env` dosyası ile kontrol edilir, kod değişikliği gerekmez.

---

## 10. Quality Confidence Mantığı

`compute_quality_confidence()` fonksiyonu 0–1 arası bir `quality_confidence` skoru üretir:

```
base = signal_quality
if not finger_detected:  base *= 0.0
if not ppg_ok:           base *= 0.5
if not hr_valid:         base *= 0.7
if not spo2_valid:       base *= 0.8
score = clamp(base, 0, 1)
```

**Kullanımı:**
- `quality_confidence < 0.5` ise `personal_deviation_bonus` sıfırlanır (global risk korunur).
- `quality_warning` metni üretilir; bu `risk_breakdown` içinde response olarak döndürülür.
- **Safety override:** SpO2 < 88 ve geçerliyse `safety_override = True`; bu durumda düşük kalite olsa bile deviation bonus uygulanır (SpO2 acil güvenlik sinyali bastırılmaz).

---

## 11. AppSettings.alert_sensitivity Entegrasyonu

### Model Değişikliği
`AppSettings.alert_sensitivity` alanı `String(20)` olarak eklendi, varsayılan `"normal"`.

### Geçerli Değerler
`"high"`, `"normal"`, `"low"`

### Severity Eşik Etkisi
`alert_sensitivity` ingestion sırasında `_risk_to_severity(risk_score, sensitivity_offset)` çağrısına iletilir:

| Sensitivity | offset | Kritik Eşik | Warning Eşik | Watch Eşik |
|-------------|--------|-------------|--------------|------------|
| `high`      | -0.10  | 0.65        | 0.45         | 0.20       |
| `normal`    | 0.00   | 0.75        | 0.55         | 0.30       |
| `low`       | +0.10  | 0.85        | 0.65         | 0.40       |

**Önemli:** `alert_sensitivity` `final_risk_score`'u **değiştirmez**. `LiveStatus.risk_score` her zaman objektif `global_risk + personal_deviation` değerini taşır. Sensitivity yalnızca severity threshold hesaplamasını etkiler.

### Sınırlama
`alert_sensitivity` alanı yeni bir ORM sütunudur. Mevcut veritabanlarında bu sütun bulunmaz. `init_db()` (`create_all`) bu sütunu yeni tablolarda otomatik oluşturur, ancak **mevcut veritabanı için migration gereklidir**.

Geçici çözüm: `_settings_to_dict` içinde `getattr(s, "alert_sensitivity", "normal")` ile `AttributeError` güvenli erişim sağlanmıştır.

---

## 12. Geriye Uyumluluk

| Özellik | Durum |
|---------|-------|
| `/ingest/device-packet` endpoint contract | Korundu |
| `DevicePacketResponse` eski alanlar | Korundu |
| `risk_breakdown` | Opsiyonel — eski istemciler görmezden gelebilir |
| `LiveStatus.risk_score` | Var olan tek alan kullanılıyor |
| `AnomalyEvent` / `AlertEvent` / `HistoryItem` / `NotificationItem` zinciri | Bozulmadı |
| `SettingsResponse.alert_sensitivity` | Opsiyonel, default `"normal"` — eski istemciler ekstra alanı yok sayar |
| Simulation akışı | `BASELINE_ALLOW_MOCK_DATA=False` → simülasyon paketleri baseline'ı etkilemez |
| host_bridge araçları | Paket şeması değişmedi |
| Firebase secret dosyaları | Dokunulmadı |
| LLM / chatbot tarafı | Dokunulmadı |
| Firmware | Dokunulmadı |
| DATA_MODE sqlite/firebase/hybrid mantığı | Korundu |

---

## 13. Demo / Simulation Etkisi

- Simülasyon paketleri `mode="mock"` ile gelir.
- `BASELINE_ALLOW_MOCK_DATA=False` (varsayılan) → baseline güncellenmez.
- Demo akışı heuristik global risk ile çalışmaya devam eder.
- `is_ready=False` iken `personal_deviation_score=0`, yani `final_risk_score == global_risk_score`.
- Simülasyon senaryolarının davranışı değişmemiştir.

---

## 14. Test Edilen Senaryolar

**Dosya:** `backend/tests/module7/test_16_baseline_mvp.py`  
**Sonuç:** 35 PASSED, 1 SKIPPED (Firebase SDK yüklü değil — beklenen)

| Test | Senaryo |
|------|---------|
| `test_baseline_get_or_create` | Yeni kullanıcı için baseline oluşturulur |
| `test_baseline_get_or_create_idempotent` | İkinci çağrı yeni satır oluşturmaz |
| `test_baseline_update_values` | Değerler doğru güncellenir |
| `test_reliable_normal` | Normal paket güvenilir sayılır |
| `test_unreliable_finger_not_detected` | finger_detected=False → güvenilmez |
| `test_unreliable_low_signal_quality` | signal_quality=0.40 → güvenilmez |
| `test_unreliable_hr_invalid` | hr_valid=False → güvenilmez |
| `test_unreliable_spo2_invalid` | spo2_valid=False → güvenilmez |
| `test_unreliable_ppg_not_ok` | ppg_ok=False → güvenilmez |
| `test_unreliable_mock_data_default` | mode=mock → güvenilmez (ALLOW=False) |
| `test_reliable_mock_data_when_allowed` | mode=mock → güvenilir (ALLOW=True) |
| `test_unreliable_high_risk` | global_risk >= 0.55 → güvenilmez |
| `test_unreliable_hr_out_of_range` | HR < 35 veya > 190 → güvenilmez |
| `test_unreliable_spo2_out_of_range` | SpO2 < 70 → güvenilmez |
| `test_update_baseline_increments_sample_count` | Güvenilir paket sample_count artırır |
| `test_update_baseline_not_incremented_on_low_quality` | Düşük kalite → sample_count değişmez |
| `test_update_baseline_not_incremented_finger_not_detected` | finger_detected=False → değişmez |
| `test_deviation_normal_range` | z ≤ 2 → bonus = 0 |
| `test_deviation_high_hr` | Yüksek HR → pozitif bonus |
| `test_deviation_low_spo2` | Düşük SpO2 → pozitif bonus |
| `test_deviation_bonus_capped` | Bonus BASELINE_PERSONAL_BONUS_MAX'ı geçmez |
| `test_quality_confidence_full` | Tam kalite → confidence = signal_quality |
| `test_quality_confidence_no_finger` | finger=False → confidence = 0 |
| `test_quality_confidence_safety_override_low_spo2` | SpO2 < 88 → safety_override=True |
| `test_apply_adjustment_baseline_not_ready` | is_ready=False → final = global |
| `test_apply_adjustment_baseline_ready_adds_bonus` | is_ready=True → final = global + bonus |
| `test_apply_adjustment_low_quality_no_bonus` | quality < 0.5 → bonus = 0 |
| `test_apply_adjustment_safety_override_passes_bonus` | safety_override=True → bonus uygulanır |
| `test_apply_adjustment_high_sensitivity_stored` | alert_sensitivity breakdown'da saklanır; risk_score değişmez |
| `test_packet_response_risk_breakdown_optional` | risk_breakdown=None → backward compat |
| `test_packet_response_with_risk_breakdown` | risk_breakdown dict döndürülebilir |
| `test_factory_sqlite_has_baselines_field` | SQLite RepoSet.baselines = SqliteBaselineRepo |
| `test_factory_firebase_has_baselines_field` | SKIPPED (google SDK yok) |
| `test_factory_hybrid_baselines_is_sqlite` | Hybrid RepoSet.baselines = SqliteBaselineRepo |
| `test_settings_response_has_alert_sensitivity` | SettingsResponse default "normal" |
| `test_settings_update_alert_sensitivity_field` | SettingsUpdate alert_sensitivity alanı var |

---

## 15. Çalıştırılan Komutlar ve Sonuçları

```powershell
# Test komutu
cd c:\project\HealthAlert\backend
python -m pytest tests/module7/test_16_baseline_mvp.py -v --tb=short
# Sonuç: 35 passed, 1 skipped

# Mevcut testlerin regresyon kontrolü
python -m pytest tests/module7/test_04_factory.py::TestRepoSetFields tests/module7/test_04_factory.py::TestFactorySqliteMode tests/module7/test_05_sqlite_repos.py -v --tb=short
# Sonuç: 21 passed (önceki geçen testlerin hepsi geçiyor)

# Import sağlığı
python -c "from routers.ingestion_router import router"
# Sonuç: başarılı, hata yok
```

**Pre-existing başarısız testler (bizim değişikliğimizden önce de başarısız):**
- `test_04_factory.py::TestFactoryFirebaseMode::test_firebase_mode_no_db_required` — `google` modülü yüklü değil
- `test_04_factory.py::TestFactoryHybridMode::test_hybrid_returns_hybrid_repos` — `google` modülü yüklü değil
- `test_08_backward_compat.py::test_config_loads_with_defaults` — `.env` dosyasında `DATA_MODE=hybrid` set edilmiş
- `test_08_backward_compat.py::test_app_has_expected_route_count` — `firestore_watcher.py` `google` modülü gerektiriyor

---

## 16. Bilinen Sınırlamalar

1. **DB Migration:** `user_baselines` tablosu ve `app_settings.alert_sensitivity` sütunu yeni. Mevcut SQLite dosyası varsa `init_db()` / `create_all` çalıştırmak veya manuel `ALTER TABLE` / `Alembic` migration gerekir.

2. **Hybrid Mode Baseline Firestore Yazımı:** Hybrid modda baseline yalnızca SQLite'a yazılır, Firestore'a yazılmaz. Bu bilinçli bir karar (bkz. Bölüm 7). Part 2'de background task ile eklenebilir.

3. **300 Paket Warm-up:** Baseline ilk 300 güvenilir ölçüme kadar `is_ready=False` kalır. Bu sürede `final_risk_score == global_risk_score` (personal deviation yoktur). Canlı deploy'da gerçek sensörle ~20 dakika (4s interval = 300 paket) warm-up gerekir.

4. **EMA Alpha Küçük Seçildi (0.02):** Kasıtlı. Ani spike'lar baseline'ı hızla değiştirmemeli. Bu değer `.env` ile `BASELINE_EMA_ALPHA` aracılığıyla ayarlanabilir.

5. **alert_sensitivity `getattr` Güvenli Erişim:** `_settings_to_dict` içinde `getattr(s, "alert_sensitivity", "normal")` kullanılmıştır; migration yapılmamış veritabanlarında `AttributeError` almamak için.

6. **Simulation Baseline:** `BASELINE_ALLOW_MOCK_DATA=False` nedeniyle demo/simülasyon çalıştırılırken baseline warm-up olmaz. Demo ortamlarında `BASELINE_ALLOW_MOCK_DATA=True` set edilmesi gerekir.

---

## 17. Part 2 için Hazırlık Notları

Bu görev aşağıdaki altyapıyı Part 2'ye hazır bırakmaktadır:

- **`UserBaseline` tablosu** mevcuttur; Part 2'de örneğin trend analizi veya ML özellik çıkarımı için kullanılabilir.
- **`is_ready` bayrağı:** Part 2, ML modeli için warm-up koşulu olarak kullanabilir.
- **`risk_breakdown` response alanı:** Mobile'da risk breakdown görselleştirmesi için kullanılabilir.
- **`quality_confidence`:** Part 2'de ML inference önceliklendirmesi için (kaliteli paketlere ML çalıştır, kalitesizlere çalıştırma) kullanılabilir.
- **`alert_sensitivity`:** Severity threshold değişikliği merkezileştirildi; Part 2'de per-user alert kanalı seçimi için genişletilebilir.
- **`AbstractBaselineRepo`:** Part 2'de zaman-serisi özeti (`get_recent_samples()`) metodu eklenerek ML feature store katmanı oluşturulabilir.
- **Firestore Baseline Sync:** Part 2'de hybrid modda background task + optimistic write ile Firestore baseline sync tamamlanabilir.
