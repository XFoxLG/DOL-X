"""cheatExtended audit helper tests."""

from types import SimpleNamespace

import pytest
import requests

from tools import cheat_extended_audit


def _rate_limit_error() -> requests.HTTPError:
    response = requests.Response()
    response.status_code = 403
    response._content = b"API rate limit exceeded for user"  # noqa: SLF001
    return requests.HTTPError("rate limit", response=response)


@pytest.mark.config
def test_resolve_asset_falls_back_to_configured_download_url(monkeypatch):
    """GitHub latest API rate limits should not block pinned local audits."""

    def raise_rate_limit(*args, **kwargs):
        raise _rate_limit_error()

    pinned_mod = SimpleNamespace(
        github_repo=cheat_extended_audit.REPO,
        key="cheat_extended",
        release_tag="V1.18(Dev20260325)",
        asset_pattern="cheat_extended.mod.zip",
        download_url="https://example.invalid/cheat_extended.mod.zip",
    )
    monkeypatch.setattr(cheat_extended_audit, "fetch_latest_asset", raise_rate_limit)
    monkeypatch.setattr(
        cheat_extended_audit,
        "load_build_config",
        lambda: SimpleNamespace(modloader_mods=[pinned_mod]),
    )

    resolution = cheat_extended_audit.resolve_asset()

    assert resolution.source == "configured_download_url"
    assert resolution.release["tag_name"] == "V1.18(Dev20260325)"
    assert resolution.asset["browser_download_url"].endswith("cheat_extended.mod.zip")
    assert "rate limited" in resolution.warning


@pytest.mark.config
def test_resolve_asset_reraises_non_rate_limit_http_errors(monkeypatch):
    """Only GitHub API rate limits use the pinned-config fallback."""
    response = requests.Response()
    response.status_code = 404
    response._content = b"not found"  # noqa: SLF001
    error = requests.HTTPError("not found", response=response)

    def raise_not_found(*args, **kwargs):
        raise error

    monkeypatch.setattr(cheat_extended_audit, "fetch_latest_asset", raise_not_found)

    with pytest.raises(requests.HTTPError):
        cheat_extended_audit.resolve_asset()


@pytest.mark.config
def test_build_framework_matrix_marks_maplebirch_canary_only(monkeypatch):
    """The matrix records pinned maplebirch as canary-only and Simple as alternate."""
    maplebirch_mod = SimpleNamespace(
        github_repo="MaplebirchLeaf/SCML-DOL-maplebirchframework",
        enabled=True,
        required_feature_ids=["cheat_extended_maplebirch"],
        release_tag="maplebirch-release-v3.1.13",
        download_url="https://example.invalid/maplebirch-0.5.8.10-v3.1.13.mod.zip",
    )
    monkeypatch.setattr(
        cheat_extended_audit,
        "load_build_config",
        lambda: SimpleNamespace(modloader_mods=[maplebirch_mod]),
    )

    matrix = cheat_extended_audit.build_framework_matrix()

    by_repo = {row.repo: row for row in matrix}
    maplebirch = by_repo["MaplebirchLeaf/SCML-DOL-maplebirchframework"]
    simple = by_repo["emicoto/SCMLSimpleFramework"]

    assert maplebirch.configured is True
    assert maplebirch.enabled is True
    assert maplebirch.status == "configured_pinned_canary_only"
    assert "cheat_extended_maplebirch" in maplebirch.feature_ids
    assert any("canary IDB schema recovery patch" in note for note in maplebirch.notes)
    assert simple.configured is False
    assert simple.status == "not_configured"
