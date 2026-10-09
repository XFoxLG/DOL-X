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


def test_sweep_workflow_summary_excludes_daily_auxiliary_reports() -> None:
    text = _workflow()
    assert "! -path '*/daily-mod-inventory/*'" in text
    assert "! -path '*/daily-mod-passages/*'" in text


def test_sweep_workflow_never_uploads_raw_local_sweep_directory() -> None:
    text = _workflow()
    assert "path: .local/sweep" not in text
    assert "path: sweep-reports" in text
    assert "report_sanitize.py --check" in text


def test_sweep_workflow_pins_target_tag_and_builds_real_package() -> None:
    text = _workflow()
    # 2026-10-06: prepare without --tag built 0.5.12.13 instead of the locked
    # 0.5.11.9 stack, and the raw prepare HTML carries no DOL-X mods.
    assert '--tag "$TARGET_TAG"' in text
    assert 'python main.py warmup' in text
    assert 'python main.py build zip' in text
    assert "--codes \"$TARGET_CODE\"" in text
    assert "v0.5.11.9-1.0.0a-0915" in text


def test_sweep_workflow_verifies_package_identity_fail_closed() -> None:
    text = _workflow()
    assert "tools/target_package_check.py" in text
    assert "--expect-version" in text
    assert "--min-mods 30" in text
    # every browser job re-checks the exact package before sweeping
    assert text.count("Verify package identity") == 5
    # only the verified build artifact (plus its manifest) is uploaded
    assert "name: sweep-package" in text
    assert "output/*.zip" in text
    assert "prepared/mods-manifest.json" in text


def test_sweep_workflow_builds_static_coverage_ledger() -> None:
    text = _workflow()
    assert "- name: Build static coverage ledger" in text
    assert "tools/combat_ledger.py" in text
    # 台账是静态证据，即使分片跑分失败也要产出，但失败时不产出假报告
    assert "HTML_PATH not set" in text
    assert "-o -name 'combat-ledger*.json'" in text
    assert "-o -name 'combat-ledger*.md'" in text
