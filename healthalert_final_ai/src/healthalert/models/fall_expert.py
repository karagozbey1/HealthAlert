"""
fall_expert.py
─────────────────────────────────────────────────────────────────────────────
Fall Detection Expert Model (binary: normal=0, fall=1)

Architecture:
  - Compact CNN1D feature extractor
  - Optional small GRU for temporal context
  - BatchNorm + Dropout for regularisation
  - Single sigmoid output head (fall probability)

Design decisions:
  - No multi-task shared loss (fall-only)
  - No PPG branch (IMU-only first baseline)
  - No attention mechanism initially (add only if binary baseline is stable)
  - near_fall is NOT a hard class here; it is excluded at the data loader level
  - Simple, auditable architecture to catch collapse early

Input:
  Tensor of shape (batch, channels, window_length)
  channels = 3 (acc) or 6 (acc+gyro), default 6
  window_length = 200 samples (4 s @ 50 Hz)

Output:
  {
    "fall_prob": Tensor (batch,),     # sigmoid fall probability
    "normal_prob": Tensor (batch,),   # 1 - fall_prob
    "logit": Tensor (batch,),         # raw logit before sigmoid
  }
"""

from __future__ import annotations

import torch
import torch.nn as nn


class FallExpertCNN(nn.Module):
    """Compact CNN1D + optional GRU fall detection expert."""

    def __init__(
        self,
        in_channels: int = 6,
        cnn_channels: tuple[int, ...] = (32, 64, 128),
        kernel_size: int = 5,
        use_gru: bool = True,
        gru_hidden: int = 64,
        dropout: float = 0.3,
        window_length: int = 200,
    ) -> None:
        super().__init__()

        # ── CNN stack ──────────────────────────────────────────────────────
        layers: list[nn.Module] = []
        in_ch = in_channels
        for out_ch in cnn_channels:
            layers += [
                nn.Conv1d(in_ch, out_ch, kernel_size=kernel_size, padding=kernel_size // 2),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(kernel_size=2, stride=2),
                nn.Dropout(p=dropout),
            ]
            in_ch = out_ch
        self.cnn = nn.Sequential(*layers)

        # Compute CNN output length after max-pool stages
        cnn_out_len = window_length
        for _ in cnn_channels:
            cnn_out_len = cnn_out_len // 2

        self.use_gru = use_gru
        if use_gru:
            self.gru = nn.GRU(
                input_size=in_ch,
                hidden_size=gru_hidden,
                num_layers=1,
                batch_first=True,
                dropout=0.0,  # dropout only for >1 layer
            )
            head_in = gru_hidden
        else:
            head_in = in_ch * cnn_out_len

        # ── Classifier head ────────────────────────────────────────────────
        self.fc1 = nn.Linear(head_in, 64)
        self.fc1_act = nn.ReLU(inplace=True)
        self.fc1_drop = nn.Dropout(p=dropout)
        self.fc_out = nn.Linear(64, 1)

        # Calibrate output bias to log(p_fall / p_normal).
        # This ensures sigmoid output matches the class prior at init,
        # preventing the model from collapsing to "predict all fall" in
        # early epochs due to class imbalance + pos_weight interaction.
        # Default 0.31 fall prevalence in prepared fall_detection dataset.
        import math
        p_fall = 0.31
        nn.init.constant_(self.fc_out.bias, math.log(p_fall / (1.0 - p_fall)))

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Args:
            x: (batch, channels, window_length)
        Returns:
            dict with fall_prob, normal_prob, logit
        """
        feat = self.cnn(x)  # (batch, cnn_channels[-1], reduced_len)

        if self.use_gru:
            # GRU expects (batch, seq_len, features)
            feat = feat.permute(0, 2, 1)
            _, h_n = self.gru(feat)          # h_n: (1, batch, gru_hidden)
            feat = h_n.squeeze(0)            # (batch, gru_hidden)
        else:
            feat = feat.flatten(1)           # (batch, cnn_channels[-1] * reduced_len)

        feat = self.fc1_drop(self.fc1_act(self.fc1(feat)))
        logit = self.fc_out(feat).squeeze(-1)  # (batch,)
        fall_prob = torch.sigmoid(logit)
        normal_prob = 1.0 - fall_prob

        return {
            "fall_prob": fall_prob,
            "normal_prob": normal_prob,
            "logit": logit,
        }


def build_fall_expert(cfg: dict | None = None) -> FallExpertCNN:
    """Construct FallExpertCNN from an optional config dict."""
    cfg = cfg or {}
    return FallExpertCNN(
        in_channels=cfg.get("in_channels", 6),
        cnn_channels=tuple(cfg.get("cnn_channels", [32, 64, 128])),
        kernel_size=cfg.get("kernel_size", 5),
        use_gru=cfg.get("use_gru", True),
        gru_hidden=cfg.get("gru_hidden", 64),
        dropout=cfg.get("dropout", 0.3),
        window_length=cfg.get("window_length", 200),
    )
