"""Maplebirch AU ``{ variant: true }`` layer-source resolution shim tests.

The pinned framework export is a one-parameter minified factory. The JavaScript
probes below execute the real expression, both before and after the patch, under
node so the shim is proven by behaviour rather than by string shape.
"""

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from lyra.build import (
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MEMBER,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_NEW,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD,
    MAPLEBIRCH_PET_REMOUNT_OLD,
    BuildTask,
    ZipBuilder,
    patch_maplebirch_au_variant_dir_priority,
)
from lyra.compatibility import (
    AU_FACE_VARIANT_DIR_PRIORITY_KEY,
    COMPATIBILITY_SURFACES,
    compatibility_surface_by_key,
)
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths


# Byte-for-byte tail of the official 4.1.14 dist/inject_early.js resolver. The
# needle only covers the factory prologue, so the tail is reproduced here and is
# additionally checked against the real payload when that local asset exists.
MAPLEBIRCH_AU_VARIANT_RESOLVER_TAIL = (
    "/^(freckles|ears|blusher|mouth-|lipstick-|blush-?|tears?-?)/.test(e)?"
    "[`img/face/${r}/${e}.png`,`img/face/${r}/${a}/${e}.png`,"
    "`img/face/default/${e}.png`,`img/face/default/${a}/${e}.png`]:"
    "[`img/face/${r}/${a}/${e}.png`,`img/face/${r}/${e}.png`,"
    "`img/face/default/${a}/${e}.png`,`img/face/default/${e}.png`]))}}"
)

MAPLEBIRCH_AU_VARIANT_RESOLVER_OLD = (
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD + MAPLEBIRCH_AU_VARIANT_RESOLVER_TAIL
)
MAPLEBIRCH_AU_VARIANT_RESOLVER_NEW = (
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_NEW + MAPLEBIRCH_AU_VARIANT_RESOLVER_TAIL
)

# The AU facial expansion registers its face styles with real image-directory
# names, so the custom-style probe uses one of them.
AU_CUSTOM_FACESTYLE = "大眼鼠鼠"

AU_FEMALE_MOD_CODE = 15705344
BASE_MOD_CODE = 15704320

REAL_MAPLEBIRCH_414 = (
    Path(__file__).resolve().parents[1]
    / ".local"
    / "maplebirch-414-investigation"
    / "maplebirch-0.5.10.12-v4.1.14.mod.zip"
)


