"""AU facial expansion asset compatibility tests."""

import base64
import io
import json
from types import SimpleNamespace
import zipfile

import pytest

from lyra.build import (
    AU_FACE_VARIANT_FALLBACK_EXPRESSION,
    AU_FACE_VARIANT_HTML_MIGRATION_OLD,
    AU_FACE_VARIANT_HTML_SWITCH_NEEDLES,
    AU_FACE_VARIANT_MIGRATION_EXPRESSION,
    AU_FACE_VARIANT_MIGRATION_NEW,
    AU_FACE_VARIANT_SWITCH_NEEDLES,
    BuildTask,
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW,
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
    MAPLEBIRCH_AU_FACE_VARIANT_MARKER,
    MAPLEBIRCH_BASEHEAD_OLD,
    MAPLEBIRCH_PET_REMOUNT_OLD,
    ZipBuilder,
    patch_maplebirch_au_face_variant_selection,
)
from lyra.config import ModCode
from lyra.config_loader import ModloaderModConfig, load_build_config
from lyra.paths import BuildPaths
from tools.au_artifact_check import (
    AU_FACE_MOD_NAME,
    AU_MODEL_NAME_BY_VARIANT,
    EXPECTED_POST_I18N_EXECUTION,
    EXPECTED_POST_I18N_RULES,
    audit_apk_artifact,
    audit_target,
    audit_zip_artifact,
)


def _zip_builder(tmp_path, mod_code: int) -> ZipBuilder:
    paths = BuildPaths(workspace=tmp_path)
    task = BuildTask(pack_type="zip", mod_code=mod_code, paths=paths)
    return ZipBuilder(task)


@pytest.mark.config
def test_au_face_compatibility_aliases_copy_default_blush_layers(tmp_path):
    """AU builds copy default blush layers to the nested runtime path."""
    builder = _zip_builder(tmp_path, 28930)
    source = builder.img_path / "face" / "default" / "blush-1.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-png")

    copied = builder._apply_au_face_compatibility_aliases()

    target = builder.img_path / "face" / "default" / "default" / "blush-1.png"
    assert target.exists()
    assert target.read_bytes() == b"fake-png"
    assert copied == ["face/default/default/blush-1.png"]


@pytest.mark.config
def test_face_compatibility_aliases_copy_default_mouth_layers_for_base_builds(tmp_path):
    """Base builds copy default mouth layers to the nested runtime path."""
    builder = _zip_builder(tmp_path, 24834)
    source = builder.img_path / "face" / "default" / "mouth-smile.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-mouth-png")

    copied = builder._apply_au_face_compatibility_aliases()

    target = builder.img_path / "face" / "default" / "default" / "mouth-smile.png"
    assert target.exists()
    assert target.read_bytes() == b"fake-mouth-png"
    assert copied == ["face/default/default/mouth-smile.png"]


@pytest.mark.config
def test_au_face_compatibility_aliases_preserve_existing_targets(tmp_path):
    """Existing nested assets are left untouched if upstream starts shipping them."""
    builder = _zip_builder(tmp_path, 25858)
    source = builder.img_path / "face" / "default" / "blush1.png"
    target = builder.img_path / "face" / "default" / "default" / "blush1.png"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(b"source-png")
    target.write_bytes(b"already-present")

    copied = builder._apply_au_face_compatibility_aliases()

    assert copied == []
    assert target.read_bytes() == b"already-present"


@pytest.mark.config
def test_au_face_compatibility_aliases_skip_non_au_build(tmp_path):
    """Stable base builds do not create AU-only blush compatibility aliases."""
    builder = _zip_builder(tmp_path, 24834)
    source = builder.img_path / "face" / "default" / "blush1.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-png")

    copied = builder._apply_au_face_compatibility_aliases()

    target = builder.img_path / "face" / "default" / "default" / "blush1.png"
    assert copied == []
    assert not target.exists()


def _write_face_style_widgets(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        """
&lt;&lt;set $facestyle to _facestyle&gt;&gt;
\t\t\t&lt;&lt;set $facevariant to "default"&gt;&gt;
&lt;&lt;set $facestyle to _faceStyles[_i]&gt;&gt;
\t\t\t\t\t&lt;&lt;set $facevariant to "default"&gt;&gt;
&lt;&lt;set $facestyle to _styleValue&gt;&gt;
\t\t\t\t\t\t\t&lt;&lt;set $facevariant to "default"&gt;&gt;
/* Code that should not be moved into a check like above */
\t&lt;&lt;set $runWardrobeSanityChecker to true&gt;&gt;
""".lstrip().encode("utf-8"),
    )


