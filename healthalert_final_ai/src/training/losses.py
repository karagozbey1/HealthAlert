import torch
import torch.nn as nn
import torch.nn.functional as F


# Dengesiz siniflar icin odaklanmis ikili kaybi hesaplar.
class FocalLoss(nn.Module):

    # Focal loss agirlik parametrelerini saklar.
    def __init__(self, alpha: float = 0.75, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    # Logit ve hedeflerden odaklanmis BCE kaybini hesaplar.
    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
        probs = torch.sigmoid(logits)
        p_t = probs * targets + (1 - probs) * (1 - targets)
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        focal_weight = alpha_t * (1 - p_t) ** self.gamma
        return (focal_weight * bce_loss).mean()


# Dort gorev icin agirlikli toplam kaybi tek yerde toplar.
class MultiTaskLoss(nn.Module):

    # Kayip turlerini ve gorev agirliklarini ayarlardan yukler.
    def __init__(self, cfg=None):
        super().__init__()

        if cfg is None:
            cfg = {}

        fall_cfg = cfg.get("fall_detection", {})
        self.fall_type = str(fall_cfg.get("type", "focal")).lower()
        self.fall_loss = FocalLoss(
            alpha=fall_cfg.get("alpha", 0.75),
            gamma=fall_cfg.get("gamma", 2.0),
        )
        self.fall_weight = fall_cfg.get("weight", 1.0)

        inst_cfg = cfg.get("instability", {})
        self.instability_weight = inst_cfg.get("weight", 0.5)
        inst_pos_weight = inst_cfg.get("pos_weight", 5.0)
        self.instability_pos_weight = torch.tensor([inst_pos_weight], dtype=torch.float32)

        qual_cfg = cfg.get("ppg_quality", {})
        self.quality_type = str(qual_cfg.get("type", "bce")).lower()
        self.quality_weight = qual_cfg.get("weight", 0.3)
        qual_pos_weight = qual_cfg.get("pos_weight", None)
        self.quality_pos_weight = (
            torch.tensor([qual_pos_weight], dtype=torch.float32)
            if qual_pos_weight is not None else None
        )

        risk_cfg = cfg.get("risk_score", {})
        self.risk_type = str(risk_cfg.get("type", "mse")).lower()
        self.risk_weight = risk_cfg.get("weight", 0.4)

    # Etkin gorevlere gore toplam ve alt kayiplari hesaplar.
    def forward(
        self,
        outputs: dict,
        targets: dict,
        active_tasks: list = None,
    ) -> tuple:
        if active_tasks is None:
            active_tasks = ["fall", "instability", "quality", "risk"]

        losses = {}
        total = torch.tensor(0.0, device=outputs["fall_logit"].device)

        # Dusme gorevi icin secilen kayip tipini uygular.
        if "fall" in active_tasks:
            if self.fall_type == "ce":
            # Tek logit cikisini iki sinifli CE bicimine cevirir.
                fall_logits_2c = torch.stack([-outputs["fall_logit"], outputs["fall_logit"]], dim=1)
                fall_target_int = targets["fall_label"].long()
                losses["fall"] = F.cross_entropy(fall_logits_2c, fall_target_int)
            elif self.fall_type == "bce":
                losses["fall"] = F.binary_cross_entropy_with_logits(
                    outputs["fall_logit"], targets["fall_label"]
                )
            else:
                losses["fall"] = self.fall_loss(outputs["fall_logit"], targets["fall_label"])
            total = total + self.fall_weight * losses["fall"]

        # Dengesizlik gorevi icin sinif agirlikli BCE uygular.
        if "instability" in active_tasks:
            pw = self.instability_pos_weight.to(outputs["instability_logit"].device)
            losses["instability"] = F.binary_cross_entropy_with_logits(
                outputs["instability_logit"], targets["instability_label"],
                pos_weight=pw,
            )
            total = total + self.instability_weight * losses["instability"]

        # PPG kalitesi icin CE ya da BCE tabanli kaybi hesaplar.
        if "quality" in active_tasks:
            if self.quality_type == "ce":
                quality_logits_2c = torch.stack([-outputs["quality_logit"], outputs["quality_logit"]], dim=1)
                quality_target_int = targets["quality_label"].long()
                losses["quality"] = F.cross_entropy(quality_logits_2c, quality_target_int)
            else:
                pw = self.quality_pos_weight
                if pw is not None:
                    pw = pw.to(outputs["quality_logit"].device)
                losses["quality"] = F.binary_cross_entropy_with_logits(
                    outputs["quality_logit"], targets["quality_label"],
                    pos_weight=pw,
                )
            total = total + self.quality_weight * losses["quality"]

        # Risk skoru icin secilen regresyon kaybini uygular.
        if "risk" in active_tasks:
            if self.risk_type == "mae":
                losses["risk"] = F.l1_loss(outputs["risk_score"], targets["risk_label"])
            elif self.risk_type == "bce":
                losses["risk"] = F.binary_cross_entropy(
                    torch.sigmoid(outputs["risk_score"]), targets["risk_label"]
                )
            else:
                losses["risk"] = F.mse_loss(outputs["risk_score"], targets["risk_label"])
            total = total + self.risk_weight * losses["risk"]

        losses["total"] = total
        return total, losses