def _resolver_payload(
    resolver: str,
    face_style: str,
    name_expression: str,
    *,
    flagged: bool,
    face_variant: str = "catty",
    extra_state: str = "",
) -> list[str]:
    """Return the ordered candidate list the real resolver produces."""
    options = "{variant:true}" if flagged else "undefined"
    state = f"{{facestyle:{face_style}, facevariant:'{face_variant}'{extra_state}}}"
    program = (
        "function aO(candidates){return candidates;}\n"
        f"{resolver}\n"
        f"const out=aD({name_expression}, {options})({state});\n"
        "console.log(JSON.stringify(out));\n"
    )
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to execute the framework resolver")
    completed = subprocess.run(
        [node, "-e", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"node failed: {completed.stderr}\n{program}")
    return json.loads(completed.stdout)


def _candidates(
    resolver: str,
    face_style: str,
    name_expression: str,
    *,
    flagged: bool,
    **kwargs,
) -> list[str]:
    return _resolver_payload(
        resolver,
        face_style,
        name_expression,
        flagged=flagged,
        **kwargs,
    )


def _write_maplebirch_payload(path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
        )
        payload_zip.writestr(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MEMBER, script)
        payload_zip.writestr("README.md", "unchanged")


def _read_maplebirch_script(path) -> str:
    with zipfile.ZipFile(path, "r") as payload_zip:
        return payload_zip.read(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MEMBER).decode(
            "utf-8"
        )


def _maplebirch_config():
    return next(
        mod
        for mod in load_build_config().modloader_mods
        if mod.cache_name == "maplebirch"
    )


# The same member is owned by three chained payload patches, so one synthetic
# payload has to carry every needle. The passage-rewrite needle is parked inside a
# comment so the whole payload stays valid JavaScript and can be syntax-checked.
def _au_payload_script(*, shim_needle: bool = True) -> str:
    resolver = (
        MAPLEBIRCH_AU_VARIANT_RESOLVER_OLD
        if shim_needle
        else "const faceStyleSrcFnShimNeedleIsGone = true;"
    )
    return (
        resolver
        + "\nclass Character{"
        + MAPLEBIRCH_PET_REMOUNT_OLD
        + "}\n/*"
        + MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
        + "*/"
    )


AU_SAMPLE_SCRIPT = _au_payload_script()


@pytest.mark.config
def test_unpatched_resolver_prefers_the_flat_path():
    """Regression evidence: the dropped flag is what selects the flat path."""
    candidates = _candidates(
        MAPLEBIRCH_AU_VARIANT_RESOLVER_OLD,
        "'default'",
        "'freckles'",
        flagged=True,
    )

    assert candidates[0] == "img/face/default/freckles.png"
    assert "img/face/default/catty/freckles.png" in candidates


@pytest.mark.config
def test_patched_resolver_honours_the_variant_flag():
    candidates = _candidates(
        MAPLEBIRCH_AU_VARIANT_RESOLVER_NEW,
        "'default'",
        "'freckles'",
        flagged=True,
    )

    assert candidates[0] == "img/face/default/catty/freckles.png"


@pytest.mark.config
def test_patched_resolver_covers_every_flagged_au_layer():
    resolver = MAPLEBIRCH_AU_VARIANT_RESOLVER_NEW

    assert (
        _candidates(resolver, "'default'", "'blusher'", flagged=True)[0]
        == "img/face/default/catty/blusher.png"
    )
    assert (
        _candidates(
            resolver,
            "'default'",
            "((o)=>`tear${o.tears}`)",
            flagged=True,
            extra_state=", tears:3",
        )[0]
        == "img/face/default/catty/tear3.png"
    )
    assert (
        _candidates(resolver, "'default'", "'ears'", flagged=True)[0]
        == "img/face/default/catty/ears.png"
    )
    assert (
        _candidates(
            resolver,
            "'default'",
            "((o)=>`blush${o.blush}`)",
            flagged=True,
            extra_state=", blush:1",
        )[0]
        == "img/face/default/catty/blush1.png"
    )


@pytest.mark.config
@pytest.mark.parametrize(
    ("face_style", "name_expression", "flagged"),
    (
        # A single-argument call must keep the upstream expression byte for byte.
        ("'default'", "'freckles'", False),
        # A non-default facestyle already took the variant-first branch upstream.
        (f"'{AU_CUSTOM_FACESTYLE}'", "'freckles'", True),
        # Layer names outside the flat-first regular expression are unaffected.
        ("'default'", "'eyes'", True),
        ("'default'", "'iris'", True),
        ("'default'", "'brow-mid'", True),
        ("'default'", "'lashes'", True),
    ),
)
def test_patched_resolver_preserves_every_other_call_shape(
    face_style,
    name_expression,
    flagged,
):
    arguments = (face_style, name_expression)
    before = _candidates(
        MAPLEBIRCH_AU_VARIANT_RESOLVER_OLD,
        *arguments,
        flagged=flagged,
    )
    after = _candidates(
        MAPLEBIRCH_AU_VARIANT_RESOLVER_NEW,
        *arguments,
        flagged=flagged,
    )

    assert after == before


@pytest.mark.config
def test_resolver_tail_matches_the_official_payload():
    if not REAL_MAPLEBIRCH_414.exists():
        pytest.skip("official 4.1.14 payload is not present locally")

    script = _read_maplebirch_script(REAL_MAPLEBIRCH_414)

    assert script.count(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD) == 1
    assert script.count(MAPLEBIRCH_AU_VARIANT_RESOLVER_OLD) == 1
    assert MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_NEW not in script


@pytest.mark.config
def test_shim_patches_the_official_payload_and_stays_valid_javascript(tmp_path):
    if not REAL_MAPLEBIRCH_414.exists():
        pytest.skip("official 4.1.14 payload is not present locally")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to syntax-check the patched payload")

    target = tmp_path / "maplebirch.patched.mod.zip"
    result = patch_maplebirch_au_variant_dir_priority(REAL_MAPLEBIRCH_414, target)

    assert result["status"] == "patched"
    patched_script = _read_maplebirch_script(target)
    assert patched_script.count(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_NEW) == 1
    assert patched_script.count(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD) == 0
    assert patched_script.count(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER) == 1

    script_path = tmp_path / "inject_early.js"
    script_path.write_text(patched_script, encoding="utf-8")
    checked = subprocess.run(
        [node, "--check", str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert checked.returncode == 0, checked.stderr

    # Every other member must survive byte for byte.
    with zipfile.ZipFile(REAL_MAPLEBIRCH_414, "r") as source_zip:
        source_members = {
            item.filename: item for item in source_zip.infolist()
        }
        source_payloads = {
            name: source_zip.read(name) for name in source_members
        }
    with zipfile.ZipFile(target, "r") as target_zip:
        assert set(target_zip.namelist()) == set(source_members)
        for name in source_members:
            if name == MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MEMBER:
                continue
            assert target_zip.read(name) == source_payloads[name]


@pytest.mark.config
def test_shim_patch_reports_missing_needle_when_the_framework_drifts(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(
        source,
        "class Character{faceStyleSrcFn=rewrittenByUpstream;}",
    )

    result = patch_maplebirch_au_variant_dir_priority(source, target)

    assert result["status"] == "patch_needle_not_found"
    assert result["applied"] is False
    assert result["needle_count"] == 0
    assert not target.exists()


@pytest.mark.config
def test_shim_patch_is_idempotent(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    first_target = tmp_path / "maplebirch.first.mod.zip"
    second_target = tmp_path / "maplebirch.second.mod.zip"
    _write_maplebirch_payload(source, AU_SAMPLE_SCRIPT)

    first_result = patch_maplebirch_au_variant_dir_priority(source, first_target)
    second_result = patch_maplebirch_au_variant_dir_priority(
        first_target,
        second_target,
    )

    assert first_result["status"] == "patched"
    assert second_result["status"] == "already_patched"
    assert second_result["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_shim_patch_rejects_a_partially_patched_payload(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(
        source,
        AU_SAMPLE_SCRIPT
        + MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_NEW.replace(
            MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER,
            f"{MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER}Second",
        ),
    )

    result = patch_maplebirch_au_variant_dir_priority(source, target)

    assert result["status"] == "partial_patch"
    assert result["applied"] is False


@pytest.mark.config
def test_shim_patch_preserves_unrelated_payload_members(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.patched.mod.zip"
    _write_maplebirch_payload(source, AU_SAMPLE_SCRIPT)

    patch_maplebirch_au_variant_dir_priority(source, target)

    with zipfile.ZipFile(target, "r") as payload_zip:
        assert payload_zip.read("README.md") == b"unchanged"
        assert payload_zip.read("boot.json") == (
            b'{"name":"maplebirch","version":"4.1.14"}'
        )


@pytest.mark.config
def test_shim_patch_rejects_a_non_zip_input(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    source.write_bytes(b"not a zip")
    target = tmp_path / "maplebirch.patched.mod.zip"

    result = patch_maplebirch_au_variant_dir_priority(source, target)

    assert result["status"] == "not_zip"
    assert result["applied"] is False


@pytest.mark.config
def test_au_injection_applies_the_variant_dir_priority_shim(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=AU_FEMALE_MOD_CODE, paths=paths)
    )
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source, AU_SAMPLE_SCRIPT)

    injected_path = builder._modloader_mod_path_for_injection(
        _maplebirch_config(),
        source,
    )

    assert injected_path != source
    assert injected_path.exists()
    injected_script = _read_maplebirch_script(injected_path)
    assert MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER in injected_script
    assert injected_script.count(MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD) == 0
    assert MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER not in _read_maplebirch_script(
        source
    )


@pytest.mark.config
def test_base_injection_skips_the_variant_dir_priority_shim(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=BASE_MOD_CODE, paths=paths)
    )
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source, AU_SAMPLE_SCRIPT)

    builder._modloader_mod_path_for_injection(_maplebirch_config(), source)

    assert MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER not in _read_maplebirch_script(
        source
    )


@pytest.mark.config
def test_au_injection_fails_closed_when_the_shim_needle_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=AU_FEMALE_MOD_CODE, paths=paths)
    )
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source, _au_payload_script(shim_needle=False))

    with pytest.raises(
        RuntimeError,
        match=(
            "AU variant directory priority shim failed: patch_needle_not_found"
        ),
    ):
        builder._modloader_mod_path_for_injection(_maplebirch_config(), source)


