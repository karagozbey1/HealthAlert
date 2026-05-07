import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

logger = logging.getLogger("healthalert.database")

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

# Asenkron veritabanı oturumu sağlayan FastAPI dependency.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# Mevcut tablolara gereken ek kolonlari guvenli sekilde ekler.
def _apply_schema_guards(sync_conn) -> None:
    # app_settings.alert_sensitivity kolonunu gerekirse ekler.
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

    # personal_health_profiles ML window alanlarini gerekirse ekler.
    rows = sync_conn.execute(text("PRAGMA table_info(personal_health_profiles)")).fetchall()
    if rows:
        existing_cols = {row[1] for row in rows}
        guards = [
            ("ml_window_count", "INTEGER NOT NULL DEFAULT 0"),
            ("ml_usable_window_count", "INTEGER NOT NULL DEFAULT 0"),
            ("ml_evidence_mean", "FLOAT NOT NULL DEFAULT 0"),
            ("ml_evidence_std", "FLOAT NOT NULL DEFAULT 0"),
            ("ml_confidence_mean", "FLOAT NOT NULL DEFAULT 0"),
            ("ml_positive_support_count", "INTEGER NOT NULL DEFAULT 0"),
            ("ml_personal_disagreement_count", "INTEGER NOT NULL DEFAULT 0"),
            ("last_ml_evidence_score", "FLOAT"),
            ("last_ml_adjustment", "FLOAT"),
            ("last_model_window_at", "DATETIME"),
        ]
        for col, ddl in guards:
            if col not in existing_cols:
                sync_conn.execute(
                    text(
                        f"ALTER TABLE personal_health_profiles ADD COLUMN {col} {ddl}"
                    )
                )
                logger.info(
                    "Schema guard: added column personal_health_profiles.%s", col
                )


# Tüm tabloları yoksa oluşturur; mevcut tablolara eksik kolonları ekler.
async def init_db() -> None:
    import models  # noqa: F401 — registers all ORM models with Base.metadata

    async with engine.begin() as conn:
        # Eksik tablolari olusturur.
        await conn.run_sync(Base.metadata.create_all)
        # Mevcut tablolardaki eksik kolonlari tamamlar.
        await conn.run_sync(_apply_schema_guards)
