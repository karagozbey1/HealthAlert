import os
import random
from typing import Optional

import numpy as np


# Tum kutuphanelerde tekrar uretilebilirligi saglayacak tohum ayarini yapar.
def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


# Ortamda kullanilabilecek en uygun hesaplama cihazini secer.
def get_device(preference: str = "auto") -> "torch.device":
    import torch
    if preference == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(preference)