@pytest.mark.config
def test_au_face_source_validation_preserves_modi18n_input(tmp_path):
    """The build validates but never rewrites ModI18N's source passages."""
    builder = _zip_builder(tmp_path, 15705344)
    _write_face_style_widgets(builder.html_path)
    original_html = builder.html_path.read_bytes()

    result = builder._validate_au_face_variant_source()

    assert result["status"] == "validated"
    assert result["applied"] is False
    assert builder.html_path.read_bytes() == original_html


@pytest.mark.config
def test_maplebirch_au_face_patch_contains_all_post_i18n_rules(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.au-face.mod.zip"
    _write_maplebirch_face_patch_payload(source)

    result = patch_maplebirch_au_face_variant_selection(source, target)

    assert result["status"] == "patched"
    assert result["applied"] is True
    patched_script = _read_maplebirch_face_patch_script(target)
    assert patched_script.count(MAPLEBIRCH_AU_FACE_VARIANT_MARKER) == 1
    assert MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD not in patched_script
    assert MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW in patched_script
    for passage_name, _old_context, _new_context in _face_passage_patch_rules():
        assert passage_name in patched_script


@pytest.mark.config
def test_maplebirch_au_face_patch_repairs_only_invalid_saved_variants(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.au-face.mod.zip"
    _write_maplebirch_face_patch_payload(source)

    patch_maplebirch_au_face_variant_selection(source, target)

    patched_script = _read_maplebirch_face_patch_script(target)
    assert "legalVariants.length" in patched_script
    assert "!legalVariants.includes(V.facevariant)" in patched_script
    assert "V.facevariant = legalVariants[0]" in patched_script


@pytest.mark.config
def test_maplebirch_au_face_patch_is_idempotent(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    first_target = tmp_path / "maplebirch.first.mod.zip"
    second_target = tmp_path / "maplebirch.second.mod.zip"
    _write_maplebirch_face_patch_payload(source)

    first = patch_maplebirch_au_face_variant_selection(source, first_target)
    second = patch_maplebirch_au_face_variant_selection(
        first_target,
        second_target,
    )

    assert first["status"] == "patched"
    assert second["status"] == "already_patched"
    assert second["applied"] is False
    assert not second_target.exists()


@pytest.mark.config
def test_maplebirch_au_face_patch_fails_closed_on_method_drift(tmp_path):
    source = tmp_path / "maplebirch.mod.zip"
    target = tmp_path / "maplebirch.au-face.mod.zip"
    _write_maplebirch_face_patch_payload(
        source,
        script="modifyFaceStyle(e){/* upstream rewrote this method */}",
    )

    result = patch_maplebirch_au_face_variant_selection(source, target)

    assert result["status"] == "patch_needle_not_found"
    assert result["needle_count"] == 0
    assert not target.exists()


@pytest.mark.config
def test_maplebirch_au_face_patch_rejects_marker_only_partial_patch(tmp_path):
    source = tmp_path / "maplebirch.partial.mod.zip"
    target = tmp_path / "maplebirch.target.mod.zip"
    _write_maplebirch_face_patch_payload(
        source,
        script=(
            _maplebirch_face_patch_script()
            + f'const marker="{MAPLEBIRCH_AU_FACE_VARIANT_MARKER}";'
        ),
    )

    result = patch_maplebirch_au_face_variant_selection(source, target)

    assert result["status"] == "partial_patch"
    assert result["complete_patch_count"] == 0
    assert result["obsolete_insertion_count"] == 1
    assert not target.exists()


@pytest.mark.config
def test_maplebirch_au_face_patch_rejects_complete_patch_with_extra_marker(tmp_path):
    source = tmp_path / "maplebirch.extra-marker.mod.zip"
    target = tmp_path / "maplebirch.target.mod.zip"
    _write_maplebirch_face_patch_payload(
        source,
        script=(
            _maplebirch_face_patch_script().replace(
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
                MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW,
                1,
            )
            + f'const marker="{MAPLEBIRCH_AU_FACE_VARIANT_MARKER}";'
        ),
    )

    result = patch_maplebirch_au_face_variant_selection(source, target)

    assert result["status"] == "partial_patch"
    assert result["marker_count"] == 2
    assert result["complete_patch_count"] == 1
    assert result["obsolete_insertion_count"] == 0
    assert not target.exists()


@pytest.mark.config
def test_au_face_source_validation_preserves_unrelated_bytes(tmp_path):
    builder = _zip_builder(tmp_path, 15705344)
    _write_face_style_widgets(builder.html_path)
    original_content = builder.html_path.read_bytes()
    binary_prefix = b"\xff\xfeunrelated-prefix\x00"
    binary_suffix = b"\x00unrelated-suffix\x81"
    builder.html_path.write_bytes(binary_prefix + original_content + binary_suffix)

    builder._validate_au_face_variant_source()

    assert builder.html_path.read_bytes() == (
        binary_prefix + original_content + binary_suffix
    )


@pytest.mark.config
def test_au_face_source_validation_fails_closed_on_migration_drift(tmp_path):
    builder = _zip_builder(tmp_path, 15705344)
    _write_face_style_widgets(builder.html_path)
    content = builder.html_path.read_bytes().replace(
        b"/* Code that should not be moved into a check like above */",
        b"/* Upstream moved this compatibility section. */",
    )
    builder.html_path.write_bytes(content)

    with pytest.raises(RuntimeError, match="source validation failed"):
        builder._validate_au_face_variant_source()


@pytest.mark.config
def test_au_face_source_validation_fails_closed_on_widget_drift(tmp_path):
    builder = _zip_builder(tmp_path, 15705344)
    builder.html_path.parent.mkdir(parents=True, exist_ok=True)
    builder.html_path.write_text(
        '&lt;&lt;set $facestyle to _styleValue&gt;&gt;',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="source validation failed"):
        builder._validate_au_face_variant_source()


@pytest.mark.config
def test_face_style_source_validation_skips_base_build(tmp_path):
    builder = _zip_builder(tmp_path, 15704320)
    _write_face_style_widgets(builder.html_path)
    original_html = builder.html_path.read_text(encoding="utf-8")

    result = builder._validate_au_face_variant_source()

    assert result["status"] == "not_applicable"
    assert result["applied"] is False
    assert builder.html_path.read_text(encoding="utf-8") == original_html


@pytest.mark.config
@pytest.mark.parametrize("mod_code", [15705344, 15706368, 15708416])
def test_face_style_source_validation_covers_all_public_au_codes(tmp_path, mod_code):
    builder = _zip_builder(tmp_path, mod_code)
    _write_face_style_widgets(builder.html_path)

    result = builder._validate_au_face_variant_source()

    assert result["status"] == "validated"
    assert result["applied"] is False


@pytest.mark.config
def test_maplebirch_injection_adds_au_patch_only_for_au_builds(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    source = paths.get_mod_cache_path("maplebirch")
    _write_maplebirch_face_patch_payload(source, include_chained_needles=True)
    maplebirch_config = next(
        mod
        for mod in load_build_config().modloader_mods
        if mod.cache_name == "maplebirch"
    )

    au_builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=15705344, paths=paths)
    )
    injected_au_path = au_builder._modloader_mod_path_for_injection(
        maplebirch_config,
        source,
    )
    assert MAPLEBIRCH_AU_FACE_VARIANT_MARKER in (
        _read_maplebirch_face_patch_script(injected_au_path)
    )

    base_builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=15704320, paths=paths)
    )
    injected_base_path = base_builder._modloader_mod_path_for_injection(
        maplebirch_config,
        source,
    )
    assert MAPLEBIRCH_AU_FACE_VARIANT_MARKER not in (
        _read_maplebirch_face_patch_script(injected_base_path)
    )


