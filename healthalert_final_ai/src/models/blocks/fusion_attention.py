from typing import Dict, List, Optional

import torch
import torch.nn as nn


# Modalite temsillerini dikkat mekanizmasiyla ortak bir uzaya birlestirir.
class FusionAttention(nn.Module):

    # Projeksiyon, CLS token ve attention katmanlarini baslatir.
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

    # Her modaliteyi ortak boyuta tasiyacak projeksiyonlari kurar.
        self.modality_order: List[str] = list(modality_dims.keys())
        self.projections = nn.ModuleDict({
            name: nn.Linear(dim, embed_dim)
            for name, dim in modality_dims.items()
        })

        # Birlesik ozeti tasiyacak ogrenilebilir CLS tokenini tanimlar.
        self.cls_token = nn.Parameter(torch.randn(1, 1, embed_dim) * 0.02)

        # Cok baslikli attention ve cikis normunu olusturur.
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
        B = next(iter(modality_dict.values())).size(0)

        # Her modaliteyi ortak embed boyutuna tasir.
        tokens = []
        key_padding_mask = []

        # CLS token her ornekte gecerli kabul edilir.
        key_padding_mask.append(torch.zeros(B, dtype=torch.bool, device=next(iter(modality_dict.values())).device))

        for name in self.modality_order:
            if name not in modality_dict:
                continue

            token = self.projections[name](modality_dict[name]).unsqueeze(1)

            # Eksik modaliteleri maskeleyip sifir agirlikla temsil eder.
            if modality_mask is not None and name in modality_mask:
                sample_mask = modality_mask[name].float().view(B, 1, 1)
                token = token * sample_mask
                key_padding_mask.append((sample_mask.view(B) <= 0.5))
            else:
                key_padding_mask.append(torch.zeros(B, dtype=torch.bool, device=token.device))

            tokens.append(token)

        cls = self.cls_token.expand(B, -1, -1)
        tokens.insert(0, cls)

        x = torch.cat(tokens, dim=1)
        attn_mask = torch.stack(key_padding_mask, dim=1)

        # Attention cikisini artik baglanti ile normalize eder.
        attn_out, _ = self.attention(x, x, x, key_padding_mask=attn_mask)
        x = self.norm(x + attn_out)

        fused = x[:, 0, :]
        fused = self.dropout(fused)
        return fused
