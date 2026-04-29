"""Path resolution utilities with support for both relative and absolute paths."""

from pathlib import Path
from typing import Union


def resolve_path(path: Union[str, Path], base: Union[str, Path, None] = None) -> Path:
    """Resolve a path, making it absolute if relative."""
    p = Path(path)
    if p.is_absolute():
        return p
    if base is not None:
        return Path(base) / p
    return p.resolve()


def ensure_dir(path: Union[str, Path]) -> Path:
    """Create directory if it doesn't exist and return the Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_project_root() -> Path:
    """Return the project root (healthalert_final_ai/)."""
    return Path(__file__).resolve().parent.parent.parent


def get_config_dir() -> Path:
    """Return the config directory."""
    return get_project_root() / "config"
