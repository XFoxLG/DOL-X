from types import SimpleNamespace

from lyra.config_loader import get_config_loader
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
