"""PPG Encoder: 1D CNN for PPG/heart rate signal encoding."""

import torch
import torch.nn as nn
from typing import List


class PPGEncoder(nn.Module):
    """1D CNN encoder for PPG signal.

    Input: (B, T, 1) - single-channel PPG
    Output: (B, output_dim) - encoded representation
    """

    def __init__(
        self,
        in_channels: int = 1,
        channels: List[int] = None,
        kernel_size: int = 7,
        dropout: float = 0.2,
    ):
        super().__init__()
        if channels is None:
            channels = [16, 32, 64]

        layers = []
        prev_ch = in_channels
        for ch in channels:
            layers.extend([
                nn.Conv1d(prev_ch, ch, kernel_size=kernel_size, padding=kernel_size // 2),
                nn.BatchNorm1d(ch),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(2, 2),
            ])
            prev_ch = ch

        self.cnn = nn.Sequential(*layers)
        self.output_dim = channels[-1]
        self.adaptive_pool = nn.AdaptiveAvgPool1d(1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, 1) PPG tensor.

        Returns:
            (B, output_dim) encoded representation.
        """
        x = x.permute(0, 2, 1)  # (B, 1, T)
        x = self.cnn(x)          # (B, C, T')
        x = self.adaptive_pool(x).squeeze(-1)  # (B, C)
        x = self.dropout(x)
        return x
