# Why Multi-Task-First Training Was Deprecated

**Date:** 2026-05-13  
**Decision:** Stop multi-task collapsed training; redesign as hybrid expert-model system.

---

## What Happened

The HealthAlert AI pipeline was initially designed as a unified multi-task model that
trained fall detection, activity instability, PPG quality, and vitals context heads
simultaneously in a single training loop.

After several smoke runs, the final multi-task training run (smoke_run8) showed a
**complete model collapse**:

| Metric | Value |
|--------|-------|
| fall_recall | **1.0000** |
| fall_precision | **0.1358** |
| fall_macro_f1 | **0.0797** |
| normal_recall | **0.0000** |
| near_fall_recall | **0.0000** |
| collapse_detected | **YES** |
| prediction behavior | predicts ALL validation windows as **fall** |

This is a full **all-fall collapse** — the model learned to predict every single
window as the fall class.

---

## Why Collapse Occurred

### 1. near_fall as a hard third class

`near_fall` (label=2) is an extremely rare class across all datasets.
When included as a hard third class in 3-class training, its gradient signal
destabilizes the shared loss function. The model collapsed to the dominant fall
class rather than learning to distinguish all three.

### 2. Extreme class imbalance with WeightedRandomSampler

Using `WeightedRandomSampler` oversampled rare classes artificially. Combined
with strong class weights in focal loss, the model overfit to the rare classes
in unexpected ways, ultimately causing it to predict fall everywhere.

### 3. Shared multi-task gradients amplified instability

All four task heads shared the same IMU and PPG encoder backbone. When the fall
head dominated the gradient signal (due to fall imbalance + focal loss), the
shared encoder was pulled toward fall prediction regardless of other tasks.
Quality, instability, and risk heads were effectively overridden.

### 4. Checkpointing was unsafe

The `ModelCheckpoint` callback accepted the collapsed best_model.pt because
fall_recall=1.0 produced a superficially good score. The checkpoint scoring
function did not reject collapses where normal_recall=0 or
fall_precision < threshold.

### 5. Dataset state was not fully verified

The multi-task training loop assumed all task labels were clean and reliable
across all datasets simultaneously. In reality:
- Some datasets contribute only to specific tasks.
- PPG-only datasets were incorrectly routed to fall detection in some runs.
- near_fall labels were not excluded from binary training.

---

## Why Expert-First Architecture is Safer

| Problem | Multi-Task Solution | Expert-First Solution |
|---------|--------------------|-----------------------|
| Fall collapse | Shared backbone pulled toward fall | Dedicated fall expert, isolated loss |
| near_fall instability | 3-class head from the start | Exclude from binary baseline; add later |
| PPG contamination | All data shared | Explicit task routing per dataset |
| Checkpoint collapse | Score accepted collapse | Hard reject if normal_recall < 0.40 |
| Multi-task gradient conflict | All heads compete | Separate expert losses, no shared gradient |
| Application correctness | Unclear due to collapse | Each expert verified independently |

---

## What Is Preserved

- The existing multi-task source code is **not deleted**. It remains in:
  - `src/models/multitask_model_v2.py`
  - `src/training/stage_trainer.py`
  - `scripts/run_train.py`
- These files can be revisited for a neural fusion model **after** expert models
  are individually stable and validated.
- Outputs from collapsed runs are archived in `outputs/prototype_model_archived_*/`

---

## Decision

**Do not train multi-task-first.**

Train each expert model in isolation. Once all experts are individually stable,
integrate them through the Risk Fusion Engine using rule-based + calibrated fusion.

Multi-task neural fusion may be revisited as an **optional later phase** only
after all expert models produce application-correct outputs.
