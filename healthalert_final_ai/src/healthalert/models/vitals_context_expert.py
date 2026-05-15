"""
vitals_context_expert.py
─────────────────────────────────────────────────────────────────────────────
Vitals Context Expert Model

Purpose:
  Provide physiological context — NOT direct clinical diagnosis.
  Output: rest_like / active_like / poor_signal / abnormal_trend

  This model can be feature-based initially:
    - mean HR, HR variability proxy, HR slope
    - PPG quality, motion level, respiration (if available), SpO2 (if available)

  Do NOT overclaim clinical diagnosis.

Architecture option A (feature-based, recommended first):
  MLP on handcrafted vitals features

Architecture option B (signal-based):
  CNN1D on PPG/BVP waveform

Allowed datasets (from hybrid_task_routing.yaml):
  bidmc, wesad, ppg_dalia, wildppg, hifd
"""

from __future__ import annotations

import torch
import torch.nn as nn

VITALS_CONTEXT_CLASSES = ["rest_like", "active_like", "poor_signal", "abnormal_trend"]
NUM_VITALS_CLASSES = len(VITALS_CONTEXT_CLASSES)


class VitalsContextMLP(nn.Module):
    """
    Feature-based MLP vitals context classifier.
    Recommended as the first baseline (more interpretable than raw signal).

    Expected input features (default 8):
      0: mean_hr
      1: hr_std (variability proxy)
      2: hr_slope
      3: ppg_quality_score
      4: motion_level
      5: respiration_rate (0 if unavailable)
      6: spo2 (0 if unavailable)
      7: window_index_normalized
    """

    def __init__(
        self,
        input_dim: int = 8,
        hidden_dims: tuple[int, ...] = (64, 32),
        dropout: float = 0.2,
        num_classes: int = NUM_VITALS_CLASSES,
    ) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        in_dim = input_dim
        for h in hidden_dims:
            layers += [
                nn.Linear(in_dim, h),
                nn.LayerNorm(h),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout),
            ]
            in_dim = h
        layers.append(nn.Linear(in_dim, num_classes))
        self.net = nn.Sequential(*layers)
        self.num_classes = num_classes

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, input_dim) — feature vector
        Returns:
            dict with vitals_probs, vitals_context_score, predicted_class
        """
        logits = self.net(x)
        probs = torch.softmax(logits, dim=-1)
        # vitals_context_score: 1 - P(rest_like) - P(poor_signal)
        # Positive score means abnormal/active context
        vitals_context_score = 1.0 - probs[:, 0] - probs[:, 2]
        vitals_context_score = vitals_context_score.clamp(0.0, 1.0)
        predicted = torch.argmax(probs, dim=-1)
        return {
            "vitals_probs": probs,
            "vitals_context_score": vitals_context_score,
            "predicted_class": predicted,
            "logits": logits,
        }


class VitalsContextCNN(nn.Module):
    """
    Signal-based CNN1D vitals context classifier (for raw PPG/BVP input).
    Use this when raw PPG waveform is available.
    """

    def __init__(
        self,
        ppg_channels: int = 1,
        cnn_channels: tuple[int, ...] = (16, 32, 64),
        kernel_size: int = 7,
        dropout: float = 0.2,
        num_classes: int = NUM_VITALS_CLASSES,
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
        self.gap = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Sequential(
            nn.Linear(in_ch, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )
        self.num_classes = num_classes

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feat = self.cnn(x)
        feat = self.gap(feat).squeeze(-1)
        logits = self.classifier(feat)
        probs = torch.softmax(logits, dim=-1)
        vitals_context_score = (1.0 - probs[:, 0] - probs[:, 2]).clamp(0.0, 1.0)
        predicted = torch.argmax(probs, dim=-1)
        return {
            "vitals_probs": probs,
            "vitals_context_score": vitals_context_score,
            "predicted_class": predicted,
            "logits": logits,
        }


def build_vitals_context_expert(cfg: dict | None = None) -> nn.Module:
    """Build feature-based (MLP) or signal-based (CNN) vitals context expert."""
    cfg = cfg or {}
    mode = cfg.get("mode", "mlp")
    if mode == "cnn":
        return VitalsContextCNN(
            ppg_channels=cfg.get("ppg_channels", 1),
            cnn_channels=tuple(cfg.get("cnn_channels", [16, 32, 64])),
            kernel_size=cfg.get("kernel_size", 7),
            dropout=cfg.get("dropout", 0.2),
            num_classes=cfg.get("num_classes", NUM_VITALS_CLASSES),
        )
    return VitalsContextMLP(
        input_dim=cfg.get("input_dim", 8),
        hidden_dims=tuple(cfg.get("hidden_dims", [64, 32])),
        dropout=cfg.get("dropout", 0.2),
        num_classes=cfg.get("num_classes", NUM_VITALS_CLASSES),
    )
