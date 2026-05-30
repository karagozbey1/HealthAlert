"""
HealthAlert Firebase CLIENT Smoke — Prompt 3 Final
===================================================
Uses ONLY the Firestore REST API with Android API key — no backend dependency.
Simulates exactly what the Flutter Android client does: unauthenticated requests
with the project API key (same as cloud_firestore SDK internals on Android).

Tests:
  1. live_status write / read
  2. alerts write / read
  3. history sub-collection write / read
  4. live_status listener (update detection via polling — no SDK WebSocket)
  5. Cleanup
"""

import json, time, datetime, requests, sys
import google.auth.transport.requests
import google.oauth2.service_account

PROJECT_ID      = "healthalertsystem-2776a"
SA_PATH         = r"c:\project\HealthAlert\backend\healthalertsystem-2776a-firebase-adminsdk-fbsvc-837c099c88.json"
ANDROID_API_KEY = "AIzaSyCDSClp689xS6Cy4S4YHD2pLUA_2G7AqlQ"
FS_BASE         = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

PATIENT_ID   = "smoke_demo_patient"
ALERT_ID     = "smoke_alert"
RECORD_ID    = "smoke_record"

results: dict[str, bool] = {}
PASS_SYM = "✅ PASS"
FAIL_SYM = "❌ FAIL"

