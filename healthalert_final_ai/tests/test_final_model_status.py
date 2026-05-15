from pathlib import Path


def test_current_model_status_contains_expected_final_statuses():
    text = Path("outputs/hybrid_redesign/CURRENT_MODEL_STATUS.md").read_text(encoding="utf-8")
    expected = [
        "Fall Expert Core no-UMAFall: `ACCEPTED`",
        "PPG Quality Expert: `ACCEPTED`",
        "Activity Expert v2 UCI-HAR-only: `ACCEPTED_SINGLE_SOURCE_BASELINE`",
        "Activity Expert v0: `REPLACED_BY_ACTIVITY_V2_UCI_ONLY`",
        "Activity Balanced v1: `REJECTED`",
        "Activity v2 PAMAP2 mixed: `REVIEWED_NOT_ACCEPTED`",
        "PAMAP2 integration: `INTEGRATED_BUT_NOT_RUNTIME_ACCEPTED`",
        "Gait Instability v2.1: `ACCEPTED_AUXILIARY_LOW_WEIGHT`",
        "Gait v2.2 ablation: `NOT_ACCEPTED_KEEP_V2_1`",
        "Vitals Context Expert: `REJECTED`",
        "Tremor Context: `DISABLED`",
    ]
    for status_line in expected:
        assert status_line in text


def test_artifact_audit_outputs_exist():
    assert Path("outputs/hybrid_redesign/final_runtime/artifact_audit.md").exists()
    assert Path("outputs/hybrid_redesign/final_runtime/artifact_audit.json").exists()
