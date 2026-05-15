"""
activity_expert.py
─────────────────────────────────────────────────────────────────────────────
Activity Context Expert Model

Purpose:
  Predict movement context, NOT health risk directly.
  Output is fed to the Risk Fusion Engine as context.

Architecture:
  - CNN1D feature extractor (IMU input)
  - GRU temporal layer
  - Multi-class softmax output head

Output classes:
  0: walking
  1: sitting
  2: standing
  3: lying
  4: running
  5: stairs
  6: transition
  7: unknown

IMPORTANT:
  Activity expert must NOT generate alarms by itself.
  It provides context: e.g., "high fall_probability + lying_after_impact"
  means stronger risk than fall alone.

Allowed datasets (from hybrid_task_routing.yaml):
  uci_har, unimib_shar, umafall, mobiact, sisfall
"""

from __future__ import annotations

import torch
import torch.nn as nn

ACTIVITY_CLASSES = [
    "walking",
    "sitting",
    "standing",
    "lying",
    "running",
    "stairs",
    "transition",
    "unknown",
]
NUM_ACTIVITY_CLASSES = len(ACTIVITY_CLASSES)


class ActivityExpertCNN(nn.Module):
    """CNN1D + GRU activity context classifier."""

    def __init__(
        self,
        in_channels: int = 6,
        cnn_channels: tuple[int, ...] = (32, 64, 128),
        kernel_size: int = 5,
        gru_hidden: int = 64,
        dropout: float = 0.3,
        num_classes: int = NUM_ACTIVITY_CLASSES,
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
            nn.Linear(64, num_classes),
        )
        self.num_classes = num_classes

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, channels, window_length)
        Returns:
            dict with activity_probs (batch, num_classes), predicted_class (batch,)
        """
        feat = self.cnn(x)
        feat = feat.permute(0, 2, 1)
        _, h_n = self.gru(feat)
        h = h_n.squeeze(0)
        logits = self.classifier(h)
        probs = torch.softmax(logits, dim=-1)
        predicted = torch.argmax(probs, dim=-1)
        return {
            "activity_probs": probs,
            "predicted_class": predicted,
            "logits": logits,
        }


def build_activity_expert(cfg: dict | None = None) -> ActivityExpertCNN:
    cfg = cfg or {}
    return ActivityExpertCNN(
        in_channels=cfg.get("in_channels", 6),
        cnn_channels=tuple(cfg.get("cnn_channels", [32, 64, 128])),
        kernel_size=cfg.get("kernel_size", 5),
        gru_hidden=cfg.get("gru_hidden", 64),
        dropout=cfg.get("dropout", 0.3),
        num_classes=cfg.get("num_classes", NUM_ACTIVITY_CLASSES),
        window_length=cfg.get("window_length", 200),
    )
