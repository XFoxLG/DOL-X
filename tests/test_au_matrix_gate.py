"""Focused tests for AU matrix gate diagnostic helpers."""

import pytest

from lyra.config_loader import get_config_loader
from tools.au_matrix_gate import (
    AU_FRAMEWORK_SUPPORT_PURPOSE,
    AU_FACE_CACHE_NAME,
    AU_VARIANTS,
    CHEAT_EXTENDED_CACHE_NAME,
    MAPLEBIRCH_CACHE_NAME,
    MAPLEBIRCH_PROVIDER,
    _restore_modloader_mods,
    _maplebirch_framework_evidence_metadata,
    _set_maplebirch_canary_injection_enabled,
    parse_args,
)


@pytest.mark.config
def test_maplebirch_canary_helper_keeps_face_and_excludes_cheat_extended():
    """The canary retargets only maplebirch to AU builds and restores globals."""
    build_config = get_config_loader().build
    original_mods = build_config.modloader_mods
    original_by_cache = {mod.cache_name: mod for mod in original_mods}
    expected_au_features = [slug for slug, _code, _terms in AU_VARIANTS]

    assert AU_FACE_CACHE_NAME in original_by_cache
    assert MAPLEBIRCH_CACHE_NAME in original_by_cache
    assert CHEAT_EXTENDED_CACHE_NAME in original_by_cache

    saved_mods = _set_maplebirch_canary_injection_enabled()
    try:
        canary_mods = build_config.modloader_mods
        canary_by_cache = {mod.cache_name: mod for mod in canary_mods}

        assert saved_mods is original_mods
        assert AU_FACE_CACHE_NAME in canary_by_cache
        assert MAPLEBIRCH_CACHE_NAME in canary_by_cache
        assert CHEAT_EXTENDED_CACHE_NAME not in canary_by_cache

        maplebirch_mod = canary_by_cache[MAPLEBIRCH_CACHE_NAME]
        assert maplebirch_mod is not original_by_cache[MAPLEBIRCH_CACHE_NAME]
        assert maplebirch_mod.enabled is True
        assert maplebirch_mod.feature_id == ""
        assert maplebirch_mod.feature_ids == expected_au_features

        original_maplebirch = original_by_cache[MAPLEBIRCH_CACHE_NAME]
        assert original_maplebirch.feature_id == "cheat_extended_maplebirch"
        assert original_maplebirch.feature_ids == []
    finally:
        _restore_modloader_mods(saved_mods)

    assert build_config.modloader_mods is original_mods


@pytest.mark.config
def test_maplebirch_canary_reports_au_framework_support_metadata():
    assert _maplebirch_framework_evidence_metadata() == {
        "provider": MAPLEBIRCH_PROVIDER,
        "purpose": AU_FRAMEWORK_SUPPORT_PURPOSE,
        "shared_framework_evidence": True,
        "default_matrix_mutated": False,
        "cheat_extended_included": False,
    }


@pytest.mark.config
@pytest.mark.parametrize(
    "command",
    [
        "build-maplebirch-canary",
        "summarize-maplebirch-browser",
        "compare-maplebirch-canary",
    ],
)
def test_maplebirch_canary_commands_are_registered(command):
    assert parse_args([command]).command == command
