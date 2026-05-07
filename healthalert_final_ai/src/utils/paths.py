from pathlib import Path
from typing import Union


# Goreli yolları gerekirse mutlak konuma cevirir.
def resolve_path(path: Union[str, Path], base: Union[str, Path, None] = None) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    if base is not None:
        return Path(base) / p
    return p.resolve()


# Dizini yoksa olusturup Path nesnesi olarak dondurur.
def ensure_dir(path: Union[str, Path]) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# AI proje kokunu standart olarak dondurur.
def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


# Yapilandirma dosyalarinin bulundugu klasoru dondurur.
def get_config_dir() -> Path:
    return get_project_root() / "config"
