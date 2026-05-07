import torch
import torch.nn as nn


# Erken risk skorunu surekli deger olarak ureten basliktir.
class RiskHead(nn.Module):

    # Risk skorunu 0-1 araligina sikistiran cikti katmanini kurar.
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    # Birlesik temsilden surekli risk skorunu hesaplar.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
