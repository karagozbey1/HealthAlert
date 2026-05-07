from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from scipy.io import loadmat
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    accuracy_score,
    classification_report,
    precision_score,
    recall_score,
    balanced_accuracy_score,
    matthews_corrcoef,
    cohen_kappa_score,
    roc_auc_score,
    average_precision_score,
)

# PNG uretiminde arayuz gerektirmeyen matplotlib kipini acar.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# MAT dosyalarindaki farkli sinyal duzenlerini tolere eden cozumleyicidir.
def _mat_get_signals(mat: Dict) -> Tuple[np.ndarray, np.ndarray]:
    keys = {k.lower(): k for k in mat.keys() if not k.startswith("__")}
    need = ["ax", "ay", "az", "heart"]

    if all(k in keys for k in need):
        ax = np.asarray(mat[keys["ax"]]).squeeze()
        ay = np.asarray(mat[keys["ay"]]).squeeze()
        az = np.asarray(mat[keys["az"]]).squeeze()
        heart = np.asarray(mat[keys["heart"]]).squeeze()

        droll = np.asarray(mat[keys["droll"]]).squeeze() if "droll" in keys else np.zeros_like(ax)
        dpitch = np.asarray(mat[keys["dpitch"]]).squeeze() if "dpitch" in keys else np.zeros_like(ax)
        dyaw = np.asarray(mat[keys["dyaw"]]).squeeze() if "dyaw" in keys else np.zeros_like(ax)

        n = min(len(ax), len(ay), len(az), len(droll), len(dpitch), len(dyaw), len(heart))
        imu = np.stack([ax[:n], ay[:n], az[:n], droll[:n], dpitch[:n], dyaw[:n]], axis=1)
        ppg = heart[:n].reshape(-1, 1)
        return ppg, imu

    candidates = []
    for k, v in mat.items():
        if k.startswith("__"):
            continue
        if isinstance(v, np.ndarray) and np.issubdtype(v.dtype, np.number) and v.ndim == 2:
            r, c = v.shape
            if (min(r, c) >= 8) and (max(r, c) >= 100):
                candidates.append((k, v))

    if not candidates:
        raise RuntimeError("Bu .mat içinde okunabilir numeric sinyal matrisi bulamadım.")

    _, M = sorted(candidates, key=lambda x: x[1].size, reverse=True)[0]
    M = np.asarray(M)

    # Ozellik once geliyorsa matrisi zaman once olacak sekilde dondurur.
    if M.shape[0] <= 20 and M.shape[1] > M.shape[0]:
        M = M.T

    if M.shape[1] < 11:
        raise RuntimeError(f"Matris kolon sayısı beklenenden az: {M.shape}")

    ax, ay, az = M[:, 0], M[:, 1], M[:, 2]
    droll, dpitch, dyaw = M[:, 7], M[:, 8], M[:, 9]
    heart = M[:, 10]

    imu = np.stack([ax, ay, az, droll, dpitch, dyaw], axis=1)
    ppg = heart.reshape(-1, 1)
    return ppg, imu


# Dosya yolundan ikili etiket adini cikarir.
def _label_from_path(fp: Path) -> str:
    parent = fp.parent.name.lower()
    if parent == "fall":
        return "FALL"
    return "ADL"


@dataclass
class WindowCfg:
    fs: int = 50
    window_sec: float = 2.0
    stride_sec: float = 0.5


# MAT kayitlarini pencerelere bolup etiket ve pencere ayarlarini dondurur.
def make_windows(data_root: Path, cfg: WindowCfg):
    mat_files = sorted(list(data_root.rglob("*.mat")))
    if not mat_files:
        raise FileNotFoundError(f".mat bulamadım. Klasör: {data_root}")

    win_len = int(cfg.fs * cfg.window_sec)
    stride = int(cfg.fs * cfg.stride_sec)

    windows = []
    labels = []

    for fp in mat_files:
        subject = fp.parents[1].name
        label_name = _label_from_path(fp)

        mat = loadmat(fp)
        ppg, imu = _mat_get_signals(mat)

        n = min(len(ppg), len(imu))
        if n < win_len:
            continue

        for start in range(0, n - win_len + 1, stride):
            end = start + win_len
            windows.append((ppg[start:end], imu[start:end], label_name, subject))
            labels.append(label_name)

    if not windows:
        raise RuntimeError("Pencere üretilemedi. (Veriler okunamadı ya da çok kısa)")

    uniq_labels = sorted(list(set(labels)))
    return windows, uniq_labels, win_len, stride


