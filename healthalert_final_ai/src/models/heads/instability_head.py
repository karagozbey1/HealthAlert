import torch
import torch.nn as nn


# Dengesizlik veya dusme oncesi sinyalini skorlayan cikti basligidir.
class InstabilityHead(nn.Module):

    # Dengesizlik tahmini icin gizli katmanli basi kurar.
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 1),
        )

    # Birlesik temsilden dengesizlik logitini uretir.
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
