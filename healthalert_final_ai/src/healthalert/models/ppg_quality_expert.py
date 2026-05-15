"""
ppg_quality_expert.py
─────────────────────────────────────────────────────────────────────────────
PPG Quality Expert Model

Purpose:
  Determine whether PPG/vitals signal is trustworthy.
  Does NOT diagnose disease. Only assesses signal reliability.

Architecture:
  - CNN1D on PPG/BVP signal
  - Optional motion signal as auxiliary input (if aligned)
  - Multi-class output: good_quality / bad_quality / motion_artifact / unknown

Runtime rule:
  If ppg_quality is poor → reduce vitals contribution in fusion engine
  → expose low confidence → do not make strong vitals-based decisions.

Allowed datasets (from hybrid_task_routing.yaml):
  but_ppg, ppg_dalia, wildppg, wesad, bidmc, hifd
"""

from __future__ import annotations

import torch
import torch.nn as nn

PPG_QUALITY_CLASSES = ["good_quality", "bad_quality", "motion_artifact", "unknown"]
NUM_PPG_QUALITY_CLASSES = len(PPG_QUALITY_CLASSES)


class PPGQualityExpertCNN(nn.Module):
    """CNN1D PPG quality classifier."""

    def __init__(
        self,
        ppg_channels: int = 1,
        cnn_channels: tuple[int, ...] = (16, 32, 64),
        kernel_size: int = 7,
        dropout: float = 0.2,
        num_classes: int = NUM_PPG_QUALITY_CLASSES,
        window_length: int = 200,
    ) -> None:
        super().__init__()

        layers: list[nn.Module] = []
        in_ch = ppg_channels
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

        # Global average pooling
        self.gap = nn.AdaptiveAvgPool1d(1)

        self.classifier = nn.Sequential(
            nn.Linear(in_ch, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )
        self.num_classes = num_classes

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, ppg_channels, window_length)
        Returns:
            dict with quality_probs, quality_score, predicted_class
        """
        feat = self.cnn(x)          # (batch, C, L')
        feat = self.gap(feat)       # (batch, C, 1)
        feat = feat.squeeze(-1)     # (batch, C)
        logits = self.classifier(feat)
        probs = torch.softmax(logits, dim=-1)
        # quality_score = P(good_quality)
        quality_score = probs[:, 0]
        predicted = torch.argmax(probs, dim=-1)
        return {
            "quality_probs": probs,
            "quality_score": quality_score,
            "predicted_class": predicted,
            "logits": logits,
        }


def build_ppg_quality_expert(cfg: dict | None = None) -> PPGQualityExpertCNN:
    cfg = cfg or {}
    return PPGQualityExpertCNN(
        ppg_channels=cfg.get("ppg_channels", 1),
        cnn_channels=tuple(cfg.get("cnn_channels", [16, 32, 64])),
        kernel_size=cfg.get("kernel_size", 7),
        dropout=cfg.get("dropout", 0.2),
        num_classes=cfg.get("num_classes", NUM_PPG_QUALITY_CLASSES),
        window_length=cfg.get("window_length", 200),
    )
