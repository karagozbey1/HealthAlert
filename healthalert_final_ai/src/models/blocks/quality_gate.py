"""Quality Gate: Learns to gate PPG contribution based on signal reliability.

Engineering Decision:
  When PPG quality is low (motion artifacts, poor contact), the gate
  attenuates PPG features to prevent noisy vitals from corrupting
  the fused representation. This is a soft gating mechanism.
"""

import torch
import torch.nn as nn


class QualityGate(nn.Module):
    """Learnable gate that modulates PPG features by estimated quality.

    Input: ppg_embedding (B, D), quality_features (B, Q)
    Output: gated_ppg (B, D), quality_score (B, 1)
    """

    def __init__(
        self,
        ppg_dim: int = 64,
        quality_input_dim: int = 2,
        hidden_dim: int = 64,
        threshold: float = 0.5,
    ):
        super().__init__()
        self.threshold = threshold

        # Quality predictor
        self.quality_net = nn.Sequential(
            nn.Linear(quality_input_dim + ppg_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        ppg_embedding: torch.Tensor,
        quality_input: torch.Tensor,
    ) -> tuple:
        """
        Args:
            ppg_embedding: (B, D) PPG encoder output.
            quality_input: (B, Q) quality-related features (e.g., vitals tensor).

        Returns:
            gated_ppg: (B, D) quality-modulated PPG embedding.
            quality_score: (B, 1) estimated quality.
        """
        combined = torch.cat([ppg_embedding, quality_input], dim=1)
        quality_score = self.quality_net(combined)  # (B, 1)

        # Soft gating: scale PPG by quality
        gated_ppg = ppg_embedding * quality_score

        return gated_ppg, quality_score