# Denek bazli sekilde egitim, dogrulama ve test bolmelerini ayirir.
def split_by_subject(windows, seed=42):
    rng = np.random.default_rng(seed)
    subjects = sorted(list(set([w[3] for w in windows])))
    rng.shuffle(subjects)

    n = len(subjects)
    if n < 3:
        n_train = max(1, int(0.8 * n))
        tr_sub = set(subjects[:n_train])
        va_sub = set(subjects[n_train:])
        te_sub = set()
    else:
        n_train = max(1, int(0.7 * n))
        n_val = max(1, int(0.15 * n))
        if n_train + n_val >= n:
            n_val = max(1, n - n_train - 1)

        tr_sub = set(subjects[:n_train])
        va_sub = set(subjects[n_train:n_train + n_val])
        te_sub = set(subjects[n_train + n_val:])

        if len(te_sub) == 0:
            te_sub = {subjects[-1]}
            if subjects[-1] in tr_sub:
                tr_sub.remove(subjects[-1])

    tr, va, te = [], [], []
    for w in windows:
        subj = w[3]
        if subj in tr_sub:
            tr.append(w)
        elif subj in va_sub:
            va.append(w)
        else:
            te.append(w)

    return tr, va, te, tr_sub, va_sub, te_sub


# Egitim bolmesinden normalizasyon istatistiklerini hesaplar.
def compute_norm_stats(train_windows):
    ppg_all = np.concatenate([w[0] for w in train_windows], axis=0)
    imu_all = np.concatenate([w[1] for w in train_windows], axis=0)

    ppg_mu = ppg_all.mean(axis=0)
    ppg_sd = ppg_all.std(axis=0) + 1e-6
    imu_mu = imu_all.mean(axis=0)
    imu_sd = imu_all.std(axis=0) + 1e-6
    return (ppg_mu, ppg_sd, imu_mu, imu_sd)


# Pencere veri setini tensor ciktilarina ceviren Dataset sinifidir.
class HIFDWindowDS(Dataset):
    def __init__(self, windows, label2id, norm_stats):
        self.windows = windows
        self.label2id = label2id
        self.ppg_mu, self.ppg_sd, self.imu_mu, self.imu_sd = norm_stats

    def __len__(self):
        return len(self.windows)

    def __getitem__(self, idx):
        ppg, imu, y_name, _subj = self.windows[idx]

        ppg = (ppg - self.ppg_mu) / self.ppg_sd
        imu = (imu - self.imu_mu) / self.imu_sd

        ppg_t = torch.from_numpy(ppg.T).float()
        imu_t = torch.from_numpy(imu.T).float()
        y = torch.tensor(self.label2id[y_name], dtype=torch.long)
        return ppg_t, imu_t, y


class CRNN(nn.Module):
    def __init__(self, num_classes: int):
        super().__init__()

        self.ppg_cnn = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=7, padding=3),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(16, 32, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )
        self.ppg_rnn = nn.LSTM(
            input_size=32, hidden_size=64, num_layers=1,
            batch_first=True, bidirectional=True
        )

        self.imu_cnn = nn.Sequential(
            nn.Conv1d(6, 32, kernel_size=7, padding=3),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )
        self.imu_rnn = nn.LSTM(
            input_size=64, hidden_size=64, num_layers=1,
            batch_first=True, bidirectional=True
        )

        self.head = nn.Sequential(
            nn.Linear(128 + 128, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, num_classes)
        )

    def forward(self, ppg, imu):
        p = self.ppg_cnn(ppg)
        p = p.transpose(1, 2)
        p_out, _ = self.ppg_rnn(p)
        p_feat = p_out[:, -1, :]

        x = self.imu_cnn(imu)
        x = x.transpose(1, 2)
        x_out, _ = self.imu_rnn(x)
        x_feat = x_out[:, -1, :]

        feat = torch.cat([p_feat, x_feat], dim=1)
        return self.head(feat)


