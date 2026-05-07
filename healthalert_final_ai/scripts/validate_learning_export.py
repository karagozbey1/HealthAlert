# Ogrenme export paketlerini denetleyip ozet rapor ureten betiktir.
# Cikis kodu 0 basariyi, 1 kritik hatayi, 2 ise yalniz uyarilari temsil eder.
from __future__ import annotations

import argparse
import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.data.loaders.learning_export_loader import (
    LearningExportLoader,
    load_all_exports,
)

REQUIRED_WINDOW_FIELDS = [
    "window_id",
    "user_id_hash",
    "device_id_hash",
    "source",
    "risk_level_at_capture",
    "final_risk_score",
    "quality_confidence",
    "training_candidate",
    "suggested_label",
    "label_confidence",
]

REQUIRED_FEEDBACK_FIELDS = [
    "feedback_id",
    "user_id_hash",
    "feedback_type",
    "feedback_source",
]

VALID_SOURCES = {"live", "demo"}
VALID_RISK_LEVELS = {"normal", "watch", "warning", "critical"}
VALID_FEEDBACK_TYPES = {
    "ok", "not_ok", "false_alarm", "sensor_error", "true_positive",
}

# Rapor satırları için tekrar eden ayraç metnini üretir.
def _sep(char: str = "-", width: int = 70) -> str:
    return char * width


# Başlık çıktısını standart biçimde ekrana yazar.
def _print_header(title: str) -> None:
    print()
    print(_sep("="))
    print(f"  {title}")
    print(_sep("="))


# Alt bölüm başlığını standart biçimde ekrana yazar.
def _print_section(title: str) -> None:
    print()
    print(_sep("-"))
    print(f"  {title}")
    print(_sep("-"))


class ValidationResult:
    # Doğrulama sırasında toplanan hata, uyarı ve bilgi satırlarını saklar.
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.infos: list[str] = []

    # Sonucun kritik hata içerip içermediğini bildirir.
    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    # Sonucun uyarı içerip içermediğini bildirir.
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    # Yeni hata mesajını sonuç listesine ekler.
    def error(self, msg: str) -> None:
        self.errors.append(msg)

    # Yeni uyarı mesajını sonuç listesine ekler.
    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    # Yeni bilgi mesajını sonuç listesine ekler.
    def info(self, msg: str) -> None:
        self.infos.append(msg)


