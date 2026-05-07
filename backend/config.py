import logging
from typing import Literal

from pydantic_settings import BaseSettings

logger = logging.getLogger("healthalert.config")

class Settings(BaseSettings):
    APP_MODE: Literal["demo", "staging", "production"] = "demo"

    SECRET_KEY: str = "healthalert-demo-secret-key-2024-local"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DATABASE_URL: str = "sqlite+aiosqlite:///./healthalert.db"

    SIMULATION_INTERVAL_SECONDS: float = 4.0
    SIMULATION_ENABLED: Literal["auto", "on", "off"] = "auto"

    LINK_CODE_EXPIRE_HOURS: int = 48
    LINK_CODE_USES: int = 1

    DATA_MODE: Literal["sqlite", "firebase", "hybrid"] = "sqlite"

    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""

    SENSOR_MODE: Literal["real", "mock", "auto"] = "auto"

    AI_MODE: Literal["real", "mock", "off"] = "mock"

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT: int = 30

    NOTIFICATION_MODE: Literal["poll", "push"] = "poll"
    FCM_SERVER_KEY: str = ""

    RISK_CRITICAL_THRESHOLD: float = 0.75
    RISK_WARNING_THRESHOLD: float = 0.55
    RISK_WATCH_THRESHOLD: float = 0.30

    # ---------------------------------------------------------------------------
    # Baseline ayarlari (Part 1 - Kisisel baseline MVP)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise tum baseline akisi kapanir ve saf heuristik risk kalir.
    BASELINE_ENABLED: bool = True

    # is_ready=True olmadan once gereken guvenilir paket sayisi.
    # Isinma suresi yaklasik olarak sunlardir:
    #   Gercek firmware (PACKET_INTERVAL_MS=1000) -> 300 sn ~= 5 dk
    #   Backend simulasyonu (SIMULATION_INTERVAL_SECONDS=4.0) -> 1200 sn ~= 20 dk
    # Demo ortamlarda .env ile 30-50 araligina cekilebilir.
    BASELINE_MIN_SAMPLES: int = 300

    # Baseline guncellemesinde kullanilan EMA yumusatma katsayisi.
    # Kucuk deger daha yavas ama daha kararlidir; buyuk deger daha hizlidir.
    # 0.02 her yeni paketin ortalamada yaklasik %2 agirligi oldugu anlamina gelir.
    BASELINE_EMA_ALPHA: float = 0.02

    # Baseline'e yazilacak paketler icin gereken asgari PPG kalite esigi.
    # Bu esigin altindaki paketler sessizce atlanir.
    BASELINE_MIN_SIGNAL_QUALITY: float = 0.50

    # Simule veya mock paketlerin baseline'e katkida bulunup bulunmayacagi.
    # Production'da False tutulur; demo/dev icin isinmayi hizlandirmak uzere True olabilir.
    BASELINE_ALLOW_MOCK_DATA: bool = False

    # global_risk_score ustune eklenebilecek en buyuk kisisel sapma bonusu.
    # Baseline etkisini nihai riskte ustten sinirlar.
    BASELINE_PERSONAL_BONUS_MAX: float = 0.20

    # ---------------------------------------------------------------------------
    # ML shadow inference (Part 2 - Kayar pencere altyapisi)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise ML inference tumden atlanir.
    ML_INFERENCE_ENABLED: bool = False

    # True iken ML cikisi yalniz metadata olarak loglanir ve response'a eklenir.
    # Alert, anomaly veya bildirim kararlarini dogrudan surmez.
    ML_SHADOW_MODE: bool = True

    # En iyi fusion model checkpoint yolu.
    # Goreli yollar proje kokune gore cozulur.
    ML_MODEL_PATH: str = "outputs/models/best_final_fusion_model.pt"

    # Inference oncesi kullanici bazli buffer'da birikmesi gereken ornek sayisi.
    # Burada her ornek bir backend paketidir; 200 ornek ~= 200 sn gercek veri demektir.
    ML_WINDOW_SIZE: int = 200

    # Buffer dolduktan sonra ML inference her N pakette bir calisir.
    # 50 degeri 1 pkt/sn akista yaklasik 50 sn aralik demektir.
    ML_INFERENCE_EVERY_N_PACKETS: int = 50

    # Modelin egitildigi beklenen ornekleme hizi.
    # Yalniz sure uyumsuzlugu uyarilarinda kullanilir; buffer davranisini degistirmez.
    ML_EXPECTED_SAMPLE_RATE_HZ: int = 50

    # True ise ML yukleme veya inference hatasi 500 yerine guvenli yanitla gecilir.
    ML_FAIL_OPEN: bool = True

    # True ise her backend paketi ham frame yerine ozetlenmis tek ornek sayilir.
    # Yalniz metadata ve uyari uretiminde kullanilir.
    ML_USE_PACKET_SUMMARY_MODE: bool = True

    # Tahmini pencere suresi egitim suresinden cok uzunsa log uyarisi basar.
    ML_WARN_ON_SAMPLE_RATE_MISMATCH: bool = True

    # /ingest/device-packet yanitina ml_shadow_result alanini ekler.
    ML_RESPONSE_INCLUDE_SHADOW_RESULT: bool = True

    # ---------------------------------------------------------------------------
    # ML evidence fusion (Part 6 - bounded contribution to final risk)
    # ---------------------------------------------------------------------------

    ML_EVIDENCE_FUSION_ENABLED: bool = True
    ML_EVIDENCE_WEIGHT: float = 0.25
    ML_EVIDENCE_MAX_POSITIVE_ADJUSTMENT: float = 0.15
    ML_EVIDENCE_ALLOW_NEGATIVE_ADJUSTMENT: bool = False
    ML_EVIDENCE_MIN_CONFIDENCE: float = 0.60
    ML_EVIDENCE_REQUIRE_MODEL_READY_WINDOW: bool = True
    ML_EVIDENCE_REQUIRE_SAMPLE_RATE_OK: bool = True

    # ---------------------------------------------------------------------------
    # ML ornekleme hizi uyum kapisi (Part 3.1 - Canli hiz uyumu)
    # ---------------------------------------------------------------------------

    # True iken sample_rate_warning varsa ML inference atlanir ve ml_skipped=True olur.
    # False yalniz deneysel tanilama ortamlari icin dusunulmelidir.
    ML_SKIP_ON_SAMPLE_RATE_MISMATCH: bool = True

    # Sure uyumsuzlugu uyarisi icin azami pencere/orijinal sure orani.
    ML_MAX_DURATION_RATIO: float = 3.0

    # Override anahtari. True ise sample_rate_warning olsa da dusuk guvenli inference'e izin verir.
    ML_ALLOW_LOW_CONFIDENCE_INFERENCE: bool = False

    # ML vitals giris boyutu. 0 otomatik algilar.
    # 2 = [heart_rate, spo2/100]
    # 3 = [heart_rate, spo2/100, signal_quality]
    ML_VITALS_DIM: int = 0

    # ---------------------------------------------------------------------------
    # Retrieval RAG shadow (Part 3 - Zaman serisi retrieval PoC)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise retrieval hatti tumden atlanir.
    RETRIEVAL_ENABLED: bool = False

    # True iken retrieval sonucu yalniz metadata olarak doner ve loglanir.
    # Karar akisini surmez.
    RETRIEVAL_SHADOW_MODE: bool = True

    # Onceden uretilmis retrieval index dizini.
    RETRIEVAL_INDEX_DIR: str = "outputs/retrieval"

    # Her sorguda alinacak benzer pencere sayisi.
    RETRIEVAL_TOP_K: int = 5

    # /ingest yanitina retrieval_shadow_result alanini ekler.
    RETRIEVAL_RESPONSE_INCLUDE_RESULT: bool = True

    # ---------------------------------------------------------------------------
    # Retrieval ornekleme hizi uyum kapisi (Part 3.1 - Canli hiz uyumu)
    # ---------------------------------------------------------------------------

    # True iken hiz uyari varsa ve slow index yoksa 50Hz retrieval atlanir.
    RETRIEVAL_SKIP_ON_SAMPLE_RATE_MISMATCH: bool = True

    # Override. True ise hiz uyarisina ragmen 50Hz index sorgusu denenir.
    RETRIEVAL_ALLOW_LOW_CONFIDENCE_QUERY: bool = False

    # True iken hiz uyarisinda once slow yani 1Hz uyumlu index denenir.
    RETRIEVAL_USE_SLOW_INDEX: bool = True

    # Yavas hizli yani 1Hz uyumlu retrieval index dizini.
    RETRIEVAL_SLOW_INDEX_DIR: str = "outputs/retrieval_slow"

    # ---------------------------------------------------------------------------
    # Learning loop (Part 5A - Egitim verisi katmani)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise learning loop calismaz ve ek kayit yazilmaz.
    LEARNING_LOOP_ENABLED: bool = True

    # Normal dusuk riskli pencerelerin egitim adayi olarak secilecek orani.
    LEARNING_CAPTURE_NORMAL_RATE: float = 0.05

    # True ise tum warning olaylari her zaman yakalanir.
    LEARNING_CAPTURE_WARNING_ALWAYS: bool = True

    # True ise tum critical olaylari her zaman yakalanir.
    LEARNING_CAPTURE_CRITICAL_ALWAYS: bool = True

    # False iken demo/mock pencereler loglanir ama egitim adayina donusmez.
    LEARNING_ALLOW_DEMO_AS_TRAINING: bool = False

    # Egitim export paketlerinin yazildigi dizin.
    LEARNING_EXPORT_DIR: str = "outputs/learning_exports"

    # Egitim adayi olmak icin gereken asgari quality_confidence.
    LEARNING_MIN_QUALITY_CONFIDENCE: float = 0.60

    # Ham model-window export varsayilan olarak kapalidir.
    MODEL_WINDOW_RAW_EXPORT_ENABLED: bool = False

    # ---------------------------------------------------------------------------
    # Adaptive personalization engine (Part 5B)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise kisisellestirme kapatilir ve baseline-only akisa donulur.
    PERSONALIZATION_ENABLED: bool = True

    # cold_start kullanicilar icin kisisel sapmadan gelebilecek azami risk bonusu.
    PERSONALIZATION_COLD_START_MAX_BONUS: float = 0.05

    # Ogrenme fazindaki kullanicilar icin azami risk bonusu.
    PERSONALIZATION_LEARNING_MAX_BONUS: float = 0.10

    # Kalibre olmus kullanicilar icin azami risk bonusu.
    PERSONALIZATION_CALIBRATED_MAX_BONUS: float = 0.20

    # Kisa vadeli trend sinyallerinden gelebilecek azami risk ayari.
    PERSONALIZATION_TREND_MAX_BONUS: float = 0.10

    # Gecmis geri bildirim desenlerinden gelebilecek azami risk ayari.
    PERSONALIZATION_FEEDBACK_MAX_ADJUSTMENT: float = 0.10

    # ---------------------------------------------------------------------------
    # Care assistant orchestrator (Part 5C)
    # ---------------------------------------------------------------------------

    # Ana anahtar. False ise orchestrator katmani kapatilir.
    ASSISTANT_ENABLED: bool = True

    # Kullaniciya kritik "iyi misin" istemi icin taninan sure.
    ASSISTANT_CRITICAL_ACK_TIMEOUT_SEC: int = 30

    # WATCH modundan NORMAL moda donmeden once beklenecek sure.
    ASSISTANT_WATCH_DURATION_SEC: int = 300

    # Tekrarlanan WARNING yonlendirmeleri arasindaki asgari sure.
    ASSISTANT_WARNING_GUIDANCE_COOLDOWN_SEC: int = 120

    # Mod bazli onerilen poll araliklari.
    ASSISTANT_NORMAL_POLL_INTERVAL_SEC: int = 60
    ASSISTANT_WATCH_POLL_INTERVAL_SEC: int = 10
    ASSISTANT_CRITICAL_POLL_INTERVAL_SEC: int = 1

    # Kullanici kritik durumda yanit vermezse bildirim gidip gitmeyecegi.
    ASSISTANT_NOTIFY_RELATIVES_ON_NO_RESPONSE: bool = True
    ASSISTANT_NOTIFY_DOCTORS_ON_NO_RESPONSE: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Kritik config uyumsuzluklari icin startup uyarilari uretir.
