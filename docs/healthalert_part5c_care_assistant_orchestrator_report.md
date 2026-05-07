# HealthAlert Part 5C — Care Assistant Orchestrator Report

## Executive Summary

Part 5C transforms HealthAlert from a passive alarm system into an active personal health assistant that responds proportionally to risk level. The assistant operates in four modes (**NORMAL → WATCH → WARNING → CRITICAL**), generates mode-appropriate actions, runs a "Are you OK?" acknowledgement flow in CRITICAL mode, and notifies relatives/doctors when the user does not respond.

---

## Architecture

```
Ingested Packet
     │
     ▼
IngestRouter (ingestion_router.py)
     │  (after ML shadow, retrieval, personalization)
     ▼
CareAssistantService.evaluate_assistant_state()
     │
     ├── determine_mode(final_risk_score, severity)
     │       ← final_risk_score NEVER modified
     │
     ├── SqliteAssistantRepo.get_or_create_state()
     ├── SqliteAssistantRepo.update_state()
     └── build_actions_for_mode()
              │
              └── SqliteAssistantRepo.create_action()
                       │
                       ▼
              DevicePacketResponse
              (assistant_state, assistant_actions)
```

---

## Mode Definitions

| Mode     | Trigger                             | Monitoring Intensity | Poll Interval |
|----------|-------------------------------------|----------------------|---------------|
| NORMAL   | score < 0.30, no severity           | normal               | 60s           |
| WATCH    | score ≥ 0.30 or severity="watch"   | increased            | 10s           |
| WARNING  | score ≥ 0.60 or severity="warning" | increased            | 10s           |
| CRITICAL | score ≥ 0.80 or severity="critical"| urgent               | 1s            |

---

## Files Created / Modified

### Backend

| File | Status | Description |
|------|--------|-------------|
| `backend/models.py` | Modified | Added `AssistantState`, `AssistantAction`, `AssistantAcknowledgement` ORM models |
| `backend/schemas.py` | Modified | Added 5 Pydantic schemas; updated `DevicePacketResponse` |
| `backend/repositories/base.py` | Modified | Added `AbstractAssistantRepo` (8 abstract methods) |
| `backend/repositories/sqlite/repos.py` | Modified | Added `SqliteAssistantRepo` + 3 helper dict functions |
| `backend/repositories/sqlite/__init__.py` | Modified | Exported `SqliteAssistantRepo` |
| `backend/repositories/factory.py` | Modified | Added `assistant: Any` field to `RepoSet`; wired in all 3 builders |
| `backend/config.py` | Modified | Added 9 `ASSISTANT_*` settings |
| `backend/services/care_assistant_service.py` | **Created** | Full orchestrator service + singleton |
| `backend/routers/assistant_router.py` | Modified | Added 5 new endpoints (existing LLM endpoints untouched) |
| `backend/routers/ingestion_router.py` | Modified | Integrated care assistant after personalization block |
| `backend/_smoke_api.py` | Modified | Added smoke tests 21–25 |
| `backend/.env.demo.example` | Modified | Added `ASSISTANT_*` env vars |

### Mobile (Flutter)

| File | Status | Description |
|------|--------|-------------|
| `mobile/lib/core/models/assistant_state.dart` | **Created** | `AssistantState` + `AssistantAction` data models |
| `mobile/lib/core/services/care_assistant_service.dart` | **Created** | `getAssistantState()`, `getAssistantActions()`, `sendAssistantAck()`, `getCareSummary()` |
| `mobile/lib/ui/widgets/assistant_card.dart` | **Created** | Mode-aware card with "Are you OK?" buttons for CRITICAL |
| `mobile/lib/ui/screens/dashboard_screen.dart` | Modified | Added `_AssistantCardLoader` + `AssistantCard` above RecommendationsCard |

### Tests & Docs

