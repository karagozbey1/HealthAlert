# HealthAlert — Part 1.1: Baseline MVP Runtime/Migration Stabilization

**Tarih:** 29 Nisan 2026  
**Durum:** Tamamlandı  
**Önceki Görev:** Part 1 — Personal Baseline MVP (docs/healthalert_part1_baseline_mvp_report.md)

---

## 1. Amaç

Part 1'in gerçek runtime'da, özellikle mevcut `healthalert.db` dosyası varken kırılmadığını garanti etmek. Bunu engelleyen sorunları tespit etmek, güvenli bir migration guard eklemek, konfigürasyon belgelendirmesini iyileştirmek ve tüm kritik endpoint'leri smoke test ile doğrulamak.

---

## 2. Part 1 Sonrası Tespit Edilen Runtime Riskleri

| # | Risk | Bileşen | Önem |
|---|------|---------|------|
| 1 | `user_baselines` tablosu eksik | SQLite DB | Yüksek — baseline_service çöker |
| 2 | `app_settings.alert_sensitivity` kolonu eksik | SQLite DB | Yüksek — her settings ve ingestion isteği çöker |
| 3 | `main.py` top-level `firestore_watcher` import | main.py | Orta — DATA_MODE=sqlite ile bile uvicorn başlamıyor |
| 4 | `risk_breakdown` UnboundLocalError | ingestion_router.py | Yüksek — kayıtsız cihazdan gelen paket 500 döndürür |
| 5 | passlib + bcrypt + Python 3.14 uyumsuzluğu | auth.py | Yüksek — login 500 döndürür |
| 6 | Baseline warm-up süresi belirsizliği | config.py | Düşük — operasyonel netlik |

---

## 3. Existing DB Migration Davranışı

### create_all() Davranışı
SQLAlchemy'nin `Base.metadata.create_all()`:
- **Mevcut olmayan tabloları** oluşturur ✅
- **Mevcut tablolara** yeni kolon **eklemez** ❌

### Önceki Durum
```
user_baselines       → YOK  (create_all ile oluşturulabilir)
app_settings         → VAR, alert_sensitivity kolonu YOK
```

### init_db() Çağrısından Sonra (schema guard ile)
```
user_baselines       → OLUŞTURULDU (create_all tarafından)
app_settings         → GÜNCELLENDI (schema guard ile ALTER TABLE)
```

---

## 4. user_baselines Tablosu Kontrolü

`create_all` bu tabloyu `UserBaseline` ORM modeli üzerinden otomatik oluşturur. Mevcut DB'de tablo yoksa, `init_db()` çağrısında SQLAlchemy `checkfirst=True` davranışı ile tablo oluşturulur.

**Sonuç:** İlave müdahale gerekmez — mevcut `create_all` yeterlidir.

---

## 5. app_settings.alert_sensitivity Kolon Kontrolü

SQLAlchemy **mevcut tablolara yeni kolon eklemez**. `app_settings` tablosu zaten vardı, dolayısıyla `create_all` sonrasında `alert_sensitivity` kolonu eklenmemiş olurdu.

**Sorun:** SQLAlchemy ORM `AppSettings` SELECT sorgusuna `alert_sensitivity` kolonunu dahil eder. Kolon DB'de yoksa:
```
sqlalchemy.exc.OperationalError: no such column: app_settings.alert_sensitivity
```

Bu hata settings endpoint'ini ve ingestion (baseline recovery path) endpoint'ini tamamen devre dışı bırakır.

---

## 6. Uygulanan Migration/Schema Guard Çözümü

### Değişen Dosya: `backend/database.py`

`init_db()` fonksiyonu genişletildi. `create_all` sonrasına idempotent bir DDL guard eklendi:

```python
def _apply_schema_guards(sync_conn) -> None:
    """Idempotent DDL guards for additive schema changes.

    SQLAlchemy's create_all creates missing *tables* but does NOT add missing
    *columns* to already-existing tables.  Each guard checks the current
    schema via PRAGMA before issuing an ALTER TABLE so the function is safe to
    run on every startup (fresh DB, upgraded DB, or already-current DB).
    """
    # Guard 1: app_settings.alert_sensitivity  (added in Part 1)
    rows = sync_conn.execute(text("PRAGMA table_info(app_settings)")).fetchall()
    existing_cols = {row[1] for row in rows}
    if "alert_sensitivity" not in existing_cols:
        sync_conn.execute(
            text(
                "ALTER TABLE app_settings"
                " ADD COLUMN alert_sensitivity VARCHAR(20) NOT NULL DEFAULT 'normal'"
            )
        )
        logger.info("Schema guard: added column app_settings.alert_sensitivity")

async def init_db() -> None:
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)    # tabloları oluştur
        await conn.run_sync(_apply_schema_guards)        # kolonları ekle
```

### Tasarım Prensipleri
- **Idempotent:** Her startup'ta çalışır, ikinci kez hata vermez.
- **Additive only:** Kolon silme veya tip değiştirme yapmaz.
- **PRAGMA-based check:** SQLite-native `PRAGMA table_info` ile mevcut kolonlar kontrol edilir.
- **Genişletilebilir:** Part 2+ için yeni guard'lar buraya eklenir.

