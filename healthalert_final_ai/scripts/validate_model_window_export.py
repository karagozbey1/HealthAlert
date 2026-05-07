from __future__ import annotations

import argparse
import json
from collections import Counter

from src.data.loaders.model_window_export_loader import ModelWindowExportLoader


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate model-window raw export bundle."
    )
    parser.add_argument("export_dir", help="Path to outputs/model_windows/<timestamp>")
    args = parser.parse_args()

    loader = ModelWindowExportLoader(args.export_dir).load()
    summary = loader.validate()
    labeled, candidates = loader.to_training_arrays()

    mode_dist = Counter((row.get("mode") or "unknown") for row in loader.windows)
    src_dist = Counter((row.get("source") or "unknown") for row in loader.windows)
    label_dist = Counter(
        (row.get("user_feedback_label") or row.get("suggested_label") or "unlabeled")
        for row in loader.windows
    )

    output = {
        **summary,
        "mode_distribution": dict(mode_dist),
        "source_distribution": dict(src_dist),
        "label_distribution": dict(label_dist),
        "labeled_tensor_count": len(labeled),
        "candidate_tensor_count": len(candidates),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
