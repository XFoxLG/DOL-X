"""Asset-selection tests for the Chinese-localization release downloader.

These cover ``Downloader.download_from_chs_repo()``, which picks the critical
build inputs out of a localization release. The 0.5.11.9 release reshaped that
asset list (ModLoader v2.101.1 packaging), so the selection rules and their
failure mode are pinned here instead of being discovered during a build.
"""

import pytest

from lyra.downloader import CRITICAL_CHS_ASSET_KEYS, Downloader
from lyra.paths import BuildPaths


# Verbatim asset list of release v0.5.11.9-chs-1.0.0a, read from the GitHub API
# on 2026-09-15. Order is preserved because selection is order-sensitive: the
# polyfill APK is listed BEFORE the plain APK, and both end in .APK and contain
# "ModLoader", so a matcher that forgets to exclude polyfill silently selects
# the wrong Android package instead of failing.
CHS_0511_ASSET_NAMES = [
    "DoL-ModLoader-0.5.11.9-v2.101.1-polyfill.APK",
    "DoL-ModLoader-0.5.11.9-v2.101.1-polyfill.zip",
    "DoL-ModLoader-0.5.11.9-v2.101.1.APK",
    "DoL-ModLoader-0.5.11.9-v2.101.1.zip",
    "GameOriginalImagePack-0.5.11.9.mod.zip",
    "ModI18N-0.5.11.9-chs-1.0.0a.mod.zip",
]

PLAIN_APK_ASSET_NAME = "DoL-ModLoader-0.5.11.9-v2.101.1.APK"
PLAIN_ZIP_ASSET_NAME = "DoL-ModLoader-0.5.11.9-v2.101.1.zip"
IMAGE_PACK_ASSET_NAME = "GameOriginalImagePack-0.5.11.9.mod.zip"
I18N_ASSET_NAME = "ModI18N-0.5.11.9-chs-1.0.0a.mod.zip"

# Which published asset satisfies each critical key.
CRITICAL_ASSET_NAME_BY_KEY = {
    "apk": PLAIN_APK_ASSET_NAME,
    "zip": PLAIN_ZIP_ASSET_NAME,
    "image_pack": IMAGE_PACK_ASSET_NAME,
    "i18n": I18N_ASSET_NAME,
}


def _release_payload(asset_names, tag="v0.5.11.9-chs-1.0.0a"):
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://example.invalid/{name}",
            }
            for name in asset_names
        ],
    }


def _downloader_with_release(tmp_path, monkeypatch, release_payload):
    """Build a Downloader whose release lookup and downloads are stubbed."""
    monkeypatch.setattr(
        Downloader,
        "_get_github_release",
        lambda self, repo, tag: release_payload,
    )

    def fake_download_file(url, dest_path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"stub-asset")
        return dest_path

    monkeypatch.setattr("lyra.downloader.download_file", fake_download_file)
    return Downloader(BuildPaths(workspace=tmp_path))


@pytest.mark.config
def test_selects_all_critical_assets_from_real_0511_release(tmp_path, monkeypatch):
    """The published 0.5.11.9 asset list yields every critical build input."""
    downloader = _downloader_with_release(
        tmp_path, monkeypatch, _release_payload(CHS_0511_ASSET_NAMES)
    )

    downloaded_files = downloader.download_from_chs_repo()

    assert CRITICAL_CHS_ASSET_KEYS <= set(downloaded_files)
    for key, expected_asset_name in CRITICAL_ASSET_NAME_BY_KEY.items():
        assert downloaded_files[key].name == expected_asset_name


@pytest.mark.config
def test_polyfill_apk_listed_first_is_not_selected_as_the_plain_apk(
    tmp_path, monkeypatch
):
    """Selection must skip the polyfill APK even though it is listed first.

    Both Android assets end in .APK and contain "ModLoader", and upstream lists
    the polyfill one first. Selection keeps the first match per key, so a
    matcher without the polyfill guard would silently ship the polyfill package
    while still reporting success.
    """
    downloader = _downloader_with_release(
        tmp_path, monkeypatch, _release_payload(CHS_0511_ASSET_NAMES)
    )

    downloaded_files = downloader.download_from_chs_repo()

    assert downloaded_files["apk"].name == PLAIN_APK_ASSET_NAME
    assert "polyfill" not in downloaded_files["apk"].name.lower()


@pytest.mark.config
def test_plain_zip_selection_excludes_the_polyfill_variant(tmp_path, monkeypatch):
    """The polyfill ModLoader zip must never be mistaken for the normal one."""
    downloader = _downloader_with_release(
        tmp_path, monkeypatch, _release_payload(CHS_0511_ASSET_NAMES)
    )

    downloaded_files = downloader.download_from_chs_repo()

    assert downloaded_files["zip"].name == PLAIN_ZIP_ASSET_NAME
    assert "polyfill" not in downloaded_files["zip"].name.lower()


@pytest.mark.config
@pytest.mark.parametrize(
    "apk_asset_name",
    [
        "DoL-ModLoader-0.5.11.9-v2.101.1.APK",
        "DoL-ModLoader-0.5.11.9-v2.101.1.apk",
        "DoL-ModLoader-0.5.11.9-v2.101.1.Apk",
    ],
)
def test_apk_extension_matching_is_case_insensitive(
    tmp_path, monkeypatch, apk_asset_name
):
    """Upstream capitalizes .APK today; a rename must not silently drop it."""
    asset_names = [
        name
        for name in CHS_0511_ASSET_NAMES
        if name != PLAIN_APK_ASSET_NAME
    ]
    asset_names.append(apk_asset_name)
    downloader = _downloader_with_release(
        tmp_path, monkeypatch, _release_payload(asset_names)
    )

    downloaded_files = downloader.download_from_chs_repo()

    assert downloaded_files["apk"].name == apk_asset_name


@pytest.mark.config
@pytest.mark.parametrize("missing_key", sorted(CRITICAL_ASSET_NAME_BY_KEY))
def test_missing_critical_asset_fails_fast_with_actual_asset_list(
    tmp_path, monkeypatch, missing_key
):
    """A missing critical asset aborts in prepare, naming the real cause.

    Without this the run continued and only failed much later in build with a
    secondary symptom such as a nonexistent APK directory.
    """
    withheld_asset_name = CRITICAL_ASSET_NAME_BY_KEY[missing_key]
    asset_names = [
        name for name in CHS_0511_ASSET_NAMES if name != withheld_asset_name
    ]
    downloader = _downloader_with_release(
        tmp_path, monkeypatch, _release_payload(asset_names)
    )

    with pytest.raises(RuntimeError) as failure:
        downloader.download_from_chs_repo()

    message = str(failure.value)
    assert missing_key in message
    assert "v0.5.11.9-chs-1.0.0a" in message
    for surviving_asset_name in asset_names:
        assert surviving_asset_name in message


@pytest.mark.config
def test_polyfill_zip_is_not_treated_as_a_critical_asset():
    """Polyfill packaging is opt-in, so its absence must not abort a build."""
    assert "polyfill_zip" not in CRITICAL_CHS_ASSET_KEYS
