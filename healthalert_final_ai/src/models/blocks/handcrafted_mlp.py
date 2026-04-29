"""Handcrafted feature MLP branch.

Small feedforward network for the handcrafted feature vector.
Sits alongside the learned encoders (IMU, PPG, vitals) and
contributes to the attention fusion.
"""

import torch
import torch.nn as nn
from typing import List


class HandcraftedMLP(nn.Module):
    """MLP for handcrafted feature embedding.

    Input: (B, feature_dim) — flat feature vector with possible NaN→0
    Output: (B, output_dim) — embedded representation
    """

    def __init__(
        self,
        input_dim: int = 38,
        hidden_dims: List[int] = None,
        dropout: float = 0.3,
    ):
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [64, 32]

        layers: list = []
        prev_dim = input_dim
        for h in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, h),
                nn.BatchNorm1d(h),
                nn.ReLU(inplace=True),
                nn.Dropout(dropout),
            ])
            prev_dim = h

        self.mlp = nn.Sequential(*layers)
        self.output_dim = hidden_dims[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: (B, feature_dim) tensor. NaN values should have been
               replaced with 0.0 before calling.

        Returns:
            (B, output_dim) embedded features.
        """
        return self.mlp(x)
