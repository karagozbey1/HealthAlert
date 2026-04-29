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

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

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

def should_run_simulation() -> bool:
    if settings.SIMULATION_ENABLED == "on":
        return True
    if settings.SIMULATION_ENABLED == "off":
        return False
    if settings.APP_MODE in ("demo", "staging"):
        return settings.SENSOR_MODE != "real"
    return False

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