### Doğrulama

```
=== BEFORE init_db ===
app_settings columns: ['user_id', 'notifications_enabled', 'battery_mode',
                       'background_monitoring', 'update_interval_seconds']
alert_sensitivity present: False
user_baselines: MISSING

=== AFTER init_db ===
app_settings columns: ['user_id', 'notifications_enabled', 'battery_mode',
                       'background_monitoring', 'update_interval_seconds',
                       'alert_sensitivity']
alert_sensitivity present: True
user_baselines columns: ['id', 'user_id', 'hr_mean', 'hr_std', 'spo2_mean', ...]

=== AFTER 2nd init_db (idempotency check) ===
(identical — no error, no double-add)
```

---

## 7. Diğer Düzeltilen Runtime Sorunları

### 7a. main.py — Firestore Watcher Import Sorunu

**Sorun:** `main.py` `from services.firestore_watcher import run_firestore_watcher_loop` ifadesi modül seviyesinde (top-level) bulunuyordu. `firestore_watcher.py` `google.cloud.firestore_v1` import eder. Google SDK yüklü olmayan ortamlarda `DATA_MODE=sqlite` seçilmiş olsa bile uvicorn startup crash eder.

**Düzeltme:** Import, yalnızca `DATA_MODE in ("firebase", "hybrid")` olduğunda çalışan startup bloğuna taşındı:
```python
# Önceden (modül seviyesi — her durumda crash):
from services.firestore_watcher import run_firestore_watcher_loop

# Sonra (lazy import — yalnızca gerektiğinde):
if settings.DATA_MODE in ("firebase", "hybrid"):
    from services.firestore_watcher import run_firestore_watcher_loop  # lazy import
```

### 7b. ingestion_router.py — UnboundLocalError

**Sorun:** `risk_breakdown` değişkeni yalnızca `if user_id:` bloğu içinde tanımlanıyordu. Kayıtsız cihazdan gelen paket için `user_id=None` olduğundan, `return DevicePacketResponse(risk_breakdown=risk_breakdown)` satırı `UnboundLocalError` fırlatıyordu (HTTP 500).

**Düzeltme:** `risk_breakdown: dict | None = None` ifadesi handler başlangıcında, `if user_id:` bloğunun dışında tanımlandı.

### 7c. auth.py — passlib + Python 3.14 Uyumsuzluğu

**Sorun:** Python 3.14 + passlib 1.7.4 + bcrypt 4.0.1 kombinasyonunda passlib'in lazy backend detection mekanizması bcrypt'i bulamıyor ve `MissingBackendError` fırlatıyor. `verify_password()` çağrısında HTTP 500'e yol açıyor.

**Kök Neden:** passlib 1.7.4 backend detection kodu Python 3.14'teki `importlib` değişiklikleriyle uyumsuz. `bcrypt` yüklü olsa bile lazy initialization başarısız oluyor.

**Düzeltme:** `auth.py`'ye import zamanı explicit backend initialization eklendi:
```python
# Force passlib bcrypt backend initialization (required for Python 3.14 + bcrypt 4.x)
try:
    from passlib.handlers.bcrypt import bcrypt as _bcrypt_cls
    _bcrypt_cls.set_backend("bcrypt")
except Exception:
    pass
```

---

## 8. Baseline Warm-up Süresi Açıklaması

`BASELINE_MIN_SAMPLES=300` (varsayılan) için warm-up süreleri:

| Senaryo | Paket Aralığı | Warm-up Süresi |
|---------|---------------|----------------|
| Gerçek firmware (PACKET_INTERVAL_MS=1000) | 1 sn | ~5 dakika |
| Backend simülasyonu (SIMULATION_INTERVAL_SECONDS=4.0) | 4 sn | ~20 dakika |
| Demo hızlandırılmış (BASELINE_MIN_SAMPLES=30, mock=True) | 4 sn | ~2 dakika |

**Warm-up öncesi davranış:**
- `baseline.is_ready = False`
- `personal_deviation_score = 0.0`
- `final_risk_score = global_risk_score` (baseline etkisi yok)

**NOT:** `BASELINE_ALLOW_MOCK_DATA=False` (varsayılan) iken simülasyon paketleri (`mode="mock"`) baseline'a dahil edilmez. Simülasyon çalışırken `is_ready` hiçbir zaman `True` olmaz.

---

## 9. Demo/Dev için Önerilen .env Değerleri

### Production / Staging
```ini
BASELINE_ENABLED=true
BASELINE_MIN_SAMPLES=300
BASELINE_EMA_ALPHA=0.02
BASELINE_MIN_SIGNAL_QUALITY=0.50
BASELINE_ALLOW_MOCK_DATA=false
BASELINE_PERSONAL_BONUS_MAX=0.20
```

