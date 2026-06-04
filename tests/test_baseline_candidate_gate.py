"""Baseline candidate gate helper tests."""

import base64
import io
import json
import zipfile

import pytest

from tools.artifact_inspection import APK_HTML_MEMBER, load_html_artifact
from tools.baseline_candidate_gate import (
    CANDIDATE_CODES,
    DEFAULT_STABLE_CODE_ORDER,
    PARTIAL_GATE_LEVEL,
    audit_apk_target,
    check_phase2_promotion,
    summarize_browser_reports,
)


REQUIRED_PAYLOAD_NAMES = (
    "ModLoaderGui",
    "ModI18N",
    "maplebirch",
    "cheatExtended",
    "More Love Interests Mod",
    "Custom-Spellbook",
    "Lyra",
)


def _embedded_candidate_mod_zip() -> str:
    buffer = io.BytesIO()
    boot_json = {
        "name": "Phase 1A baseline candidate bundle",
        "mods": list(REQUIRED_PAYLOAD_NAMES),
    }
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", json.dumps(boot_json, ensure_ascii=False))
        zf.writestr("main.js", "console.log('phase1a candidate');")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _candidate_html() -> str:
    return (
        "<html><script>window.modDataValueZipList = "
        + json.dumps([_embedded_candidate_mod_zip()])
        + ";</script></html>"
    )


def _candidate_artifact_name(slug: str, suffix: str) -> str:
    code = CANDIDATE_CODES[slug]
    slug_prefix = "" if slug == "base" else f"{slug}-"
    return f"DoL-{slug_prefix}ucb-more-love-custom-spellbook-cheat-extended-maplebirch-{code}.{suffix}"


def _write_candidate_apk(root, slug: str):
    apk_path = root / _candidate_artifact_name(slug, "apk")
    with zipfile.ZipFile(apk_path, "w") as zf:
        zf.writestr(APK_HTML_MEMBER, _candidate_html())
        zf.writestr("AndroidManifest.xml", "<manifest />")
    return apk_path


@pytest.mark.config
def test_baseline_candidate_apk_audit_is_static_and_requires_all_four_candidates(tmp_path):
    apk_paths = [_write_candidate_apk(tmp_path, slug) for slug in DEFAULT_STABLE_CODE_ORDER]
    html_member, html_content = load_html_artifact(apk_paths[0])

    assert html_member == APK_HTML_MEMBER
    assert html_content is not None
    assert "modDataValueZipList" in html_content

    output = tmp_path / "baseline-candidate-apk-audit.json"
    assert audit_apk_target(tmp_path, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert payload["strict_candidate_presence"]["missing_slugs"] == []
    assert set(payload["strict_candidate_presence"]["seen_slugs"]) == set(DEFAULT_STABLE_CODE_ORDER)
    assert len(payload["results"]) == 4
    for result in payload["results"]:
        assert result["success"] is True
        assert result["html_member"] == APK_HTML_MEMBER
        assert result["manifest_debuggable"] is None
        assert result["release_debuggable_ok"] is None
        assert all(result["required_payloads"].values())
        assert not result["errors"]
        assert any("Phase 1A APK audit is static" in warning for warning in result["warnings"])


def _write_browser_smoke_evidence(reports_dir, slug: str) -> None:
    slug_dir = reports_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "success": True,
        "issue_counts": {"high": 0},
        "browser_diagnostics": {"pageerror_count": 0},
        "game_ready": {"ready": True, "passage": "Orphanage Intro"},
        "enter_game": {"success": True},
        "startup_interactions": {"success": True},
        "package_identity": {"profile_slug_match": True},
    }
    report = {"issues": []}
    (slug_dir / "browser-smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False),
        encoding="utf-8",
    )
    (slug_dir / "browser-smoke-report.json").write_text(
        json.dumps(report, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.mark.config
def test_baseline_candidate_browser_summary_requires_four_strict_zip_smokes(tmp_path):
    reports_dir = tmp_path / "browser-smoke"
    for slug in DEFAULT_STABLE_CODE_ORDER:
        _write_browser_smoke_evidence(reports_dir, slug)

    output = tmp_path / "baseline-candidate-zip-browser-summary.json"
    assert summarize_browser_reports(reports_dir, output) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["gate_level"] == PARTIAL_GATE_LEVEL
    assert payload["counts_for_phase2_promotion"] is False
    assert [result["slug"] for result in payload["results"]] == list(DEFAULT_STABLE_CODE_ORDER)
    assert all(result["success"] for result in payload["results"])
    assert all(result["checks"]["passage_orphanage_intro"] for result in payload["results"])


@pytest.mark.config
def test_phase2_promotion_rejects_phase1a_partial_candidate_evidence(tmp_path):
    evidence_paths = []
    for index in range(2):
        evidence_path = tmp_path / f"partial-green-{index}.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "success": True,
                    "gate_level": PARTIAL_GATE_LEVEL,
                    "counts_for_phase2_promotion": False,
                    "head_sha": "abc123",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        evidence_paths.append(evidence_path)

    output = tmp_path / "phase2-promotion-check.json"
    assert check_phase2_promotion(evidence_paths, "abc123", output) == 1

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["default_migration_allowed"] is False
    assert payload["eligible_green_runs"] == []
    assert len(payload["rejected_runs"]) == 2
    assert all(not item["checks"]["gate_level_full"] for item in payload["rejected_runs"])
    assert all(not item["checks"]["counts_for_phase2"] for item in payload["rejected_runs"])