@pytest.mark.config
def test_au_injection_fails_when_maplebirch_cache_is_missing(tmp_path):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=15705344, paths=paths)
    )

    with pytest.raises(RuntimeError, match="required mod payload cache is missing"):
        builder._inject_modloader_mods()


@pytest.mark.config
@pytest.mark.parametrize("missing_cache_name", ["au_f", "au_face", "maplebirch"])
def test_au_injection_fails_when_any_required_payload_cache_is_missing(
    tmp_path,
    missing_cache_name,
    monkeypatch,
):
    paths = BuildPaths(workspace=tmp_path)
    builder = ZipBuilder(
        BuildTask(pack_type="zip", mod_code=15705344, paths=paths)
    )
    mod_config = ModloaderModConfig(
        key=missing_cache_name,
        feature_id="au-f",
        github_repo="example/required-mod",
        asset_pattern=f"{missing_cache_name}.mod.zip",
    )
    monkeypatch.setattr(
        "lyra.build.load_build_config",
        lambda: SimpleNamespace(modloader_mods=[mod_config]),
    )
    monkeypatch.setattr(
        "lyra.build.get_config_loader",
        lambda: SimpleNamespace(
            get_feature_by_id=lambda _feature_id: SimpleNamespace(
                bit=ModCode.AU_FEMALE,
                name="AU Female",
            )
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=rf"required mod payload cache is missing: .*{missing_cache_name}",
    ):
        builder._inject_modloader_mods()


def _face_passage_patch_rules():
    return (
        ("Widgets Mirror", *AU_FACE_VARIANT_SWITCH_NEEDLES[0]),
        ("Cheats", *AU_FACE_VARIANT_SWITCH_NEEDLES[1]),
        ("Widgets Settings", *AU_FACE_VARIANT_SWITCH_NEEDLES[2]),
        (
            "Widgets variablesVersionUpdate",
            "/* Code that should not be moved into a check like above */\n"
            '\t<<set $runWardrobeSanityChecker to true>>',
            AU_FACE_VARIANT_MIGRATION_NEW,
        ),
    )


def _maplebirch_face_patch_script(*, include_chained_needles: bool = False) -> str:
    script = (
        "modifyFaceStyle(e){let t=e.SC2DataManager.getSC2DataInfoAfterPatch(),"
        "n=t.cloneSC2DataInfo(),r=n.passageDataItems.map;"
        'for(let t of["Cheats","clothesTestingImageGenerate","Widgets Mirror",'
        '"Widgets Settings"]){let n=r.get(t);if(!n?.content)continue;'
        'let a=[[/setup.faceStyleOptions.length gt/g,'
        '"Object.keys(setup.faceStyleOptions).length gte"]];'
        'n.content=e.replace(n.content,a,"FaceStyle"),r.set(t,n)}'
        "n.passageDataItems.back2Array(),"
        "e.modUtils.replaceFollowSC2DataInfo(n,t)}"
    )
    if not include_chained_needles:
        return script
    return (
        # The basehead patch resolves the face-index Set from the payload, so the
        # fixture must contain Maplebirch's real aO() helper, not an alias.
        "let aP=new Set;"
        "function aO(e){let t=e.find(e=>aP.has(e));if(t)return t;"
        'let n="";for(let t of e){let e=no(t);if(e===t||!0===e)return t;'
        "!1===e||n||(n=t)}return n||e[0]}"
        f"const layers={{{MAPLEBIRCH_BASEHEAD_OLD}}};"
        f"class Character{{{MAPLEBIRCH_PET_REMOUNT_OLD}}}"
        + script
    )


def _write_maplebirch_face_patch_payload(
    path,
    *,
    script: str | None = None,
    include_chained_needles: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
        )
        payload_zip.writestr(
            "dist/inject_early.js",
            script
            if script is not None
            else _maplebirch_face_patch_script(
                include_chained_needles=include_chained_needles
            ),
        )
        payload_zip.writestr("README.md", "unchanged")


def _read_maplebirch_face_patch_script(path) -> str:
    with zipfile.ZipFile(path, "r") as payload_zip:
        return payload_zip.read("dist/inject_early.js").decode("utf-8")


def _patched_maplebirch_payload() -> bytes:
    source_buffer = io.BytesIO()
    with zipfile.ZipFile(source_buffer, "w") as source_zip:
        source_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
        )
        source_zip.writestr(
            "dist/inject_early.js",
            _maplebirch_face_patch_script(),
        )

    source_buffer.seek(0)
    target_buffer = io.BytesIO()
    with zipfile.ZipFile(source_buffer, "r") as source_zip:
        original_script = source_zip.read("dist/inject_early.js").decode("utf-8")
        patched_script = original_script.replace(
            MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
            MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_NEW,
            1,
        )
        with zipfile.ZipFile(target_buffer, "w") as target_zip:
            target_zip.writestr("boot.json", source_zip.read("boot.json"))
            target_zip.writestr("dist/inject_early.js", patched_script)
    return target_buffer.getvalue()


