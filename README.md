# HealthAlert

**Multi-layer smart wearable health monitoring system with AI-powered risk detection.**

## Architecture

| Layer | Technology | Directory | Role |
|-------|-----------|-----------|------|
| Firmware | C++ / PlatformIO / ESP32 | `firmware/` | Sensor data collection, BLE/Wi-Fi transmission |
| Mobile | Flutter / Dart | `mobile/` | BLE receiver, transport fallback, Firebase sync, UI |
| Cloud | Firebase / Firestore (**mandatory for production**) | `backend/firebase_client.py` | Shared sync surface for multi-role visibility |
| Backend | Python / FastAPI / SQLAlchemy | `backend/` | Reads from Firebase/Firestore, AI/risk/alert processing |
| AI/ML | PyTorch / multi-task CNN-RNN | `healthalert_final_ai/` | Fall detection, risk scoring, anomaly detection |
| Host Bridge | Python CLI tools (**dev/debug only**) | `host_bridge/` | USB serial debug utilities (NOT production data path) |

### Production Data Flow

```
ESP32 → BLE → Flutter Mobile App → Firebase/Firestore → FastAPI Backend → derived outputs
```

- **Primary transport:** BLE (device → phone)
- **Fallback transport:** Wi-Fi (automatic, when BLE unavailable)
- **Cloud sync:** Firebase/Firestore (mandatory for multi-role visibility)
- **Backend:** Processes data from Firebase/Firestore (not from USB/serial)
- **USB:** Power, firmware flashing, and debug only

## Quick Start (Demo Mode)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Login: `self@demo.com` / `demo1234`  
Roles: `self@demo.com` (SELF), `relative@demo.com` (RELATIVE), `doctor@demo.com` (DOCTOR)

## Final Role-Based Navigation

- SELF: `Ana Panel` · `Canlı İzleme` · `Sağlık Asistanı` · `Geçmiş` · `Ayarlar`
- RELATIVE: `Ana Panel` · `Uyarılar` · `Sağlık Asistanı` · `Geçmiş` · `Ayarlar`
- DOCTOR: `Ana Panel` · `Hastalar` · `Sağlık Asistanı` · `Uyarılar` · `Ayarlar`

Mode switch (`Canlı Mod` / `Demo Mod`) is in the bottom section of `Ayarlar`.
Header mode badge/text and header mode toggle are removed from final UI.

## Final Link / Relation Flow

- Only `SELF` can generate link codes.
- `RELATIVE` and `DOCTOR` can only redeem (enter) a code shared by `SELF`.
- Role compatibility is enforced (`RELATIVE` code can only be used by `RELATIVE`, same for `DOCTOR`).
- Duplicate relation creation is blocked.

## Demo Accounts (Teslim/Test)

- SELF: `self@demo.com` / `demo1234`
- RELATIVE: `relative@demo.com` / `demo1234`
- DOCTOR: `doctor@demo.com` / `demo1234`

## Mode Matrix

| Variable | Options | Default |
|----------|---------|---------|
| `APP_MODE` | demo / staging / production | demo |
| `DATA_MODE` | sqlite / firebase / hybrid | sqlite |
| `SENSOR_MODE` | real / mock / auto | auto |
| `AI_MODE` | real / mock / off | mock |
| `NOTIFICATION_MODE` | poll / push | poll |
| `SIMULATION_ENABLED` | auto / on / off | auto |

## Live-First, Fallback-Safe

- **BLE available** → Primary device-to-phone transport active
- **BLE unavailable** → Automatic Wi-Fi fallback transport
- **Firebase credentials present** → Firestore cloud persistence (required for production)
- **Firebase credentials absent** → SQLite local persistence, no crash (dev/demo only)
- **FCM server key present** → Push notifications active
- **FCM server key absent** → Poll-based notifications, no crash
- **Real sensors connected** → Real device packets via BLE
- **No sensors** → Simulation engine auto-runs
- **AI pipeline running** → Real risk inference
- **AI offline** → Heuristic risk scoring

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness probe |
| `GET /readiness` | Full system status |
| `GET /cloud/smoke` | Firestore connectivity test |
| `GET /push/smoke` | FCM push test |
| `POST /auth/login` | JWT authentication |
| `POST /ingest/device-packet` | Device data ingestion |
| `POST /ingest/ai-result` | AI pipeline result intake |

## Mobile App

```bash
cd mobile
flutter pub get
flutter run --dart-define=BACKEND_URL=http://YOUR_IP:8000
```

## Firmware

```bash
cd firmware
pio run                  # Build
pio run -t upload        # Flash to ESP32
pio device monitor       # Serial monitor
```

## Host Bridge Tools

```bash
cd host_bridge
python serial_reader.py --port COM3              # Capture packets
python ingestion_bridge.py --port COM3 --backend http://localhost:8000  # Forward to backend
python mock_serial_emitter.py --cycle            # Mock sensor data
python replay_tool.py --file capture.jsonl       # Replay packets
```

## Tests

```bash
cd backend && python -m pytest tests/module7/ -v   # 253 tests
cd host_bridge && python -m pytest tests/ -v        # 51 tests
cd mobile && flutter test                           # Widget/logic tests
```

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust values.  
See [CLOUD_AND_PUSH_FINALIZATION.md](CLOUD_AND_PUSH_FINALIZATION.md) for Firebase/push setup.  
See [ARCHITECTURE.md](ARCHITECTURE.md) for full system architecture.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and API reference
- [CLOUD_AND_PUSH_FINALIZATION.md](CLOUD_AND_PUSH_FINALIZATION.md) — Firebase & FCM setup guide
- [RELEASE_CANDIDATE_REPORT.md](RELEASE_CANDIDATE_REPORT.md) — Release candidate details
- [INTEGRATION_REPORT.md](INTEGRATION_REPORT.md) — Integration sprint report
- [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) — Full project documentation (TR)
