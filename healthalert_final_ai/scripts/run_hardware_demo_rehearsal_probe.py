from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from urllib import request


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sample(i: int, patient_id: str, include_ppg: bool) -> Dict[str, Any]:
    sample: Dict[str, Any] = {
        "patient_id": patient_id,
        "timestamp": _timestamp(),
        "source": "esp32",
        "imu": {
            "acc_x": 0.04 + (i % 8) * 0.001,
            "acc_y": 0.02 + (i % 5) * 0.001,
            "acc_z": 1.0 + (i % 7) * 0.001,
            "gyro_x": 0.12 + (i % 6) * 0.001,
            "gyro_y": 0.08 + (i % 4) * 0.001,
            "gyro_z": 0.05 + (i % 3) * 0.001,
        },
        "heart_rate": 82,
        "spo2": 97,
    }
    if include_ppg:
        sample["ppg"] = {"ir": 18000 + i, "red": 12000 + i}
    return sample


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_probe(
    *,
    base_url: str,
    patient_id: str,
    samples: int,
    rate_hz: float,
    include_ppg: bool,
    output_path: Path,
) -> Dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/api/healthalert/sensor-sample"
    interval = 1.0 / rate_hz
    started = time.perf_counter()
    first_inference_elapsed = None
    inference_at_sample = None
    last_response: Dict[str, Any] | None = None

    for i in range(samples):
        next_target = started + i * interval
        now = time.perf_counter()
        if next_target > now:
            time.sleep(next_target - now)

        last_response = _post_json(endpoint, _sample(i, patient_id, include_ppg))
        if last_response.get("inference_triggered") and first_inference_elapsed is None:
            first_inference_elapsed = time.perf_counter() - started
            inference_at_sample = i + 1

    elapsed = time.perf_counter() - started
    inference_result = None if last_response is None else last_response.get("inference_result")
    risk = {} if inference_result is None else inference_result.get("risk", {})
    missing = {} if inference_result is None else inference_result.get("missing_modalities", {})

    latest_json_path = Path("outputs/hybrid_redesign/live_stream") / f"{patient_id}_latest.json"
    result = {
        "probe_source": "simulated_esp32_http_50hz",
        "endpoint": endpoint,
        "patient_id": patient_id,
        "samples_sent": samples,
        "rate_hz": rate_hz,
        "include_ppg": include_ppg,
        "elapsed_seconds": round(elapsed, 3),
        "inference_triggered": bool(inference_result is not None),
        "inference_at_sample": inference_at_sample,
        "first_inference_elapsed_seconds": (
            None if first_inference_elapsed is None else round(first_inference_elapsed, 3)
        ),
        "window_ready": False if last_response is None else bool(last_response.get("window_ready")),
        "buffered_imu_samples": None if last_response is None else last_response.get("buffered_imu_samples"),
        "final_risk_score": risk.get("final_risk_score"),
        "risk_level": risk.get("risk_level"),
        "recommended_action": risk.get("recommended_action"),
        "reasons": risk.get("reasons", []),
        "missing_modalities": missing,
        "latest_json_path": str(latest_json_path),
        "latest_json_exists": latest_json_path.exists(),
        "last_response": last_response,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18765")
    parser.add_argument("--patient-id", default="demo_patient_001")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--rate-hz", type=float, default=50.0)
    parser.add_argument("--no-ppg", action="store_true")
    parser.add_argument(
        "--output",
        default="outputs/hybrid_redesign/live_stream/final_hardware_rehearsal_probe_result.json",
    )
    args = parser.parse_args()

    result = run_probe(
        base_url=args.base_url,
        patient_id=args.patient_id,
        samples=args.samples,
        rate_hz=args.rate_hz,
        include_ppg=not args.no_ppg,
        output_path=Path(args.output),
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