### Demo / Geliştirme (Hızlı warm-up)
```ini
# Simülasyon paketleri baseline'a dahil edilsin
BASELINE_ALLOW_MOCK_DATA=true
# 30 pakette is_ready=True (~2 dakika simülasyon ile)
BASELINE_MIN_SAMPLES=30
# Daha hızlı adaptasyon
BASELINE_EMA_ALPHA=0.10
```

### Baseline Devre Dışı (Debug / A-B test)
```ini
BASELINE_ENABLED=false
```

---

## 10. Çalıştırılan Smoke Testler

Smoke testleri `backend/_smoke_api.py` ile yapıldı. Uvicorn `DATA_MODE=sqlite` ile başlatıldı, mevcut `healthalert.db` dosyası üzerinde.

| Test | Endpoint | Beklenen | Sonuç |
|------|----------|----------|-------|
| Health check | GET /health | 200 | ✅ PASS |
| Login | POST /auth/login | 200 + token | ✅ PASS |
| Settings default | GET /settings | 200, alert_sensitivity=normal | ✅ PASS |
| Settings PUT high | PUT /settings | 200, alert_sensitivity=high | ✅ PASS |
| Settings PUT reset | PUT /settings | 200, alert_sensitivity=normal | ✅ PASS |
| Ingest normal | POST /ingest/device-packet | 200, no 500 | ✅ PASS |
| Ingest low quality | POST /ingest/device-packet | 200, no 500 | ✅ PASS |
| Invalid sensitivity | PUT /settings (extreme) | 422 | ✅ PASS |

**Toplam: 12/12 PASSED**

---

## 11. Test/Komut Sonuçları

### Schema Guard (Mevcut DB'ye Karşı)
```powershell
$env:DATA_MODE="sqlite"; python _smoke_schema_guard.py
# Sonuç:
#   BEFORE: alert_sensitivity=False, user_baselines=MISSING
#   AFTER:  alert_sensitivity=True, user_baselines=CREATED (14 kolon)
#   AFTER 2ND: identical (idempotent)
```

### Uvicorn Startup
```powershell
$env:DATA_MODE="sqlite"; python _run_backend.py
# Sonuç:
#   INFO:healthalert.database:Schema guard: added column app_settings.alert_sensitivity
#   INFO:main:HealthAlert API ready — APP_MODE=demo
#   INFO: Application startup complete.
#   INFO: Uvicorn running on http://127.0.0.1:18765
```

### Smoke API Tests
```powershell
python _smoke_api.py
# Sonuç: SMOKE TEST RESULTS: 12/12 PASSED
```

### Baseline + Regression Tests
```powershell
$env:DATA_MODE="sqlite"; python -m pytest tests/module7/test_16_baseline_mvp.py tests/module7/test_04_factory.py::TestRepoSetFields tests/module7/test_04_factory.py::TestFactorySqliteMode tests/module7/test_05_sqlite_repos.py -v --tb=short
# Sonuç: 56 passed, 1 skipped (firebase skip — beklenen)
```

---

## 12. Bilinen Sınırlamalar

1. **DATA_MODE=hybrid startup:** `hybrid` mod için `google-cloud-firestore` SDK gereklidir. SDK yüklü değilse uvicorn lazy import ile başlamaz. Bu görevin kapsamı dışında (pre-existing).

2. **SQLite için Alembic yoktur:** Şu an tüm migration'lar `_apply_schema_guards` içinde el ile yazılmıştır. Part 2+ için Alembic migration altyapısı önerilebilir.

3. **Schema guard yalnızca SQLite için:** `_apply_schema_guards` içindeki `PRAGMA table_info` SQLite-specific. Firebase/Firestore için schema management ayrı ele alınmalıdır.

4. **Warm-up süresi:** Demo ortamında gerçek sensör kullanılmadan baseline is_ready olması için `BASELINE_ALLOW_MOCK_DATA=true` ve `BASELINE_MIN_SAMPLES=30` gibi ayarlar gereklidir.

5. **passlib + Python 3.14 workaround:** `auth.py`'deki `_bcrypt_cls.set_backend("bcrypt")` çağrısı bir workaround'dur. Kalıcı çözüm `passlib`'i daha yeni bir sürüme (veya `pwdlib` gibi aktif bir alternatife) güncellemektir.

---

## 13. Part 2'ye Geçiş Kararı

**Geçişe hazır.** Aşağıdaki tüm kritik runtime sorunları çözülmüştür:

| Kriter | Durum |
|--------|-------|
| Mevcut DB ile startup | ✅ Çalışıyor |
| user_baselines tablosu | ✅ Schema guard ile oluşturuluyor |
| app_settings.alert_sensitivity kolonu | ✅ Schema guard ile ekleniyor |
| DATA_MODE=sqlite startup | ✅ Çalışıyor (lazy import fix) |
| Login endpoint | ✅ 200 dönüyor (bcrypt fix) |
| GET/PUT /settings | ✅ 200 dönüyor |
| POST /ingest/device-packet | ✅ 200 dönüyor (UnboundLocalError fix) |
| Baseline test suite | ✅ 56 passed, 1 skipped |
| Smoke test suite | ✅ 12/12 passed |
