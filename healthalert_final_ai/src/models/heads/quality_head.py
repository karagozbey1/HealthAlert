"""PPG quality prediction head."""
import torch
import torch.nn as nn


class QualityHead(nn.Module):
    """PPG signal quality classification head.

    Input: (B, D) fused or PPG-specific features
    Output: (B, 1) quality score
    """
    def __init__(self, input_dim: int = 128, hidden_dim: int = 32):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
