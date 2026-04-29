"""Fall detection prediction head."""
import torch
import torch.nn as nn


class FallHead(nn.Module):
    """Binary fall detection head.

    Input: (B, D) fused representation
    Output: (B, 1) fall probability
    """
    def __init__(self, input_dim: int = 128, hidden_dim: int = 64):
        super().__init__()
        self.head = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)  # Raw logit; apply sigmoid at loss/inference
