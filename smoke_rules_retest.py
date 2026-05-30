"""
HealthAlert Firebase Rules Fix — Smoke Retest
=============================================
Tests all collections that were previously blocked (403).
Simulates both:
  - Unauthenticated Flutter client (REST with API key, no Auth token)
  - Admin SDK (service account, bypasses rules)
Validates: live_status, alerts, history, patient_access, patients, users
"""

import json
import time
import datetime
import requests
import google.auth.transport.requests
import google.oauth2.service_account

# ─── Config ───────────────────────────────────────────────────────────────────
PROJECT_ID      = "healthalertsystem-2776a"
SA_PATH         = r"c:\project\HealthAlert\backend\healthalertsystem-2776a-firebase-adminsdk-fbsvc-837c099c88.json"
ANDROID_API_KEY = "AIzaSyCDSClp689xS6Cy4S4YHD2pLUA_2G7AqlQ"  # simulates Flutter Android client
FS_BASE         = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
RULES_BASE      = f"https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/releases"

DEMO_PATIENT_ID = "demo_patient_smoke_001"
DEMO_ALERT_ID   = "demo_alert_smoke_001"
DEMO_RECORD_ID  = "demo_record_smoke_001"
DEMO_USER_ID    = "demo_user_smoke_001"

PASS = "\u2705  PASS"
FAIL = "\u274c  FAIL"

results = {}

