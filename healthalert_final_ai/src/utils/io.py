import os
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from omegaconf import OmegaConf, DictConfig


# YAML dosyasini duz Python sozlugune yukler.
def load_yaml(path: Union[str, Path]) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Birden fazla ayar dosyasini sirayla birlestirip cozer.
def load_config(*config_files: Union[str, Path]) -> DictConfig:
    configs = []
    for cf in config_files:
        configs.append(OmegaConf.load(str(cf)))
    merged = OmegaConf.merge(*configs)
    OmegaConf.resolve(merged)
    return merged


# Standart temel ayar dosyalarini bulup tek bir konfigurasyonda toplar.
def load_all_configs(config_dir: Union[str, Path, None] = None) -> DictConfig:
    if config_dir is None:
        from src.utils.paths import get_config_dir
        config_dir = get_config_dir()
    config_dir = Path(config_dir)

    # Proje koku tanimli degilse etkin config klasorunun ustunu kullanir.
    if "HEALTHALERT_PROJECT_ROOT" not in os.environ:
        os.environ["HEALTHALERT_PROJECT_ROOT"] = str(config_dir.parent.resolve())

    files = ["base.yaml", "data.yaml", "train.yaml", "inference.yaml"]
    existing = [config_dir / f for f in files if (config_dir / f).exists()]
    return load_config(*existing)


# Egitim durumunu checkpoint olarak diske kaydeder.
def save_checkpoint(state: Dict[str, Any], path: Union[str, Path]) -> None:
    import torch
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, str(p))


# Kaydedilmis checkpoint'i belirtilen cihaza yukler.
def load_checkpoint(path: Union[str, Path], device: str = "cpu") -> Dict[str, Any]:
    import torch
    return torch.load(str(path), map_location=device)