# ─── helpers ──────────────────────────────────────────────────────────────────
def _sa_token() -> str:
    """Firebase smoke çağrıları için servis hesabı tokenı üretir."""
    creds = google.oauth2.service_account.Credentials.from_service_account_file(
        SA_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/datastore"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

def _field(v):
    """Smoke script değerini Firestore REST field formatına dönüştürür."""
    if isinstance(v, bool):   return {"booleanValue": v}
    if isinstance(v, int):    return {"integerValue": str(v)}
    if isinstance(v, float):  return {"doubleValue": v}
    return {"stringValue": str(v)}

def _patch(collection: str, doc_id: str, data: dict, *, admin=False, token=""):
    """Smoke script içinde Firestore belgesine patch isteği gönderir."""
    url = f"{FS_BASE}/{collection}/{doc_id}"
    url += f"" if admin else f"?key={ANDROID_API_KEY}"
    headers = ({"Authorization": f"Bearer {token}"} if admin else {})
    body = {"fields": {k: _field(v) for k, v in data.items()}}
    return requests.patch(url, json=body, headers=headers, timeout=15)

def _get(collection: str, doc_id: str, *, admin=False, token=""):
    """Smoke script içinde Firestore belgesini REST API üzerinden okur."""
    url = f"{FS_BASE}/{collection}/{doc_id}"
    url += "" if admin else f"?key={ANDROID_API_KEY}"
    headers = ({"Authorization": f"Bearer {token}"} if admin else {})
    return requests.get(url, headers=headers, timeout=15)

def _delete(path: str, token: str):
    """Smoke script içinde Firestore belgesini REST API üzerinden siler."""
    return requests.delete(f"{FS_BASE}/{path}",
                           headers={"Authorization": f"Bearer {token}"}, timeout=10)

def check(name: str, ok: bool, detail: str = ""):
    """Smoke kontrol sonucunu okunabilir PASS veya FAIL satırı olarak yazdırır."""
    results[name] = ok
    sym = PASS_SYM if ok else FAIL_SYM
    suffix = f"  ({detail})" if detail else ""
    print(f"  {sym}  {name}{suffix}")
    return ok

def ts() -> str:
    """Smoke verisi için ISO zaman damgası üretir."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

# ─── header ───────────────────────────────────────────────────────────────────
print("\n══════════════════════════════════════════════════")
print("  HealthAlert Firebase CLIENT Smoke — Prompt 3")
print(f"  {ts()}")
print("══════════════════════════════════════════════════\n")

# ─── Step 0: verify active rules ──────────────────────────────────────────────
print("▶ Step 0 — Verify active Firestore rules")
try:
    token = _sa_token()
    rel = requests.get(
        f"https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/releases/cloud.firestore",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    active = rel.json().get("rulesetName", "")
    rs = requests.get(f"https://firebaserules.googleapis.com/v1/{active}",
                      headers={"Authorization": f"Bearer {token}"}, timeout=15)
    content = (rs.json().get("source", {}).get("files") or [{}])[0].get("content", "")
    ok = "isDemoWindow" in content and "2026, 6, 30" in content
    check("rules_isDemoWindow_2026_06_30_active", ok, active.split("/")[-1][:8])
except Exception as e:
    check("rules_isDemoWindow_2026_06_30_active", False, str(e))
print()

# ─── Step 1: live_status write / read ─────────────────────────────────────────
print("▶ Step 1 — live_status write / read (unauth Flutter simulation)")
ls_data = {
    "patient_id":          PATIENT_ID,
    "patient_name":        "Smoke Demo Patient",
    "heart_rate":          78,
    "hr_valid":            True,
    "spo2":                97,
    "spo2_valid":          True,
    "movement_percent":    3,
    "movement_label":      "Sakin",
    "risk_score":          12,
    "risk_level":          "normal",
    "source":              "smoke_test",
    "signal_quality":      0.95,
    "finger_detected":     True,
    "measurement_state":   "stable",
    "motion_artifact":     False,
    "updated_at":          ts(),
    "last_seen_seconds":   0,
    "is_stale":            False,
    "active_alert_count":  0,
}
try:
    wr = _patch("live_status", PATIENT_ID, ls_data)
    w_ok = check("live_status_write", wr.status_code == 200, f"HTTP {wr.status_code}")
    if not w_ok:
        print(f"    body: {wr.text[:300]}")
    time.sleep(0.5)
    rd = _get("live_status", PATIENT_ID)
    r_ok = check("live_status_read",  rd.status_code == 200, f"HTTP {rd.status_code}")
    if r_ok:
        hr = rd.json()["fields"]["heart_rate"]["integerValue"]
        check("live_status_field_hr",  str(hr) == "78", f"heart_rate={hr}")
except Exception as e:
    check("live_status_write", False, str(e))
    results.setdefault("live_status_read", False)
    results.setdefault("live_status_field_hr", False)
print()

# ─── Step 2: alerts write / read ──────────────────────────────────────────────
print("▶ Step 2 — alerts write / read")
al_data = {
    "alert_id":     ALERT_ID,
    "patient_id":   PATIENT_ID,
    "patient_name": "Smoke Demo Patient",
    "type":         "manual_help_request",
    "severity":     "medium",
    "title":        "Smoke Test Alert",
    "message":      "Smoke test",
    "acknowledged": False,
    "source":       "smoke_test",
    "created_at":   ts(),
}
try:
    wr = _patch("alerts", ALERT_ID, al_data)
    w_ok = check("alerts_write", wr.status_code == 200, f"HTTP {wr.status_code}")
    if not w_ok:
        print(f"    body: {wr.text[:300]}")
    time.sleep(0.5)
    rd = _get("alerts", ALERT_ID)
    r_ok = check("alerts_read",  rd.status_code == 200, f"HTTP {rd.status_code}")
    if r_ok:
        sev = rd.json()["fields"]["severity"]["stringValue"]
        check("alerts_field_severity", sev == "medium", f"severity={sev}")
except Exception as e:
    check("alerts_write", False, str(e))
    results.setdefault("alerts_read", False)
    results.setdefault("alerts_field_severity", False)
print()

# ─── Step 3: history sub-collection write / read ──────────────────────────────
print("▶ Step 3 — history sub-collection write / read")
hist_data = {
    "record_id":        RECORD_ID,
    "patient_id":       PATIENT_ID,
    "event_type":       "smoke",
    "heart_rate":       78,
    "spo2":             97,
    "movement_percent": 3,
    "risk_score":       12,
    "source":           "smoke_test",
    "note":             "Firestore client smoke",
    "timestamp":        ts(),
}
sub = f"history/{PATIENT_ID}/records"
try:
    wr = _patch(sub, RECORD_ID, hist_data)
    w_ok = check("history_write", wr.status_code == 200, f"HTTP {wr.status_code}")
    if not w_ok:
        print(f"    body: {wr.text[:300]}")
    time.sleep(0.5)
    rd = _get(sub, RECORD_ID)
    r_ok = check("history_read",  rd.status_code == 200, f"HTTP {rd.status_code}")
    if r_ok:
        hr = rd.json()["fields"]["heart_rate"]["integerValue"]
        check("history_field_hr", str(hr) == "78", f"heart_rate={hr}")
except Exception as e:
    check("history_write", False, str(e))
    results.setdefault("history_read", False)
    results.setdefault("history_field_hr", False)
print()

# ─── Step 4: listener smoke (update detection via REST polling) ───────────────
print("▶ Step 4 — live_status listener smoke (REST polling)")
try:
    # Update heart_rate to 79
    upd = _patch("live_status", PATIENT_ID, {"heart_rate": 79})
    if upd.status_code == 200:
        time.sleep(0.8)
        rd2 = _get("live_status", PATIENT_ID)
        if rd2.status_code == 200:
            hr2 = rd2.json()["fields"]["heart_rate"]["integerValue"]
            check("listener_update_visible", str(hr2) == "79", f"heart_rate after update={hr2}")
        else:
            check("listener_update_visible", False, f"read HTTP {rd2.status_code}")
    else:
        check("listener_update_visible", False, f"update write HTTP {upd.status_code}")
except Exception as e:
    check("listener_update_visible", False, str(e))
print()

# ─── Step 5: cleanup ──────────────────────────────────────────────────────────
print("▶ Step 5 — Cleanup smoke docs")
try:
    adm = _sa_token()
    paths = [
        f"live_status/{PATIENT_ID}",
        f"alerts/{ALERT_ID}",
        f"history/{PATIENT_ID}/records/{RECORD_ID}",
    ]
    cleaned = sum(1 for p in paths if _delete(p, adm).status_code in (200, 204, 404))
    check("cleanup", cleaned == len(paths), f"{cleaned}/{len(paths)}")
except Exception as e:
    check("cleanup", False, str(e))
print()

# ─── Summary ──────────────────────────────────────────────────────────────────
print("══════════════════════════════════════════════════")
print("  FIREBASE CLIENT SMOKE SUMMARY")
print("══════════════════════════════════════════════════")
total  = len(results)
passed = sum(1 for v in results.values() if v)
failed = total - passed
for name, ok in results.items():
    print(f"  {'✅' if ok else '❌'}  {name}")
print()
print(f"  {passed}/{total} PASS  |  {failed} FAIL")
verdict = "ALL TESTS PASSED" if failed == 0 else f"{failed} TEST(S) FAILED"
print(f"  ► {verdict}")
print("══════════════════════════════════════════════════\n")

# save JSON result
out = {
    "timestamp": ts(),
    "total": total, "passed": passed, "failed": failed,
    "all_pass": failed == 0,
    "results": {k: ("PASS" if v else "FAIL") for k, v in results.items()}
}
path = r"c:\project\HealthAlert\firebase_client_smoke_result.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"Saved: {path}")

sys.exit(0 if failed == 0 else 1)
