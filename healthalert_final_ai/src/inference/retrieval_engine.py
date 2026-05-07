from __future__ import annotations

import json
import logging
import os
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("healthalert.retrieval.engine")

_INDEX_FILE = "retrieval_index.joblib"
_SCALER_FILE = "retrieval_scaler.joblib"
_FEATURES_FILE = "retrieval_features.npy"
_METADATA_FILE = "retrieval_metadata.json"
_SUMMARY_FILE = "retrieval_build_summary.json"


# Önceden üretilmiş retrieval indeksini güvenli biçimde yükleyip sorgular.
class RetrievalEngine:

    # İndeks ve yardımcı bileşenler için başlangıç durumunu kurar.
    def __init__(self) -> None:
        self._nn = None
        self._scaler = None
        self._features: Optional[np.ndarray] = None
        self._metadata: List[Dict[str, Any]] = []
        self._summary: Dict[str, Any] = {}
        self._available: bool = False
        self._load_error: Optional[str] = None
        self._feature_dim: int = 0

    # İndeks dosyalarını yükler ve sorguya hazır duruma getirir.
    def load(self, index_dir: str) -> bool:
        try:
            import joblib
        except ImportError as exc:
            self._load_error = f"joblib not installed: {exc}"
            logger.error(self._load_error)
            return False

        try:
            idx_path = os.path.join(index_dir, _INDEX_FILE)
            scaler_path = os.path.join(index_dir, _SCALER_FILE)
            feat_path = os.path.join(index_dir, _FEATURES_FILE)
            meta_path = os.path.join(index_dir, _METADATA_FILE)
            summary_path = os.path.join(index_dir, _SUMMARY_FILE)

            if not os.path.exists(idx_path):
                self._load_error = f"Index file not found: {idx_path}"
                logger.warning(self._load_error)
                return False

            if not os.path.exists(scaler_path):
                self._load_error = f"Scaler file not found: {scaler_path}"
                logger.warning(self._load_error)
                return False

            self._nn = joblib.load(idx_path)
            self._scaler = joblib.load(scaler_path)

            if os.path.exists(feat_path):
                self._features = np.load(feat_path)

            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)

            if os.path.exists(summary_path):
                with open(summary_path, "r", encoding="utf-8") as f:
                    self._summary = json.load(f)

            self._feature_dim = int(
                self._summary.get(
                    "feature_dim",
                    self._features.shape[1] if self._features is not None else 0,
                )
            )
            self._available = True
            logger.info(
                "RetrievalEngine loaded: %d windows, feature_dim=%d, datasets=%s",
                len(self._metadata),
                self._feature_dim,
                self._summary.get("datasets_included", []),
            )
            return True

        except Exception as exc:
            self._load_error = str(exc)
            self._available = False
            logger.error("RetrievalEngine load failed: %s", exc)
            return False

    # Motorun sorguya hazır olup olmadığını bildirir.
    def is_available(self) -> bool:
        return self._available

    # Verilen özellik vektörü için en yakın örnekleri ve özet oranları döndürür.
    def query(
        self,
        feature_vector: np.ndarray,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        if not self._available:
            return {
                "retrieval_available": False,
                "error": self._load_error or "Index not loaded",
            }

        try:
            fv = np.asarray(feature_vector, dtype=np.float32).flatten()

            if self._feature_dim > 0 and len(fv) != self._feature_dim:
                return {
                    "retrieval_available": False,
                    "error": (
                        f"Feature dimension mismatch: "
                        f"got {len(fv)}, expected {self._feature_dim}"
                    ),
                }

            if not np.all(np.isfinite(fv)):
                fv = np.nan_to_num(fv, nan=0.0, posinf=0.0, neginf=0.0)

            fv_scaled = self._scaler.transform(fv.reshape(1, -1))

            actual_k = min(top_k, len(self._metadata))
            distances, indices = self._nn.kneighbors(fv_scaled, n_neighbors=actual_k)
            distances_list = distances[0].tolist()
            indices_list = indices[0].tolist()

            similar: List[Dict[str, Any]] = []
            for dist, idx in zip(distances_list, indices_list):
                m = self._metadata[idx]
                similar.append({
                    "dataset": m.get("dataset", "unknown"),
                    "subject_id": m.get("subject_id", "unknown"),
                    "scenario": m.get("scenario", "unknown"),
                    "label_group": m.get("label_group", "unknown"),
                    "risk_level_estimate": m.get("risk_level_estimate", "unknown"),
                    "distance": round(float(dist), 4),
                    "window_index": m.get("window_index", 0),
                })

            support = self.compute_support(similar)
            label_dist = self._label_distribution(similar)

            return {
                "retrieval_available": True,
                "top_k": actual_k,
                "support_score": support["support_score"],
                "fall_like_ratio": support["fall_like_ratio"],
                "near_fall_ratio": support["near_fall_ratio"],
                "normal_ratio": support["normal_ratio"],
                "label_distribution": label_dist,
                "similar_examples": similar,
            }

        except Exception as exc:
            logger.error("RetrievalEngine query error: %s", exc)
            return {
                "retrieval_available": False,
                "error": str(exc),
            }

    # Benzer pencerelerden düşme desteği oranlarını hesaplar.
    def compute_support(self, similar_items: List[Dict[str, Any]]) -> Dict[str, float]:
        if not similar_items:
            return {
                "support_score": 0.0,
                "fall_like_ratio": 0.0,
                "near_fall_ratio": 0.0,
                "normal_ratio": 0.0,
            }

        n = len(similar_items)
        fall_count = sum(1 for x in similar_items if x.get("label_group") == "fall")
        near_fall_count = sum(1 for x in similar_items if x.get("label_group") == "near_fall")
        normal_count = sum(1 for x in similar_items if x.get("label_group") == "normal")

        fall_ratio = fall_count / n
        near_fall_ratio = near_fall_count / n
        normal_ratio = normal_count / n

        support_score = min(1.0, fall_ratio + 0.5 * near_fall_ratio)

        return {
            "support_score": round(support_score, 4),
            "fall_like_ratio": round(fall_ratio, 4),
            "near_fall_ratio": round(near_fall_ratio, 4),
            "normal_ratio": round(normal_ratio, 4),
        }

    # Benzer sonuç listesini kullanıcıya gösterilebilir kısa metne çevirir.
    def explain(self, similar_items: List[Dict[str, Any]]) -> str:
        if not similar_items:
            return "No similar windows found."

        support = self.compute_support(similar_items)
        parts: List[str] = []

        if support["fall_like_ratio"] >= 0.6:
            parts.append(
                f"High fall-like pattern "
                f"({support['fall_like_ratio']:.0%} of similar windows)."
            )
        elif support["fall_like_ratio"] >= 0.3:
            parts.append(
                f"Moderate fall-like pattern "
                f"({support['fall_like_ratio']:.0%} of similar windows)."
            )

        if support["near_fall_ratio"] >= 0.3:
            parts.append(
                f"Near-fall patterns present ({support['near_fall_ratio']:.0%})."
            )

        if support["normal_ratio"] >= 0.7:
            parts.append(
                f"Mostly normal activity ({support['normal_ratio']:.0%})."
            )

        datasets = list({x.get("dataset", "?") for x in similar_items})
        parts.append(f"Sources: {', '.join(sorted(datasets))}.")

        return " ".join(parts) if parts else "Mixed pattern — insufficient evidence."

    # Benzer örneklerin etiket dağılımını oran olarak hesaplar.
    @staticmethod
    def _label_distribution(similar_items: List[Dict[str, Any]]) -> Dict[str, float]:
        if not similar_items:
            return {}
        counts = Counter(x.get("label_group", "unknown") for x in similar_items)
        n = len(similar_items)
        return {k: round(v / n, 4) for k, v in counts.items()}