def validate_settings() -> list[str]:
    import os
    warnings: list[str] = []

    if settings.APP_MODE == "production":
        if settings.SECRET_KEY == "healthalert-demo-secret-key-2024-local":
            warnings.append(
                "CRITICAL: SECRET_KEY is using the demo default. "
                "Set a strong random key for production."
            )
        if settings.DATA_MODE == "sqlite":
            warnings.append(
                "WARNING: Production mode with sqlite DATA_MODE. "
                "Consider firebase or hybrid for cloud persistence."
            )

    if settings.DATA_MODE in ("firebase", "hybrid"):
        if not settings.FIREBASE_PROJECT_ID:
            warnings.append(
                "WARNING: DATA_MODE=%s but FIREBASE_PROJECT_ID is empty. "
                "Firebase operations will fail." % settings.DATA_MODE
            )
        if not settings.FIREBASE_CREDENTIALS_PATH:
            warnings.append(
                "INFO: FIREBASE_CREDENTIALS_PATH is empty. "
                "Will attempt Application Default Credentials (ADC)."
            )
        elif not os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
            warnings.append(
                "ERROR: FIREBASE_CREDENTIALS_PATH='%s' — file not found. "
                "Firebase will not initialise. Place the service-account JSON "
                "at the specified path." % settings.FIREBASE_CREDENTIALS_PATH
            )

    if settings.NOTIFICATION_MODE == "push":
        if not settings.FCM_SERVER_KEY:
            warnings.append(
                "WARNING: NOTIFICATION_MODE=push but FCM_SERVER_KEY is empty. "
                "Push delivery will be skipped; falling back to poll."
            )

    return warnings

