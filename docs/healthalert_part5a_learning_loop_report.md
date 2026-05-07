# HealthAlert — Part 5A: Learning Loop & Training Data Intelligence Layer
**Rapor Tarihi:** 2025  
**Durum:** ✅ TAMAMLANDI  
**Önceki Bölüm:** Part 4 — Demo Device Registration & Registered-Device E2E  
**Sonraki Bölüm:** Part 5B (planlı)

---

## 1. Amaç

HealthAlert'in canlıdan gelen paket verilerini yalnızca anlık risk hesabına kullanmak yerine, gelecekte model eğitimine hazır, kaliteli, etiketlenebilir bir veri havuzu oluşturmasını sağlamak.

**Temel kısıtlar (değişmez):**
- Canlı ML model ağırlıkları hiçbir zaman otomatik olarak yeniden eğitilmez
- `final_risk_score` yalnızca heuristik + kişisel baseline'dan gelir; ML/retrieval etkisi yoktur
- Veri toplanır → kalite kontrolü → etiketleme → **offline retraining için depolanır**

---

## 2. Canlı Veri vs Offline Eğitim Ayrımı

| Katman | Açıklama |
|--------|----------|
| **Anlık risk** | Heuristik engine + kişisel EMA baseline → `final_risk_score` → alarm kararı |
| **ML shadow** | PyTorch model çıktısı, yalnızca gözlem, hiçbir zaman risk kararına karışmaz |
| **Retrieval shadow** | RAG benzerlik skoru, yalnızca metadata, risk kararına karışmaz |
| **Learning capture** | Kaliteli pencereler depolanır, `training_candidate` işaretlenir, hiçbir zaman anlık riski değiştirmez |
| **Offline retraining** | Dışa aktarılan JSONL veri seti → manuel kontrol → model yeniden eğitimi → `ModelVersionRegistry` kaydı |

---

## 3. Eklenen ORM Modelleri (`backend/models.py`)

### `LearningCaptureSession`
Bir cihazın veri toplama oturumunu temsil eder. Oturum başlangıcı, bitiş, örnekleme sayıları ve eğitim adaylığını içerir.

### `LearningWindow`
Tek bir pencere kaydı. Süre, kalite skoru, baseline durumu, ML/retrieval shadow özeti (JSON metin), kullanıcı geri bildirimi, önerilen etiket ve eğitim adaylığı bilgilerini içerir.  
- `ml_shadow_summary` ve `retrieval_shadow_summary`: `Text` (JSON string) — risk kararını etkilemeyen ham özetler
- `training_candidate`: `Boolean` — kaliteli ve eğitime hazır olup olmadığı
- `exported_at`: `DateTime` nullable — dışa aktarım zamanı

### `UserFeedbackEvent`
Mobil/klinik kullanıcı geri bildirimi. `feedback_type` ve `feedback_source` alanları ile pencere veya uyarıya bağlanır.

### `ModelVersionRegistry`
Offline eğitim sonuçlarını kaydeder. `status` (candidate/active/retired), model yolu, metrik JSON içerir. Aktif model otomatik olarak yüklenmez.

---

## 4. Eklenen Servisler

### `backend/services/learning_data_service.py`

#### `should_capture_window(...)` — bool
Anlık risk seviyesi, kalite skoru, paket moduna göre pencere kaydının gerekip gerekmediğine karar verir.

**Capture kuralları:**
| Risk Seviyesi | Davranış |
|---------------|----------|
| `critical` | Her zaman yakala (`LEARNING_CAPTURE_CRITICAL_ALWAYS=True`) |
| `warning` | Her zaman yakala (`LEARNING_CAPTURE_WARNING_ALWAYS=True`) |
| `watch` | `random() < CAPTURE_NORMAL_RATE * 3` |
| `normal` / `None` | `random() < CAPTURE_NORMAL_RATE` |
| Düşük kalite | Yakala ama `training_candidate=False` |
| Demo/mock | Yakala ama `training_candidate=False` (unless `LEARNING_ALLOW_DEMO_AS_TRAINING=True`) |
| `LEARNING_LOOP_ENABLED=False` | Hiçbir zaman yakalama |