@torch.no_grad()
# Yukleyici uzerinden tahmin, etiket ve gerekirse pozitif skor toplar.
def eval_model_with_scores(model, loader, device, num_classes: int):
    model.eval()
    ys, ps, scores = [], [], []

    for ppg, imu, y in loader:
        ppg, imu = ppg.to(device), imu.to(device)
        logits = model(ppg, imu)
        probs = torch.softmax(logits, dim=1)

        pred = torch.argmax(probs, dim=1).cpu().numpy()
        ys.append(y.numpy())
        ps.append(pred)

        if num_classes == 2:
            scores.append(probs[:, 1].detach().cpu().numpy())

    if len(ys) == 0:
        return np.array([], dtype=int), np.array([], dtype=int), None

    y_true = np.concatenate(ys)
    y_pred = np.concatenate(ps)
    y_score = np.concatenate(scores) if (num_classes == 2 and len(scores) > 0) else None
    return y_true, y_pred, y_score


@torch.no_grad()
# Bir yukleyici icin ortalama kaybi ornek sayisina gore hesaplar.
def compute_loader_loss(model, loader, device, criterion):
    model.eval()
    total = 0.0
    n = 0
    for ppg, imu, y in loader:
        ppg, imu, y = ppg.to(device), imu.to(device), y.to(device)
        logits = model(ppg, imu)
        loss = criterion(logits, y)
        total += float(loss.item()) * int(y.shape[0])
        n += int(y.shape[0])
    return total / max(1, n)


# Siniflandirma ciktilarindan saglam bir metric paketi uretir.
def compute_metrics(y_true, y_pred, y_score: Optional[np.ndarray], class_names: List[str]) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    if len(y_true) == 0:
        return metrics

    metrics["Accuracy"] = float(accuracy_score(y_true, y_pred))
    metrics["BalancedAcc"] = float(balanced_accuracy_score(y_true, y_pred))
    metrics["Precision_macro"] = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    metrics["Recall_macro"] = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    metrics["F1_macro"] = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    metrics["F1_weighted"] = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
    metrics["MCC"] = float(matthews_corrcoef(y_true, y_pred))
    metrics["Kappa"] = float(cohen_kappa_score(y_true, y_pred))

    # Ikili siniflandirmada ek duyarlilik, ozgulluk ve AUC metrikleri ekler.
    if len(class_names) == 2:
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        sensitivity = tp / (tp + fn + 1e-12)
        specificity = tn / (tn + fp + 1e-12)

        metrics["Sensitivity_pos"] = float(sensitivity)
        metrics["Specificity_neg"] = float(specificity)

        if y_score is not None and len(np.unique(y_true)) == 2:
            try:
                metrics["ROC_AUC"] = float(roc_auc_score(y_true, y_score))
            except Exception:
                metrics["ROC_AUC"] = float("nan")
            try:
                metrics["PR_AUC"] = float(average_precision_score(y_true, y_score))
            except Exception:
                metrics["PR_AUC"] = float("nan")

    return metrics


