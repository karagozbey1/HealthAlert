import torch
import torch.optim as optim
from typing import Any


# Ayardan optimizer nesnesini uretir.
def build_optimizer(model: torch.nn.Module, cfg) -> torch.optim.Optimizer:
    name = cfg.get("name", "adamw").lower()
    lr = cfg.get("lr", 0.001)
    wd = cfg.get("weight_decay", 0.01)
    betas = tuple(cfg.get("betas", [0.9, 0.999]))

    if name == "adamw":
        return optim.AdamW(model.parameters(), lr=lr, weight_decay=wd, betas=betas)
    elif name == "adam":
        return optim.Adam(model.parameters(), lr=lr, weight_decay=wd, betas=betas)
    elif name == "sgd":
        return optim.SGD(model.parameters(), lr=lr, weight_decay=wd, momentum=0.9)
    else:
        raise ValueError(f"Unknown optimizer: {name}")


# Ayardan ogrenme orani zamanlayicisini olusturur.
def build_scheduler(optimizer: torch.optim.Optimizer, cfg) -> Any:
    name = cfg.get("name", "cosine_annealing").lower()

    if name == "cosine_annealing":
        return optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=cfg.get("T_max", 100),
            eta_min=cfg.get("eta_min", 1e-5),
        )
    elif name == "step":
        return optim.lr_scheduler.StepLR(
            optimizer,
            step_size=cfg.get("step_size", 30),
            gamma=cfg.get("gamma", 0.1),
        )
    elif name == "plateau":
        return optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="max",
            patience=cfg.get("patience", 10),
            factor=cfg.get("factor", 0.5),
        )
    else:
        return None
