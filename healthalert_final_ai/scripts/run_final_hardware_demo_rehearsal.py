from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib import request
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_hardware_demo_rehearsal_probe import run_probe


BASE_URL = "http://127.0.0.1:18765"
OUTPUT_DIR = Path("outputs/hybrid_redesign/live_stream")
RESULT_PATH = OUTPUT_DIR / "final_hardware_demo_rehearsal_result.json"
BACKEND_LOG_PATH = OUTPUT_DIR / "final_hardware_demo_backend_run.log"
PROBE_PATH = OUTPUT_DIR / "final_hardware_rehearsal_probe_result.json"


def _wait_for_backend(proc: subprocess.Popen[str], timeout_sec: float = 30.0) -> bool:
    deadline = time.perf_counter() + timeout_sec
    while time.perf_counter() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with request.urlopen(BASE_URL + "/openapi.json", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except URLError:
            time.sleep(0.5)
    return False


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.healthalert.api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "18765",
        "--log-level",
        "info",
    ]

    started_at = time.time()
    log_file = BACKEND_LOG_PATH.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=Path.cwd(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    backend_ready = _wait_for_backend(proc)
    probe_result = None
    error = None
    try:
        if backend_ready:
            probe_result = run_probe(
                base_url=BASE_URL,
                patient_id="demo_patient_001",
                samples=200,
                rate_hz=50.0,
                include_ppg=True,
                output_path=PROBE_PATH,
            )
        else:
            error = "backend_not_ready"
    except Exception as exc:  # pragma: no cover - script-level diagnostics
        error = repr(exc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    log_file.close()

    result = {
        "backend_command": " ".join(cmd),
        "backend_ready": backend_ready,
        "backend_exit_code": proc.returncode,
        "backend_log_path": str(BACKEND_LOG_PATH),
        "backend_runtime_seconds": round(time.time() - started_at, 3),
        "real_esp32_observed": False,
        "real_esp32_observation_note": (
            "No physical ESP32 stream was observable from this execution environment; "
            "the endpoint was rehearsed with ESP32-format 50 Hz HTTP payloads."
        ),
        "probe_result": probe_result,
        "error": error,
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
