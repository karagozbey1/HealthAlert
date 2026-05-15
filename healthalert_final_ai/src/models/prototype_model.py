"""Prototype HealthAlert multi-task model.

Compact, efficient architecture designed for:
- Fast CPU inference
- 5 task heads: fall_detection, ppg_quality, vitals_context,
  activity_context, gait_instability
- Graceful handling of missing modalities (zeroed inputs)
- Stable training with realistic accuracy targets

Architecture:
  IMUEncoder  : CNN1D(6→32→64→128) + BiGRU(128) → 256-dim
  PPGEncoder  : CNN1D(1→16→32→64) + AdaptiveAvgPool → 64-dim
  FusionProj  : Linear(320→256) + BN + ReLU
  Heads:
    fall_detection   : Linear(256, 3)          [IMU-primary]
    ppg_quality      : Linear(64, 2)           [PPG-primary]
    vitals_context   : Linear(64, 3)           [PPG-primary]
    activity_context : Linear(256, 8)  fused   [IMU+PPG]
    gait_instability : Linear(256, 2)          [IMU-primary]
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn


# ── Building blocks ──────────────────────────────────────────────────────


class _Conv1DBlock(nn.Module):
    """Conv1D → BatchNorm → ReLU → MaxPool."""

    def __init__(self, in_ch: int, out_ch: int, kernel: int, dropout: float = 0.0):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size=kernel, padding=kernel // 2),
            nn.BatchNorm1d(out_ch),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout) if dropout > 0 else nn.Identity(),
            nn.MaxPool1d(kernel_size=2, stride=2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class PrototypeIMUEncoder(nn.Module):
    """Lightweight CNN + BiGRU encoder for IMU signals.

    Input:  (B, T, 6)  — T=200 samples, 6 axes (accel_xyz + gyro_xyz)
    Output: (B, 256)   — bidirectional GRU last-step hidden
    """

    def __init__(
        self,
        in_channels: int = 6,
        cnn_channels: List[int] = (32, 64, 128),
        cnn_kernel: int = 5,
        gru_hidden: int = 128,
        gru_layers: int = 2,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        channels = list(cnn_channels)
        cnn_blocks = []
        prev = in_channels
        for ch in channels:
            cnn_blocks.append(_Conv1DBlock(prev, ch, cnn_kernel, dropout=dropout * 0.5))
            prev = ch
        self.cnn = nn.Sequential(*cnn_blocks)

        self.gru = nn.GRU(
            input_size=channels[-1],
            hidden_size=gru_hidden,
            num_layers=gru_layers,
            batch_first=True,
            dropout=dropout if gru_layers > 1 else 0.0,
            bidirectional=True,
        )
        self.output_dim: int = gru_hidden * 2  # 256
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, 6)
        x = x.permute(0, 2, 1)      # → (B, 6, T)
        x = self.cnn(x)             # → (B, 128, T')
        x = x.permute(0, 2, 1)      # → (B, T', 128)
        _, h = self.gru(x)          # h: (2*layers, B, hidden)
        # Concat last forward + last backward hidden states
        h = torch.cat([h[-2], h[-1]], dim=-1)  # (B, 256)
        return self.drop(h)


class PrototypePPGEncoder(nn.Module):
    """Lightweight CNN encoder for PPG signals.

    Input:  (B, T, 1)  — T=200 samples, 1 channel
    Output: (B, 64)
    """

    def __init__(
        self,
        in_channels: int = 1,
        channels: List[int] = (16, 32, 64),
        kernel_size: int = 7,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        chs = list(channels)
        blocks = []
        prev = in_channels
        for ch in chs:
            blocks.append(_Conv1DBlock(prev, ch, kernel_size, dropout=0.0))
            prev = ch
        self.cnn = nn.Sequential(*blocks)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.output_dim: int = chs[-1]  # 64
        self.drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, T, 1)
        x = x.permute(0, 2, 1)      # → (B, 1, T)
        x = self.cnn(x)             # → (B, 64, T')
        x = self.pool(x).squeeze(-1)  # → (B, 64)
        return self.drop(x)


# ── Main model ────────────────────────────────────────────────────────────


class PrototypeHealthAlertModel(nn.Module):
    """Compact multi-task model for HealthAlert prototype.

    Forward input dict must contain:
      "imu": (B, T, 6)
      "ppg": (B, T, 1)

    Forward returns dict of task logits:
      "fall_detection":   (B, 3)
      "ppg_quality":      (B, 2)
      "vitals_context":   (B, 3)
      "activity_context": (B, 8)
      "gait_instability": (B, 2)
    """

    # Configurable defaults matching prototype_training.yaml
    _DEFAULTS = {
        "imu_encoder": {
            "in_channels": 6,
            "cnn_channels": [32, 64, 128],
            "cnn_kernel": 5,
            "gru_hidden": 128,
            "gru_layers": 2,
            "dropout": 0.3,
        },
        "ppg_encoder": {
            "in_channels": 1,
            "channels": [16, 32, 64],
            "kernel_size": 7,
            "dropout": 0.2,
        },
        "fusion_proj_dim": 256,
    }

    def __init__(self, model_cfg: Optional[Dict] = None) -> None:
        super().__init__()

        cfg = dict(self._DEFAULTS)
        if model_cfg:
            for k, v in model_cfg.items():
                if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                    cfg[k] = {**cfg[k], **v}
                else:
                    cfg[k] = v

        imu_cfg = cfg["imu_encoder"]
        self.imu_encoder = PrototypeIMUEncoder(
            in_channels=imu_cfg["in_channels"],
            cnn_channels=imu_cfg["cnn_channels"],
            cnn_kernel=imu_cfg["cnn_kernel"],
            gru_hidden=imu_cfg["gru_hidden"],
            gru_layers=imu_cfg["gru_layers"],
            dropout=imu_cfg["dropout"],
        )

        ppg_cfg = cfg["ppg_encoder"]
        self.ppg_encoder = PrototypePPGEncoder(
            in_channels=ppg_cfg["in_channels"],
            channels=ppg_cfg["channels"],
            kernel_size=ppg_cfg["kernel_size"],
            dropout=ppg_cfg["dropout"],
        )

        imu_dim = self.imu_encoder.output_dim   # 256
        ppg_dim = self.ppg_encoder.output_dim   # 64
        fused_raw = imu_dim + ppg_dim           # 320
        proj_dim = int(cfg.get("fusion_proj_dim", 256))

        # Shared fusion projection (for multi-modal heads)
        self.fusion_proj = nn.Sequential(
            nn.Linear(fused_raw, proj_dim),
            nn.BatchNorm1d(proj_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
        )

        # ── Task heads ─────────────────────────────────────────────────────
        self.fall_detection_head = nn.Linear(imu_dim, 3)
        self.ppg_quality_head = nn.Linear(ppg_dim, 2)
        self.vitals_context_head = nn.Linear(ppg_dim, 3)
        self.activity_context_head = nn.Linear(proj_dim, 8)
        self.gait_instability_head = nn.Linear(imu_dim, 2)

    # ── Forward ───────────────────────────────────────────────────────────

    def encode(
        self, imu: torch.Tensor, ppg: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Run encoders and compute fused representation.

        Returns (imu_emb, ppg_emb, fused_emb).
        """
        imu_emb = self.imu_encoder(imu)   # (B, 256)
        ppg_emb = self.ppg_encoder(ppg)   # (B, 64)
        fused = self.fusion_proj(torch.cat([imu_emb, ppg_emb], dim=-1))  # (B, 256)
        return imu_emb, ppg_emb, fused

    def forward(self, batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        imu = batch["imu"]   # (B, 200, 6)
        ppg = batch["ppg"]   # (B, 200, 1)

        imu_emb, ppg_emb, fused = self.encode(imu, ppg)

        return {
            "fall_detection":   self.fall_detection_head(imu_emb),
            "ppg_quality":      self.ppg_quality_head(ppg_emb),
            "vitals_context":   self.vitals_context_head(ppg_emb),
            "activity_context": self.activity_context_head(fused),
            "gait_instability": self.gait_instability_head(imu_emb),
        }

    def forward_task(
        self, batch: Dict[str, torch.Tensor], task: str
    ) -> torch.Tensor:
        """Efficient single-task forward — avoids unused head computations."""
        imu = batch["imu"]
        ppg = batch["ppg"]

        if task in ("fall_detection", "gait_instability"):
            imu_emb = self.imu_encoder(imu)
            if task == "fall_detection":
                return self.fall_detection_head(imu_emb)
            return self.gait_instability_head(imu_emb)

        if task in ("ppg_quality", "vitals_context"):
            ppg_emb = self.ppg_encoder(ppg)
            if task == "ppg_quality":
                return self.ppg_quality_head(ppg_emb)
            return self.vitals_context_head(ppg_emb)

        if task == "activity_context":
            imu_emb = self.imu_encoder(imu)
            ppg_emb = self.ppg_encoder(ppg)
            fused = self.fusion_proj(torch.cat([imu_emb, ppg_emb], dim=-1))
            return self.activity_context_head(fused)

        raise ValueError(f"Unknown task: {task!r}")

    # ── Utilities ──────────────────────────────────────────────────────────

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def parameter_count_by_component(self) -> Dict[str, int]:
        return {
            "imu_encoder":          sum(p.numel() for p in self.imu_encoder.parameters()),
            "ppg_encoder":          sum(p.numel() for p in self.ppg_encoder.parameters()),
            "fusion_proj":          sum(p.numel() for p in self.fusion_proj.parameters()),
            "fall_detection_head":  sum(p.numel() for p in self.fall_detection_head.parameters()),
            "ppg_quality_head":     sum(p.numel() for p in self.ppg_quality_head.parameters()),
            "vitals_context_head":  sum(p.numel() for p in self.vitals_context_head.parameters()),
            "activity_context_head": sum(p.numel() for p in self.activity_context_head.parameters()),
            "gait_instability_head": sum(p.numel() for p in self.gait_instability_head.parameters()),
        }
