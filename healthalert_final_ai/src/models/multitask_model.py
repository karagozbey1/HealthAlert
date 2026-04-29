"""HealthAlert Multi-Task Model.

Architecture overview:
    IMU → IMUEncoder (CRNN) → imu_embed
    PPG → PPGEncoder (CNN1D) → ppg_embed → QualityGate → gated_ppg
    Vitals → VitalsMLP → vitals_embed
    [imu_embed, gated_ppg, vitals_embed] → FusionAttention → fused
    fused → FallHead    → fall_probability
    fused → InstabilityHead → instability_probability
    fused → QualityHead → ppg_quality_score
    fused → RiskHead    → early_risk_score
"""

import torch
import torch.nn as nn
from typing import Dict, Optional

from src.models.blocks.imu_encoder import IMUEncoder
from src.models.blocks.ppg_encoder import PPGEncoder
from src.models.blocks.vitals_mlp import VitalsMLP
from src.models.blocks.fusion_attention import FusionAttention
from src.models.blocks.quality_gate import QualityGate
from src.models.heads.fall_head import FallHead
from src.models.heads.instability_head import InstabilityHead
from src.models.heads.quality_head import QualityHead
from src.models.heads.risk_head import RiskHead


class HealthAlertModel(nn.Module):
    """Multi-task, multi-modal health alert model.

    Processes IMU (6-axis), PPG (1-channel), and scalar vitals
    through specialized encoders, fuses with attention, and produces
    four task-specific outputs.
    """

    def __init__(self, cfg=None):
        super().__init__()

        # Default config
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
            input_dim=vitals_cfg.get("input_dim", 3),
            hidden_dims=list(vitals_cfg.get("hidden_dims", [32, 16])),
            dropout=vitals_cfg.get("dropout", 0.2),
        )

        # === Quality Gate ===
        qg_cfg = model_cfg.get("quality_gate", {})
        self.quality_gate = QualityGate(
            ppg_dim=self.ppg_encoder.output_dim,
            quality_input_dim=vitals_cfg.get("input_dim", 3),
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
        """
        Args:
            batch: Dict with keys 'imu', 'ppg', 'vitals'
                - imu: (B, T, 6)
                - ppg: (B, T, 1)
                - vitals: (B, 3)

        Returns:
            Dict with all task outputs.
        """
        imu = batch["imu"]
        ppg = batch["ppg"]
        vitals = batch["vitals"]

        # Encode each modality
        imu_embed = self.imu_encoder(imu)          # (B, D_imu)
        ppg_embed = self.ppg_encoder(ppg)           # (B, D_ppg)
        vitals_embed = self.vitals_mlp(vitals)      # (B, D_vitals)

        # Quality gate on PPG
        gated_ppg, quality_score = self.quality_gate(ppg_embed, vitals)

        # Fuse modalities
        fused = self.fusion({
            "imu": imu_embed,
            "ppg": gated_ppg,
            "vitals": vitals_embed,
        })

        # Task heads
        fall_logit = self.fall_head(fused)              # (B, 1)
        instability_logit = self.instability_head(fused) # (B, 1)
        quality_logit = self.quality_head(fused)         # (B, 1)
        risk_score = self.risk_head(fused)               # (B, 1)

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
                "imu_encoder": {"cnn_channels": [32, 64, 128], "cnn_kernel": 5,
                                "rnn_hidden": 128, "rnn_layers": 2, "rnn_type": "gru", "dropout": 0.3},
                "ppg_encoder": {"channels": [16, 32, 64], "kernel_size": 7, "dropout": 0.2},
                "vitals_mlp": {"input_dim": 3, "hidden_dims": [32, 16], "dropout": 0.2},
                "quality_gate": {"hidden_dim": 64},
                "fusion": {"embed_dim": 128, "num_heads": 4, "dropout": 0.2},
            }
        })

    def count_parameters(self) -> int:
        """Count total trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