def save_plots_and_tables(
    *,
    out_dir: Path,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_names: List[str],
    final_metrics: Dict[str, float],
    train_losses: List[float],
    val_losses: List[float],
    val_metrics_history: Dict[str, List[float]],
    cfg_info: Dict[str, str],
):
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Confusion Matrix
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))
    fig1, ax1 = plt.subplots(figsize=(7, 6))
    ax1.imshow(cm)
    ax1.set_title("Confusion Matrix")
    ax1.set_xlabel("Pred")
    ax1.set_ylabel("True")
    ax1.set_xticks(range(len(class_names)))
    ax1.set_yticks(range(len(class_names)))
    ax1.set_xticklabels(class_names, rotation=45, ha="right")
    ax1.set_yticklabels(class_names)
    for (i, j), v in np.ndenumerate(cm):
        ax1.text(j, i, str(v), ha="center", va="center")
    fig1.tight_layout()
    fig1.savefig(out_dir / "confusion_matrix.png", dpi=220)
    plt.close(fig1)

    # 2) Final Metrics Bar (selected)
    bar_keys = ["Accuracy", "BalancedAcc", "F1_macro", "MCC", "ROC_AUC", "PR_AUC", "Sensitivity_pos", "Specificity_neg"]
    names = [k for k in bar_keys if k in final_metrics and not (isinstance(final_metrics[k], float) and np.isnan(final_metrics[k]))]
    vals = [final_metrics[k] for k in names]

    fig2, ax2 = plt.subplots(figsize=(10, 5))
    ax2.bar(names, vals)
    ax2.set_ylim(0, 1.0)
    ax2.set_title("Final Metrics (Selected)")
    ax2.tick_params(axis="x", rotation=25)
    for i, v in enumerate(vals):
        ax2.text(i, min(0.98, v + 0.02), f"{v:.3f}", ha="center")
    fig2.tight_layout()
    fig2.savefig(out_dir / "final_metrics_bar.png", dpi=220)
    plt.close(fig2)

    # 3) Loss curves (Train + Val)
    epochs = np.arange(1, len(train_losses) + 1)
    fig3, ax3 = plt.subplots(figsize=(9, 5))
    ax3.plot(epochs, train_losses, label="Train Loss")
    if len(val_losses) == len(train_losses):
        ax3.plot(epochs, val_losses, label="Val Loss")
    ax3.set_title("Loss Curves")
    ax3.set_xlabel("Epoch")
    ax3.set_ylabel("Loss")
    ax3.legend()
    fig3.tight_layout()
    fig3.savefig(out_dir / "loss_curves.png", dpi=220)
    plt.close(fig3)

    # 4) Validation metric curves (Accuracy, F1, MCC, BalancedAcc)
    fig4, ax4 = plt.subplots(figsize=(9, 5))
    for k in ["Accuracy", "F1_macro", "MCC", "BalancedAcc"]:
        if k in val_metrics_history and len(val_metrics_history[k]) == len(epochs):
            ax4.plot(epochs, val_metrics_history[k], label=f"Val {k}")
    ax4.set_title("Validation Metrics per Epoch")
    ax4.set_xlabel("Epoch")
    ax4.set_ylabel("Score")
    ax4.set_ylim(0, 1.0)
    ax4.legend()
    fig4.tight_layout()
    fig4.savefig(out_dir / "val_metrics_curve.png", dpi=220)
    plt.close(fig4)

    # 5) Final metrics table (PNG)
    rows = [[k, f"{v:.4f}" if isinstance(v, (int, float)) and not np.isnan(v) else str(v)] for k, v in final_metrics.items()]
    rows = sorted(rows, key=lambda x: x[0])

    fig5, ax5 = plt.subplots(figsize=(8.2, 0.55 + 0.32 * len(rows)))
    ax5.axis("off")
    t = ax5.table(
        cellText=rows,
        colLabels=["Metric", "Value"],
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    t.auto_set_font_size(False)
    t.set_fontsize(10)
    t.scale(1, 1.2)
    ax5.set_title("Final Metrics (Full)", pad=12)
    fig5.tight_layout()
    fig5.savefig(out_dir / "final_metrics_table.png", dpi=220)
    plt.close(fig5)

    # 6) Epoch metrics table (PNG) — loss + val metrics
    epoch_rows = []
    for i in range(len(epochs)):
        epoch_rows.append([
            str(int(epochs[i])),
            f"{train_losses[i]:.4f}",
            f"{val_losses[i]:.4f}" if i < len(val_losses) else "n/a",
            f"{val_metrics_history.get('Accuracy', [np.nan]*len(epochs))[i]:.4f}" if "Accuracy" in val_metrics_history else "n/a",
            f"{val_metrics_history.get('F1_macro', [np.nan]*len(epochs))[i]:.4f}" if "F1_macro" in val_metrics_history else "n/a",
            f"{val_metrics_history.get('MCC', [np.nan]*len(epochs))[i]:.4f}" if "MCC" in val_metrics_history else "n/a",
            f"{val_metrics_history.get('BalancedAcc', [np.nan]*len(epochs))[i]:.4f}" if "BalancedAcc" in val_metrics_history else "n/a",
        ])

    fig6, ax6 = plt.subplots(figsize=(10.5, 0.8 + 0.28 * len(epoch_rows)))
    ax6.axis("off")
    t2 = ax6.table(
        cellText=epoch_rows,
        colLabels=["Epoch", "TrainLoss", "ValLoss", "ValAcc", "ValF1m", "ValMCC", "ValBalAcc"],
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    t2.auto_set_font_size(False)
    t2.set_fontsize(9)
    t2.scale(1, 1.1)
    ax6.set_title("Epoch Metrics (for Report)", pad=12)
    fig6.tight_layout()
    fig6.savefig(out_dir / "epoch_metrics_table.png", dpi=220)
    plt.close(fig6)

    # 7) Classification report table (PNG)
    rep = classification_report(y_true, y_pred, target_names=class_names, output_dict=True, zero_division=0)
    row_names = class_names + ["macro avg", "weighted avg"]
    cr_rows = []
    for rn in row_names:
        r = rep.get(rn, {})
        cr_rows.append([
            rn,
            f"{r.get('precision', 0.0):.3f}",
            f"{r.get('recall', 0.0):.3f}",
            f"{r.get('f1-score', 0.0):.3f}",
            f"{int(r.get('support', 0))}",
        ])

    fig7, ax7 = plt.subplots(figsize=(9.2, 0.7 + 0.45 * len(cr_rows)))
    ax7.axis("off")
    t3 = ax7.table(
        cellText=cr_rows,
        colLabels=["Class", "Precision", "Recall", "F1", "Support"],
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    t3.auto_set_font_size(False)
    t3.set_fontsize(10)
    t3.scale(1, 1.15)
    ax7.set_title("Classification Report", pad=12)
    fig7.tight_layout()
    fig7.savefig(out_dir / "classification_report_table.png", dpi=220)
    plt.close(fig7)

    # 8) Experiment / Config info table (PNG)
    cfg_rows = [[k, str(v)] for k, v in cfg_info.items()]
    cfg_rows = sorted(cfg_rows, key=lambda x: x[0])

    fig8, ax8 = plt.subplots(figsize=(8.5, 0.7 + 0.32 * len(cfg_rows)))
    ax8.axis("off")
    t4 = ax8.table(
        cellText=cfg_rows,
        colLabels=["Config", "Value"],
        cellLoc="left",
        colLoc="left",
        loc="center",
    )
    t4.auto_set_font_size(False)
    t4.set_fontsize(10)
    t4.scale(1, 1.2)
    ax8.set_title("Experiment Configuration", pad=12)
    fig8.tight_layout()
    fig8.savefig(out_dir / "experiment_config_table.png", dpi=220)
    plt.close(fig8)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_root", type=str, default=r"Data\HIFD")
    ap.add_argument("--fs", type=int, default=50)
    ap.add_argument("--window_sec", type=float, default=2.0)
    ap.add_argument("--stride_sec", type=float, default=0.5)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[Device] {device}")

    cfg = WindowCfg(fs=args.fs, window_sec=args.window_sec, stride_sec=args.stride_sec)
    windows, uniq_labels, win_len, stride = make_windows(Path(args.data_root), cfg)
    print(f"[Data] windows={len(windows)} | labels={uniq_labels}")

    label2id = {name: i for i, name in enumerate(uniq_labels)}
    id2label = {i: name for name, i in label2id.items()}
    class_names = [id2label[i] for i in range(len(uniq_labels))]

    tr_w, va_w, te_w, tr_sub, va_sub, te_sub = split_by_subject(windows, seed=args.seed)
    print(f"[Subjects] train={sorted(tr_sub)}")
    print(f"[Subjects] val  ={sorted(va_sub)}")
    print(f"[Subjects] test ={sorted(te_sub)}")
    print(f"[Split] train={len(tr_w)} val={len(va_w)} test={len(te_w)}")

    norm = compute_norm_stats(tr_w)

    train_ds = HIFDWindowDS(tr_w, label2id, norm)
    val_ds = HIFDWindowDS(va_w, label2id, norm)
    test_ds = HIFDWindowDS(te_w, label2id, norm) if len(te_w) > 0 else None

    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=args.batch, shuffle=False, num_workers=0) if test_ds else None

    model = CRNN(num_classes=len(uniq_labels)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    crit = nn.CrossEntropyLoss()

    n_params = count_parameters(model)

    best_f1 = -1.0
    train_losses: List[float] = []
    val_losses: List[float] = []
    val_metrics_history: Dict[str, List[float]] = {
        "Accuracy": [],
        "BalancedAcc": [],
        "F1_macro": [],
        "MCC": [],
    }

    print("[Train] start...")
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        n = 0

        for ppg, imu, y in train_loader:
            ppg, imu, y = ppg.to(device), imu.to(device), y.to(device)
            opt.zero_grad()
            logits = model(ppg, imu)
            loss = crit(logits, y)
            loss.backward()
            opt.step()

            total += float(loss.item()) * int(y.shape[0])
            n += int(y.shape[0])

        tr_loss = total / max(1, n)
        train_losses.append(tr_loss)

        va_loss = compute_loader_loss(model, val_loader, device, crit)
        val_losses.append(va_loss)

        y_true_v, y_pred_v, _ = eval_model_with_scores(model, val_loader, device, num_classes=len(class_names))
        if len(y_true_v) > 0:
            acc_v = float(accuracy_score(y_true_v, y_pred_v))
            bal_v = float(balanced_accuracy_score(y_true_v, y_pred_v))
            f1m_v = float(f1_score(y_true_v, y_pred_v, average="macro", zero_division=0))
            mcc_v = float(matthews_corrcoef(y_true_v, y_pred_v))
        else:
            acc_v = bal_v = f1m_v = mcc_v = 0.0

        val_metrics_history["Accuracy"].append(acc_v)
        val_metrics_history["BalancedAcc"].append(bal_v)
        val_metrics_history["F1_macro"].append(f1m_v)
        val_metrics_history["MCC"].append(mcc_v)

        print(f"Epoch {epoch:02d}/{args.epochs} | train_loss={tr_loss:.4f} | val_loss={va_loss:.4f} | val_acc={acc_v:.3f} | val_f1m={f1m_v:.3f} | val_mcc={mcc_v:.3f}")

        if f1m_v > best_f1:
            best_f1 = f1m_v
            Path("reports").mkdir(exist_ok=True)
            torch.save(model.state_dict(), Path("reports") / "best_model.pt")

    # Final eval (best model)
    model.load_state_dict(torch.load(Path("reports") / "best_model.pt", map_location=device))

    if test_loader is None:
        print("[Eval] Test yok, VAL üzerinden final rapor üretiyorum.")
        y_true, y_pred, y_score = eval_model_with_scores(model, val_loader, device, num_classes=len(class_names))
        split_name = "VAL"
        split_count = len(val_ds)
    else:
        y_true, y_pred, y_score = eval_model_with_scores(model, test_loader, device, num_classes=len(class_names))
        split_name = "TEST"
        split_count = len(test_ds)

    final_metrics = compute_metrics(y_true, y_pred, y_score, class_names)

    # Extra config table info
    cfg_info = {
        "DatasetRoot": str(args.data_root),
        "Classes": str(class_names),
        "fs": str(args.fs),
        "window_sec": str(args.window_sec),
        "stride_sec": str(args.stride_sec),
        "window_len_samples": str(win_len),
        "stride_samples": str(stride),
        "epochs": str(args.epochs),
        "batch": str(args.batch),
        "lr": str(args.lr),
        "seed": str(args.seed),
        "device": str(device),
        "model_trainable_params": str(n_params),
        "windows_total": str(len(windows)),
        "train_windows": str(len(train_ds)),
        "val_windows": str(len(val_ds)),
        f"{split_name}_windows": str(split_count),
        "train_subjects": str(sorted(list(tr_sub))),
        "val_subjects": str(sorted(list(va_sub))),
        "test_subjects": str(sorted(list(te_sub))),
    }

    save_plots_and_tables(
        out_dir=Path("reports"),
        y_true=y_true,
        y_pred=y_pred,
        class_names=class_names,
        final_metrics=final_metrics,
        train_losses=train_losses,
        val_losses=val_losses,
        val_metrics_history=val_metrics_history,
        cfg_info=cfg_info,
    )

    print("\nSaved (reports/):")
    print("- confusion_matrix.png")
    print("- final_metrics_bar.png")
    print("- loss_curves.png")
    print("- val_metrics_curve.png")
    print("- final_metrics_table.png")
    print("- epoch_metrics_table.png")
    print("- classification_report_table.png")
    print("- experiment_config_table.png")
    print("- best_model.pt")


if __name__ == "__main__":
    main()