| File | Status | Description |
|------|--------|-------------|
| `backend/tests/module7/test_24_care_assistant_orchestrator.py` | **Created** | 35 unit tests across 14 test classes |
| `docs/healthalert_part5c_care_assistant_orchestrator_report.md` | **Created** | This document |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/assistant/state/{user_id}` | Current assistant state |
| GET | `/assistant/actions/{user_id}` | Active (unacknowledged) actions |
| POST | `/assistant/ack` | Submit "Are you OK?" response |
| POST | `/assistant/check-timeouts` | Process due CRITICAL ack timeouts |
| GET | `/assistant/care-summary/{user_id}` | Full care summary |

All existing LLM-based endpoints (`/assistant/summary`, `/assistant/alert-explanation/{id}`, `/assistant/daily-summary`, `/assistant/trends`) remain unchanged.

---

## Critical Constraints Respected

1. **`final_risk_score` NEVER modified** — the assistant reads the risk score only as input; it never writes back to it.
2. **No ML/retrieval in mode logic** — `determine_mode()` uses only `final_risk_score` and `severity`.
3. **No tıbbi teşhis** — `safe_guidance_for_context()` returns only 6 pre-approved, non-clinical messages.
4. **Existing `assistant_service.py` untouched** — new `care_assistant_service.py` is separate.
5. **Fail-open everywhere** — all orchestrator calls in ingestion_router wrapped in `try/except`; `repos.assistant=None` returns safe defaults.
6. **All existing tests pass** — no changes to existing test files.

---

## "Are you OK?" Flow

```
CRITICAL mode entered
       │
       ├── sound_alarm action created
       └── ask_are_you_ok action created (ack_deadline = now + 30s)
                │
       ┌────────┼────────┐
       ▼        ▼        ▼
     "İyiyim"  "Yardım" "Yanlış Alarm"
       │        │        │
    WATCH    CRITICAL   WATCH/NORMAL
    mode     + notify   + false_alarm
             relatives  feedback to
             + doctor   PersonalRiskMemory
             
    (No response after 30s)
       │
    notify_relative + notify_doctor
    last_user_response = "no_response"
```

---

## Database Tables Added

### `assistant_states` (one per user)
Stores current mode, timestamps for each mode entry, ack state, monitoring intensity, and poll interval.

### `assistant_actions` (many per user)
Immutable log of every generated action. Soft-deleted via `completed_at`.

### `assistant_acknowledgements`
Records every user response to a CRITICAL prompt (ok / not_ok / false_alarm).

---

## Configuration

```env
ASSISTANT_ENABLED=true
ASSISTANT_CRITICAL_ACK_TIMEOUT_SEC=30
ASSISTANT_WATCH_DURATION_SEC=300
ASSISTANT_WARNING_GUIDANCE_COOLDOWN_SEC=120
ASSISTANT_NORMAL_POLL_INTERVAL_SEC=60
ASSISTANT_WATCH_POLL_INTERVAL_SEC=10
ASSISTANT_CRITICAL_POLL_INTERVAL_SEC=1
ASSISTANT_NOTIFY_RELATIVES_ON_NO_RESPONSE=true
ASSISTANT_NOTIFY_DOCTORS_ON_NO_RESPONSE=true
```

---

## Test Results

```
35 passed, 152 warnings in 1.13s
```

All 14 test classes pass:
- A) Mode determination (5 tests)
- B) Safe guidance — no forbidden clinical terms (4 tests)
- C) Action building per mode (5 tests)
- D) evaluate_assistant_state — all 4 modes (4 tests)
- E) handle_user_ack "ok" (2 tests)
- F) handle_user_ack "not_ok" (1 test)
- G) handle_user_ack "false_alarm" (1 test)
- H) handle_critical_timeout (2 tests)
- I) get_current_assistant_summary (1 test)
- J) final_risk_score invariance (1 test)
- K) InMemoryAssistantRepo CRUD (4 tests)
- L) Fail-open with repos.assistant=None (2 tests)
- M) Mode transition timestamps (2 tests)
- N) Action creation logic (1 test)
