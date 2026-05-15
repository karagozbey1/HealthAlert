from __future__ import annotations

from typing import Any, Dict, Optional

from src.healthalert.api.schemas.live_sensor_schema import LiveSensorSampleRequest
from src.healthalert.api.services.live_sensor_ingestion_service import LiveSensorIngestionService


class FirebaseSensorAdapter:
    """
    Optional Firestore adapter for live ESP32 samples.

    If a Firestore client is provided, the adapter can read the latest sample
    from `patients/{patient_id}/sensor_stream/latest` and write latest inference
    output to `patients/{patient_id}/inference_results/latest`.

    Without a Firestore client, it still runs the same backend ingestion path and
    persists events through the JSONL fallback configured in LiveSensorIngestionService.
    """

    def __init__(
        self,
        firestore_client: Optional[Any] = None,
        ingestion_service: Optional[LiveSensorIngestionService] = None,
    ) -> None:
        self.firestore_client = firestore_client
        self.ingestion_service = ingestion_service or LiveSensorIngestionService()

    def fetch_latest_sample(self, patient_id: str) -> Optional[Dict[str, Any]]:
        if self.firestore_client is None:
            return None
        doc = (
            self.firestore_client.collection("patients")
            .document(patient_id)
            .collection("sensor_stream")
            .document("latest")
            .get()
        )
        if not doc.exists:
            return None
        data = doc.to_dict()
        if data and "patient_id" not in data:
            data["patient_id"] = patient_id
        return data

    def process_latest_sample(self, patient_id: str) -> Dict[str, Any]:
        sample = self.fetch_latest_sample(patient_id)
        if sample is None:
            return {
                "patient_id": patient_id,
                "window_ready": False,
                "inference_triggered": False,
                "status": "no_firebase_sample",
            }
        return self.process_sample(sample)

    def process_sample(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        payload = LiveSensorSampleRequest(**sample)
        response = self.ingestion_service.ingest_sample(payload)
        response_dict = response.model_dump()
        if response.inference_triggered and response.inference_result is not None:
            self.write_inference_result(payload.patient_id, response.inference_result.model_dump())
        return response_dict

    def write_inference_result(self, patient_id: str, inference_result: Dict[str, Any]) -> None:
        if self.firestore_client is None:
            return
        (
            self.firestore_client.collection("patients")
            .document(patient_id)
            .collection("inference_results")
            .document("latest")
            .set(inference_result)
        )
