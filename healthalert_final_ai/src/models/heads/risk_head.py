"""Risk score prediction head."""
import torch
import torch.nn as nn


class RiskHead(nn.Module):
    """Early risk score regression head.

    Outputs a continuous risk score in [0, 1].
    Input: (B, D) fused representation
    Output: (B, 1) risk score
    """
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
