"""Maplebirch release matrix and static candidate selection tests."""

import zipfile
from pathlib import Path

import pytest

from tools.canary_payload_introspect import PayloadInspection
from tools.maplebirch_version_matrix import (
    BASELINE_TAG,
    HYBRID_TRIAGE_TAGS,
    MAPLEBIRCH_IDB_PATCH_MEMBER,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED,
    assess_idb_patch,
    build_report,
    candidates_from_releases,
    scan_candidates,
    select_smoke_candidates,
    write_json,
    write_markdown,
)


def _release(tag: str, asset_name: str, url_suffix: str | None = None) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"https://example.invalid/{url_suffix or asset_name}",
                "size": 123,
            }
        ],
    }


def _write_payload(payload_path: Path, runtime: str | None) -> None:
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload_path, "w") as payload_zip:
        payload_zip.writestr("boot.json", '{"name":"maplebirch"}')
        if runtime is not None:
            payload_zip.writestr(MAPLEBIRCH_IDB_PATCH_MEMBER, runtime)


@pytest.mark.config
def test_candidates_rank_exact_rollback_before_current_baseline():
    candidates = candidates_from_releases(
        [
            _release(BASELINE_TAG, "maplebirch-0.5.8.10-v3.2.5.modpack"),
            _release("maplebirch-release-v3.2.3", "maplebirch-0.5.8.10-v3.2.3.modpack"),
            _release("maplebirch-release-v3.1.14", "maplebirch-0.5.7.9-v3.1.14.modpack"),
        ]
    )

    assert candidates[0].tag == "maplebirch-release-v3.2.3"
    assert candidates[0].exact_game_match is True
    assert candidates[0].compatibility_risk == "low"
    assert candidates[-1].tag == BASELINE_TAG
    assert candidates[-1].is_baseline is True
    assert candidates[-1].compatibility_risk == "baseline"

    mismatch = next(candidate for candidate in candidates if candidate.tag == "maplebirch-release-v3.1.14")
    assert mismatch.compatibility_risk == "high"


@pytest.mark.config
def test_scan_candidates_selects_static_framework_evidence_once(tmp_path, monkeypatch):
    candidates = candidates_from_releases(
        [
            _release("maplebirch-release-v3.2.3", "maplebirch-0.5.8.10-v3.2.3.modpack"),
            _release("maplebirch-release-v3.1.14", "maplebirch-0.5.7.9-v3.1.14.modpack"),
            _release(BASELINE_TAG, "maplebirch-0.5.8.10-v3.2.5.modpack"),
        ]
    )

    def fake_download(url, dest_path, quiet=False):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(f"downloaded:{url}".encode("utf-8"))

    def fake_inspect(path: Path):
        inspection = PayloadInspection(path=str(path), exists=True, kind="non_zip")
        if "v3.2.5" in path.name:
            inspection.keyword_hits = {}
        elif "v3.1.14" in path.name:
            inspection.keyword_hits = {"TimeEvent": 1, "addto": 1}
        else:
            inspection.keyword_hits = {"maplebirchFrameworks": 1}
        return inspection

    monkeypatch.setattr("tools.maplebirch_version_matrix.download_file", fake_download)
    monkeypatch.setattr("tools.maplebirch_version_matrix.inspect_payload", fake_inspect)

    scans = scan_candidates(candidates, tmp_path)
    selected = select_smoke_candidates(scans, max_count=2)

    assert [candidate.tag for candidate in selected] == [
        "maplebirch-release-v3.2.3",
        "maplebirch-release-v3.1.14",
    ]
    assert all(not scan.candidate.is_baseline or not scan.likely_old_api_candidate for scan in scans)


@pytest.mark.config
def test_build_report_stops_when_static_scan_finds_no_candidate(tmp_path, monkeypatch):
    releases = [_release("maplebirch-release-v3.2.3", "maplebirch-0.5.8.10-v3.2.3.modpack")]

    def fake_download(url, dest_path, quiet=False):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"payload")

    def fake_inspect(path: Path):
        return PayloadInspection(path=str(path), exists=True, kind="non_zip", keyword_hits={})

    monkeypatch.setattr("tools.maplebirch_version_matrix.download_file", fake_download)
    monkeypatch.setattr("tools.maplebirch_version_matrix.inspect_payload", fake_inspect)

    report = build_report(releases, "0.5.8.10", BASELINE_TAG, 2, cache_dir=tmp_path, scan=True)

    assert report.selected_for_smoke == []
    assert report.stop_reason == "no static candidate exposed enough old framework/API evidence; do not build"


