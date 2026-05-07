import torch
import torch.nn as nn
from typing import List


# IMU zaman serisini CNN ve RNN ile ortak temsile cevirir.
class IMUEncoder(nn.Module):

        # Konvolusyon ve tekrarli katmanlardan olusan IMU encoderini kurar.
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

        # Yerel hareket kaliplarini yakalayacak CNN bloklarini kurar.
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

    # Zamansal baglam icin iki yonlu tekrarli kodlayici ekler.
        RNNClass = nn.GRU if rnn_type.lower() == "gru" else nn.LSTM
        self.rnn = RNNClass(
            input_size=cnn_channels[-1],
            hidden_size=rnn_hidden,
            num_layers=rnn_layers,
            batch_first=True,
            dropout=dropout if rnn_layers > 1 else 0,
            bidirectional=True,
        )

        self.output_dim = rnn_hidden * 2
        self.dropout = nn.Dropout(dropout)

    # IMU tensörunu encode ederek sabit boyutlu temsil dondurur.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # CNN katmani kanal boyutunu once bekledigi icin eksenleri cevirir.
        x = x.permute(0, 2, 1)
        x = self.cnn(x)

        # Tekrar zaman once gelecek bicime dondurur.
        x = x.permute(0, 2, 1)

        rnn_out, _ = self.rnn(x)

        # Son zaman adimini temsil olarak secip dropout uygular.
        x = rnn_out[:, -1, :]
        x = self.dropout(x)
        return x
