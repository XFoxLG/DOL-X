"""Tests for upstream release and mutable asset update detection."""

import json
from types import SimpleNamespace

import pytest
import requests

from tools.check_mod_updates import (
    assess_risk,
    check_all_mods,
    check_github_release,
    extract_version_from_tag,
    main,
    render_summary,
)
from lyra.config_loader import ModloaderModConfig


class FakeGitHubResponse:
    """Minimal requests response used by update-checker tests."""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_extract_version_from_prefixed_framework_tag():
    assert extract_version_from_tag("maplebirch-release-v4.1.13") == "4.1.13"
    assert extract_version_from_tag("v1.0.1") == "1.0.1"


def test_same_prerelease_tag_detects_changed_asset_digest(monkeypatch):
    release_payload = [
        {
            "tag_name": "Pre-release",
            "html_url": "https://example.invalid/release",
            "published_at": "2026-07-23T15:09:21Z",
            "prerelease": True,
            "draft": False,
            "body": "",
            "assets": [
                {
                    "name": "cheat_extended.mod.zip",
                    "digest": "sha256:new-digest",
                }
            ],
        }
    ]
    monkeypatch.setattr(
        "tools.check_mod_updates.requests.get",
        lambda *args, **kwargs: FakeGitHubResponse(release_payload),
    )

    result = check_github_release(
        repo="example/project",
        current_tag="Pre-release",
        mod_key="cheat_extended",
        asset_pattern="cheat_extended.mod.zip",
        include_prerelease=True,
        lock_data={
            "mods": {
                "cheat_extended": {
                    "last_tested_sha256": "old-digest",
                }
            }
        },
    )

    assert result["has_update"] is True
    assert result["release_tag_changed"] is False
    assert result["release_asset_changed"] is True
    assert result["risk_level"] == "medium"


def test_same_tag_and_digest_are_current(monkeypatch):
    release_payload = {
        "tag_name": "maplebirch-release-v4.1.13",
        "html_url": "https://example.invalid/release",
        "published_at": "2026-07-01T15:32:51Z",
        "prerelease": False,
        "draft": False,
        "body": "",
        "assets": [
            {
                "name": "maplebirch-0.5.10.12-v4.1.13.mod.zip",
                "digest": "sha256:known-digest",
            }
        ],
    }
    monkeypatch.setattr(
        "tools.check_mod_updates.requests.get",
        lambda *args, **kwargs: FakeGitHubResponse(release_payload),
    )

    result = check_github_release(
        repo="example/project",
        current_tag="maplebirch-release-v4.1.13",
        mod_key="maplebirch",
        asset_pattern="maplebirch-0.5.10.12-v4.1.13.mod.zip",
        include_prerelease=False,
        lock_data={
            "mods": {
                "maplebirch": {
                    "last_tested_sha256": "known-digest",
                }
            }
        },
    )

    assert result["has_update"] is False
    assert result["release_tag_changed"] is False
    assert result["release_asset_changed"] is False


def check_payload(monkeypatch, payload, **kwargs):
    monkeypatch.setattr("tools.check_mod_updates.requests.get", lambda *a, **k: FakeGitHubResponse(payload))
    return check_github_release("example/project", "v1.0.0", "example", "mod.zip", True, {}, **kwargs)


def test_release_order_uses_publication_date_and_ignores_draft(monkeypatch):
    def release(tag, date, draft=False):
        return {"tag_name": tag, "html_url": "https://example.invalid/release", "published_at": date, "draft": draft}
    result = check_payload(monkeypatch, [
        release("v9.0.0", "2026-11-08T00:00:00Z", True),
        release("v1.0.0", "2026-10-01T00:00:00Z"),
        release("v2.0.0", "2026-11-07T00:00:00Z"),
    ])
    assert result["latest"] == "v2.0.0"
    assert result["has_update"]
    assert result["asset_verification"] == "not_matched"


@pytest.mark.parametrize("payload", [[], [{"tag_name": "v1.0.0", "assets": []}], {"message": "bad gateway"}])
def test_empty_or_invalid_release_is_a_reported_failure(monkeypatch, payload):
    result = check_payload(monkeypatch, payload)
    assert result["status"] == "error"
    assert result["error_kind"] == "invalid_release"


def test_prerelease_does_not_hide_major_risk_and_minor_is_medium():
    assert assess_risk("x", "v4.1.14", "v5.6.2", {}, True)[0] == "high"
    assert assess_risk("x", "v4.1.14", "v4.2.0", {}, False)[0] == "medium"


def test_failed_checks_and_skipped_mods_never_report_everything_current(monkeypatch, tmp_path):
    mods = [
        ModloaderModConfig("example/live", "mod.zip", key="live", release_tag="v1"),
        ModloaderModConfig("example/pin", "mod.zip", key="pin", track_upstream=False),
        ModloaderModConfig("example/off", "mod.zip", key="off", enabled=False),
    ]
    monkeypatch.setattr("tools.check_mod_updates.load_build_config", lambda: SimpleNamespace(modloader_mods=mods))
    def offline(*args, **kwargs):
        raise requests.ConnectionError("network unavailable")
    monkeypatch.setattr("tools.check_mod_updates.requests.get", offline)
    watch = tmp_path / "watch.toml"
    watch.write_text('[[sources]]\nkey="fork"\nname="Fork"\nrepo="example/fork"\nobserved_tag="v2"\n', encoding="utf-8")
    report = check_all_mods(watch_path=watch)
    assert report["check_complete"] is False
    assert report["total_checked"] == 1
    assert report["errors_count"] == 2
    assert {row["reason"] for row in report["skipped"]} == {"pinned", "disabled"}
    summary = render_summary(report)
    assert "检查未完成" in summary
    assert "主动锁定" in summary
    assert "所有 Mod 均为最新版本" not in summary
    monkeypatch.setattr("tools.check_mod_updates.check_all_mods", lambda **kwargs: report)
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert main(["--output", str(output), "--markdown", str(markdown)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["errors_count"] == 2
    assert markdown.read_text(encoding="utf-8") == summary
