from __future__ import annotations

from fastapi import APIRouter

from src.healthalert.api.schemas.hybrid_inference_schema import (
    HybridInferenceRequest,
    HybridInferenceResponse,
)
from src.healthalert.api.services.hybrid_inference_api_service import HybridInferenceAPIService


router = APIRouter(prefix="/api/healthalert", tags=["healthalert"])
service = HybridInferenceAPIService()


@router.post("/inference", response_model=HybridInferenceResponse)
def run_hybrid_inference(payload: HybridInferenceRequest) -> HybridInferenceResponse:
    return service.infer(payload)
