import torch
import torch.nn as nn


# PPG temsilini tahmini sinyal kalitesine gore agirliklandirir.
class QualityGate(nn.Module):

        # Kalite tahmin agini ve esik ayarini baslatir.
    def __init__(
        self,
        ppg_dim: int = 64,
        quality_input_dim: int = 2,
        hidden_dim: int = 64,
        threshold: float = 0.5,
    ):
        super().__init__()
        self.threshold = threshold

        # PPG ve kalite girdilerini birlestirip kalite skoru tahmin eder.
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
        # PPG temsili ile kalite girdisini birlestirip kalite skoru hesaplar.
        combined = torch.cat([ppg_embedding, quality_input], dim=1)
        quality_score = self.quality_net(combined)

        # PPG katkisini kalite skoruyla yumusak sekilde carpip zayiflatir.
        gated_ppg = ppg_embedding * quality_score

        return gated_ppg, quality_score
