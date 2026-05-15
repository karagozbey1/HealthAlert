"""HealthAlert Dataset Bulk Downloader.

Reads datasets.yaml, checks local presence, attempts automatic downloads
where possible (PhysioNet/WFDB, UCI, direct URLs), and reports manual/form
datasets without pretending to download them.

Usage:
    python scripts/download_datasets.py [--config config/datasets.yaml]
                                        [--output-dir outputs/reports]
                                        [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── project root / path setup ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent  # healthalert_final_ai/
WORKSPACE_ROOT = PROJECT_ROOT.parent  # c:/project/HealthAlert/

sys.path.insert(0, str(PROJECT_ROOT))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("healthalert.download_datasets")

# ─── Status codes ────────────────────────────────────────────────────────────
STATUS_PRESENT = "already_present"
STATUS_DOWNLOADED = "downloaded"
STATUS_PARTIAL = "partial"
STATUS_MANUAL = "manual_required"
STATUS_REQUEST = "request_required"
STATUS_FAILED = "failed"
STATUS_BLOCKED_DEP = "BLOCKED_BY_DEPENDENCY"
STATUS_SKIP = "skipped"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _resolve_local_path(raw_local_path: str, name: str = "") -> Path:
    """Resolve local_path relative to project root or workspace root.

    Mirrors the logic in build_multi_source_windowed_dataset._resolve_path.
    """
    lp = raw_local_path
    # Strip OmegaConf-style interpolations: ${paths.hifd_dir} → Data/HIFD
    if "${" in lp:
        guessed_name = (name or lp).upper().replace("-", "_")
        lp = f"Data/{guessed_name}"

    p = Path(lp)
    if p.is_absolute():
        return p

    candidates = [
        PROJECT_ROOT / lp,
        WORKSPACE_ROOT / lp,
        WORKSPACE_ROOT / "Data" / p.name,
        PROJECT_ROOT / "Data" / p.name,
        PROJECT_ROOT / "data" / "raw" / p.name,
    ]
    for c in candidates:
        if c.exists():
            return c
    # Return the most-likely path even if it doesn't exist yet
    return PROJECT_ROOT / lp


def _dir_has_files(path: Path, min_files: int = 1) -> bool:
    if not path.exists():
        return False
    return sum(1 for _ in path.rglob("*") if _.is_file()) >= min_files


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob("*") if _.is_file())


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


# ─── Downloaders ─────────────────────────────────────────────────────────────

def _try_download_physionet(
    db_name: str,
    dest_dir: Path,
    dry_run: bool = False,
) -> Tuple[str, str]:
    """Attempt to download a PhysioNet database via wfdb.dl_database."""
    try:
        import wfdb
    except ImportError:
        return STATUS_BLOCKED_DEP, "wfdb not installed"

    if dry_run:
        return STATUS_SKIP, "dry_run"

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        log.info(f"  Downloading PhysioNet db='{db_name}' → {dest_dir}")
        wfdb.dl_database(db_name, dl_dir=str(dest_dir))
        n = _count_files(dest_dir)
        return STATUS_DOWNLOADED, f"{n} files downloaded"
    except Exception as exc:
        return STATUS_FAILED, str(exc)


def _try_download_uci_har(dest_dir: Path, dry_run: bool = False) -> Tuple[str, str]:
    """Download UCI-HAR from the canonical Kaggle mirror (no auth required zip)."""
    import urllib.request

    # Primary: direct from UCI
    url = (
        "https://archive.ics.uci.edu/static/public/240/"
        "human+activity+recognition+using+smartphones.zip"
    )
    if dry_run:
        return STATUS_SKIP, "dry_run"

    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "uci_har.zip"

    try:
        log.info(f"  Downloading UCI-HAR from {url}")
        urllib.request.urlretrieve(url, zip_path)
        log.info(f"  Extracting {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        zip_path.unlink(missing_ok=True)
        n = _count_files(dest_dir)
        return STATUS_DOWNLOADED, f"{n} files extracted"
    except Exception as exc:
        return STATUS_FAILED, str(exc)


def _try_download_umafall(dest_dir: Path, dry_run: bool = False) -> Tuple[str, str]:
    """Download UMAFall CSV zip from Figshare."""
    import urllib.request

    url = "https://figshare.com/ndownloader/files/7800851"  # UMAFall zip
    if dry_run:
        return STATUS_SKIP, "dry_run"

    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "umafall.zip"
    try:
        log.info(f"  Downloading UMAFall from Figshare → {dest_dir}")
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
        zip_path.unlink(missing_ok=True)
        n = _count_files(dest_dir)
        return STATUS_DOWNLOADED, f"{n} files extracted"
    except Exception as exc:
        return STATUS_FAILED, str(exc)


def _try_download_direct(
    url: str,
    dest_dir: Path,
    filename: str = "download.zip",
    dry_run: bool = False,
    extract: bool = True,
) -> Tuple[str, str]:
    """Generic direct URL download with optional zip extraction."""
    import urllib.request

    if dry_run:
        return STATUS_SKIP, "dry_run"

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / filename
    try:
        log.info(f"  Downloading {url} → {out_path}")
        urllib.request.urlretrieve(url, out_path)
        if extract and filename.endswith(".zip") and out_path.exists():
            with zipfile.ZipFile(out_path, "r") as zf:
                zf.extractall(dest_dir)
            out_path.unlink(missing_ok=True)
        n = _count_files(dest_dir)
        return STATUS_DOWNLOADED, f"{n} files"
    except Exception as exc:
        return STATUS_FAILED, str(exc)


# ─── Per-dataset download logic ───────────────────────────────────────────────

def _check_but_ppg(cfg: Dict, dest_dir: Path, dry_run: bool) -> Dict[str, Any]:
    """BUT_PPG: present locally; wfdb enables waveform loading."""
    n = _count_files(dest_dir)
    size_mb = _dir_size_mb(dest_dir)

    try:
        import wfdb  # noqa: F401
        wfdb_ok = True
    except ImportError:
        wfdb_ok = False

    # Check for a few known waveform subdirectories
    waveform_dirs = [d for d in dest_dir.iterdir() if d.is_dir()] if dest_dir.exists() else []
    has_waveforms = len(waveform_dirs) >= 5  # expect 100+ record dirs

    if n == 0:
        return {
            "status": STATUS_MANUAL,
            "detail": "BUT_PPG directory empty – download from PhysioNet",
            "wfdb_available": wfdb_ok,
            "files": 0,
            "size_mb": 0.0,
        }

    status = STATUS_PRESENT if has_waveforms else STATUS_PARTIAL
    return {
        "status": status,
        "detail": (
            f"{n} files ({size_mb:.1f} MB), waveform dirs={len(waveform_dirs)}, "
            f"wfdb={'ok' if wfdb_ok else 'MISSING'}"
        ),
        "wfdb_available": wfdb_ok,
        "files": n,
        "size_mb": size_mb,
        "waveform_dirs_found": len(waveform_dirs),
    }


def _download_one(
    key: str,
    cfg: Dict,
    dry_run: bool,
) -> Dict[str, Any]:
    """Determine download strategy and execute for a single dataset."""
    access_type = (cfg.get("access") or {}).get("type", "manual")
    access_url = (cfg.get("access") or {}).get("url", "")
    access_status = (cfg.get("access") or {}).get("status", "missing")
    name = cfg.get("name", key)
    raw_local_path = cfg.get("local_path", f"data/raw/{key}")
    dest_dir = _resolve_local_path(raw_local_path, name=name)

    result: Dict[str, Any] = {
        "dataset": name,
        "key": key,
        "access_type": access_type,
        "url": access_url,
        "dest_dir": str(dest_dir),
    }

    # ── Already present check ────────────────────────────────────────────────
    if _dir_has_files(dest_dir, min_files=3):
        n = _count_files(dest_dir)
        size_mb = _dir_size_mb(dest_dir)
        # Special handling for BUT_PPG to check wfdb / waveforms
        if key == "but_ppg":
            r = _check_but_ppg(cfg, dest_dir, dry_run)
            result.update(r)
            return result
        result.update({
            "status": STATUS_PRESENT,
            "detail": f"{n} files, {size_mb:.1f} MB",
            "files": n,
            "size_mb": size_mb,
        })
        return result

    # ── Empty / missing – attempt download by access type ────────────────────
    if access_type == "physionet":
        # Map dataset key → PhysioNet db slug
        physionet_slugs = {
            "but_ppg": "butpvdb",
            "bidmc": "bidmc",
        }
        slug = physionet_slugs.get(key)
        if slug:
            status, detail = _try_download_physionet(slug, dest_dir, dry_run)
        else:
            status, detail = STATUS_MANUAL, "No PhysioNet slug configured"
        result.update({"status": status, "detail": detail})
        if status == STATUS_DOWNLOADED:
            result["files"] = _count_files(dest_dir)
            result["size_mb"] = _dir_size_mb(dest_dir)
        return result

    if access_type == "direct":
        # Special cases with known working download URLs
        if key == "uci_har":
            status, detail = _try_download_uci_har(dest_dir, dry_run)
        elif key == "umafall":
            status, detail = _try_download_umafall(dest_dir, dry_run)
        else:
            status = STATUS_MANUAL
            detail = f"direct URL set but no auto-downloader implemented for {key}"
        result.update({"status": status, "detail": detail})
        if status == STATUS_DOWNLOADED:
            result["files"] = _count_files(dest_dir)
            result["size_mb"] = _dir_size_mb(dest_dir)
        return result

    if access_type == "kaggle":
        # Check credentials
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if not kaggle_json.exists():
            result.update({
                "status": STATUS_MANUAL,
                "detail": "Kaggle credentials not found (~/.kaggle/kaggle.json). "
                          "Run 'kaggle auth login' or place kaggle.json.",
            })
        else:
            result.update({
                "status": STATUS_MANUAL,
                "detail": "Kaggle credentials found but Kaggle dataset slug not configured",
            })
        return result

    # manual / request_required / unknown
    manual_notes = {
        "sisfall": "Download from http://sistemic.udea.edu.co/en/research/projects/falls/ – extract to data/raw/sisfall/",
        "upfall": "Download from https://sites.google.com/up.edu.mx/har-up/ – extract to data/raw/upfall/",
        "umafall": "If auto-download failed: https://figshare.com/articles/dataset/UMAFall_Fall_Detection_Dataset/4214283 – extract to data/raw/umafall/",
        "unimib_shar": "Download from http://www.sal.disco.unimib.it/technologies/unimib-shar/ – need fall_data.mat + adl_data.mat → data/raw/unimib_shar/",
        "mobiact": "Request at https://bmi.teicrete.gr/index.php/research/mobifall – form required, free for research",
        "fallalld": "Download from https://falldataset.com/ – extract to data/raw/fallalld/",
        "ppg_dalia": "Download from https://archive.ics.uci.edu/dataset/495/ppg+dalia – extract S*.pkl files to data/raw/ppg_dalia/",
        "wesad": "Download from https://archive.ics.uci.edu/dataset/465/wesad – extract S*.pkl to data/raw/wesad/",
        "wildppg": "Clone https://github.com/EPiC-Lab/WildPPG or download parquet/h5 files → data/raw/wildppg/",
        "bidmc": "pip install wfdb then: import wfdb; wfdb.dl_database('bidmc/1.0.0', dl_dir='healthalert_final_ai/data/raw/bidmc')",
    }
    note = manual_notes.get(key, f"Manual download required – see {access_url}")
    result.update({
        "status": STATUS_MANUAL if access_type == "manual" else STATUS_REQUEST,
        "detail": note,
    })
    return result


# ─── Loader validation ───────────────────────────────────────────────────────

def _validate_loader(key: str, cfg: Dict) -> Dict[str, Any]:
    """Try importing the loader and loading a single record."""
    raw_local_path = cfg.get("local_path", f"data/raw/{key}")
    dest_dir = _resolve_local_path(raw_local_path, name=cfg.get("name", key))

    if not _dir_has_files(dest_dir, min_files=1):
        return {"loader_ok": False, "reason": "directory empty or missing"}

    try:
        from src.data.loader_registry import load_dataset_by_name  # noqa: F401
        result = load_dataset_by_name(cfg)
        if result.status in ("missing", "error", "no_data"):
            return {"loader_ok": False, "reason": f"loader returned status={result.status}, errors={result.errors[:2]}"}
        n_rec = len(result.records)
        return {
            "loader_ok": True,
            "records_loaded": n_rec,
            "reason": f"ok – {n_rec} StandardRecord(s)",
        }
    except Exception as exc:
        return {"loader_ok": False, "reason": str(exc)[:200]}


# ─── Main ────────────────────────────────────────────────────────────────────

def download_all_datasets(
    config_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if config_path is None:
        config_path = str(PROJECT_ROOT / "config" / "datasets.yaml")
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / "outputs" / "reports")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(config_path, "r", encoding="utf-8") as f:
        raw_cfg = yaml.safe_load(f)

    datasets = raw_cfg.get("datasets", {})
    results: List[Dict[str, Any]] = []
    validation: List[Dict[str, Any]] = []

    log.info(f"Processing {len(datasets)} datasets ...")
    for key, cfg in datasets.items():
        name = cfg.get("name", key)
        log.info(f"[{key.upper()}] {name}")
        r = _download_one(key, cfg, dry_run)
        log.info(f"  → {r['status']}: {r.get('detail', '')}")
        results.append(r)

    log.info("Running loader validation for available datasets ...")
    for key, cfg in datasets.items():
        raw_local_path = cfg.get("local_path", f"data/raw/{key}")
        dest_dir = _resolve_local_path(raw_local_path)
        if _dir_has_files(dest_dir, min_files=1):
            v = _validate_loader(key, cfg)
            v["dataset"] = cfg.get("name", key)
            v["key"] = key
            validation.append(v)
            log.info(f"  [{key}] loader valid={v['loader_ok']}: {v['reason']}")
        else:
            validation.append({
                "dataset": cfg.get("name", key),
                "key": key,
                "loader_ok": False,
                "reason": "no data files",
            })

    # ── Summary ──────────────────────────────────────────────────────────────
    def _by_status(s: str) -> List[str]:
        return [r["dataset"] for r in results if r.get("status") == s]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "total_datasets": len(results),
        "already_present": _by_status(STATUS_PRESENT),
        "downloaded": _by_status(STATUS_DOWNLOADED),
        "partial": _by_status(STATUS_PARTIAL),
        "manual_required": _by_status(STATUS_MANUAL),
        "request_required": _by_status(STATUS_REQUEST),
        "failed": _by_status(STATUS_FAILED),
        "blocked_by_dependency": _by_status(STATUS_BLOCKED_DEP),
        "details": results,
        "loader_validation": validation,
    }

    # ── Write JSON ────────────────────────────────────────────────────────────
    json_path = out_dir / "dataset_download_status.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Wrote {json_path}")

    # ── Write audit JSON ──────────────────────────────────────────────────────
    audit = {
        "generated_at": summary["generated_at"],
        "datasets": {
            v["key"]: {
                "loader_ok": v["loader_ok"],
                "records_loaded": v.get("records_loaded", 0),
                "reason": v["reason"],
            }
            for v in validation
        },
    }
    audit_path = out_dir / "dataset_availability_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Wrote {audit_path}")

    # ── Write Markdown download report ────────────────────────────────────────
    docs_dir = WORKSPACE_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    md_path = docs_dir / "healthalert_dataset_download_report.md"
    _write_markdown_report(summary, md_path)
    log.info(f"Wrote {md_path}")

    print(json.dumps({k: v for k, v in summary.items() if k != "details"}, indent=2, ensure_ascii=False))
    return summary


def _write_markdown_report(summary: Dict[str, Any], path: Path) -> None:
    ts = summary["generated_at"]
    lines = [
        f"# HealthAlert Dataset Download Report",
        f"",
        f"**Tarih:** {ts}  ",
        f"**Dry run:** {summary['dry_run']}  ",
        f"",
        f"---",
        f"",
        f"## Download Durumu Özeti",
        f"",
        f"| Durum | Sayı | Dataset'ler |",
        f"|-------|------|-------------|",
    ]
    groups = [
        ("already_present", "✅ Zaten Mevcut"),
        ("downloaded", "⬇️ İndirildi"),
        ("partial", "⚠️ Kısmi"),
        ("manual_required", "📋 Manuel"),
        ("request_required", "📧 İstek Gerekli"),
        ("failed", "❌ Başarısız"),
        ("blocked_by_dependency", "🔴 Bağımlılık Eksik"),
    ]
    for key, label in groups:
        items = summary.get(key, [])
        lines.append(f"| {label} | {len(items)} | {', '.join(items) if items else '—'} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Dataset Detayları",
        f"",
        f"| Dataset | Tip | Durum | Detay |",
        f"|---------|-----|-------|-------|",
    ]
    for r in summary["details"]:
        lines.append(
            f"| {r['dataset']} | {r['access_type']} | {r['status']} | {r.get('detail', '')} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## Loader Validation",
        f"",
        f"| Dataset | Loader OK | Kayıt Sayısı | Detay |",
        f"|---------|-----------|--------------|-------|",
    ]
    for v in summary["loader_validation"]:
        ok = "✅" if v["loader_ok"] else "❌"
        recs = v.get("records_loaded", "—")
        lines.append(f"| {v['dataset']} | {ok} | {recs} | {v['reason']} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Manuel İndirme Talimatları",
        f"",
    ]
    for r in summary["details"]:
        if r["status"] in (STATUS_MANUAL, STATUS_REQUEST, STATUS_FAILED):
            lines.append(f"### {r['dataset']}")
            lines.append(f"- **URL:** {r.get('url', '—')}")
            lines.append(f"- **Talimat:** {r.get('detail', '—')}")
            lines.append(f"- **Hedef klasör:** `{r.get('dest_dir', '—')}`")
            lines.append(f"")

    path.write_text("\n".join(lines), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HealthAlert dataset bulk downloader")
    p.add_argument("--config", default=None)
    p.add_argument("--output-dir", default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    download_all_datasets(
        config_path=args.config,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
