from __future__ import annotations

from fastapi import FastAPI

from src.healthalert.api.routes.hybrid_inference_routes import router as hybrid_router
from src.healthalert.api.routes.live_sensor_routes import router as live_sensor_router


def create_app() -> FastAPI:
    app = FastAPI(title="HealthAlert Backend API", version="1.0.0")
    app.include_router(hybrid_router)
    app.include_router(live_sensor_router)
    return app


app = create_app()
