"""I/O utilities for loading configs and saving artifacts."""

import os
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from omegaconf import OmegaConf, DictConfig


def load_yaml(path: Union[str, Path]) -> Dict[str, Any]:
    """Load a YAML file as a plain dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(*config_files: Union[str, Path]) -> DictConfig:
    """Load and merge multiple YAML config files using OmegaConf.

    Later files override earlier ones.
    """
    configs = []
    for cf in config_files:
        configs.append(OmegaConf.load(str(cf)))
    merged = OmegaConf.merge(*configs)
    OmegaConf.resolve(merged)
    return merged


def load_all_configs(config_dir: Union[str, Path, None] = None) -> DictConfig:
    """Load all standard config files (base, data, train, inference)."""
    if config_dir is None:
        from src.utils.paths import get_config_dir
        config_dir = get_config_dir()
    config_dir = Path(config_dir)

    # Ensure portable defaults: if not provided, bind project root to the
    # parent of the active config directory.
    if "HEALTHALERT_PROJECT_ROOT" not in os.environ:
        os.environ["HEALTHALERT_PROJECT_ROOT"] = str(config_dir.parent.resolve())

    files = ["base.yaml", "data.yaml", "train.yaml", "inference.yaml"]
    existing = [config_dir / f for f in files if (config_dir / f).exists()]
    return load_config(*existing)


def save_checkpoint(state: Dict[str, Any], path: Union[str, Path]) -> None:
    """Save a training checkpoint."""
    import torch
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, str(p))


def load_checkpoint(path: Union[str, Path], device: str = "cpu") -> Dict[str, Any]:
    """Load a training checkpoint."""
    import torch
    return torch.load(str(path), map_location=device)