@pytest.mark.config
def test_assess_idb_patch_detects_patchable_and_patched_payloads(tmp_path):
    patchable_path = tmp_path / "patchable.mod.zip"
    patched_path = tmp_path / "patched.mod.zip"
    unknown_path = tmp_path / "unknown.mod.zip"
    missing_path = tmp_path / "missing.mod.zip"

    _write_payload(
        patchable_path,
        f"resetDatabase(); objectStoreNames.contains('settings'); {MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL}",
    )
    _write_payload(patched_path, MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED)
    _write_payload(unknown_path, "async withTransaction(e,t,n){return this.db.transaction(e,t)}")
    _write_payload(missing_path, None)

    patchable = assess_idb_patch(patchable_path)
    patched = assess_idb_patch(patched_path)
    unknown = assess_idb_patch(unknown_path)
    missing = assess_idb_patch(missing_path)

    assert patchable.status == "patchable"
    assert patchable.has_original_needle is True
    assert patchable.has_reset_database is True
    assert patchable.has_check_store is True
    assert patchable.has_settings_store is True
    assert patched.status == "already_patched"
    assert patched.has_patched_needle is True
    assert unknown.status == "needle_not_found"
    assert missing.status == "missing_member"


@pytest.mark.config
def test_build_report_filters_hybrid_tags_and_ranks_top_fallback(tmp_path, monkeypatch):
    releases = [
        _release("maplebirch-release-v3.2.3", "maplebirch-0.5.8.10-v3.2.3.mod.zip"),
        _release("maplebirch-release-v3.1.14", "maplebirch-0.5.8.10-v3.1.14.mod.zip"),
        _release("maplebirch-release-v3.1.13", "maplebirch-0.5.8.10-v3.1.13.mod.zip"),
        _release("maplebirch-release-v3.1.10", "maplebirch-0.5.8.10-v3.1.10.mod.zip"),
        _release(BASELINE_TAG, "maplebirch-0.5.8.10-v3.2.5.mod.zip"),
    ]

    def fake_download(url, dest_path, quiet=False):
        runtime = f"resetDatabase(); objectStoreNames.contains('settings'); {MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL}"
        _write_payload(dest_path, runtime)

    def fake_inspect(path: Path):
        inspection = PayloadInspection(path=str(path), exists=True, kind="zip")
        inspection.keyword_hits = {"maplebirchFrameworks": 1, "SCMLSimpleFramework": 1, "CE_options": 1}
        inspection.defines_maplebirch_frameworks = True
        inspection.references_ce_options = True
        return inspection

    monkeypatch.setattr("tools.maplebirch_version_matrix.download_file", fake_download)
    monkeypatch.setattr("tools.maplebirch_version_matrix.inspect_payload", fake_inspect)

    report = build_report(
        releases,
        "0.5.8.10",
        BASELINE_TAG,
        2,
        cache_dir=tmp_path,
        scan=True,
        candidate_tags=HYBRID_TRIAGE_TAGS,
    )

    assert [candidate.tag for candidate in report.candidates] == [
        "maplebirch-release-v3.2.3",
        "maplebirch-release-v3.1.14",
        "maplebirch-release-v3.1.13",
    ]
    assert report.top_candidate is not None
    assert report.top_candidate.tag == "maplebirch-release-v3.2.3"
    assert report.fallback_candidate is not None
    assert report.fallback_candidate.tag == "maplebirch-release-v3.1.14"
    assert [assessment.recommendation for assessment in report.assessments[:2]] == [
        "top_candidate",
        "fallback_candidate",
    ]
    assert report.assessments[0].patch_status == "patchable"
    assert any("Do not trigger Build" in step for step in report.ci_handoff)
    assert any("Manual canary play test" in gate for gate in report.manual_gates)


@pytest.mark.config
def test_report_writers_emit_matrix_outputs(tmp_path):
    report = build_report(
        [_release("maplebirch-release-v3.2.3", "maplebirch-0.5.8.10-v3.2.3.modpack")],
        "0.5.8.10",
        BASELINE_TAG,
        2,
    )
    json_path = tmp_path / "matrix.json"
    markdown_path = tmp_path / "matrix.md"

    write_json(report, json_path)
    write_markdown(report, markdown_path)

    assert "maplebirch-release-v3.2.3" in json_path.read_text(encoding="utf-8")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Maplebirch version candidate matrix" in markdown
    assert "## CI handoff" in markdown
    assert "## Manual gates" in markdown
