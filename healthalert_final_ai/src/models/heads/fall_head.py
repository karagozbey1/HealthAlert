import torch
import torch.nn as nn


# Birlesik temsil uzerinden dusme logiti ureten cikti basligidir.
class FallHead(nn.Module):

    # Dusme sinifi icin iki katmanli tahmin basligini kurar.
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, 1),
        )

    # Birlesik temsilden ham dusme logitini hesaplar.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