# Ortama gore simulasyon akisinin calisip calismayacagini belirler.
def should_run_simulation() -> bool:
    if settings.SIMULATION_ENABLED == "on":
        return True
    if settings.SIMULATION_ENABLED == "off":
        return False
    if settings.APP_MODE in ("demo", "staging"):
        return settings.SENSOR_MODE != "real"
    return False

# Uygulama acilisinda temel config ozetini log'a yazar.
def log_startup_config() -> None:
    sim = "ON" if should_run_simulation() else "OFF"
    logger.info("=" * 60)
    logger.info("  HealthAlert Configuration Summary")
    logger.info("=" * 60)
    logger.info("  APP_MODE           : %s", settings.APP_MODE)
    logger.info("  DATA_MODE          : %s", settings.DATA_MODE)
    logger.info("  SENSOR_MODE        : %s", settings.SENSOR_MODE)
    logger.info("  AI_MODE            : %s", settings.AI_MODE)
    logger.info("  NOTIFICATION_MODE  : %s", settings.NOTIFICATION_MODE)
    logger.info("  SIMULATION         : %s", sim)
    logger.info("  DATABASE_URL       : %s", settings.DATABASE_URL)
    if settings.DATA_MODE in ("firebase", "hybrid"):
        logger.info("  FIREBASE_PROJECT   : %s", settings.FIREBASE_PROJECT_ID or "(not set)")
    logger.info("=" * 60)
    for w in validate_settings():
        logger.warning("  CONFIG: %s", w)

    if settings.SECRET_KEY == "healthalert-demo-secret-key-2024-local":
        if settings.APP_MODE == "production":
            logger.critical(
                "🚨 SECURITY: Using demo SECRET_KEY in production mode! "
                "Set a strong random SECRET_KEY immediately."
            )
        elif settings.APP_MODE == "staging":
            logger.warning(
                "⚠️  SECURITY: Using demo SECRET_KEY in staging mode. "
                "Set a proper SECRET_KEY before going live."
            )
