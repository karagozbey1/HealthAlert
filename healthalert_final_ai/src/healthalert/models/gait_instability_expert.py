"""
gait_instability_expert.py
─────────────────────────────────────────────────────────────────────────────
Gait Instability Expert Model

Purpose:
  Detect movement instability / risky gait — NOT direct fall prediction.
  Output: gait_instability_score + stable_gait / unstable_gait class

  A single unstable window must NOT trigger a critical alert by itself.
  It increases future risk context and is combined in the Risk Fusion Engine.

Architecture:
  - CNN1D + GRU on IMU windows
  - Binary sigmoid head (stable=0, unstable=1)

Allowed datasets (from hybrid_task_routing.yaml):
  daphnet_fog, gaitpdb, pads_smartwatch_pd, bits2_geriatric_fall_hr, sisfall
"""

from __future__ import annotations

import torch
import torch.nn as nn

GAIT_CLASSES = ["stable_gait", "unstable_gait"]
NUM_GAIT_CLASSES = len(GAIT_CLASSES)


class GaitInstabilityExpertCNN(nn.Module):
    """CNN1D + GRU gait instability binary classifier."""

    def __init__(
        self,
        in_channels: int = 6,
        cnn_channels: tuple[int, ...] = (32, 64, 128),
        kernel_size: int = 5,
        gru_hidden: int = 64,
        dropout: float = 0.3,
        window_length: int = 200,
    ) -> None:
        super().__init__()

        layers: list[nn.Module] = []
        in_ch = in_channels
        for out_ch in cnn_channels:
            layers += [
                nn.Conv1d(in_ch, out_ch, kernel_size=kernel_size, padding=kernel_size // 2),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(2, 2),
                nn.Dropout(dropout),
            ]
            in_ch = out_ch
        self.cnn = nn.Sequential(*layers)
        self.gru = nn.GRU(in_ch, gru_hidden, num_layers=1, batch_first=True)
        self.classifier = nn.Sequential(
            nn.Linear(gru_hidden, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, channels, window_length)
        Returns:
            dict with gait_instability_score, stable_prob, unstable_prob, logit
        """
        feat = self.cnn(x)
        feat = feat.permute(0, 2, 1)
        _, h_n = self.gru(feat)
        h = h_n.squeeze(0)
        logit = self.classifier(h).squeeze(-1)
        unstable_prob = torch.sigmoid(logit)
        stable_prob = 1.0 - unstable_prob
        return {
            "gait_instability_score": unstable_prob,
            "unstable_prob": unstable_prob,
            "stable_prob": stable_prob,
            "logit": logit,
        }


def build_gait_instability_expert(cfg: dict | None = None) -> GaitInstabilityExpertCNN:
    cfg = cfg or {}
    return GaitInstabilityExpertCNN(
        in_channels=cfg.get("in_channels", 6),
        cnn_channels=tuple(cfg.get("cnn_channels", [32, 64, 128])),
        kernel_size=cfg.get("kernel_size", 5),
        gru_hidden=cfg.get("gru_hidden", 64),
        dropout=cfg.get("dropout", 0.3),
        window_length=cfg.get("window_length", 200),
    )
