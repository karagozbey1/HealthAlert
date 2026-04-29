"""Vitals MLP: Small feedforward network for scalar vital signs."""

import torch
import torch.nn as nn
from typing import List


class VitalsMLP(nn.Module):
    """MLP for scalar vitals (HR, SpO2).

    Input: (B, vitals_dim) - e.g., [hr_mean, spo2_norm]
    Output: (B, output_dim)
    """

    def __init__(
        self,
        input_dim: int = 2,
        hidden_dims: List[int] = None,
        dropout: float = 0.2,
    ):
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [32, 16]

        layers = []
        prev_dim = input_dim
        for h in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout),
            ])
            prev_dim = h

        self.mlp = nn.Sequential(*layers)
        self.output_dim = hidden_dims[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)
