import sys
import json
import urllib.request
import urllib.error
import urllib.parse

BASE = "http://127.0.0.1:18765"
_RESULTS: list[tuple[str, bool, str]] = []


# HTTP istegi gonderip JSON yaniti veya hata govdesini dondurur.
def req(method: str, path: str, body: dict | None = None, token: str | None = None):
    """Smoke kontrolünde kullanılan ilgili Firebase yardımcı işlemini yürütür."""
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"_raw": raw.decode(errors="replace")}


# Test sonucunu kaydedip terminale PASS veya FAIL olarak basar.
def check(name: str, cond: bool, detail: str = "") -> None:
    """Smoke kontrol sonucunu okunabilir PASS veya FAIL satırı olarak yazdırır."""
    status = "PASS" if cond else "FAIL"
    _RESULTS.append((name, cond, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# 1. Health
print("\n== 1. Health check ==")
status, body = req("GET", "/health")
check("GET /health → 200", status == 200, str(body))

# 2. Login
print("\n== 2. Login ==")
status, body = req("POST", "/auth/login", {"email": "self@demo.com", "password": "demo1234"})
check("POST /auth/login → 200", status == 200, f"keys={list(body.keys())}")
token = body.get("access_token") if status == 200 else None

# 3. Settings GET
print("\n== 3. GET /settings ==")
if token:
    status, body = req("GET", "/settings", token=token)
    check("GET /settings → 200", status == 200, str(body))
    check("alert_sensitivity default=normal", body.get("alert_sensitivity") == "normal",
          f"got={body.get('alert_sensitivity')}")
else:
    check("GET /settings (skipped - no token)", False, "login failed")

# 4. Settings PUT alert_sensitivity
print("\n== 4. PUT /settings alert_sensitivity=high ==")
if token:
    status, body = req("PUT", "/settings", {"alert_sensitivity": "high"}, token=token)
    check("PUT /settings → 200", status == 200, str(body))
    check("alert_sensitivity=high stored", body.get("alert_sensitivity") == "high",
          f"got={body.get('alert_sensitivity')}")

    # Degeri tekrar normal seviyeye ceker.
    status, body = req("PUT", "/settings", {"alert_sensitivity": "normal"}, token=token)
    check("PUT /settings reset to normal → 200", status == 200, str(body))

# 5. Demo cihazi kaydi
print("\n== 5. POST /ingest/register-device (demo device) ==")
registered_user_id = None
if token:
    status, body = req("POST", "/ingest/register-device", {"device_id": "ha-esp32-001"}, token=token)
    check("POST /ingest/register-device → 200", status == 200, str(body))
    registered_user_id = body.get("user_id") if status == 200 else None
    check("register-device user_id present", bool(registered_user_id), f"user_id={registered_user_id}")

# 6. Kayitli cihazdan paket ingest
print("\n== 6. POST /ingest/device-packet (registered device) ==")
registered_pkt = {
    "device_id": "ha-esp32-001", "packet_seq": 1501, "timestamp_ms": 1700000100000,
    "mode": "real",
    "accel_x": 0.01, "accel_y": 0.02, "accel_z": 1.0,
    "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
    "red_value": 50000, "ir_value": 55000,
    "heart_rate": 72.0, "spo2": 98.0, "signal_quality": 0.9,
    "imu_ok": True, "ppg_ok": True,
    "hr_valid": True, "spo2_valid": True, "finger_detected": True,
    "state_hint": "normal",
}
status, body = req("POST", "/ingest/device-packet", registered_pkt)
check("POST /ingest (registered) → 200", status == 200, str(body))
check("registered ingest user_id != null", body.get("user_id") is not None, f"user_id={body.get('user_id')}")
check("registered ingest status accepted/duplicate", body.get("status") in ("accepted", "duplicate", "ok", "logged"), str(body))
check("registered ingest has window_status", body.get("window_status") is not None, str(body.get("window_status")))

# 7. Kayitli ingest sonrasi live sorgusu
print("\n== 7. GET /live/{user_id} (after registered ingest) ==")
if token and registered_user_id:
    status, body = req("GET", f"/live/{registered_user_id}", token=token)
    check("GET /live/{user_id} → 200", status == 200, str(body))
    if status == 200:
        check("live status has risk_score", "risk_score" in body, f"keys={list(body.keys())}")
        check("live status has timestamp", "timestamp" in body, f"keys={list(body.keys())}")
else:
    check("GET /live/{user_id} (skipped - no token or user_id)", False, "missing auth or registered user")

# 8. Kayitsiz cihazdan normal paket ingest
print("\n== 8. POST /ingest/device-packet (normal, unregistered device) ==")
normal_pkt = {
    "device_id": "smoke-dev-001", "packet_seq": 1001, "timestamp_ms": 1700000000000,
    "mode": "real",
    "accel_x": 0.01, "accel_y": 0.02, "accel_z": 1.0,
    "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
    "red_value": 50000, "ir_value": 55000,
    "heart_rate": 72.0, "spo2": 98.0, "signal_quality": 0.9,
    "imu_ok": True, "ppg_ok": True,
    "hr_valid": True, "spo2_valid": True, "finger_detected": True,
    "state_hint": "normal",
}
status, body = req("POST", "/ingest/device-packet", normal_pkt)
check("POST /ingest (normal) → 200", status == 200, str(body))
check("status=accepted or duplicate", body.get("status") in ("accepted", "ok", "duplicate", "logged"), str(body))

# 9. Kayitsiz dusuk kalite paket ingest
print("\n== 9. POST /ingest/device-packet (low quality) ==")
low_q_pkt = {**normal_pkt, "packet_seq": 1002, "signal_quality": 0.2,
             "finger_detected": False, "hr_valid": False, "spo2_valid": False}
status, body = req("POST", "/ingest/device-packet", low_q_pkt)
check("POST /ingest (low quality) → 200", status == 200, str(body))
check("no 5xx on bad quality", status < 500, f"status={status}")

# 10. Kayitli cihazda dusuk kalite paket ingest
print("\n== 10. POST /ingest/device-packet (low quality, registered) ==")
registered_low_q = {
    **registered_pkt,
    "packet_seq": 1502,
    "signal_quality": 0.2,
    "finger_detected": False,
    "hr_valid": False,
    "spo2_valid": False,
}
status, body = req("POST", "/ingest/device-packet", registered_low_q)
check("POST /ingest (registered low quality) → 200", status == 200, str(body))
check("registered low quality no 5xx", status < 500, f"status={status}")

# 11. Settings gecersiz deger
print("\n== 11. PUT /settings invalid alert_sensitivity ==")
if token:
    status, body = req("PUT", "/settings", {"alert_sensitivity": "extreme"}, token=token)
    check("PUT invalid sensitivity → 422", status == 422, f"status={status}")

# 12. Part 2 ve Part 3 response anahtarlari
print("\n== 12. Part 2 window_status field present ==")
wstatus_pkt = {**normal_pkt, "packet_seq": 2001}
status, body = req("POST", "/ingest/device-packet", wstatus_pkt)
check("POST /ingest Part2 schema → 200", status == 200, str(body))
check("window_status key in response", "window_status" in body,
      f"keys={list(body.keys())}")
check("ml_shadow_result key in response", "ml_shadow_result" in body,
      f"keys={list(body.keys())}")
check("retrieval_shadow_result key in response", "retrieval_shadow_result" in body,
      f"keys={list(body.keys())}")

# 13. Part 5A learning loop smoke
print("\n== 13. POST /learning/feedback ==")
if token and registered_user_id:
    fb_body = {
        "user_id": registered_user_id,
        "related_window_id": None,
        "feedback_type": "ok",
        "feedback_source": "mobile",
        "note": "smoke test feedback",
    }
    status, body = req("POST", "/learning/feedback", fb_body, token=token)
    check("POST /learning/feedback → 200", status == 200, str(body))
    check("feedback_type in response", body.get("feedback_type") == "ok",
          f"got={body.get('feedback_type')}")
else:
    check("POST /learning/feedback (skipped - no token/user)", False, "missing auth")

print("\n== 14. GET /learning/summary/{user_id} ==")
if token and registered_user_id:
    status, body = req("GET", f"/learning/summary/{registered_user_id}", token=token)
    check("GET /learning/summary → 200", status == 200, str(body))
    check("summary has user_id", body.get("user_id") == registered_user_id,
          f"got={body.get('user_id')}")
    check("summary has available field", "available" in body,
          f"keys={list(body.keys())}")
else:
    check("GET /learning/summary (skipped - no token/user)", False, "missing auth")

print("\n== 15. POST /learning/export (dry-run) ==")
if token:
    export_body = {
        "include_demo": False,
        "limit": 10,
    }
    status, body = req("POST", "/learning/export", export_body, token=token)
    check("POST /learning/export → 200", status == 200, str(body))
    if status == 200:
        check("export has window_count", "window_count" in body,
              f"keys={list(body.keys())}")
        check("export has export_dir", "export_dir" in body,
              f"keys={list(body.keys())}")
else:
    check("POST /learning/export (skipped - no token)", False, "missing auth")

print("\n== 16. GET /learning/windows ==")
if token:
    status, body = req("GET", "/learning/windows?limit=5", token=token)
    check("GET /learning/windows → 200", status == 200, str(body))
    check("learning/windows returns list", isinstance(body, list),
          f"type={type(body).__name__}")
else:
    check("GET /learning/windows (skipped)", False, "missing auth")

print("\n== 17. GET /learning/model-versions ==")
if token:
    status, body = req("GET", "/learning/model-versions", token=token)
    check("GET /learning/model-versions → 200", status == 200, str(body))
    check("model-versions returns list", isinstance(body, list),
          f"type={type(body).__name__}")
else:
    check("GET /learning/model-versions (skipped)", False, "missing auth")

# 18-20. Part 5B kisisellestirme smoke
print("\n== 18. GET /personalization/summary/{user_id} ==")
if token and user_id:
    status, body = req("GET", f"/personalization/summary/{user_id}", token=token)
    check("GET /personalization/summary → 200", status == 200, str(body))
    if isinstance(body, dict):
        check("personalization_level present", "personalization_level" in body, str(body))
        check("typical_ranges present", "typical_ranges" in body, str(body))
else:
    check("GET /personalization/summary (skipped)", False, "missing auth or user_id")

print("\n== 19. GET /personalization/profile/{user_id} ==")
if token and user_id:
    status, body = req("GET", f"/personalization/profile/{user_id}", token=token)
    check("GET /personalization/profile → 200", status == 200, str(body))
    if isinstance(body, dict):
        check("profile user_id correct", body.get("user_id") == user_id, str(body))
else:
    check("GET /personalization/profile (skipped)", False, "missing auth or user_id")

print("\n== 20. POST ingest → personalization_result present ==")
if token:
    pkt = {
        "device_id": "ha-esp32-001", "packet_seq": 5099, "timestamp_ms": 1700099900000,
        "mode": "real",
        "accel_x": 0.01, "accel_y": 0.02, "accel_z": 1.0,
        "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        "red_value": 50000, "ir_value": 55000,
        "heart_rate": 72.0, "spo2": 98.0, "signal_quality": 0.9,
        "imu_ok": True, "ppg_ok": True,
        "hr_valid": True, "spo2_valid": True, "finger_detected": True,
        "state_hint": "normal",
    }
    status, body = req("POST", "/ingest/device-packet", token=token, json=pkt)
    check("POST ingest with auth → 200", status == 200, str(body)[:200])
    if isinstance(body, dict):
        check(
            "personalization_result field present",
            "personalization_result" in body,
            str(list(body.keys())),
        )
else:
    check("POST ingest personalization_result (skipped)", False, "missing auth")

print("\n== 21. POST ingest → assistant_state field present ==")
if token:
    pkt = {
        "device_id": "ha-esp32-001", "packet_seq": 5100, "timestamp_ms": 1700099901000,
        "mode": "real",
        "accel_x": 0.01, "accel_y": 0.02, "accel_z": 1.0,
        "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        "red_value": 50000, "ir_value": 55000,
        "heart_rate": 72.0, "spo2": 98.0, "signal_quality": 0.9,
        "imu_ok": True, "ppg_ok": True,
        "hr_valid": True, "spo2_valid": True, "finger_detected": True,
        "state_hint": "normal",
    }
    status, body = req("POST", "/ingest/device-packet", token=token, json=pkt)
    check("POST ingest 21 → 200", status == 200, str(body)[:200])
    if isinstance(body, dict):
        check(
            "assistant_state field present in response",
            "assistant_state" in body,
            str(list(body.keys())),
        )
else:
    check("POST ingest assistant_state (skipped)", False, "missing auth")

print("\n== 22. GET /assistant/state/{user_id} → 200 ==")
if token and user_id:
    status, body = req("GET", f"/assistant/state/{user_id}", token=token)
    check("GET /assistant/state → 200", status == 200, str(body)[:200])
    if isinstance(body, dict):
        check("current_mode field present", "current_mode" in body, str(body)[:200])
else:
    check("GET /assistant/state (skipped)", False, "missing auth or user_id")

print("\n== 23. GET /assistant/actions/{user_id} → 200 ==")
if token and user_id:
    status, body = req("GET", f"/assistant/actions/{user_id}", token=token)
    check("GET /assistant/actions → 200", status == 200, str(body)[:200])
    check("response is list", isinstance(body, list), str(body)[:200])
else:
    check("GET /assistant/actions (skipped)", False, "missing auth or user_id")

print("\n== 24. GET /assistant/care-summary/{user_id} → 200 ==")
if token and user_id:
    status, body = req("GET", f"/assistant/care-summary/{user_id}", token=token)
    check("GET /assistant/care-summary → 200", status == 200, str(body)[:200])
    if isinstance(body, dict):
        check("care summary user_id correct", body.get("user_id") == user_id, str(body)[:200])
else:
    check("GET /assistant/care-summary (skipped)", False, "missing auth or user_id")

print("\n== 25. POST /assistant/ack → 200 ==")
if token and user_id:
    ack_payload = {"user_id": user_id, "response": "false_alarm", "note": "smoke test"}
    status, body = req("POST", "/assistant/ack", token=token, json=ack_payload)
    check("POST /assistant/ack → 200", status == 200, str(body)[:200])
    if isinstance(body, dict):
        check("ack success field present", "success" in body, str(body)[:200])
else:
    check("POST /assistant/ack (skipped)", False, "missing auth or user_id")

# Ozet
print("\n" + "=" * 50)
passed = sum(1 for _, ok, _ in _RESULTS if ok)
total = len(_RESULTS)
print(f"SMOKE TEST RESULTS: {passed}/{total} PASSED")
if passed < total:
    print("FAILED:")
    for name, ok, detail in _RESULTS:
        if not ok:
            print(f"  ✗ {name} — {detail}")
sys.exit(0 if passed == total else 1)
