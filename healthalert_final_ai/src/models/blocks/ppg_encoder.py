import torch
import torch.nn as nn
from typing import List


# Tek kanalli PPG sinyalini CNN ile ozet temsile cevirir.
class PPGEncoder(nn.Module):

    # PPG icin konvolusyonel kodlayici yapisini kurar.
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

    # PPG penceresini sabit boyutlu ozellige indirger.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.permute(0, 2, 1)
        x = self.cnn(x)
        x = self.adaptive_pool(x).squeeze(-1)
        x = self.dropout(x)
        return x
