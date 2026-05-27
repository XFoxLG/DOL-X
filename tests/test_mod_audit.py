"""Mod audit error classification tests."""

import io
import zipfile

import pytest

from lyra.utils import GitHubReleaseAsset, GitHubReleaseError
from tools import mod_audit


def _mod_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("boot.json", "{}")
        zf.writestr("main.js", "console.log('ok');")
    return buffer.getvalue()


@pytest.mark.mod
def test_github_rate_limit_is_classified_separately(tmp_path, monkeypatch):
    """A GitHub rate limit is inconclusive, not proof that an asset vanished."""

    def raise_rate_limit(*args, **kwargs):
        raise GitHubReleaseError(
            "rate limit",
            status_code=403,
            response_text="API rate limit exceeded for user",
        )

    monkeypatch.setattr(mod_audit, "get_github_release_asset", raise_rate_limit)

    result = mod_audit.ModAuditor(tmp_path, use_cache=False).audit_mod(
        key="modloader_gui",
        name="modloader_gui",
        github_repo="DoL-Lyra/sugarcube-2-ModLoaderGui",
        asset_pattern=".mod.zip",
        release_tag="latest",
    )

    assert result.download_success is False
    assert result.error_kind == "rate_limited"
    assert any("不是 asset 删除证据" in note for note in result.risk_notes)
    assert not any("Release asset 不存在" in note for note in result.risk_notes)


@pytest.mark.mod
def test_missing_release_asset_is_classified_as_asset_missing(tmp_path, monkeypatch):
    """A successful GitHub response with no matching asset remains asset_missing."""

    monkeypatch.setattr(mod_audit, "get_github_release_asset", lambda *a, **k: None)

    result = mod_audit.ModAuditor(tmp_path, use_cache=False).audit_mod(
        key="missing",
        name="missing",
        github_repo="owner/repo",
        asset_pattern="missing.mod.zip",
        release_tag="latest",
    )

    assert result.download_success is False
    assert result.error_kind == "asset_missing"
    assert any("Release asset 不存在" in note for note in result.risk_notes)


@pytest.mark.mod
def test_resolved_asset_name_controls_zip_validation(tmp_path, monkeypatch):
    """AU .model patterns resolve to .zip assets and should still be validated."""

    monkeypatch.setattr(
        mod_audit,
        "get_github_release_asset",
        lambda *a, **k: GitHubReleaseAsset(
            url="https://example.invalid/AUfemale.model_v0.8.0.zip?download=1",
            name="AUfemale.model_v0.8.0.zip",
            tag="mod",
            version="v0.8.0",
        ),
    )

    auditor = mod_audit.ModAuditor(tmp_path, use_cache=False)
    monkeypatch.setattr(auditor, "_download_file", lambda *a, **k: _mod_zip_bytes())

    result = auditor.audit_mod(
        key="AUfemale.model",
        name="AUfemale.model",
        github_repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_pattern="AUfemale.model",
        release_tag="mod",
    )

    assert result.download_success is True
    assert result.asset_name == "AUfemale.model_v0.8.0.zip"
    assert result.is_zip is True
    assert result.zip_valid is True
    assert result.risk_level == "low"
