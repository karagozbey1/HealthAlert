from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, log_startup_config, should_run_simulation, validate_settings
from database import init_db
from firebase_client import init_firebase
from routers.auth_router import router as auth_router
from routers.users_router import router as users_router
from routers.link_codes_router import router as link_codes_router
from routers.live_status_router import router as live_router
from routers.anomalies_router import router as anomalies_router
from routers.alerts_router import router as alerts_router
from routers.history_router import router as history_router
from routers.notifications_router import router as notifications_router
from routers.clinical_notes_router import router as clinical_notes_router
from routers.settings_router import router as settings_router
from routers.ingestion_router import router as ingestion_router
from routers.assistant_router import router as assistant_router
from routers.chat_router import router as chat_router
from routers.learning_router import router as learning_router
from routers.personalization_router import router as personalization_router
from routers.model_window_router import router as model_window_router
from services.simulation import run_simulation_loop
# firestore_watcher import'u sqlite modunda gereksiz bagimlilik yuklemez.

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="HealthAlert API",
    description="Role-based health monitoring backend — live-first, mock-fallback.",
    version="2.0.0",
)

_cors_origins = ["*"]
if settings.APP_MODE == "production":
    import os
    _allowed = os.getenv("CORS_ORIGINS", "")
    _parsed = [o.strip() for o in _allowed.split(",") if o.strip()]
    if _parsed:
        _cors_origins = _parsed
    else:
        _cors_origins = []
        logger.warning(
            "CORS_ORIGINS is empty in production mode. "
            "No cross-origin requests will be allowed. "
            "Set CORS_ORIGINS to allowed domains."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(link_codes_router)
app.include_router(live_router)
app.include_router(anomalies_router)
app.include_router(alerts_router)
app.include_router(history_router)
app.include_router(notifications_router)
app.include_router(clinical_notes_router)
app.include_router(settings_router)
app.include_router(ingestion_router)
app.include_router(assistant_router)
app.include_router(chat_router)
app.include_router(learning_router)
app.include_router(personalization_router)
app.include_router(model_window_router)

_sim_task: asyncio.Task | None = None
_firestore_watcher_task: asyncio.Task | None = None

# Uygulama baslangicinda DB, seed ve arka plan gorevlerini hazirlar.
@app.on_event("startup")
async def startup() -> None:
    log_startup_config()

    for w in validate_settings():
        logger.warning(w)

    await init_db()

    init_firebase()

    from seed import seed_demo_data
    await seed_demo_data()

    if should_run_simulation():
        global _sim_task
        _sim_task = asyncio.create_task(run_simulation_loop())
        logger.info("Simulation engine started (SENSOR_MODE=%s).", settings.SENSOR_MODE)
    else:
        logger.info(
            "Simulation engine NOT started "
            "(SIMULATION_ENABLED=%s, SENSOR_MODE=%s, APP_MODE=%s).",
            settings.SIMULATION_ENABLED, settings.SENSOR_MODE, settings.APP_MODE,
        )

    if settings.DATA_MODE in ("firebase", "hybrid"):
        from database import AsyncSessionLocal
        from services.firestore_watcher import run_firestore_watcher_loop
        global _firestore_watcher_task
        _firestore_watcher_task = asyncio.create_task(
            run_firestore_watcher_loop(None, AsyncSessionLocal)
        )
        logger.info("Firestore watcher started (DATA_MODE=%s).", settings.DATA_MODE)
    else:
        logger.info(
            "Firestore watcher NOT started (DATA_MODE=%s). "
            "Data ingestion via HTTP POST /ingest/device-packet.",
            settings.DATA_MODE,
        )

    logger.info("HealthAlert API ready — APP_MODE=%s", settings.APP_MODE)

# Uygulama kapanirken arka plan gorevlerini durdurur.
@app.on_event("shutdown")
async def shutdown() -> None:
    if _sim_task:
        _sim_task.cancel()
        logger.info("Simulation engine stopped.")
    if _firestore_watcher_task:
        _firestore_watcher_task.cancel()
        logger.info("Firestore watcher stopped.")

# Temel servis saglik bilgisini dondurur.
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "HealthAlert API", "version": "2.0.0"}

# Bagimlilik ve fallback durumlarini birlikte raporlar.
@app.get("/readiness")
async def readiness_check():
    from firebase_client import get_firebase_status
    from services.push_service import get_push_status

    firebase = get_firebase_status()
    push = get_push_status()

    firebase_ready = firebase.get("firestore_connected", False) if firebase.get("needed") else True
    push_ready = push.get("push_ready", False) if push.get("push_enabled") else True

    return {
        "status": "ready",
        "version": "2.0.0",
        "app_mode": settings.APP_MODE,
        "data_mode": settings.DATA_MODE,
        "sensor_mode": settings.SENSOR_MODE,
        "ai_mode": settings.AI_MODE,
        "simulation_running": _sim_task is not None and not _sim_task.done(),

        "firebase": {
            "needed": firebase.get("needed", False),
            "project_id": settings.FIREBASE_PROJECT_ID or None,
            "credentials_configured": firebase.get("credentials_path_configured", False),
            "credentials_file_found": firebase.get("credentials_file_exists", False),
            "sdk_initialised": firebase.get("sdk_initialised", False),
            "firestore_connected": firebase.get("firestore_connected", False),
            "cloud_ready": firebase_ready,
            "error": firebase.get("error"),
        },

        "push": {
            "notification_mode": push.get("notification_mode", "poll"),
            "fcm_key_configured": push.get("fcm_key_configured", False),
            "push_ready": push.get("push_ready", False),
            "effective_mode": push.get("push_effective_mode", "poll_only"),
            "delivery_stats": push.get("stats", {}),
        },

        "fallback_info": {
            "firebase_fallback": (
                "Using local SQLite — Firebase credentials not configured."
                if not firebase_ready and firebase.get("needed")
                else "No fallback needed." if firebase_ready
                else "Firebase not required for current DATA_MODE."
            ),
            "push_fallback": (
                "Push degraded to poll — FCM_SERVER_KEY not configured."
                if push.get("push_enabled") and not push.get("push_ready")
                else "Poll-only mode — push not enabled."
                if not push.get("push_enabled")
                else "Push active and ready."
            ),
        },
    }

# Bulut baglantisinin temel okuma-yazma sagligini sinar.
@app.get("/cloud/smoke")
async def cloud_smoke_test():
    from firebase_client import firebase_smoke_test, get_firebase_status

    status_info = get_firebase_status()
    if not status_info.get("needed"):
        return {
            "ok": False,
            "detail": (
                f"DATA_MODE={settings.DATA_MODE} — Firebase not required. "
                "Set DATA_MODE=firebase or DATA_MODE=hybrid to enable cloud."
            ),
            "firebase_status": status_info,
        }

    result = await firebase_smoke_test()
    return {**result, "firebase_status": status_info}

# Push altyapisinin etkin durumunu ornek istekle dogrular.
@app.get("/push/smoke")
async def push_notification_smoke_test():
    from database import AsyncSessionLocal
    from services.push_service import push_smoke_test, get_push_status

    async with AsyncSessionLocal() as db:
        result = await push_smoke_test(db)

    push_status = get_push_status()
    return {**result, "push_status": push_status}
