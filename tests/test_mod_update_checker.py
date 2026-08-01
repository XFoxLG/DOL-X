"""Tests for upstream release and mutable asset update detection."""

from tools.check_mod_updates import (
    check_github_release,
    extract_version_from_tag,
)


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
