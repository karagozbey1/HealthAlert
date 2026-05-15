from src.healthalert.live.firebase_sensor_adapter import FirebaseSensorAdapter


class FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocument:
    def __init__(self, store, path):
        self.store = store
        self.path = tuple(path)

    def collection(self, name):
        return FakeCollection(self.store, self.path + (name,))

    def get(self):
        return FakeSnapshot(self.store.get(self.path))

    def set(self, data):
        self.store[self.path] = data


class FakeCollection:
    def __init__(self, store, path):
        self.store = store
        self.path = tuple(path)

    def document(self, name):
        return FakeDocument(self.store, self.path + (name,))


class FakeFirestoreClient:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return FakeCollection(self.store, (name,))


def test_firebase_adapter_gracefully_skips_without_client():
    adapter = FirebaseSensorAdapter(firestore_client=None)

    out = adapter.process_latest_sample("firebase_no_credentials")

    assert out["patient_id"] == "firebase_no_credentials"
    assert out["window_ready"] is False
    assert out["inference_triggered"] is False
    assert out["status"] == "no_firebase_sample"


def test_firebase_adapter_reads_latest_sample_path_and_adds_patient_id():
    fake = FakeFirestoreClient()
    fake.store[
        ("patients", "firebase_patient_001", "sensor_stream", "latest")
    ] = {
        "ax": 0.1,
        "ay": 0.2,
        "az": 0.3,
        "gx": 0.4,
        "gy": 0.5,
        "gz": 0.6,
    }
    adapter = FirebaseSensorAdapter(firestore_client=fake)

    sample = adapter.fetch_latest_sample("firebase_patient_001")

    assert sample is not None
    assert sample["patient_id"] == "firebase_patient_001"
    assert sample["ax"] == 0.1


def test_firebase_adapter_writes_latest_inference_result_path():
    fake = FakeFirestoreClient()
    adapter = FirebaseSensorAdapter(firestore_client=fake)

    adapter.write_inference_result("firebase_patient_002", {"risk": {"risk_level": "normal"}})

    assert fake.store[
        ("patients", "firebase_patient_002", "inference_results", "latest")
    ] == {"risk": {"risk_level": "normal"}}