@pytest.mark.config
def test_au_injection_fails_closed_when_the_source_metadata_drifts(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=AU_FEMALE_MOD_CODE, paths=paths)
    )
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_payload(source, AU_SAMPLE_SCRIPT)

    drifted_config = SimpleNamespace(
        cache_name="maplebirch",
        github_repo="example/wrong",
        release_tag="maplebirch-release-v4.1.14",
        asset_pattern="maplebirch-0.5.10.12-v4.1.14.mod.zip",
    )

    with pytest.raises(RuntimeError, match="source mismatch"):
        builder._modloader_mod_path_for_injection(drifted_config, source)


@pytest.mark.config
def test_variant_dir_priority_surface_is_registered_as_fail_closed():
    surface = compatibility_surface_by_key(AU_FACE_VARIANT_DIR_PRIORITY_KEY)

    assert surface.scope == "default-path"
    assert surface.kind == "payload-patch"
    assert surface.fail_policy == "fail-closed"
    assert surface.cache_name == "maplebirch"
    assert surface.release_tag == "maplebirch-release-v4.1.14"
    assert surface.asset_pattern == "maplebirch-0.5.10.12-v4.1.14.mod.zip"
    assert surface.marker == MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER
    assert "tests/test_au_face_variant_dir_priority.py" in surface.tests
    assert surface.removal_condition

    keys = [item.key for item in COMPATIBILITY_SURFACES]
    assert keys.count(AU_FACE_VARIANT_DIR_PRIORITY_KEY) == 1


@pytest.mark.config
def test_variant_dir_priority_surface_records_the_ab_verdict():
    notes = compatibility_surface_by_key(AU_FACE_VARIANT_DIR_PRIORITY_KEY).notes

    # The 2026-10-13 A/B landed as no_visual_change: the shim stays a
    # contract-level correction and must never be described as a visual fix.
    assert "hypothesis_under_test" not in notes
    assert "accepted_upstream" in notes
    assert "visual_incomplete" in notes
    assert "no_visual_change" in notes