def _embedded_boot_payload(name: str, *, script: str | None = None) -> bytes:
    payload_buffer = io.BytesIO()
    with zipfile.ZipFile(payload_buffer, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            json.dumps({"name": name, "version": "test"}, ensure_ascii=False),
        )
        if script is not None:
            payload_zip.writestr("dist/inject_early.js", script)
    return payload_buffer.getvalue()


def _html_with_payloads(payloads: list[bytes]) -> str:
    encoded_payloads = [
        base64.b64encode(payload).decode("ascii") for payload in payloads
    ]
    source_contexts = [
        *(old_text for old_text, _new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES),
        AU_FACE_VARIANT_HTML_MIGRATION_OLD,
    ]
    return (
        "<script>window.modDataValueZipList = "
        f"{json.dumps(encoded_payloads)};</script>"
        + "\n".join(source_contexts)
    )


def _source_face_html(
    *,
    include_face_patch: bool = True,
    variant: str | None = None,
) -> str:
    embedded_payloads: list[bytes] = []
    if include_face_patch:
        embedded_payloads.append(_patched_maplebirch_payload())
    if variant in AU_MODEL_NAME_BY_VARIANT:
        embedded_payloads.extend(
            [
                _embedded_boot_payload(AU_MODEL_NAME_BY_VARIANT[variant]),
                _embedded_boot_payload(AU_FACE_MOD_NAME),
            ]
        )
    return _html_with_payloads(embedded_payloads)


