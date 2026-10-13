"""AU face-source contract tests: framework export vs AU call shapes.

The plan requires that a sample with "framework side 0 while the AU side references
more than 0" must fail. The AU facial expansion is normally encrypted, so the
contract must also never pass silently when the call sites are unobservable.
"""

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest

from lyra.build import (
    MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER,
    MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD,
    MAPLEBIRCH_PET_REMOUNT_OLD,
    patch_maplebirch_au_face_variant_selection,
    patch_maplebirch_au_variant_dir_priority,
    patch_maplebirch_pet_passage_remount,
)
from tools.au_artifact_check import (
    AU_CONTRACT_SCHEMA,
    AU_DEFECT_STATUS,
    AU_FACE_MOD_NAME,
    AU_MODEL_NAME_BY_VARIANT,
    audit_zip_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_AU_PAYLOAD = (
    REPO_ROOT
    / ".local"
    / "au-manifest-inspection"
    / "AUsDoL.facial.expansion.mod.zip"
)
AU_FEMALE_MODEL = AU_MODEL_NAME_BY_VARIANT["au-f"]


def _chain_maplebirch_payload(
    tmp_path: Path,
    *,
    export: bool = True,
    shim_marker: bool = True,
) -> bytes:
    """Run the real payload patch chain, then optionally remove contract parts."""
    source = tmp_path / "maplebirch.mod.zip"
    script = (
        f"class Character{{faceStyleSrcFn=aD;{MAPLEBIRCH_PET_REMOUNT_OLD}}}"
        f"/*{MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_OLD}*/"
        + MAPLEBIRCH_AU_FACE_VARIANT_INSERTION_OLD
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "w") as payload:
        payload.writestr("boot.json", '{"name":"maplebirch","version":"4.1.14"}')
        payload.writestr("dist/inject_early.js", script)

    current = source
    for index, patch in enumerate(
        (
            patch_maplebirch_pet_passage_remount,
            patch_maplebirch_au_face_variant_selection,
            patch_maplebirch_au_variant_dir_priority,
        )
    ):
        target = tmp_path / f"chained{index}.mod.zip"
        result = patch(current, target)
        assert result["status"] == "patched", result
        current = target

    patched = current.read_bytes()
    if not export:
        patched = _strip_export(patched)
    if not shim_marker:
        patched = _strip_shim_marker(patched)
    return patched


def _rewrite_script(payload: bytes, mutate) -> bytes:
    source = io.BytesIO(payload)
    target = io.BytesIO()
    with zipfile.ZipFile(source, "r") as source_zip:
        script = source_zip.read("dist/inject_early.js").decode("utf-8")
        with zipfile.ZipFile(target, "w") as target_zip:
            for item in source_zip.infolist():
                data = source_zip.read(item.filename)
                if item.filename == "dist/inject_early.js":
                    data = mutate(script).encode("utf-8")
                target_zip.writestr(item, data)
    return target.getvalue()


def _strip_export(payload: bytes) -> bytes:
    return _rewrite_script(payload, lambda text: text.replace("faceStyleSrcFn=aD;", ""))


def _strip_shim_marker(payload: bytes) -> bytes:
    return _rewrite_script(
        payload,
        lambda text: text.replace(
            f"/*{MAPLEBIRCH_AU_VARIANT_DIR_PRIORITY_MARKER}*/", "/**/"
        ),
    )


def _au_payload(
    *,
    name: str = AU_FACE_MOD_NAME,
    plaintext_sites: int = 0,
    crypt: bool = False,
    boot_version: str = "1.1.0",
) -> bytes:
    """Build an AU facial-expansion payload shaped like the real one."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as payload:
        payload.writestr(
            "boot.json",
            json.dumps({"name": name, "version": boot_version}, ensure_ascii=False),
        )
        payload.writestr("README.md", "readme text that carries no call sites")
        if plaintext_sites:
            body = "\n".join(
                f"srcfn: faceStyleSrcFn('layer{index}', {{ variant: true }})"
                for index in range(plaintext_sites)
            )
            payload.writestr("js/faceSelector.js", body)
        if crypt:
            payload.writestr(f"{name}.zip.crypt", bytes(range(256)))
            payload.writestr(f"{name}.zip.salt", bytes(range(16)))
            payload.writestr(f"{name}.zip.nonce", bytes(range(8)))
    return buffer.getvalue()


def _write_artifact(
    path: Path,
    payloads: list[bytes],
    *,
    include_model: bool = True,
) -> Path:
    embedded = [
        base64.b64encode(payload).decode("ascii") for payload in payloads
    ]
    if include_model:
        model = io.BytesIO()
        with zipfile.ZipFile(model, "w") as model_zip:
            model_zip.writestr(
                "boot.json",
                json.dumps({"name": AU_FEMALE_MODEL, "version": "test"}),
            )
        embedded.insert(0, base64.b64encode(model.getvalue()).decode("ascii"))
    html = (
        "<script>window.modDataValueZipList = "
        f"{json.dumps(embedded)};</script>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as artifact:
        for index in range(1, 6):
            artifact.writestr(
                f"img/face/default/default/blush-{index}.png", b"png"
            )
        artifact.writestr("Degrees of Lewdity.html", html)
    return path


def _au_artifact(tmp_path: Path, payloads: list[bytes], **kwargs):
    path = _write_artifact(
        tmp_path / "DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.zip", payloads, **kwargs
    )
    return audit_zip_artifact(path)


@pytest.mark.config
def test_framework_zero_with_au_references_fails_fast(tmp_path):
    """The plan's named sample: framework exports 0 while AU references it."""
    payload = _strip_export(_chain_maplebirch_payload(tmp_path))
    result = _au_artifact(
        tmp_path,
        [payload, _au_payload(plaintext_sites=2)],
    )

    contract = result.au_contract
    assert contract.framework_face_style_src_fn_export_count == 0
    # The AU side's call sites are readable here, so this is a proven contradiction.
    assert contract.au_payload_logic_observable is True
    assert contract.au_variant_true_site_count == 2
    assert any(
        "AU contract violation" in error and "faceStyleSrcFn" in error
        for error in contract.errors
    )
    assert result.success is False


@pytest.mark.config
def test_framework_export_present_passes_the_cross_assertion(tmp_path):
    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(tmp_path, [payload, _au_payload(plaintext_sites=2)])

    contract = result.au_contract
    assert contract.framework_face_style_src_fn_export_count == 1
    assert contract.framework_variant_dir_shim_marker_count == 1
    assert contract.framework_pet_remount_marker_count == 1
    assert contract.au_variant_true_site_count == 2
    assert contract.errors == []


@pytest.mark.config
def test_missing_variant_dir_shim_marker_fails(tmp_path):
    payload = _strip_shim_marker(_chain_maplebirch_payload(tmp_path))
    result = _au_artifact(tmp_path, [payload, _au_payload()])

    contract = result.au_contract
    assert contract.framework_variant_dir_shim_marker_count == 0
    assert any(
        "variant-directory priority shim marker" in error
        for error in contract.errors
    )
    assert result.success is False


@pytest.mark.config
def test_encrypted_au_payload_is_never_a_silent_pass(tmp_path):
    """Real AU payloads hide the call sites; the contract must say so."""
    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(
        tmp_path,
        [payload, _au_payload(crypt=True)],
    )

    contract = result.au_contract
    assert contract.au_payload_present is True
    assert contract.au_payload_logic_observable is False
    assert contract.au_variant_true_sites_unobservable is True
    assert contract.runtime_query_required is True
    assert contract.au_variant_true_site_count == 0
    assert contract.au_payload_opaque_members
    # The encrypted payload is not an error by itself, but it is a hard obligation.
    assert contract.errors == []


@pytest.mark.config
def test_readable_call_sites_clear_the_runtime_query_obligation(tmp_path):
    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(tmp_path, [payload, _au_payload(plaintext_sites=3)])

    contract = result.au_contract
    assert contract.au_payload_logic_observable is True
    assert contract.runtime_query_required is False
    assert contract.au_variant_true_site_count == 3


@pytest.mark.config
def test_contract_report_carries_the_plan_schema_and_defect_status(tmp_path):
    from dataclasses import asdict

    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(tmp_path, [payload, _au_payload(crypt=True)])
    serialized = json.loads(json.dumps(asdict(result.au_contract)))

    assert serialized["schema"] == AU_CONTRACT_SCHEMA == "dolx.au_contract.v1"
    # The 2026-10-13 A/B landed as a visual no-op, so the AU layer gap stays
    # accepted_upstream with an explicit visual_incomplete tag; "fixed" is unused.
    assert serialized["defect_status"] == AU_DEFECT_STATUS == "accepted_upstream"
    assert serialized["defect_visual_status"] == "visual_incomplete"
    assert serialized["ab_verdict"] == "no_visual_change"
    assert serialized["ab_evidence"].startswith("docs/CURRENT_PROJECT_STATE.md#")
    assert serialized["legacy_naming_404_count"] is None
    for key in (
        "framework_face_style_src_fn_export_count",
        "framework_variant_dir_shim_marker_count",
        "au_variant_true_site_count",
        "runtime_query_required",
        "defect_visual_status",
        "ab_verdict",
    ):
        assert key in serialized


@pytest.mark.config
def test_missing_au_payload_is_reported(tmp_path):
    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(tmp_path, [payload], include_model=True)

    contract = result.au_contract
    assert contract.au_payload_present is False
    assert any(
        "no readable AU facial-expansion payload" in error
        for error in contract.errors
    )


@pytest.mark.config
def test_base_artifact_does_not_require_the_au_contract(tmp_path):
    payload = _chain_maplebirch_payload(tmp_path)
    path = _write_artifact(
        tmp_path / "DoL-0.5.11.9-XFox-1.0.0a-base-0915.zip",
        [payload],
        include_model=False,
    )

    result = audit_zip_artifact(path)

    assert result.is_au is False
    assert result.au_contract.framework_export_required is False
    assert result.au_contract.runtime_query_required is False


@pytest.mark.config
def test_real_au_payload_records_the_runtime_query_obligation(tmp_path):
    if not REAL_AU_PAYLOAD.exists():
        pytest.skip("the AU facial-expansion payload is not present locally")

    payload = _chain_maplebirch_payload(tmp_path)
    result = _au_artifact(
        tmp_path,
        [payload, REAL_AU_PAYLOAD.read_bytes()],
    )

    contract = result.au_contract
    assert contract.au_payload_present is True
    # The outer boot.json claims 1.1.0 while the decrypted inner archive is 1.2.8,
    # so the metadata version is recorded as a clue, never as the identity.
    assert contract.au_payload_boot_version == "1.1.0"
    assert contract.au_payload_runtime_identity == "1.2.8"
    assert contract.au_payload_logic_observable is False
    assert contract.runtime_query_required is True
    assert any(name.endswith(".crypt") for name in contract.au_payload_opaque_members)
