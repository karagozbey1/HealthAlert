"""Multi-head Attention Fusion for combining modality embeddings.

Engineering Decision:
  Uses scaled dot-product multi-head attention to learn cross-modal
  importance weights. A learnable CLS token aggregates information.
"""

from typing import Dict, List, Optional

import torch
import torch.nn as nn


class FusionAttention(nn.Module):
    """Attention-based fusion of multiple modality embeddings.

    Projects each modality to a common dimension, then applies
    multi-head self-attention followed by a CLS-token readout.

    Input: List of (B, dim_i) tensors from each encoder
    Output: (B, embed_dim) fused representation
    """

    def __init__(
        self,
        modality_dims: dict = None,
        embed_dim: int = 128,
        num_heads: int = 4,
        dropout: float = 0.2,
    ):
        super().__init__()
        if modality_dims is None:
            modality_dims = {"imu": 256, "ppg": 64, "vitals": 16}

        self.embed_dim = embed_dim

        # Projection layers for each modality
        self.modality_order: List[str] = list(modality_dims.keys())
        self.projections = nn.ModuleDict({
            name: nn.Linear(dim, embed_dim)
            for name, dim in modality_dims.items()
        })

        # CLS token
        self.cls_token = nn.Parameter(torch.randn(1, 1, embed_dim) * 0.02)

        # Multi-head self-attention
        self.attention = nn.MultiheadAttention(
            embed_dim=embed_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.norm = nn.LayerNorm(embed_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        modality_dict: Dict[str, torch.Tensor],
        modality_mask: Optional[Dict[str, torch.Tensor]] = None,
    ) -> torch.Tensor:
        """
        Args:
            modality_dict: {"imu": (B, D1), "ppg": (B, D2), "vitals": (B, D3)}
            modality_mask: optional {"imu": (B,), "ppg": (B,), ...} with
                1.0 meaning available and 0.0 meaning missing.

        Returns:
            (B, embed_dim) fused representation.
        """
        B = next(iter(modality_dict.values())).size(0)

        # Project each modality to common dimension
        tokens = []
        key_padding_mask = []

        # CLS token is always valid
        key_padding_mask.append(torch.zeros(B, dtype=torch.bool, device=next(iter(modality_dict.values())).device))

        for name in self.modality_order:
            if name not in modality_dict:
                continue

            token = self.projections[name](modality_dict[name]).unsqueeze(1)  # (B, 1, E)

            # Missing modality samples are represented as zero tokens and masked.
            if modality_mask is not None and name in modality_mask:
                sample_mask = modality_mask[name].float().view(B, 1, 1)
                token = token * sample_mask
                key_padding_mask.append((sample_mask.view(B) <= 0.5))
            else:
                key_padding_mask.append(torch.zeros(B, dtype=torch.bool, device=token.device))

            tokens.append(token)

        # Add CLS token
        cls = self.cls_token.expand(B, -1, -1)  # (B, 1, E)
        tokens.insert(0, cls)

        # Concatenate all tokens
        x = torch.cat(tokens, dim=1)  # (B, N+1, E)
        attn_mask = torch.stack(key_padding_mask, dim=1)  # (B, N+1)

        # Self-attention
        attn_out, _ = self.attention(x, x, x, key_padding_mask=attn_mask)
        x = self.norm(x + attn_out)

        # Return CLS token output
        fused = x[:, 0, :]  # (B, E)
        fused = self.dropout(fused)
        return fused
