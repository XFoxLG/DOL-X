"""Static contracts for the cloud shard workflow."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "sweep.yaml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_sweep_workflow_declares_prepare_shards_and_summary() -> None:
    text = _workflow()
    assert "prepare:" in text
    assert "passage-shards:" in text
    assert "scenario:" in text
    assert "env-shards:" in text
    assert "combat-shards:" in text
    assert "summary:" in text
    assert "fail-fast: false" in text
    assert "timeout-minutes: 210" in text


def test_sweep_workflow_shard_counts_and_summary_expectations() -> None:
    text = _workflow()
    assert "shard: [0, 1, 2, 3]" in text
    assert "shard: [0, 1, 2, 3, 4, 5, 6, 7]" in text
    assert "daily) EXPECTED=4" in text
    assert "full) EXPECTED=13" in text
    assert "combat-full) EXPECTED=8" in text
    assert "env-full) EXPECTED=8" in text
    assert "tools/sweep_summary.py" in text


def test_sweep_workflow_passes_identity_shard_args() -> None:
    text = _workflow()
    assert "--shard-index" in text
    assert "--shard-count" in text
    assert "--tier initiators" in text
    assert "--tier full" in text
    assert "--expected-shards" in text


def test_sweep_workflow_never_uploads_raw_local_sweep_directory() -> None:
    text = _workflow()
    assert "path: .local/sweep" not in text
    assert "path: sweep-reports" in text
    assert "report_sanitize.py --check" in text
