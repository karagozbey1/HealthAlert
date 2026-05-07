from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# Pencere verisinin beklenen uzunluk ve NaN kurallarini denetler.
def validate_window(data: np.ndarray, expected_length: int, name: str = "window") -> bool:
    if data.shape[0] != expected_length:
        raise ValueError(
            f"{name}: expected length {expected_length}, got {data.shape[0]}"
        )
    if np.isnan(data).all():
        raise ValueError(f"{name}: all values are NaN")
    return True


# Veri tablosunda zorunlu sutunlarin mevcut oldugunu denetler.
def validate_dataframe(
    df: pd.DataFrame,
    required_cols: List[str],
    name: str = "dataframe",
) -> bool:
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")
    return True


# Yapilandirmadaki veri yollarinin mevcut olup olmadigini kontrol eder.
def validate_config_paths(cfg) -> List[str]:
    from pathlib import Path
    warnings = []
    if hasattr(cfg, "paths"):
        for key in ["hifd_dir", "but_ppg_dir", "weda_fall_dir"]:
            p = getattr(cfg.paths, key, None)
            if p and not Path(p).exists():
                warnings.append(f"Path not found: {key} = {p}")
    return warnings
