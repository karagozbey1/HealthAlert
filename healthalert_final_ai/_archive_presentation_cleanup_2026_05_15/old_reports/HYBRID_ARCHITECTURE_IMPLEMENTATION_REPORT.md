    # HealthAlert Hybrid Expert Model Architecture — Implementation Report

    **Project**: HealthAlert  
    **Module**: `healthalert_final_ai/`  
    **Report Version**: 1.0  
    **Architecture**: Hybrid Expert Model + Runtime Personalization  
    **Status**: Architecture Complete — Fall Expert v1 Trained (baseline, not final) — Threshold Analysis Complete — UMAFall Audit Pending — Activity/PPG/Gait Training Pending

    ---

    ## 1. Executive Summary

    This report documents the complete redesign of the HealthAlert AI pipeline from a collapsed multi-task model into a correct, modular Hybrid Expert architecture with runtime personalization and calibrated risk fusion.

    The original multi-task model achieved `fall_recall = 1.0000` but `normal_recall = 0.0000` and `macro_f1 = 0.0797`, representing a total model collapse where **every window was classified as fall**. This report documents the root cause analysis, redesign decisions, implementation, and validation of the new architecture.

    ---

    ## 2. Collapse Proof — Original Multi-Task System

    | Metric | Value | Status |
    |---|---|---|
    | `fall_recall` | 1.0000 | Apparent win |
    | `normal_recall` | 0.0000 | FATAL COLLAPSE |
    | `near_fall_recall` | 0.0000 | FATAL COLLAPSE |
    | `fall_precision` | 0.1358 | FAILED |
    | `macro_f1` | 0.0797 | FAILED |
    | `collapse_detected` | YES | System unusable |

    **Conclusion**: The original system was completely unusable in a real application. Any patient monitored would receive continuous false fall alerts.

    ---

    ## 3. Root Cause Analysis

    Five root causes were identified:

    1. **Shared gradient interference**: Multi-task architecture caused fall detection gradients to dominate all other task heads, suppressing normal/near_fall predictions.

    2. **near_fall as a hard 3rd class**: Including near_fall as a training class introduced gradient instability — the model found it easier to map all patterns to "fall" than to distinguish near_fall from fall.

    3. **Extreme WeightedRandomSampler**: Aggressive class weighting forced the model to overfit on fall patterns at the expense of all other classes.

    4. **Unsafe checkpoint metric (fall_recall alone)**: `best_model.pt` was saved based solely on `fall_recall`, which rewarded collapse behavior (1.0 recall = save as best).

    5. **No collapse detection**: No rejection mechanism existed to detect and reject collapsed checkpoints.

    ---

    ## 4. Architecture Decision: Expert-First

    **Decision**: Replace the single multi-task model with independent expert models, each trained on a single task with appropriate data.

    **Rationale**:
    - Each expert has a clear objective function.
    - Data routing prevents modality contamination (PPG-only data cannot enter fall expert).
    - Collapse in one expert does not affect others.
    - Each expert can be independently validated, replaced, or retrained.

    ---

    ## 5. Expert Models Implemented

    ### 5.1 Fall Detection Expert (`fall_expert.py`)
    - **Architecture**: CNN1D (3 layers) + GRU + binary sigmoid head
    - **Input**: 6-channel IMU (acc+gyro), 200-sample window (4s @ 50Hz)
    - **Output**: `{"fall_prob", "normal_prob", "logit"}`
    - **Labels**: normal=0, fall=1 (near_fall excluded from training)
    - **near_fall policy**: Excluded from binary training; kept as holdout for threshold analysis only
    - **Collapse rejection**: `is_collapse()` — hard reject if `normal_recall < 0.40`, `fall_precision < 0.40`, `macro_f1 < 0.40`, or dominant class ratio > 90%

    ### 5.2 Activity Context Expert (`activity_expert.py`)
    - **Architecture**: CNN1D + GRU + 8-class softmax head
    - **Classes**: walking, sitting, standing, lying, running, stairs, transition, unknown
    - **Purpose**: Provides activity context to modulate risk (e.g., running vs lying during motion)

    ### 5.3 PPG Quality Expert (`ppg_quality_expert.py`)
    - **Architecture**: CNN1D + GlobalAvgPool + 4-class softmax head
    - **Classes**: good_quality, bad_quality, motion_artifact, unknown
    - **Purpose**: Gates vitals context contribution — poor PPG quality suppresses vitals score

    ### 5.4 Vitals Context Expert (`vitals_context_expert.py`)
    - **Architecture**: VitalsContextMLP (recommended) or VitalsContextCNN
    - **Input**: 8 physiological features (HR, HR std, HR slope, PPG quality, motion, RR, SpO2, window norm)
    - **Purpose**: Physiological context only — NOT diagnosis

    ### 5.5 Gait Instability Expert (`gait_instability_expert.py`)
    - **Architecture**: CNN1D + GRU + binary sigmoid head
    - **Output**: `gait_instability_score` (P(unstable))
    - **Purpose**: Detects pre-fall gait degradation; contributes 15 points max to risk score

    ### 5.6 Tremor Context (Disabled)
    - **Status**: `enabled_for_training: false` — insufficient data (< 500 windows)
    - **Policy**: See `outputs/hybrid_redesign/personalization/tremor_policy.md`

    ---

    ## 6. Dataset Routing Contract

    Dataset routing is defined in `config/hybrid_task_routing.yaml` — the single source of truth for which datasets can enter each expert's training pipeline.

    **Key protections**:
    - `but_ppg`, `bidmc`, `ppg_dalia`, `wildppg`, `wesad` are **forbidden** in `fall_detection`
    - `near_fall` label is `exclude` in `fall_detection.label_policy.binary_baseline`
    - `tremor_context.enabled_for_training: false`

    The `scripts/audit_hybrid_dataset_contract.py` script validates routing compliance before any training run.

    ---

    ## 7. Collapse Rejection System

    The `FallExpertTrainer` implements hard rejection of collapsed checkpoints:

    ```python
    # is_collapse() rejects if ANY condition is true:
    normal_recall < 0.40          # must detect normal patterns
    fall_precision < 0.40          # must have acceptable precision
    macro_f1 < 0.40               # must be balanced across classes
    dominant_class_ratio > 0.90    # cannot predict one class > 90% of time
    ```

    **Checkpoint save policy**:
    - `last_model.pt`: saved every epoch (for debugging collapsed runs)
    - `best_model.pt`: only saved when `checkpoint_valid=True` and `app_score > prev_best`
    - `app_score = 0.35*fall_recall + 0.25*fall_precision + 0.25*macro_f1 + 0.15*normal_recall`

    ---

    ## 8. Runtime Personalization Engine

    **Design principle**: Personalization is purely statistical at runtime — NO model retraining per user.

    **Components**:

    | File | Purpose |
    |---|---|
    | `baseline_storage_schema.py` | `UserBaselineProfile` dataclass — all user baseline fields |
    | `user_baseline.py` | `UserBaselineEngine` — EMA-based runtime accumulation |
    | `personal_deviation.py` | Standalone deviation scoring for fusion engine |

    **EMA alpha schedule**:
    - Cold-start (confidence=0): alpha=0.50 (fast adaptation)
    - Calibrated (confidence≥0.80): alpha=0.05 (stable baseline)

    **Baseline update blocking** — update NEVER occurs when:
    - `risk_level in ("high_risk", "critical")`
    - `fall_probability >= 0.30`
    - `final_risk_score >= 40`
    - `signal_confidence < 0.50`
    - `user_confirmed_emergency = True`

    ---

    ## 9. Risk Fusion Engine

    The `RiskFusionEngine` combines all expert outputs into a single risk score using deterministic rules.

    **Score formula**:
    ```
    fall_score     = fall_probability × 55 × signal_confidence
    gait_score     = gait_instability × 15 × signal_confidence
    vitals_score   = vitals_context × 10 × ppg_quality_factor
    near_fall_score = near_fall_signal × 10 × signal_confidence
    post_impact_boost = 10 if fall_prob ≥ 0.6 AND lying ≥ 0.4 else 0

    ml_risk_score = sum of above components
    personalization_adjustment = deviation × scale × confidence  (range: -10 to +20)
    final_risk_score = clip(ml_risk_score + personalization_adjustment, 0, 100)
    ```

    **Risk levels**:
    | Level | Score Range | Action |
    |---|---|---|
    | normal | < 25 | continue_monitoring |
    | caution | 25–50 | increase_monitoring_frequency |
    | high_risk | 50–70 | prepare_alert |
    | critical | ≥ 70 | ask_user_are_you_okay |

    **Robustness**:
    - Missing IMU → fall score = 0, reason added
    - Missing PPG → vitals score = 0, reason added
    - Missing baseline → no personalization adjustment
    - Score always clipped to [0, 100]

    ---

    ## 10. Temporal Risk Smoother

    The `TemporalRiskSmoother` prevents single noisy windows from triggering alerts.

    **Rules**:
    - Rolling buffer of last 5 windows
    - EMA smoothing (alpha=0.40) on risk score
    - Escalation: 2+ consecutive high-risk windows required to escalate
    - De-escalation: 3+ consecutive lower readings required
    - **Exception**: Immediate critical if `fall_probability ≥ 0.85` AND post-impact evidence (lying ≥ 0.30)
    - Cooldown: 120s after critical alert, suppresses duplicate alerts

    ---

    ## 11. Hybrid Inference Service

    `HybridInferenceService` orchestrates all components for a single inference call.

    **Supported modes**:
    - IMU-only (no PPG sensor)
    - IMU + PPG (full pipeline)
    - Missing IMU at runtime (fall = 0, no crash)
    - Poor PPG quality (vitals contribution reduced)
    - No user baseline (cold-start, population defaults)

    **Output schema**:
    ```json
    {
    "final_risk_score": 0-100,
    "risk_level": "normal|caution|high_risk|critical",
    "fall_probability": 0-1,
    "gait_instability_score": 0-1,
    "ppg_quality_score": 0-1 or null,
    "vitals_context_score": 0-1,
    "personal_deviation_score": 0-1,
    "personalization_confidence": 0-1,
    "confidence_score": 0-1,
    "reasons": ["list", "of", "reasons"],
    "recommended_action": "string",
    "temporal_smoothing_applied": true/false
    }
    ```

    ---

    ## 12. Tests

    All 15 required test cases implemented in `tests/test_hybrid_architecture.py`:

    | # | Test | Status |
    |---|---|---|
    | 1 | Dataset routing respected (allowed_datasets defined) | PASS |
    | 2 | PPG-only data forbidden in fall expert | PASS |
    | 3 | tremor_context not enabled for training | PASS |
    | 4 | Collapsed checkpoint detected by is_collapse() | PASS |
    | 5 | best_model.pt not saved on collapse | PASS |
    | 6 | Fall expert excludes near_fall (label_policy) | PASS |
    | 7 | Risk fusion score always [0, 100] (4 parametrized cases) | PASS |
    | 8 | Missing PPG does not crash (fusion engine) | PASS |
    | 8b | Missing PPG does not crash (inference service) | PASS |
    | 9 | Missing baseline → cold-start confidence=0 | PASS |
    | 10 | Baseline blocked during critical risk | PASS |
    | 11 | Baseline allowed during normal risk | PASS |
    | 12 | High personal deviation increases final_risk_score | PASS |
    | 13 | Temporal smoothing reduces single-window spike | PASS |
    | 14 | Critical escalation after persistent high risk | PASS |
    | 15 | Output contains reasons and confidence_score | PASS |

    **Total**: 19 test cases (including parametrized variants), **19 PASSED**.

    ---

    ## 13. File Inventory

    ### Config
    - `config/hybrid_task_routing.yaml` — dataset routing contract

    ### Source Package: `src/healthalert/`
    - `__init__.py`
    - `models/fall_expert.py`
    - `models/activity_expert.py`
    - `models/ppg_quality_expert.py`
    - `models/vitals_context_expert.py`
    - `models/gait_instability_expert.py`
    - `training/fall_expert_trainer.py`
    - `evaluation/fall_expert_eval.py`
    - `personalization/__init__.py`
    - `personalization/baseline_storage_schema.py`
    - `personalization/user_baseline.py`
    - `personalization/personal_deviation.py`
    - `fusion/__init__.py`
    - `fusion/risk_thresholds.py`
    - `fusion/risk_fusion_engine.py`
    - `fusion/temporal_risk_smoother.py`
    - `inference/__init__.py`
    - `inference/hybrid_inference_service.py`

    ### Scripts
    - `scripts/audit_hybrid_dataset_contract.py`
    - `scripts/train_fall_expert.py`
    - `scripts/train_activity_expert.py`
    - `scripts/train_ppg_quality_expert.py`
    - `scripts/train_vitals_context_expert.py`
    - `scripts/train_gait_instability_expert.py`
    - `scripts/simulate_personalization_engine.py`
    - `scripts/test_risk_fusion_engine.py`
    - `scripts/run_hybrid_inference_demo.py`

    ### Tests
    - `tests/test_hybrid_architecture.py`

    ### Reports & Docs
    - `outputs/hybrid_redesign/audit/why_multitask_first_was_deprecated.md`
    - `outputs/hybrid_redesign/personalization/tremor_policy.md`

    ---

    ## 14. Smoke Training

    **Command**:
    ```bash
    cd healthalert_final_ai
    python scripts/train_fall_expert.py --smoke --device cpu
    ```

    **Expected behavior**:
    - No real windowed data found → generates synthetic data (2000 windows)
    - Trains for 5 epochs
    - Collapse rejection logic activated if any epoch produces collapsed metrics
    - Output in `outputs/hybrid_redesign/fall_expert/`
    - `best_model.pt` saved only if not collapsed

    ---

    ## 15. Data Strategy Clarification

    ### Training Data Source — Public Academic Datasets Only

    All expert models are trained exclusively on **prepared public academic dataset windows**
    stored in the offline pipeline:

    ```
    data/raw/             ← downloaded open datasets
    data/standardized/    ← format-normalized
    data/windowed/        ← 4-second windows @ 50Hz
    data/splits/          ← train/val/test splits
    outputs/windowed_dataset/  ← final NPZ files consumed by training scripts
    ```

    ESP32 + MPU6050 + MAX30102 **live sensor data is NOT used for model training**.

    ### Live Sensor Data — Inference and Personalization Only

    | Use Case | Data Source |
    |---|---|
    | Offline expert model training | Prepared public dataset NPZ windows |
    | Presentation / demo inference | Live ESP32 sensor stream |
    | App live risk display | Live ESP32 sensor stream |
    | Runtime user baseline (EMA) | Live ESP32 sensor stream |
    | final_risk_score demonstration | Live ESP32 sensor stream |

    ### Current Limitations
    - Training scripts currently fall back to synthetic data when prepared dataset NPZ files
      are not found in the expected pipeline directories
    - Activity and PPG quality expert trainers need loaders wired to their respective
      allowed datasets from `config/hybrid_task_routing.yaml`
    - Vitals context features must be pre-computed from PPG+HR signals before training

    ### Recommended Next Steps

    1. **UMAFall diagnostic audit** — UMAFall dominates test set (91.2%) and contributes
       98.7% of false negatives (miss_rate=0.387). Visualise raw IMU windows, verify sensor
       placement metadata, check normalization alignment. Required before Fall Expert v2.
    2. **Activity Expert training** — wire `train_activity_expert.py` to UCI HAR / MobiAct
       NPZ windows; train and validate non-collapse
    3. **PPG Quality Expert training** — wire `train_ppg_quality_expert.py` to allowed
       PPG datasets from `config/hybrid_task_routing.yaml`
    4. **Gait Instability Expert training** — wire `train_gait_instability_expert.py`
    5. **Risk Fusion integration** — combine Fall Expert v1 with Activity/Gait/PPG outputs;
       `fall_prob` alone must NOT determine final `risk_level`; use risk-band design
       (see `config/fall_expert_v1.yaml`)
    6. **Fall Expert v2 (post-audit)** — retrain with UMAFall-aware normalization if audit
       confirms distribution mismatch
    7. **Integration testing** — connect `HybridInferenceService` to backend API
       (`backend/routers/`) for live ESP32 inference demo
    8. **Clinical validation** — validate risk thresholds before deployment

    ---

    ## 16. Architecture Summary Diagram

    ```
    Sensor Window (4s @ 50Hz)
            │
            ├── IMU (6ch) ──────────────────────────────────┐
            │       │                                         │
            │       ├──► FallExpertCNN ──────────► fall_prob │
            │       ├──► ActivityExpertCNN ─────► activity   │
            │       └──► GaitInstabilityExpertCNN ► gait     │
            │                                                 │
            └── PPG (1ch) ─────────────────────────────────  │
                    │                                         │
                    ├──► PPGQualityExpertCNN ──► ppg_quality  │
                    └──► VitalsContextMLP ─────► vitals_score │
                                                            │
                                                            ▼
    UserBaselineEngine ──────────────────────► deviation_score
                                                            │
                                                            ▼
                                            RiskFusionEngine
                                                    │
                                                    ▼
                                        TemporalRiskSmoother
                                                    │
                                                    ▼
                                        { final_risk_score,
                                            risk_level,
                                            reasons,
                                            recommended_action }
                                                    │
                                                    ▼
                                        Backend API / Mobile App
    ```

    ---

    ---

    ## 17. Fall Expert v1 Training Summary

    | Item | Value |
    |------|-------|
    | Status | **Baseline — valid, non-collapsed, NOT final** |
    | Best epoch | 23 / 30 |
    | Val app_score | 0.7902 |
    | Test app_score (t=0.40) | 0.7596 |
    | Test roc_auc | 0.8427 |
    | Test fall_recall (t=0.35) | 0.678 |
    | Test fall_recall (t=0.30) | 0.713 |
    | collapse_detected | false (all 30 epochs) |
    | Config | `config/fall_expert_v1.yaml` |
    | Checkpoint | `outputs/hybrid_redesign/fall_expert/best_model.pt` |

    ### Risk-Band Thresholds (operational)

    | fall_prob range | Band | Action |
    |-----------------|------|--------|
    | `< 0.30` | normal | No fall contribution |
    | `0.30 – 0.59` | caution | Elevated monitoring; score scales linearly |
    | `0.60 – 0.84` | high_risk | Prepare alert; gated by Activity/Gait |
    | `≥ 0.85` + post-impact | critical | Immediate alert |

    ### Known Limitation — UMAFall

    UMAFall accounts for 91.2% of the test set and 98.7% of all false negatives
    (miss_rate=0.387 vs 0.026–0.077 for all other datasets). The model assigns
    fall_prob < 0.10 to 21.6% of these misses, indicating a structural gap.
    A dedicated UMAFall normalization/source-distribution audit is required before
    declaring Fall Expert final.

    ---

    *Report generated as part of HealthAlert Hybrid Expert Model Architecture Redesign.*
