"""HealthAlert Multi-Task Model (v2).

Architecture overview:
    IMU → IMUEncoder (CRNN) → imu_embed
    PPG → PPGEncoder (CNN1D) → ppg_embed → QualityGate → gated_ppg
    Vitals → VitalsMLP → vitals_embed
    Handcrafted → HandcraftedMLP → hc_embed
    [imu_embed, gated_ppg, vitals_embed, hc_embed] → FusionAttention → fused
    fused → FallHead    → fall_probability
    fused → InstabilityHead → instability_probability
    fused → QualityHead → ppg_quality_score
    fused → RiskHead    → early_risk_score

Missing-modality aware:
    If a modality is entirely zero / missing, the fusion attention
    learns to down-weight it via the CLS token mechanism.
"""

from typing import Dict

import torch
import torch.nn as nn

from src.models.blocks.imu_encoder import IMUEncoder
from src.models.blocks.ppg_encoder import PPGEncoder
from src.models.blocks.vitals_mlp import VitalsMLP
from src.models.blocks.handcrafted_mlp import HandcraftedMLP
from src.models.blocks.fusion_attention import FusionAttention
from src.models.blocks.quality_gate import QualityGate
from src.models.heads.fall_head import FallHead
from src.models.heads.instability_head import InstabilityHead
from src.models.heads.quality_head import QualityHead
from src.models.heads.risk_head import RiskHead


