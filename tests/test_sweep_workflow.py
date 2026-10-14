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
    assert "assisted-shards:" in text
    assert "assisted-gate:" in text
    assert "nightly:" in text
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
    assert "--shrink-failures" in text
    assert "tools/exploration_gate.py" in text
    assert "--assisted-full-coverage" in text
    assert "tools/mod_passage_inventory.py" in text
    assert "--mod-passage-sweep" in text


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
    assert text.count("Verify package identity") == 8
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


def _job_block(text: str, job_name: str) -> list[str]:
    """Return the raw lines of one top-level job, without a YAML dependency."""
    lines = text.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line == f"  {job_name}:"
    )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ") and not lines[index].startswith("    ")
        ),
        len(lines),
    )
    return lines[start:end]


def _block_scalar_body(block: list[str], step_name: str) -> list[str]:
    """Return the dedented ``run: |`` body of one named step."""
    start = next(
        index for index, line in enumerate(block) if line.strip() == f"- name: {step_name}"
    )
    run_at = next(
        index
        for index in range(start, len(block))
        if block[index].strip().startswith("run:")
    )
    assert block[run_at].strip() == "run: |", block[run_at]
    body: list[str] = []
    indent: int | None = None
    for line in block[run_at + 1 :]:
        if not line.strip():
            body.append("")
            continue
        current = len(line) - len(line.lstrip(" "))
        if indent is None:
            indent = current
        if current < indent:
            break
        body.append(line[indent:])
    return body


def test_sweep_workflow_nightly_heredoc_terminator_is_unindented() -> None:
    """2026-10-14: the nightly batch check failed with
    ``here-document at line 21 delimited by end-of-file``.

    Inside a YAML block scalar every line is dedented, so a heredoc terminator
    written at the surrounding indentation stays indented in the rendered script
    and bash never matches it. The terminator must dedent to column 0.
    """
    body = _block_scalar_body(
        _job_block(_workflow(), "nightly"),
        "Run natural exploration across seeds",
    )
    openers = [
        i for i, line in enumerate(body) if line.strip().startswith("python - <<'PY'")
    ]
    assert openers, "nightly batch heredoc disappeared"
    for index in openers:
        terminator = next(
            (line for line in body[index + 1 :] if line.strip() == "PY"),
            None,
        )
        assert terminator is not None, "nightly batch heredoc has no PY terminator"
        assert terminator == "PY", (
            "heredoc terminator must dedent to column 0; got "
            f"{terminator!r} (bash reports 'delimited by end-of-file')"
        )


def test_sweep_workflow_nightly_upload_references_an_existing_step_id() -> None:
    """2026-10-14: nightly's upload step was gated on ``steps.export`` but the
    export step had no ``id``, so every nightly report was silently discarded.
    """
    for job_name in ("daily", "nightly"):
        block = _job_block(_workflow(), job_name)
        ids = {
            line.strip().split(":", 1)[1].strip()
            for line in block
            if line.strip().startswith("id:")
        }
        gated = [line for line in block if "steps.export." in line]
        assert gated, f"job {job_name!r} no longer gates anything on steps.export"
        assert "export" in ids, (
            f"job {job_name!r} gates a step on steps.export.* but no step in that "
            "job declares id: export"
        )