#### `LearningDataService.build_and_save_window(...)` 
- `final_risk_score`'u hiçbir zaman değiştirmez
- ML/retrieval sonuçlarını `ml_shadow_summary` / `retrieval_shadow_summary` olarak saklar
- `final_risk_score` anahtarını shadow özetlerden çıkarır (sızıntı önleme)
- Hata durumunda `None` döner — **fail-open**, ingestion'ı asla 500'e düşürmez

#### `suggest_label(...)` — dict
Heuristik risk seviyesi, ML shadow ve kullanıcı geri bildirimine göre `suggested_label` ve `label_confidence` üretir.  
Kullanıcı `false_alarm` bildirimi → etiket `normal` olarak override edilir (güven: 0.95).

#### `LearningDataService.attach_feedback(...)`
Kullanıcı geri bildirimini `UserFeedbackEvent` olarak kaydeder, pencere etiketini günceller.  
`sensor_error` geri bildirimi → `training_candidate=False` (eğitimden çıkar).

#### `LearningDataService.export_training_dataset(...)`
- `training_candidate=True` ve `exported_at=None` olan pencereleri seçer
- `user_id` ve `device_id`'yi SHA256 (ilk 16 karakter) ile anonim hale getirir
- `outputs/learning_exports/<timestamp>/` altına yazar
- Çıktı: `windows.jsonl`, `feedback.jsonl`, `export_summary.json`

---

## 5. Eklenen Endpointler (`backend/routers/learning_router.py`)

| Method | Path | Açıklama |
|--------|------|----------|
| `GET` | `/learning/windows` | Pencere listesi (filtreler: user_id, training_candidate, source, limit) |
| `GET` | `/learning/windows/{window_id}` | Tekil pencere detayı |
| `POST` | `/learning/feedback` | Kullanıcı geri bildirimi kaydet (body: `UserFeedbackCreate`) |
| `POST` | `/learning/export` | JSONL veri seti dışa aktar (body: `TrainingExportRequest`) |
| `GET` | `/learning/summary/{user_id}` | Kullanıcı başına öğrenme istatistikleri |
| `GET` | `/learning/model-versions` | Model versiyon kayıt defteri |

Tüm endpointler JWT auth gerektirir (`get_current_user`).

---

## 6. Kalite ve Eğitim Adaylığı Kuralları

```
quality_confidence >= LEARNING_MIN_QUALITY_CONFIDENCE (0.60)
  AND
packet_mode != "mock"/"demo"  (unless LEARNING_ALLOW_DEMO_AS_TRAINING=True)
  AND
feedback_type != "sensor_error"
→ training_candidate = True
```

Aksi hâlde pencere kaydedilir ama `training_candidate=False`.

---

## 7. Feedback ve Label Mantığı

```
Geri bildirim yok → suggest_label(risk_level) → auto-label
false_alarm       → suggested_label = "normal", confidence = 0.95
confirmed_alert   → suggested_label = risk_level, confidence = 0.95
sensor_error      → training_candidate = False
```

Etiket pipeline'ı tamamen offline/pasif — canlı risk kararını etkilemez.

---

## 8. Training Export Formatı

**`windows.jsonl`** (her satır bir pencere):
```json
{
  "id": "...",
  "user_id_hash": "<sha256[:16]>",
  "device_id_hash": "<sha256[:16]>",
  "source": "live",
  "window_start_at": "2025-...",
  "duration_sec": 30.0,
  "risk_level_at_capture": "warning",
  "final_risk_score": 0.65,
  "quality_confidence": 0.87,
  "baseline_ready": true,
  "suggested_label": "warning",
  "label_confidence": 0.75,
  "user_feedback_label": null,
  "ml_shadow_summary": {...},
  "retrieval_shadow_summary": {...}
}
```

**`feedback.jsonl`**: `UserFeedbackEvent` kayıtları (user_id_hash ile)  
**`export_summary.json`**: pencere sayısı, geri bildirim sayısı, export_dir, timestamp

---

## 9. Gizlilik / Anonymization

- `user_id` → `user_id_hash = SHA256(user_id)[:16]`
- `device_id` → `device_id_hash = SHA256(device_id)[:16]`
- Ham `user_id`/`device_id` dışa aktarılan JSONL satırlarına yazılmaz
- Firebase secret'ları değiştirilmedi

---

