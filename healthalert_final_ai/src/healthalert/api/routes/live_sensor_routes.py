from __future__ import annotations

from fastapi import APIRouter

from src.healthalert.api.schemas.live_sensor_schema import (
    LiveSensorSampleRequest,
    LiveSensorSampleResponse,
)
from src.healthalert.api.services.live_sensor_ingestion_service import LiveSensorIngestionService


router = APIRouter(prefix="/api/healthalert", tags=["healthalert-live"])
service = LiveSensorIngestionService()


@router.post("/sensor-sample", response_model=LiveSensorSampleResponse)
def ingest_sensor_sample(payload: LiveSensorSampleRequest) -> LiveSensorSampleResponse:
    return service.ingest_sample(payload)
