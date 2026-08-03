"""Compatibility shim registry tests."""

import pytest

from lyra.compatibility import (
    APK_CDP_REMOTE_END_RECONNECT_KEY,
    AU_FACE_ALIAS_KEY,
    COMPATIBILITY_SURFACES,
    DOLI_FLOAT_ICON_PATCH_KEY,
    GENERIC_REFACTOR_PLAN,
    MORE_LOVE_DRAG_PATCH_KEY,
    TEST_POLICY_REQUIREMENTS,
    compatibility_surface_by_key,
    compatibility_surfaces_by_scope,
    compatibility_source_errors,
    is_patch_success_status,
)
from lyra.config_loader import get_config_loader, load_build_config


@pytest.mark.config
def test_compatibility_surfaces_are_registered_and_classified():
    surfaces_by_key = {surface.key: surface for surface in COMPATIBILITY_SURFACES}

    assert set(surfaces_by_key) == {
        MORE_LOVE_DRAG_PATCH_KEY,
        DOLI_FLOAT_ICON_PATCH_KEY,
        AU_FACE_ALIAS_KEY,
        APK_CDP_REMOTE_END_RECONNECT_KEY,
    }
    assert surfaces_by_key[MORE_LOVE_DRAG_PATCH_KEY].scope == "default-path"
    assert surfaces_by_key[MORE_LOVE_DRAG_PATCH_KEY].kind == "payload-patch"
    assert surfaces_by_key[MORE_LOVE_DRAG_PATCH_KEY].fail_policy == "fail-closed"
    assert surfaces_by_key[DOLI_FLOAT_ICON_PATCH_KEY].scope == "default-path"
    assert surfaces_by_key[DOLI_FLOAT_ICON_PATCH_KEY].kind == "payload-patch"
    assert surfaces_by_key[DOLI_FLOAT_ICON_PATCH_KEY].fail_policy == "fail-closed"
    assert surfaces_by_key[AU_FACE_ALIAS_KEY].scope == "default-path"
    assert surfaces_by_key[APK_CDP_REMOTE_END_RECONNECT_KEY].scope == "generic-harness"


@pytest.mark.config
def test_compatibility_surfaces_declare_tests_and_removal_conditions():
    for surface in COMPATIBILITY_SURFACES:
        assert surface.scope
        assert surface.kind
        assert surface.fail_policy
        assert surface.tests, f"{surface.key} must list covering tests"
        assert surface.removal_condition, f"{surface.key} must state how local compatibility can be removed"


@pytest.mark.config
def test_default_path_payload_patches_are_fail_closed_and_version_scoped():
    default_payload_patches = [
        surface
        for surface in compatibility_surfaces_by_scope("default-path")
        if surface.kind == "payload-patch"
    ]

    assert [surface.key for surface in default_payload_patches] == [
        MORE_LOVE_DRAG_PATCH_KEY,
        DOLI_FLOAT_ICON_PATCH_KEY,
    ]
    more_love = default_payload_patches[0]
    assert more_love.fail_policy == "fail-closed"
    assert more_love.cache_name == "more_love"
    assert more_love.github_repo == "Nephthelana/DoL-More-Love-Interests-Mod"
    assert more_love.release_tag == "More-Love-Interests-Mod-v0.1.7.0"
    assert more_love.asset_pattern == "More.Love.Interests.Mod.mod.zip"
    assert more_love.member == "game/More_Love_Interest_Mod_Drag.js"
    assert more_love.marker == "function preventDefaultMLIM(ev)"

    doli = default_payload_patches[1]
    assert doli.fail_policy == "fail-closed"
    assert doli.cache_name == "doli"
    assert doli.github_repo == "ArsNativa/Degrees-of-Lewdity-Intelligence"
    assert doli.release_tag == "v0.2.3"
    assert doli.asset_pattern == "DOLI.mod.zip"
    assert doli.member == "dist/DOLI.js"
    assert doli.marker == "img/ui/sym_awareness.png"


@pytest.mark.config
def test_doli_registry_matches_current_build_config():
    surface = compatibility_surface_by_key(DOLI_FLOAT_ICON_PATCH_KEY)
    doli_config = next(mod for mod in load_build_config().modloader_mods if mod.cache_name == "doli")

    assert compatibility_source_errors(surface, doli_config) == []


@pytest.mark.config
def test_more_love_registry_matches_current_build_config():
    surface = compatibility_surface_by_key(MORE_LOVE_DRAG_PATCH_KEY)
    more_love_config = next(mod for mod in load_build_config().modloader_mods if mod.cache_name == "more_love")

    assert compatibility_source_errors(surface, more_love_config) == []


@pytest.mark.config
def test_fail_closed_patch_statuses_are_narrow():
    assert is_patch_success_status("patched") is True
    assert is_patch_success_status("already_patched") is True
    assert is_patch_success_status("patch_needle_not_found") is False
    assert is_patch_success_status("missing_patch_member") is False
    assert is_patch_success_status(None) is False


@pytest.mark.config
def test_generic_refactor_plan_preserves_stable_outputs_first():
    assert {item.key for item in GENERIC_REFACTOR_PLAN} == {
        "config_driven_feature_suffixes",
        "config_driven_image_warmup",
    }
    for item in GENERIC_REFACTOR_PLAN:
        assert item.first_safe_step
        assert "unchanged" in item.stable_output_policy or "No stable matrix mutation" in item.stable_output_policy
        assert item.tests


@pytest.mark.config
def test_test_policy_requires_scope_and_boundaries():
    requirements = {item.key: item for item in TEST_POLICY_REQUIREMENTS}

    assert set(requirements) == {
        "compatibility_surfaces_are_registered",
        "default_payload_patches_fail_closed",
        "canary_and_diagnostic_do_not_mutate_stable_matrix",
        "generic_refactors_preserve_stable_outputs",
    }
    assert "default-path" in requirements["default_payload_patches_fail_closed"].applies_to
    assert "canary-only" in requirements["canary_and_diagnostic_do_not_mutate_stable_matrix"].applies_to
    assert "diagnostic-only" in requirements["canary_and_diagnostic_do_not_mutate_stable_matrix"].applies_to