# Tek bir export klasörünü şema ve içerik eşikleri açısından doğrular.
def validate_bundle(
    export_dir: str,
    *,
    min_candidates: int = 0,
    min_quality_confidence: float = 0.0,
    errors_only: bool = False,
) -> ValidationResult:
    result = ValidationResult()
    abs_dir = os.path.abspath(export_dir)

    if not os.path.isdir(abs_dir):
        result.error(f"Export directory does not exist: {abs_dir}")
        return result

    windows_path = os.path.join(abs_dir, "windows.jsonl")
    feedback_path = os.path.join(abs_dir, "feedback.jsonl")
    summary_path = os.path.join(abs_dir, "export_summary.json")

    if not os.path.exists(windows_path):
        result.error(f"Missing required file: windows.jsonl in {abs_dir}")
        return result
    result.info("windows.jsonl — present")

    if not os.path.exists(feedback_path):
        result.warning("feedback.jsonl — missing (no user feedback recorded, OK for new exports)")
    else:
        result.info("feedback.jsonl — present")

    if not os.path.exists(summary_path):
        result.warning("export_summary.json — missing (export incomplete or truncated)")
    else:
        result.info("export_summary.json — present")

    try:
        loader = LearningExportLoader(abs_dir).load()
    except Exception as exc:
        result.error(f"Failed to load export bundle: {exc}")
        return result

    windows = loader.windows
    feedback = loader.feedback

    schema_errors = 0
    for i, w in enumerate(windows):
        for field in REQUIRED_WINDOW_FIELDS:
            if field not in w:
                result.error(f"windows.jsonl row {i}: missing required field '{field}'")
                schema_errors += 1
                if schema_errors >= 20:
                    result.error("Too many schema errors — stopping field checks.")
                    break
        if schema_errors >= 20:
            break

        src = w.get("source")
        if src not in VALID_SOURCES:
            result.warning(
                f"windows.jsonl row {i}: unknown source '{src}' "
                f"(expected: {sorted(VALID_SOURCES)})"
            )

        risk = w.get("risk_level_at_capture")
        if risk not in VALID_RISK_LEVELS:
            result.warning(
                f"windows.jsonl row {i}: unknown risk_level_at_capture '{risk}'"
            )

        score = w.get("final_risk_score")
        if score is not None and not (0.0 <= float(score) <= 1.0):
            result.error(
                f"windows.jsonl row {i}: final_risk_score={score} out of [0,1]"
            )

        qc = w.get("quality_confidence")
        if qc is not None and not (0.0 <= float(qc) <= 1.0):
            result.error(
                f"windows.jsonl row {i}: quality_confidence={qc} out of [0,1]"
            )

    for i, fb in enumerate(feedback):
        for field in REQUIRED_FEEDBACK_FIELDS:
            if field not in fb:
                result.warning(f"feedback.jsonl row {i}: missing field '{field}'")

        fb_type = fb.get("feedback_type")
        if fb_type not in VALID_FEEDBACK_TYPES:
            result.warning(
                f"feedback.jsonl row {i}: unknown feedback_type '{fb_type}'"
            )

    stats = loader.stats_summary()
    total = stats["total_windows"]
    candidates = stats["training_candidates"]

    if total == 0:
        result.error("windows.jsonl contains 0 records — export appears empty.")
        return result

    candidate_ratio = candidates / total if total else 0.0
    if candidate_ratio < 0.05 and total > 50:
        result.warning(
            f"Only {candidates}/{total} ({candidate_ratio:.1%}) windows are "
            "training candidates. Check LEARNING_MIN_QUALITY_CONFIDENCE and "
            "source filter settings."
        )

    if min_candidates > 0 and candidates < min_candidates:
        result.error(
            f"Insufficient training candidates: got {candidates}, "
            f"required {min_candidates}."
        )

    qstats = stats["quality_confidence"]
    if qstats.get("mean", 1.0) < min_quality_confidence:
        result.warning(
            f"Mean quality_confidence {qstats['mean']:.3f} is below "
            f"requested threshold {min_quality_confidence:.3f}."
        )

    label_dist = stats["label_distribution"]
    if len(label_dist) < 2 and candidates >= 20:
        result.warning(
            f"Only 1 distinct label present among candidates: {label_dist}. "
            "Training on a single class may not improve the model."
        )

    source_dist = stats["source_distribution"]
    demo_count = source_dist.get("demo", 0)
    live_count = source_dist.get("live", 0)
    if demo_count > 0 and live_count == 0:
        result.warning(
            f"All {demo_count} windows are from 'demo' source — "
            "LEARNING_ALLOW_DEMO_AS_TRAINING=False will mark them as "
            "training_candidate=False. Collect live data for production training."
        )

    if os.path.exists(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
            declared_count = summary.get("window_count", None)
            if declared_count is not None and declared_count != total:
                result.warning(
                    f"export_summary.json declares window_count={declared_count} "
                    f"but windows.jsonl contains {total} lines."
                )
        except json.JSONDecodeError as exc:
            result.warning(f"export_summary.json could not be parsed: {exc}")

    return result


# Doğrulama sonucunu okunabilir başlıklar ve istatistiklerle ekrana basar.
def print_bundle_report(
    export_dir: str,
    result: ValidationResult,
    loader: LearningExportLoader,
    *,
    errors_only: bool = False,
) -> None:
    status = "PASSED" if result.passed else "FAILED"
    if result.passed and result.has_warnings:
        status = "PASSED (with warnings)"

    _print_header(f"Learning Export Validation — {status}")
    print(f"  Directory : {os.path.abspath(export_dir)}")

    if result.errors:
        _print_section("ERRORS")
        for err in result.errors:
            print(f"  ✗ {err}")

    if result.warnings:
        _print_section("WARNINGS")
        for w in result.warnings:
            print(f"  ⚠ {w}")

    if result.infos and not errors_only:
        _print_section("INFO")
        for info in result.infos:
            print(f"  ℹ {info}")

    if not errors_only and result.passed:
        stats = loader.stats_summary()
        _print_section("Statistics")
        print(f"  Total windows        : {stats['total_windows']}")
        print(f"  Training candidates  : {stats['training_candidates']}")
        print(f"  Total feedback events: {stats['total_feedback']}")

        _print_section("Label Distribution (training candidates)")
        label_dist = stats["label_distribution"]
        for label, count in sorted(label_dist.items()):
            print(f"  {label:12s} : {count}")

        _print_section("Risk Level Distribution (all windows)")
        risk_dist = stats["risk_level_distribution"]
        for level, count in sorted(risk_dist.items()):
            print(f"  {level:12s} : {count}")

        _print_section("Source Distribution")
        src_dist = stats["source_distribution"]
        for src, count in sorted(src_dist.items()):
            print(f"  {src:12s} : {count}")

        _print_section("Quality Confidence")
        qc = stats["quality_confidence"]
        print(f"  Mean  : {qc['mean']:.4f}")
        print(f"  Std   : {qc['std']:.4f}")
        print(f"  Min   : {qc['min']:.4f}")
        print(f"  Max   : {qc['max']:.4f}")
        print(f"  Count : {qc['count']}")

        weights = loader.compute_class_weights()
        if weights:
            _print_section("Inverse-Frequency Class Weights")
            for label, w in sorted(weights.items()):
                print(f"  {label:12s} : {w:.4f}")

    print()
    print(_sep("="))
    print(f"  Result: {status}")
    print(_sep("="))
    print()


# Komut satırı çağrısını çözüp tüm istenen export klasörlerini denetler.
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a HealthAlert learning export bundle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Exit codes")[0].strip(),
    )
    parser.add_argument(
        "export_dir",
        nargs="?",
        default=None,
        help="Path to a single export bundle directory.",
    )
    parser.add_argument(
        "--all",
        metavar="ROOT_DIR",
        default=None,
        help="Validate all export bundles under ROOT_DIR.",
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Suppress stats output — print only errors and warnings.",
    )
    parser.add_argument(
        "--min-candidates",
        type=int,
        default=0,
        metavar="N",
        help="Fail if fewer than N training candidates found.",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.0,
        metavar="Q",
        help="Warn if mean quality_confidence is below Q.",
    )

    args = parser.parse_args()

    if args.all is None and args.export_dir is None:
        parser.error("Provide either <export_dir> or --all <root_dir>.")

    dirs_to_validate: list[str] = []

    if args.all:
        root = args.all
        if not os.path.isdir(root):
            print(f"ERROR: Root directory does not exist: {root}", file=sys.stderr)
            return 1
        for entry in sorted(os.listdir(root)):
            candidate = os.path.join(root, entry)
            if os.path.isdir(candidate) and os.path.exists(
                os.path.join(candidate, "windows.jsonl")
            ):
                dirs_to_validate.append(candidate)
        if not dirs_to_validate:
            print(f"No export bundles found under: {root}", file=sys.stderr)
            return 1
        print(f"Found {len(dirs_to_validate)} export bundle(s) under {root}")
    else:
        dirs_to_validate = [args.export_dir]

    overall_passed = True
    has_any_warnings = False

    for export_dir in dirs_to_validate:
        result = validate_bundle(
            export_dir,
            min_candidates=args.min_candidates,
            min_quality_confidence=args.min_quality,
            errors_only=args.errors_only,
        )

        if result.passed:
            try:
                loader = LearningExportLoader(export_dir).load()
            except Exception:
                loader = None
        else:
            loader = None

        if loader is not None:
            print_bundle_report(
                export_dir,
                result,
                loader,
                errors_only=args.errors_only,
            )
        else:
            _print_header(
                f"Learning Export Validation — {'FAILED' if not result.passed else 'PASSED'}"
            )
            print(f"  Directory : {os.path.abspath(export_dir)}")
            if result.errors:
                _print_section("ERRORS")
                for err in result.errors:
                    print(f"  ✗ {err}")
            if result.warnings:
                _print_section("WARNINGS")
                for w in result.warnings:
                    print(f"  ⚠ {w}")
            print()

        if not result.passed:
            overall_passed = False
        if result.has_warnings:
            has_any_warnings = True

    if not overall_passed:
        return 1
    if has_any_warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
