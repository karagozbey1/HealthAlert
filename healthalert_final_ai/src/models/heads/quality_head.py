import torch
import torch.nn as nn


# PPG sinyal kalitesini tek skora indirgeyen cikti basligidir.
class QualityHead(nn.Module):

    # PPG kalite tahmini icin kompakt cikti katmanini kurar.
    def __init__(self, input_dim: int = 128, hidden_dim: int = 32):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
        )

    # Verilen temsilden kalite logitini hesaplar.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
