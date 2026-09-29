"""Tests for boot.json parsing leniency in artifact auditing.

ModLoader parses every mod's boot.json with json5.parse(), which tolerates
trailing commas and comments. Auditing with strict json.loads() is therefore
stricter than the runtime and rejects payloads the game loads fine:
cheat_extended 1.20(dev260903) ships a trailing comma in its scriptFileList and
failed the AU artifact audit while loading correctly in game. These tests pin
the audit parser to runtime semantics.
"""

import builtins
import json

import pytest

from tools.artifact_inspection import parse_boot_json


# Shape of the real cheat_extended boot.json defect: a trailing comma plus a
# blank line before the array closer.
CHEAT_EXTENDED_TRAILING_COMMA_BOOT_JSON = """{
  "name": "cheat extended",
  "version": "1.20(dev260903)",
  "scriptFileList": [
    "scripts/CE_forestMapGui.js",
    "scripts/CE_farmRoadMapGui.js",
    
  ],
  "tweeFileList": [
    "game/CE_cheatExtendedMenu.twee"
  ]
}
"""


@pytest.mark.config
def test_strict_json_rejects_the_shipped_cheat_extended_boot_json():
    """Guard the premise: this payload really is invalid strict JSON."""
    with pytest.raises(json.JSONDecodeError):
        json.loads(CHEAT_EXTENDED_TRAILING_COMMA_BOOT_JSON)


@pytest.mark.config
def test_trailing_comma_boot_json_parses_like_modloader_does():
    """A trailing comma must not fail the audit, because it does not fail the game."""
    parsed = parse_boot_json(CHEAT_EXTENDED_TRAILING_COMMA_BOOT_JSON)

    assert parsed["name"] == "cheat extended"
    assert parsed["version"] == "1.20(dev260903)"
    assert parsed["scriptFileList"] == [
        "scripts/CE_forestMapGui.js",
        "scripts/CE_farmRoadMapGui.js",
    ]


@pytest.mark.config
def test_strict_boot_json_still_parses():
    parsed = parse_boot_json('{"name":"maplebirch","version":"4.1.14"}')

    assert parsed == {"name": "maplebirch", "version": "4.1.14"}


@pytest.mark.config
def test_byte_order_mark_is_tolerated():
    parsed = parse_boot_json('\ufeff{"name":"maplebirch","version":"4.1.14"}')

    assert parsed["name"] == "maplebirch"


@pytest.mark.config
def test_trailing_comma_still_parses_without_the_json5_package(monkeypatch):
    """The fallback path must work on machines that lack json5.

    json5 is not declared in requirements.txt, so CI and fresh clones may not
    have it. The audit must not silently regress to strict parsing there.
    """
    real_import = builtins.__import__

    def refuse_json5(name, *args, **kwargs):
        if name == "json5":
            raise ImportError("simulated missing json5")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_json5)

    parsed = parse_boot_json(CHEAT_EXTENDED_TRAILING_COMMA_BOOT_JSON)

    assert parsed["name"] == "cheat extended"
    assert parsed["scriptFileList"] == [
        "scripts/CE_forestMapGui.js",
        "scripts/CE_farmRoadMapGui.js",
    ]


@pytest.mark.config
def test_genuinely_malformed_boot_json_still_raises():
    """Leniency must not swallow real corruption."""
    with pytest.raises(Exception):
        parse_boot_json('{"name": "broken", "version":}')
