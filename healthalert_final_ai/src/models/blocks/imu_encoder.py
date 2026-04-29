"""IMU Encoder: CRNN (CNN + GRU) for accelerometer + gyroscope data.

Architecture:
  Conv1D blocks → GRU → encoded representation
  Captures both local patterns (CNN) and temporal dynamics (GRU).
"""

import torch
import torch.nn as nn
from typing import List


class IMUEncoder(nn.Module):
    """Convolutional Recurrent Neural Network for 6-axis IMU encoding.

    Input: (B, T, 6) - accel_xyz + gyro_xyz
    Output: (B, hidden_dim) - encoded representation
    """

    def __init__(
        self,
        in_channels: int = 6,
        cnn_channels: List[int] = None,
        cnn_kernel: int = 5,
        rnn_hidden: int = 128,
        rnn_layers: int = 2,
        rnn_type: str = "gru",
        dropout: float = 0.3,
    ):
        super().__init__()
        if cnn_channels is None:
            cnn_channels = [32, 64, 128]

        # 1D CNN feature extractor
        layers = []
        prev_ch = in_channels
        for ch in cnn_channels:
            layers.extend([
                nn.Conv1d(prev_ch, ch, kernel_size=cnn_kernel, padding=cnn_kernel // 2),
                nn.BatchNorm1d(ch),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout * 0.5),
                nn.MaxPool1d(kernel_size=2, stride=2),
            ])
            prev_ch = ch

        self.cnn = nn.Sequential(*layers)

        # RNN temporal encoder
        RNNClass = nn.GRU if rnn_type.lower() == "gru" else nn.LSTM
        self.rnn = RNNClass(
            input_size=cnn_channels[-1],
            hidden_size=rnn_hidden,
            num_layers=rnn_layers,
            batch_first=True,
            dropout=dropout if rnn_layers > 1 else 0,
            bidirectional=True,
        )

        self.output_dim = rnn_hidden * 2  # bidirectional
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, C) IMU tensor where C=6.

        Returns:
            (B, output_dim) encoded representation.
        """
        # CNN expects (B, C, T)
        x = x.permute(0, 2, 1)
        x = self.cnn(x)

        # Back to (B, T', C')
        x = x.permute(0, 2, 1)

        # RNN
        rnn_out, _ = self.rnn(x)

        # Use last timestep output
        x = rnn_out[:, -1, :]
        x = self.dropout(x)
        return x