class HealthAlertModelV2(nn.Module):
    """Multi-task, multi-modal health alert model (v2).

    Adds handcrafted feature MLP branch and missing-modality support
    on top of the original HealthAlertModel.
    """

    def __init__(self, cfg=None):
        super().__init__()

        if cfg is None:
            cfg = self._default_config()

        model_cfg = cfg if not hasattr(cfg, "model") else cfg.model

        # === Encoders ===
        imu_cfg = model_cfg.get("imu_encoder", {})
        self.imu_encoder = IMUEncoder(
            in_channels=imu_cfg.get("in_channels", 6),
            cnn_channels=list(imu_cfg.get("cnn_channels", [32, 64, 128])),
            cnn_kernel=imu_cfg.get("cnn_kernel", 5),
            rnn_hidden=imu_cfg.get("rnn_hidden", 128),
            rnn_layers=imu_cfg.get("rnn_layers", 2),
            rnn_type=imu_cfg.get("rnn_type", "gru"),
            dropout=imu_cfg.get("dropout", 0.3),
        )

        ppg_cfg = model_cfg.get("ppg_encoder", {})
        self.ppg_encoder = PPGEncoder(
            in_channels=ppg_cfg.get("in_channels", 1),
            channels=list(ppg_cfg.get("channels", [16, 32, 64])),
            kernel_size=ppg_cfg.get("kernel_size", 7),
            dropout=ppg_cfg.get("dropout", 0.2),
        )

        vitals_cfg = model_cfg.get("vitals_mlp", {})
        self.vitals_mlp = VitalsMLP(
            input_dim=vitals_cfg.get("input_dim", 2),
            hidden_dims=list(vitals_cfg.get("hidden_dims", [32, 16])),
            dropout=vitals_cfg.get("dropout", 0.2),
        )

        # Handcrafted feature branch (new in v2)
        hc_cfg = model_cfg.get("handcrafted_mlp", {})
        self.handcrafted_mlp = HandcraftedMLP(
            input_dim=hc_cfg.get("input_dim", 38),
            hidden_dims=list(hc_cfg.get("hidden_dims", [64, 32])),
            dropout=hc_cfg.get("dropout", 0.3),
        )

        # === Quality Gate ===
        qg_cfg = model_cfg.get("quality_gate", {})
        self.quality_gate = QualityGate(
            ppg_dim=self.ppg_encoder.output_dim,
            quality_input_dim=vitals_cfg.get("input_dim", 2),
            hidden_dim=qg_cfg.get("hidden_dim", 64),
        )

        # === Fusion ===
        fusion_cfg = model_cfg.get("fusion", {})
        embed_dim = fusion_cfg.get("embed_dim", 128)

        self.fusion = FusionAttention(
            modality_dims={
                "imu": self.imu_encoder.output_dim,
                "ppg": self.ppg_encoder.output_dim,
                "vitals": self.vitals_mlp.output_dim,
                "handcrafted": self.handcrafted_mlp.output_dim,
            },
            embed_dim=embed_dim,
            num_heads=fusion_cfg.get("num_heads", 4),
            dropout=fusion_cfg.get("dropout", 0.2),
        )

        # === Task Heads ===
        self.fall_head = FallHead(input_dim=embed_dim)
        self.instability_head = InstabilityHead(input_dim=embed_dim)
        self.quality_head = QualityHead(input_dim=embed_dim)
        self.risk_head = RiskHead(input_dim=embed_dim)

    def forward(self, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Forward pass.

        Args:
            batch: Dict with keys:
                - imu: (B, T, 6)
                - ppg: (B, T, 1)
                - vitals: (B, 3)
                - handcrafted_features: (B, D_hc)  — optional, zeros if missing

        Returns:
            Dict with all task outputs.
        """
        imu = batch["imu"]
        ppg = batch["ppg"]
        vitals = batch["vitals"]

        # Handcrafted features (optional)
        if "handcrafted_features" in batch:
            hc_input = batch["handcrafted_features"]
        else:
            hc_input = torch.zeros(
                imu.size(0), self.handcrafted_mlp.mlp[0].in_features,
                device=imu.device, dtype=imu.dtype,
            )

        # Modality availability masks (B,)
        modality_mask = {}
        if "modality_mask" in batch:
            modality_mask = {
                "imu": batch["modality_mask"][:, 0],
                "ppg": batch["modality_mask"][:, 1],
                "vitals": batch["modality_mask"][:, 2],
                "handcrafted": batch["modality_mask"][:, 3],
            }
        else:
            # Fallback heuristic if mask not provided by the dataset.
            modality_mask = {
                "imu": (imu.abs().sum(dim=(1, 2)) > 0).float(),
                "ppg": (ppg.abs().sum(dim=(1, 2)) > 0).float(),
                "vitals": (vitals.abs().sum(dim=1) > 0).float(),
                "handcrafted": (hc_input.abs().sum(dim=1) > 0).float(),
            }

        # Encode each modality
        imu_embed = self.imu_encoder(imu)            # (B, D_imu)
        ppg_embed = self.ppg_encoder(ppg)             # (B, D_ppg)
        vitals_embed = self.vitals_mlp(vitals)        # (B, D_vitals)
        hc_embed = self.handcrafted_mlp(hc_input)     # (B, D_hc)

        # Quality gate on PPG
        gated_ppg, quality_score = self.quality_gate(ppg_embed, vitals)
        gated_ppg = gated_ppg * modality_mask["ppg"].unsqueeze(1)

        # Fuse all modalities
        fused = self.fusion(
            {
                "imu": imu_embed,
                "ppg": gated_ppg,
                "vitals": vitals_embed,
                "handcrafted": hc_embed,
            },
            modality_mask=modality_mask,
        )

        # Task heads
        fall_logit = self.fall_head(fused)
        instability_logit = self.instability_head(fused)
        quality_logit = self.quality_head(fused)
        risk_score = self.risk_head(fused)

        return {
            "fall_logit": fall_logit.squeeze(-1),
            "instability_logit": instability_logit.squeeze(-1),
            "quality_logit": quality_logit.squeeze(-1),
            "risk_score": risk_score.squeeze(-1),
            "quality_gate_score": quality_score.squeeze(-1),
            "fused_embedding": fused,
        }

    def _default_config(self):
        """Return default model config as a dict."""
        from omegaconf import OmegaConf
        return OmegaConf.create({
            "model": {
                "imu_encoder": {
                    "cnn_channels": [32, 64, 128], "cnn_kernel": 5,
                    "rnn_hidden": 128, "rnn_layers": 2, "rnn_type": "gru",
                    "dropout": 0.3,
                },
                "ppg_encoder": {
                    "channels": [16, 32, 64], "kernel_size": 7, "dropout": 0.2,
                },
                "vitals_mlp": {
                    "input_dim": 2, "hidden_dims": [32, 16], "dropout": 0.2,
                },
                "handcrafted_mlp": {
                    "input_dim": 38, "hidden_dims": [64, 32], "dropout": 0.3,
                },
                "quality_gate": {"hidden_dim": 64},
                "fusion": {"embed_dim": 128, "num_heads": 4, "dropout": 0.2},
            }
        })

    def count_parameters(self) -> int:
        """Count total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def freeze_encoders(self) -> None:
        """Freeze encoder weights (useful for stage-wise training)."""
        for module in [self.imu_encoder, self.ppg_encoder]:
            for param in module.parameters():
                param.requires_grad = False

    def unfreeze_all(self) -> None:
        """Unfreeze all parameters."""
        for param in self.parameters():
            param.requires_grad = True