def _variant_from_test_artifact_path(path) -> str | None:
    normalized_name = path.name.lower().replace("_", "-")
    for variant in AU_MODEL_NAME_BY_VARIANT:
        if f"-{variant}-" in normalized_name:
            return variant
    return None


def _write_zip(path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, b"png")
        zf.writestr(
            "Degrees of Lewdity.html",
            _source_face_html(variant=_variant_from_test_artifact_path(path)),
        )


def _write_custom_artifact_zip(
    path,
    *,
    payloads: list[bytes],
    names: list[str] | None = None,
    include_required_au_payloads: bool = True,
) -> None:
    final_payloads = list(payloads)
    variant = _variant_from_test_artifact_path(path)
    if include_required_au_payloads and variant in AU_MODEL_NAME_BY_VARIANT:
        final_payloads.extend(
            [
                _embedded_boot_payload(AU_MODEL_NAME_BY_VARIANT[variant]),
                _embedded_boot_payload(AU_FACE_MOD_NAME),
            ]
        )
    with zipfile.ZipFile(path, "w") as artifact_zip:
        for name in names or []:
            artifact_zip.writestr(name, b"png")
        artifact_zip.writestr(
            "Degrees of Lewdity.html",
            _html_with_payloads(final_payloads),
        )


def _write_zip_with_embedded_mod(path, embedded_names: list[str]) -> None:
    payload_buffer = io.BytesIO()
    with zipfile.ZipFile(payload_buffer, "w") as zf:
        for name in embedded_names:
            zf.writestr(name, b"png")

    encoded_payloads = [
        base64.b64encode(payload_buffer.getvalue()).decode("ascii"),
        base64.b64encode(_patched_maplebirch_payload()).decode("ascii"),
        base64.b64encode(_embedded_boot_payload("【AUmale】model")).decode("ascii"),
        base64.b64encode(_embedded_boot_payload(AU_FACE_MOD_NAME)).decode("ascii"),
    ]
    html = (
        "<script>window.modDataValueZipList = "
        f"{json.dumps(encoded_payloads)};</script>"
        + "\n".join(
            [
                *(
                    old_text
                    for old_text, _new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES
                ),
                AU_FACE_VARIANT_HTML_MIGRATION_OLD,
            ]
        )
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Degrees of Lewdity.html", html)


def _write_apk(path, *, include_face_patch: bool) -> None:
    html_content = _source_face_html(
        include_face_patch=include_face_patch,
        variant=_variant_from_test_artifact_path(path),
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("assets/www/index.html", html_content)
        for index in range(1, 6):
            zf.writestr(
                f"assets/www/img/face/default/default/blush-{index}.png",
                b"png",
            )


@pytest.mark.config
def test_au_artifact_check_accepts_nested_blush_aliases(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush{index}.png" for index in range(1, 6)]
    names.append("img/face/default/default/blusher.png")
    _write_zip(zip_path, names)

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.is_au is True
    assert result.required_nested_blush_present is True
    assert result.nested_blush_count == 5
    assert result.errors == []


@pytest.mark.config
def test_au_artifact_check_accepts_current_hyphenated_outer_aliases(tmp_path):
    """Current official AU assets use blush-1..5 plus independent blusher.png."""
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    names.append("img/face/default/default/blusher.png")
    _write_zip(zip_path, names)

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.outer_required_nested_blush_present is True
    assert result.outer_nested_blush_count == 5
    assert result.nested_blush_count == 5
    assert result.errors == []


@pytest.mark.config
def test_au_artifact_check_accepts_embedded_hyphenated_blush_aliases(tmp_path):
    """HTML-centric AU ZIPs keep model face assets in embedded ModLoader payloads."""
    zip_path = tmp_path / "DoL-au-m-ucb-more-love-custom-spellbook.zip"
    names = [
        f"AUmale/img/face/default/default/blush-{index}.png"
        for index in range(1, 6)
    ]
    names.append("AUmale/img/face/default/default/blusher.png")
    _write_zip_with_embedded_mod(zip_path, names)

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.is_au is True
    assert result.outer_nested_blush_count == 0
    assert result.embedded_nested_blush_count == 5
    assert result.nested_blush_count == 5
    assert result.embedded_required_nested_blush_present is True
    assert result.required_nested_blush_present is True
    assert result.errors == []


@pytest.mark.config
def test_au_artifact_check_rejects_missing_nested_blush_aliases(tmp_path):
    zip_path = tmp_path / "DoL-au-a-ucb-more-love-custom-spellbook.zip"
    _write_zip(zip_path, ["img/face/default/default/blush2.png"])

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert result.required_nested_blush_present is False
    assert result.nested_blush_count == 1
    assert any("blush-1.png" in error for error in result.errors)
    assert any("layers 1-5" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_requires_distinct_blush_layers_one_through_five(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    outer_names = [
        "img/face/default/default/blush-1.png",
        "img/face/default/default/blush-6.png",
        "img/face/default/default/blush-7.png",
    ]
    embedded_names = [
        "AUfemale/img/face/default/default/blush-1.png",
        "AUfemale/img/face/default/default/blush-6.png",
    ]
    payload_buffer = io.BytesIO()
    with zipfile.ZipFile(payload_buffer, "w") as payload_zip:
        for name in embedded_names:
            payload_zip.writestr(name, b"png")
    encoded_payloads = [
        base64.b64encode(payload_buffer.getvalue()).decode("ascii"),
        base64.b64encode(_patched_maplebirch_payload()).decode("ascii"),
    ]
    html = (
        "<script>window.modDataValueZipList = "
        f"{json.dumps(encoded_payloads)};</script>"
        + "\n".join(
            [
                *(
                    old_text
                    for old_text, _new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES
                ),
                AU_FACE_VARIANT_HTML_MIGRATION_OLD,
            ]
        )
    )
    with zipfile.ZipFile(zip_path, "w") as artifact_zip:
        for name in outer_names:
            artifact_zip.writestr(name, b"png")
        artifact_zip.writestr("Degrees of Lewdity.html", html)

    result = audit_zip_artifact(zip_path)

    assert result.numbered_nested_blush_layers == [1, 6, 7]
    assert result.nested_blush_count == 3
    assert result.success is False
    assert any("missing 2, 3, 4, 5" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_missing_face_variant_patch(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    names.append("img/face/default/default/blusher.png")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in names:
            zf.writestr(name, b"png")
        zf.writestr("Degrees of Lewdity.html", "unpatched")

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert result.face_variant_switch_marker_count == 0
    assert result.face_variant_migration_marker_count == 0
    assert any("face-style switch markers" in error for error in result.errors)
    assert any("old-save face migration marker" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_correct_marker_counts_in_wrong_context(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    misplaced_script = (
        MAPLEBIRCH_AU_FACE_VARIANT_MARKER
        + AU_FACE_VARIANT_FALLBACK_EXPRESSION * 3
        + AU_FACE_VARIANT_MIGRATION_EXPRESSION
    )
    payload_buffer = io.BytesIO()
    with zipfile.ZipFile(payload_buffer, "w") as payload_zip:
        payload_zip.writestr(
            "boot.json",
            '{"name":"maplebirch","version":"4.1.14"}',
        )
        payload_zip.writestr("dist/inject_early.js", misplaced_script)
    encoded_payloads = [
        base64.b64encode(payload_buffer.getvalue()).decode("ascii"),
        base64.b64encode(_embedded_boot_payload("【AUfemale】model")).decode("ascii"),
        base64.b64encode(_embedded_boot_payload(AU_FACE_MOD_NAME)).decode("ascii"),
    ]
    source_contexts = "\n".join(
        [
            *(
                old_text
                for old_text, _new_text in AU_FACE_VARIANT_HTML_SWITCH_NEEDLES
            ),
            AU_FACE_VARIANT_HTML_MIGRATION_OLD,
        ]
    )
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in names:
            zf.writestr(name, b"png")
        zf.writestr(
            "Degrees of Lewdity.html",
            "<script>window.modDataValueZipList = "
            f"{json.dumps(encoded_payloads)};</script>"
            + source_contexts,
        )

    result = audit_zip_artifact(zip_path)

    assert result.face_variant_switch_marker_count == 3
    assert result.face_variant_migration_marker_count == 1
    assert result.success is False
    assert any("rules are missing or misplaced" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_declared_but_unexecuted_patch_rules(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    no_op_script = (
        f'const patchName="{MAPLEBIRCH_AU_FACE_VARIANT_MARKER}",'
        f"{EXPECTED_POST_I18N_RULES}"
    )
    no_op_payload = _embedded_boot_payload("maplebirch", script=no_op_script)
    _write_custom_artifact_zip(
        zip_path,
        payloads=[no_op_payload],
        names=names,
    )

    result = audit_zip_artifact(zip_path)

    assert result.face_variant_switch_marker_count == 3
    assert result.face_variant_migration_marker_count == 1
    assert result.post_i18n_patch_marker_count == 1
    assert result.success is False
    assert any("patch execution is missing" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_complete_patch_outside_owner(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    outside_owner_script = (
        _maplebirch_face_patch_script()
        + EXPECTED_POST_I18N_EXECUTION
    )
    outside_owner_payload = _embedded_boot_payload(
        "maplebirch",
        script=outside_owner_script,
    )
    _write_custom_artifact_zip(
        zip_path,
        payloads=[outside_owner_payload],
        names=names,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("outside the Maplebirch owner" in error for error in result.errors)
    assert any("unpatched Maplebirch modifyFaceStyle owner remains" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_duplicate_maplebirch_owners(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    patched_payload = _patched_maplebirch_payload()
    _write_custom_artifact_zip(
        zip_path,
        payloads=[patched_payload, patched_payload],
        names=names,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("exactly one Maplebirch payload owner, found 2" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_detects_renamed_au_model_payload(tmp_path):
    zip_path = tmp_path / "DoL-base-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    au_model_payload = _embedded_boot_payload("【AUfemale】model")
    _write_custom_artifact_zip(
        zip_path,
        payloads=[au_model_payload],
        names=names,
    )

    result = audit_zip_artifact(zip_path)

    assert result.is_au is True
    assert result.success is False
    assert any("base artifact contains AU model payloads" in error for error in result.errors)


@pytest.mark.config
@pytest.mark.parametrize(
    ("artifact_variant", "embedded_model_name"),
    [
        ("au-f", "【AUmale】model"),
        ("au-m", "【AUandrogynous】model"),
        ("au-a", "【AUfemale】model"),
    ],
)
def test_au_artifact_check_rejects_wrong_model_for_declared_variant(
    tmp_path,
    artifact_variant,
    embedded_model_name,
):
    zip_path = tmp_path / f"DoL-{artifact_variant}-ucb-more-love.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    _write_custom_artifact_zip(
        zip_path,
        payloads=[
            _patched_maplebirch_payload(),
            _embedded_boot_payload(embedded_model_name),
            _embedded_boot_payload(AU_FACE_MOD_NAME),
        ],
        names=names,
        include_required_au_payloads=False,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("exactly the matching AU model" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_missing_model_payload(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    _write_custom_artifact_zip(
        zip_path,
        payloads=[
            _patched_maplebirch_payload(),
            _embedded_boot_payload(AU_FACE_MOD_NAME),
        ],
        names=names,
        include_required_au_payloads=False,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("exactly the matching AU model" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_missing_au_face_payload(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    _write_custom_artifact_zip(
        zip_path,
        payloads=[
            _patched_maplebirch_payload(),
            _embedded_boot_payload("【AUfemale】model"),
        ],
        names=names,
        include_required_au_payloads=False,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("exactly one AU Face payload" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_rejects_duplicate_model_payload(tmp_path):
    zip_path = tmp_path / "DoL-au-f-ucb-more-love.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    model_payload = _embedded_boot_payload("【AUfemale】model")
    _write_custom_artifact_zip(
        zip_path,
        payloads=[
            _patched_maplebirch_payload(),
            model_payload,
            model_payload,
            _embedded_boot_payload(AU_FACE_MOD_NAME),
        ],
        names=names,
        include_required_au_payloads=False,
    )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("exactly the matching AU model" in error for error in result.errors)


@pytest.mark.config
def test_artifact_check_rejects_unreadable_embedded_inventory(tmp_path):
    zip_path = tmp_path / "DoL-base-ucb-more-love-custom-spellbook.zip"
    invalid_payload = base64.b64encode(b"not-a-zip").decode("ascii")
    html_content = (
        "<script>window.modDataValueZipList = "
        f"{json.dumps([invalid_payload])};</script>"
    )
    with zipfile.ZipFile(zip_path, "w") as artifact_zip:
        artifact_zip.writestr("Degrees of Lewdity.html", html_content)

    result = audit_zip_artifact(zip_path)

    assert result.is_au is False
    assert result.success is False
    assert any("embedded mod entry 0 is unreadable" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_accepts_patched_apk(tmp_path):
    apk_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.apk"
    _write_apk(apk_path, include_face_patch=True)

    result = audit_apk_artifact(apk_path)

    assert result.success is True
    assert result.face_variant_switch_marker_count == 3
    assert result.face_variant_migration_marker_count == 1
    assert result.nested_blush_count == 5


@pytest.mark.config
def test_au_artifact_check_rejects_unpatched_apk(tmp_path):
    apk_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.apk"
    _write_apk(apk_path, include_face_patch=False)

    result = audit_apk_artifact(apk_path)

    assert result.success is False
    assert any("face-style switch markers" in error for error in result.errors)
    assert any("old-save face migration marker" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_ignores_base_apk(tmp_path):
    apk_path = tmp_path / "DoL-base-ucb-more-love-custom-spellbook.apk"
    _write_apk(apk_path, include_face_patch=False)

    result = audit_apk_artifact(apk_path)

    assert result.success is True
    assert result.is_au is False


@pytest.mark.config
def test_au_artifact_check_ignores_non_au_zip(tmp_path):
    zip_path = tmp_path / "DoL-base-ucb-more-love-custom-spellbook.zip"
    _write_zip(zip_path, [])

    result = audit_zip_artifact(zip_path)

    assert result.success is True
    assert result.is_au is False


@pytest.mark.config
@pytest.mark.parametrize(
    "artifact_name",
    [
        "DoL-ucb-more-love-custom-spellbook.zip",
        "DoL-base-au-f-ucb-more-love-custom-spellbook.zip",
    ],
)
def test_artifact_check_rejects_ambiguous_release_identity(tmp_path, artifact_name):
    """Every uploaded artifact must declare exactly one public variant identity."""
    zip_path = tmp_path / artifact_name
    _write_zip(zip_path, [])

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any(
        "must declare exactly one of base/au-f/au-m/au-a" in error
        for error in result.errors
    )


@pytest.mark.config
def test_artifact_check_rejects_duplicate_mod_list_assignments(tmp_path):
    """A second runtime assignment would load payloads the audit never saw."""
    zip_path = tmp_path / "DoL-au-f-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    audited_html = _source_face_html(variant="au-f")
    runtime_override_payloads = [
        base64.b64encode(_embedded_boot_payload("【AUmale】model")).decode("ascii")
    ]
    with zipfile.ZipFile(zip_path, "w") as artifact_zip:
        for name in names:
            artifact_zip.writestr(name, b"png")
        artifact_zip.writestr(
            "Degrees of Lewdity.html",
            audited_html
            + "<script>window.modDataValueZipList = "
            + f"{json.dumps(runtime_override_payloads)};</script>",
        )

    result = audit_zip_artifact(zip_path)

    assert result.success is False
    assert any("duplicate_assignment" in error for error in result.errors)


@pytest.mark.config
def test_au_artifact_check_directory_covers_all_zips(tmp_path):
    au_zip = tmp_path / "DoL-au-m-ucb-more-love-custom-spellbook.zip"
    base_zip = tmp_path / "DoL-base-ucb-more-love-custom-spellbook.zip"
    names = [f"img/face/default/default/blush-{index}.png" for index in range(1, 6)]
    names.append("img/face/default/default/blusher.png")
    _write_zip(au_zip, names)
    _write_zip(base_zip, [])

    results = audit_target(tmp_path)

    assert len(results) == 2
    assert all(result.success for result in results)
    assert any(result.is_au for result in results)
    assert any(not result.is_au for result in results)
