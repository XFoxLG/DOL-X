from types import SimpleNamespace
import hashlib
import json

from lyra.config_loader import get_config_loader
from lyra.config_loader import ModloaderModConfig
from lyra.paths import BuildPaths
from lyra.warmup import ResourceWarmer
from main import cmd_warmup


PUBLIC_BASE_CODE = "15704320"


def get_enabled_feature_ids(code: int) -> set[str]:
    return {
        feature.id
        for feature in get_config_loader().features
        if code & feature.bit
    }


def test_default_warmup_still_uses_configured_build_matrix(tmp_path):
    resource_warmer = ResourceWarmer(BuildPaths(workspace=tmp_path))

    assert "ucb" in resource_warmer.required_feature_ids
    assert "besc" not in resource_warmer.required_feature_ids


def test_explicit_warmup_codes_select_requested_public_resources(tmp_path):
    resource_warmer = ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=[PUBLIC_BASE_CODE],
    )

    expected_feature_ids = get_enabled_feature_ids(int(PUBLIC_BASE_CODE))
    assert resource_warmer.required_feature_ids == expected_feature_ids
    assert "ucb" in expected_feature_ids
    assert "besc" not in expected_feature_ids


def test_explicit_warmup_codes_do_not_mutate_default_matrix(tmp_path):
    config_loader = get_config_loader()
    default_codes_before = list(config_loader.combinations.build_codes)

    ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=[PUBLIC_BASE_CODE],
    )

    assert config_loader.combinations.build_codes == default_codes_before


def test_invalid_warmup_code_stops_before_resource_warmer(monkeypatch, tmp_path):
    class UnexpectedResourceWarmer:
        def __init__(self, *args, **kwargs):
            raise AssertionError("invalid codes must stop before resource warmup")

    monkeypatch.setattr("lyra.warmup.ResourceWarmer", UnexpectedResourceWarmer)
    command_arguments = SimpleNamespace(
        verbose=False,
        workspace=str(tmp_path),
        codes=["0"],
    )

    assert cmd_warmup(command_arguments) == 1


def test_each_imagepack_component_selects_only_its_own_source_urls(tmp_path):
    resource_warmer = ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=[PUBLIC_BASE_CODE],
    )

    for config_name, pack_names in resource_warmer.DOLP_PACKS.items():
        for pack_name in pack_names:
            source_urls = resource_warmer._get_dolp_pack_urls(pack_name, config_name)

            assert source_urls
            assert all(
                resource_warmer._url_targets_dolp_pack(source_url, pack_name)
                for source_url in source_urls
            )


def test_ucb_keeps_all_mysterious_mirror_urls(tmp_path):
    resource_warmer = ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=[PUBLIC_BASE_CODE],
    )

    source_urls = resource_warmer._get_dolp_pack_urls("mysterious", "ucb")

    assert len(source_urls) == 2
    assert all("mysterious" in source_url for source_url in source_urls)
    assert any("github.com" in source_url for source_url in source_urls)
    assert any("gitgud.io" in source_url for source_url in source_urls)


def _write_au_lock_file(tmp_path, cache_name: str, payload: bytes) -> None:
    config_directory = tmp_path / "config"
    config_directory.mkdir(parents=True, exist_ok=True)
    (config_directory / "mods.lock.json").write_text(
        json.dumps(
            {
                "mods": {
                    cache_name: {
                        "last_tested_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_au_modloader_cache_must_match_lock_digest(tmp_path):
    resource_warmer = ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=["15705344"],
    )
    mod_config = ModloaderModConfig(
        key="au_f",
        feature_id="au-f",
        github_repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_pattern="AUfemale.model_v0.9.3.zip",
        release_tag="mod",
    )
    cached_payload = b"tampered AU model payload"
    cache_path = resource_warmer.paths.get_mod_cache_path("au_f")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(cached_payload)
    _write_au_lock_file(tmp_path, "au_f", b"expected AU model payload")

    try:
        resource_warmer._download_modloader_mod(mod_config, get_config_loader())
    except RuntimeError as exc:
        assert "AU payload digest mismatch" in str(exc)
    else:
        raise AssertionError("tampered cached AU payload must fail closed")


def test_downloaded_au_modloader_payload_must_match_lock_digest(
    tmp_path,
    monkeypatch,
):
    resource_warmer = ResourceWarmer(
        BuildPaths(workspace=tmp_path),
        codes=["15705344"],
    )
    mod_config = ModloaderModConfig(
        key="au_face",
        feature_ids=["au-f", "au-m", "au-a"],
        github_repo="AOKIUTAGE/UTAGEsDOL3.0",
        asset_pattern="AUsDoL.facial.expansion.mod.zip",
        release_tag="facemod",
        download_url="https://example.invalid/au-face.zip",
    )
    _write_au_lock_file(tmp_path, "au_face", b"expected AU Face payload")

    def write_tampered_payload(_url, destination, quiet):
        del quiet
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"tampered downloaded AU Face payload")

    monkeypatch.setattr("lyra.warmup.download_file", write_tampered_payload)

    try:
        resource_warmer._download_modloader_mod(mod_config, get_config_loader())
    except RuntimeError as exc:
        assert "AU payload digest mismatch" in str(exc)
    else:
        raise AssertionError("tampered downloaded AU payload must fail closed")
