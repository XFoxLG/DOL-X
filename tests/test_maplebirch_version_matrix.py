"""Maplebirch release matrix and static candidate selection tests."""

from pathlib import Path

import pytest

from tools.canary_payload_introspect import PayloadInspection
from tools.maplebirch_version_matrix import (
    BASELINE_TAG,
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
    assert "Maplebirch version candidate matrix" in markdown_path.read_text(encoding="utf-8")