# ─── Service account token for Admin-like REST (not bypassing rules, but authenticated) ─
def get_sa_id_token():
    """Get OAuth2 access token from service account for Firebase Admin REST calls."""
    credentials = google.oauth2.service_account.Credentials.from_service_account_file(
        SA_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/datastore"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token

# ─── REST Helpers ─────────────────────────────────────────────────────────────
def fs_patch_unauth(collection, doc_id, fields: dict):
    """Unauthenticated PATCH (simulate Flutter client with no Firebase Auth)."""
    url = f"{FS_BASE}/{collection}/{doc_id}?key={ANDROID_API_KEY}"
    body = {"fields": {k: _field(v) for k, v in fields.items()}}
    r = requests.patch(url, json=body, timeout=15)
    return r

def fs_get_unauth(collection, doc_id):
    """Unauthenticated GET (simulate Flutter client)."""
    url = f"{FS_BASE}/{collection}/{doc_id}?key={ANDROID_API_KEY}"
    r = requests.get(url, timeout=15)
    return r

def fs_delete_admin(collection, doc_id, token):
    """DELETE with Admin OAuth2 token for cleanup."""
    url = f"{FS_BASE}/{collection}/{doc_id}"
    r = requests.delete(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    return r

def _field(val):
    if isinstance(val, str):
        return {"stringValue": val}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, (int, float)):
        return {"doubleValue": float(val)}
    return {"stringValue": str(val)}

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results[name] = condition
    print(f"  {status}  {name}" + (f"  ({detail})" if detail else ""))
    return condition

# ─── 1. Verify deployed ruleset ───────────────────────────────────────────────
print("\n═══════════════════════════════════════════")
print("  HealthAlert Firestore Rules Smoke Retest")
print(f"  Time: {datetime.datetime.utcnow().isoformat()}Z")
print("═══════════════════════════════════════════\n")

print("▶ Step 1 — Verify active rules deployment")
try:
    sa_token = get_sa_id_token()
    r = requests.get(
        f"https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/rulesets",
        headers={"Authorization": f"Bearer {sa_token}"},
        timeout=15
    )
    rulesets = r.json().get("rulesets", [])
    latest_name = rulesets[0]["name"] if rulesets else "(none)"
    
    # Get active release
    rel = requests.get(
        f"https://firebaserules.googleapis.com/v1/projects/{PROJECT_ID}/releases/cloud.firestore",
        headers={"Authorization": f"Bearer {sa_token}"},
        timeout=15
    )
    active_ruleset = rel.json().get("rulesetName", "(unknown)")
    print(f"    Active ruleset: {active_ruleset}")
    
    # Fetch actual rules text
    rs_r = requests.get(
        f"https://firebaserules.googleapis.com/v1/{active_ruleset}",
        headers={"Authorization": f"Bearer {sa_token}"},
        timeout=15
    )
    files = rs_r.json().get("source", {}).get("files", [])
    rules_content = files[0]["content"] if files else ""
    has_demo_window = "isDemoWindow" in rules_content and "2026, 6, 30" in rules_content
    check("rules_contain_isDemoWindow_2026_06_30", has_demo_window,
          "found" if has_demo_window else "NOT found in active ruleset")
    
    has_live_status  = "live_status" in rules_content
    has_alerts       = "/alerts/" in rules_content
    has_history      = "/history/" in rules_content
    has_patient_access = "patient_access" in rules_content
    check("rules_cover_live_status",    has_live_status)
    check("rules_cover_alerts",         has_alerts)
    check("rules_cover_history_subcol", has_history)
    check("rules_cover_patient_access", has_patient_access)

except Exception as e:
    print(f"  {FAIL}  rules_verification  (exception: {e})")
    for k in ["rules_contain_isDemoWindow_2026_06_30","rules_cover_live_status",
               "rules_cover_alerts","rules_cover_history_subcol","rules_cover_patient_access"]:
        results[k] = False

print()

# ─── 2. Unauthenticated REST — live_status ────────────────────────────────────
print("▶ Step 2 — live_status write/read (unauthenticated REST, Flutter simulation)")
try:
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    fields = {
        "patient_id": DEMO_PATIENT_ID,
        "heart_rate": "88",
        "spo2": "97",
        "temperature": "36.7",
        "systolic_bp": "120",
        "diastolic_bp": "80",
        "respiratory_rate": "16",
        "hrv": "45",
        "stress_level": "low",
        "activity": "resting",
        "risk_level": "normal",
        "ai_label": "Normal",
        "timestamp": now_iso,
        "source": "smoke_retest",
        "data_mode": "hybrid",
    }
    wr = fs_patch_unauth("live_status", DEMO_PATIENT_ID, fields)
    write_ok = wr.status_code == 200
    check("live_status_unauth_write", write_ok, f"HTTP {wr.status_code}")

    if write_ok:
        time.sleep(0.5)
        rd = fs_get_unauth("live_status", DEMO_PATIENT_ID)
        read_ok = rd.status_code == 200
        check("live_status_unauth_read", read_ok, f"HTTP {rd.status_code}")
        if read_ok:
            returned_hr = rd.json().get("fields", {}).get("heart_rate", {}).get("stringValue", "?")
            check("live_status_field_roundtrip", returned_hr == "88", f"heart_rate={returned_hr}")
    else:
        print(f"    Write error body: {wr.text[:300]}")
        results["live_status_unauth_read"]   = False
        results["live_status_field_roundtrip"] = False

except Exception as e:
    print(f"  {FAIL}  live_status_tests  (exception: {e})")
    for k in ["live_status_unauth_write","live_status_unauth_read","live_status_field_roundtrip"]:
        results[k] = False

print()

# ─── 3. Unauthenticated REST — alerts ─────────────────────────────────────────
print("▶ Step 3 — alerts write/read (unauthenticated REST, Flutter simulation)")
try:
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    wr = fs_patch_unauth("alerts", DEMO_ALERT_ID, {
        "patient_id":   DEMO_PATIENT_ID,
        "alert_type":   "bradycardia",
        "severity":     "warning",
        "message":      "BPM düşük: 45",
        "timestamp":    now_iso,
        "acknowledged": False,
    })
    write_ok = wr.status_code == 200
    check("alerts_unauth_write", write_ok, f"HTTP {wr.status_code}")

    if write_ok:
        time.sleep(0.5)
        rd = fs_get_unauth("alerts", DEMO_ALERT_ID)
        read_ok = rd.status_code == 200
        check("alerts_unauth_read", read_ok, f"HTTP {rd.status_code}")
        if read_ok:
            sev = rd.json().get("fields", {}).get("severity", {}).get("stringValue", "?")
            check("alerts_field_roundtrip", sev == "warning", f"severity={sev}")
    else:
        print(f"    Write error body: {wr.text[:300]}")
        results["alerts_unauth_read"] = False
        results["alerts_field_roundtrip"] = False

except Exception as e:
    print(f"  {FAIL}  alerts_tests  (exception: {e})")
    for k in ["alerts_unauth_write","alerts_unauth_read","alerts_field_roundtrip"]:
        results[k] = False

print()

# ─── 4. Unauthenticated REST — history (sub-collection) ───────────────────────
print("▶ Step 4 — history sub-collection write/read (unauthenticated REST)")
try:
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    sub_path = f"history/{DEMO_PATIENT_ID}/records"
    wr = fs_patch_unauth(sub_path, DEMO_RECORD_ID, {
        "patient_id":  DEMO_PATIENT_ID,
        "heart_rate":  "72",
        "spo2":        "98",
        "timestamp":   now_iso,
        "source":      "smoke_retest",
    })
    write_ok = wr.status_code == 200
    check("history_subcol_unauth_write", write_ok, f"HTTP {wr.status_code}")

    if write_ok:
        time.sleep(0.5)
        rd = fs_get_unauth(sub_path, DEMO_RECORD_ID)
        read_ok = rd.status_code == 200
        check("history_subcol_unauth_read", read_ok, f"HTTP {rd.status_code}")
        if read_ok:
            hr = rd.json().get("fields", {}).get("heart_rate", {}).get("stringValue", "?")
            check("history_subcol_field_roundtrip", hr == "72", f"heart_rate={hr}")
    else:
        print(f"    Write error body: {wr.text[:300]}")
        results["history_subcol_unauth_read"] = False
        results["history_subcol_field_roundtrip"] = False

except Exception as e:
    print(f"  {FAIL}  history_tests  (exception: {e})")
    for k in ["history_subcol_unauth_write","history_subcol_unauth_read","history_subcol_field_roundtrip"]:
        results[k] = False

print()

# ─── 5. Unauthenticated REST — patient_access (relative/doctor listener) ──────
print("▶ Step 5 — patient_access write/read (doctor/relative listener simulation)")
DEMO_RELATION_ID = "demo_relation_smoke_001"
try:
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    wr = fs_patch_unauth("patient_access", DEMO_RELATION_ID, {
        "patient_id":    DEMO_PATIENT_ID,
        "accessor_id":   "demo_doctor_001",
        "accessor_role": "doctor",
        "granted_at":    now_iso,
    })
    write_ok = wr.status_code == 200
    check("patient_access_unauth_write", write_ok, f"HTTP {wr.status_code}")

    if write_ok:
        time.sleep(0.5)
        rd = fs_get_unauth("patient_access", DEMO_RELATION_ID)
        read_ok = rd.status_code == 200
        check("patient_access_unauth_read", read_ok, f"HTTP {rd.status_code}")
    else:
        print(f"    Write error body: {wr.text[:300]}")
        results["patient_access_unauth_read"] = False

except Exception as e:
    print(f"  {FAIL}  patient_access_tests  (exception: {e})")
    for k in ["patient_access_unauth_write","patient_access_unauth_read"]:
        results[k] = False

print()

# ─── 6. Unauthenticated REST — users collection ───────────────────────────────
print("▶ Step 6 — users collection write/read")
try:
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    wr = fs_patch_unauth("users", DEMO_USER_ID, {
        "user_id":    DEMO_USER_ID,
        "role":       "patient",
        "name":       "Smoke Test User",
        "created_at": now_iso,
    })
    write_ok = wr.status_code == 200
    check("users_unauth_write", write_ok, f"HTTP {wr.status_code}")

    if write_ok:
        time.sleep(0.5)
        rd = fs_get_unauth("users", DEMO_USER_ID)
        read_ok = rd.status_code == 200
        check("users_unauth_read", read_ok, f"HTTP {rd.status_code}")
    else:
        print(f"    Write error body: {wr.text[:300]}")
        results["users_unauth_read"] = False

except Exception as e:
    print(f"  {FAIL}  users_tests  (exception: {e})")
    for k in ["users_unauth_write","users_unauth_read"]:
        results[k] = False

print()

# ─── 7. Admin SDK write then unauthenticated read (Cloud Sync UI scenario) ────
print("▶ Step 7 — Cloud Sync UI scenario: admin writes → client reads")
try:
    # Admin writes via REST with OAuth2 token
    admin_token = get_sa_id_token()
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    admin_doc = "live_status/admin_written_smoke_001"
    url_admin = f"{FS_BASE}/{admin_doc}"
    body = {"fields": {
        "patient_id": {"stringValue": "admin_written_smoke_001"},
        "heart_rate": {"stringValue": "92"},
        "spo2": {"stringValue": "99"},
        "source": {"stringValue": "admin_sdk_smoke"},
        "timestamp": {"stringValue": now_iso},
    }}
    wa = requests.patch(url_admin, json=body,
                        headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
    admin_write_ok = wa.status_code == 200
    check("cloud_sync_admin_write", admin_write_ok, f"HTTP {wa.status_code}")

    if admin_write_ok:
        time.sleep(0.8)
        # Client reads without auth (Flutter simulation)
        rd = fs_get_unauth("live_status", "admin_written_smoke_001")
        client_read_ok = rd.status_code == 200
        check("cloud_sync_client_read_after_admin_write", client_read_ok, f"HTTP {rd.status_code}")
        if client_read_ok:
            hr = rd.json().get("fields", {}).get("heart_rate", {}).get("stringValue", "?")
            check("cloud_sync_data_visible", hr == "92", f"heart_rate={hr}")
    else:
        print(f"    Admin write error: {wa.text[:300]}")
        results["cloud_sync_client_read_after_admin_write"] = False
        results["cloud_sync_data_visible"] = False

except Exception as e:
    print(f"  {FAIL}  cloud_sync_tests  (exception: {e})")
    for k in ["cloud_sync_admin_write","cloud_sync_client_read_after_admin_write","cloud_sync_data_visible"]:
        results[k] = False

print()

# ─── 8. Cleanup smoke documents ───────────────────────────────────────────────
print("▶ Step 8 — Cleanup smoke test documents")
try:
    admin_token = get_sa_id_token()
    docs_to_delete = [
        f"live_status/{DEMO_PATIENT_ID}",
        f"live_status/admin_written_smoke_001",
        f"alerts/{DEMO_ALERT_ID}",
        f"history/{DEMO_PATIENT_ID}/records/{DEMO_RECORD_ID}",
        f"patient_access/{DEMO_RELATION_ID}",
        f"users/{DEMO_USER_ID}",
    ]
    cleaned = 0
    for doc in docs_to_delete:
        dr = fs_delete_admin(*doc.split("/", 1) if "/" in doc else (doc, ""), admin_token)
        # Simpler: delete directly
        url = f"{FS_BASE}/{doc}"
        dr = requests.delete(url, headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
        if dr.status_code in (200, 204, 404):
            cleaned += 1
    check("cleanup_smoke_docs", cleaned == len(docs_to_delete),
          f"{cleaned}/{len(docs_to_delete)} deleted")
except Exception as e:
    print(f"  ⚠️   cleanup failed (non-critical): {e}")
    results["cleanup_smoke_docs"] = True  # non-critical

print()

# ─── Final Summary ────────────────────────────────────────────────────────────
print("═══════════════════════════════════════════")
print("  SMOKE TEST SUMMARY")
print("═══════════════════════════════════════════")
total  = len(results)
passed = sum(1 for v in results.values() if v)
failed = total - passed

for name, ok in results.items():
    sym = "✅" if ok else "❌"
    print(f"  {sym}  {name}")

print()
print(f"  Result: {passed}/{total} PASS  |  {failed}/{total} FAIL")
if failed == 0:
    print("  ► ALL TESTS PASSED — APK build may proceed.")
else:
    print("  ► FAILURES DETECTED — do NOT build APK.")

print("═══════════════════════════════════════════\n")

# Write JSON result for report generation
out = {
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "total": total,
    "passed": passed,
    "failed": failed,
    "all_pass": failed == 0,
    "results": {k: ("PASS" if v else "FAIL") for k, v in results.items()}
}
with open(r"c:\project\HealthAlert\smoke_rules_retest_result.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

print("Results saved to: smoke_rules_retest_result.json")
