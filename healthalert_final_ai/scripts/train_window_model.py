from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


LABEL_NAMES = {
    0: "normal",
    1: "fall",
    2: "near_fall",
    3: "instability",
    4: "bad_quality",
    5: "unknown",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a compact window model from exported windows")
    parser.add_argument("--dataset-dir", default=str(PROJECT_ROOT / "outputs" / "windowed_dataset"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "models"))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-samples", type=int, default=None)
    return parser.parse_args()


def _load_split(path: Path) -> tuple[np.ndarray, np.ndarray]:
    payload = np.load(path, allow_pickle=True)
    return payload["features"].astype(np.float32), payload["labels"].astype(np.int64)


def train_window_model(
    *,
    dataset_dir: str,
    output_dir: str,
    smoke: bool,
    max_samples: int | None = None,
) -> dict:
    ds_dir = Path(dataset_dir)
    train_x, train_y = _load_split(ds_dir / "train.npz")
    val_x, val_y = _load_split(ds_dir / "val.npz")
    test_x, test_y = _load_split(ds_dir / "test.npz")

    if smoke:
        max_keep = max_samples or min(len(train_x), 256)
        train_x = train_x[:max_keep]
        train_y = train_y[:max_keep]
        val_x = val_x[: min(len(val_x), 128)]
        val_y = val_y[: min(len(val_y), 128)]
        test_x = test_x[: min(len(test_x), 128)]
        test_y = test_y[: min(len(test_y), 128)]

    if len(train_x) == 0:
        raise RuntimeError("No training samples found in outputs/windowed_dataset/train.npz")

    classifier = LogisticRegression(max_iter=300)
    classifier.fit(train_x, train_y)

    val_pred = classifier.predict(val_x) if len(val_x) else np.array([], dtype=np.int64)
    test_pred = classifier.predict(test_x) if len(test_x) else np.array([], dtype=np.int64)

    def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
        if len(y_true) == 0:
            return {
                "accuracy": None,
                "precision": None,
                "recall": None,
                "f1": None,
                "confusion_matrix": [],
                "class_wise_recall": {},
            }
        labels = sorted(set(y_true.tolist()) | set(y_pred.tolist()))
        cm = confusion_matrix(y_true, y_pred, labels=labels)
        class_recall = {}
        for idx, label in enumerate(labels):
            denom = cm[idx].sum()
            class_recall[LABEL_NAMES.get(label, str(label))] = round(float(cm[idx, idx] / denom), 4) if denom else 0.0
        return {
            "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            "precision": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
            "confusion_matrix": cm.tolist(),
            "class_wise_recall": class_recall,
        }

    metrics = {
        "val": _metrics(val_y, val_pred),
        "test": _metrics(test_y, test_pred),
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_path / "healthalert_window_model.pt"
    with checkpoint_path.open("wb") as f:
        pickle.dump(
            {
                "artifact_type": "sklearn_logistic_regression_window_model",
                "coef_": classifier.coef_,
                "intercept_": classifier.intercept_,
                "classes_": classifier.classes_,
                "feature_dim": int(train_x.shape[1]),
            },
            f,
        )

    metadata = {
        "trained_on_datasets": ["HIFD", "WEDA_FALL", "BUT_PPG"],
        "window_sec": 4,
        "target_sample_rate_hz": 50,
        "target_sample_count": 200,
        "label_mapping": LABEL_NAMES,
        "train_size": int(len(train_x)),
        "val_size": int(len(val_x)),
        "test_size": int(len(test_x)),
        "metrics": metrics,
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "smoke_run": bool(smoke),
        "model_output_fields": [
            "fall_probability",
            "instability_probability",
            "ppg_quality_score",
            "ml_risk_score",
            "confidence",
            "model_version",
            "model_available",
        ],
    }
    (output_path / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    args = _parse_args()
    metadata = train_window_model(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        smoke=args.smoke,
        max_samples=args.max_samples,
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()