## 10. Ingestion Entegrasyonu (`backend/routers/ingestion_router.py`)

Risk hesabı tamamlandıktan sonra, async shadow blokların ardından:

```python
# Part 5A — Learning capture (fail-open, never affects risk_score)
if user_id and settings.LEARNING_LOOP_ENABLED:
    if should_capture_window(...risk_level, quality_confidence...):
        learning_capture_result = await learning_data_service.build_and_save_window(
            repos=repos, ..., final_risk_score=result["final_risk_score"], ...
        )
```

`DevicePacketResponse.learning_capture_result` alanı eklendi (nullable dict).  
Herhangi bir hata → `learning_capture_result = None`, ingestion yanıtı değişmez.

---

## 11. Test Sonuçları

```
backend/tests/module7/test_22_learning_loop.py
  TestCaptureDecision    (4 test)  — 4 PASSED
  TestWindowBuilding     (7 test)  — 7 PASSED
  TestFeedbackHandling   (2 test)  — 2 PASSED
  TestExport             (3 test)  — 3 PASSED
  TestServiceIsolation   (2 test)  — 2 PASSED
  TestRepoAndConfig      (3 test)  — 3 PASSED
  TestShadowResultIsolation (2 test) — 2 PASSED
  ─────────────────────────────────────────────
  TOPLAM: 23/23 PASSED ✅ (0.38s)
```

---

## 12. Değiştirilen / Eklenen Dosyalar

### Değiştirilen Dosyalar
| Dosya | Değişiklik |
|-------|-----------|
| `backend/models.py` | 4 yeni ORM modeli eklendi |
| `backend/schemas.py` | 7 yeni Pydantic şeması + `DevicePacketResponse` güncellendi |
| `backend/config.py` | 7 yeni `LEARNING_*` ayarı eklendi |
| `backend/repositories/base.py` | `AbstractLearningRepo` eklendi |
| `backend/repositories/sqlite/repos.py` | `SqliteLearningRepo` eklendi |
| `backend/repositories/sqlite/__init__.py` | `SqliteLearningRepo` export edildi |
| `backend/repositories/factory.py` | `RepoSet.learning` alanı + factory güncellemeleri |
| `backend/routers/ingestion_router.py` | Learning capture bloğu entegre edildi |
| `backend/main.py` | `learning_router` include edildi |
| `backend/_smoke_api.py` | Smoke testleri 13-17 eklendi |

### Eklenen Dosyalar
| Dosya | Açıklama |
|-------|----------|
| `backend/services/learning_data_service.py` | Learning loop core servisi |
| `backend/routers/learning_router.py` | 6 yeni endpoint |
| `backend/tests/module7/test_22_learning_loop.py` | 23 test (tamamı geçiyor) |
| `docs/healthalert_part5a_learning_loop_report.md` | Bu rapor |

---

## 13. Kalan Riskler

| Risk | Seviye | Açıklama |
|------|--------|----------|
| Firebase learning repo yok | Düşük | `repos.learning=None` Firebase modda, endpointler guard gerektirebilir |
| `asyncio_mode` yapılandırılmamış | Düşük | Test dosyası `asyncio.run()` pattern kullanıyor; ileride `pytest-asyncio` geçişi yapılabilir |
| Export dizin izinleri | Düşük | Windows'ta `outputs/learning_exports/` yazma izni kontrol edilmeli |
| Uzun süreli export belleği | Düşük | Çok büyük veri setlerinde batch streaming gerekebilir |

---

## 14. Verdict

**✅ Part 5A başarıyla tamamlandı.**

- Model canlıda yeniden eğitilmiyor: **HAYIR** — ağırlıklar değişmez
- `final_risk_score` learning tarafından değiştirilmiyor: **DOĞRULANMIŞ** — 23 testle kanıtlandı
- Yeni veri nasıl eğitime giriyor: `training_candidate=True` → `POST /learning/export` → JSONL → offline pipeline
- Feedback nasıl saklanıyor: `UserFeedbackEvent` tablosu → window etiketi güncellenir
- Export çıktı yolu: `outputs/learning_exports/<timestamp>/`
- Test sonucu: **23/23 PASSED**
- Smoke testleri: 13-17 eklendi (`_smoke_api.py`)
