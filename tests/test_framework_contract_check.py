"""Framework contract matrix and content-over-tag identity tests."""

import json
import zipfile
from pathlib import Path

import pytest

from tools.framework_contract_check import (
    BOOT_MEMBER,
    SCRIPT_MEMBER,
    build_report,
    classify_payload,
    find_asset,
    load_matrix,
    main,
    read_payload,
    self_check,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "config" / "framework-contract-matrix.toml"
HELD_414 = (
    REPO_ROOT
    / ".local"
    / "maplebirch-414-investigation"
    / "maplebirch-0.5.10.12-v4.1.14.mod.zip"
)
HELD_413 = (
    REPO_ROOT
    / ".local"
    / "maplebirch-414-investigation"
    / "maplebirch-0.5.10.12-v4.1.13.mod.zip"
)

RESOLVER_PROLOGUE = (
    'function aD(e){let t="function"==typeof e?e:()=>e;return function(e){'
)


def _write_payload(
    path: Path,
    *,
    version: str,
    floor: str,
    script: str,
    name: str = "maplebirch",
    omit_boot: bool = False,
    extra_member: bytes = b"unchanged",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    boot = {
        "name": name,
        "version": version,
        "dependenceInfo": [{"modName": "GameVersion", "version": floor}],
    }
    with zipfile.ZipFile(path, "w") as payload:
        if not omit_boot:
            payload.writestr(BOOT_MEMBER, json.dumps(boot))
        payload.writestr(SCRIPT_MEMBER, script)
        payload.writestr("README.md", extra_member)
    return path


@pytest.mark.config
def test_matrix_declares_the_content_over_tag_contract():
    matrix = load_matrix(MATRIX_PATH)

    assert matrix["schema"] == "dolx.framework-contract-matrix.v1"
    assert matrix["game_version_in_use"] == "0.5.11.9"
    assert matrix["locked_version"] == "4.1.14"
    assert matrix["archaeology"]["upstream_tag_count"] == 9
    assert matrix["archaeology"]["fork_tag_count"] == 34
    assert matrix["archaeology"]["software_heritage_status"] == "not-archived"
    assert matrix["signature_history"]["declared_parameter_count"] == 1


@pytest.mark.config
def test_matrix_records_the_v412_trap():
    matrix = load_matrix(MATRIX_PATH)
    traps = {trap["claim"]: trap for trap in matrix["traps"]}
    trap = traps["maplebirch-release-v4.1.2"]

    assert "4.2.0" in trap["content_identity"]
    assert "face_style_src_fn_export" in trap["detection"]
    assert "tag name" in trap["lesson"]

    row = next(
        item for item in matrix["candidates"] if item["version"] == "4.1.2"
    )
    assert row["content_verdict"] == "mislabeled"
    assert row["face_style_src_fn_export"] is False
    assert row["game_version_floor"] == ">=0.5.11.9"
    assert row["claimed_metadata_version"] == "4.1.2"


@pytest.mark.config
def test_matrix_marks_only_the_held_lock_usable_on_the_pinned_game():
    matrix = load_matrix(MATRIX_PATH)
    usable = {
        row["version"]
        for row in matrix["candidates"]
        if row["usable_on_game_version_in_use"]
    }

    assert usable == {"4.1.13", "4.1.14"}
    locked = next(
        row for row in matrix["candidates"] if row["version"] == matrix["locked_version"]
    )
    assert locked["face_style_src_fn_export"] is True
    assert locked["needle_hits"] == {
        "maplebirch_au_variant_dir_priority": 1,
        "maplebirch_au_face_variant_insertion": 1,
        "maplebirch_pet_remount": 1,
    }


@pytest.mark.config
def test_matrix_records_the_5_1_3_rewrite_and_floor():
    matrix = load_matrix(MATRIX_PATH)
    row = next(item for item in matrix["candidates"] if item["version"] == "5.1.3")

    assert row["face_style_src_fn_export"] is False
    assert row["source_face_style_src_fn_count"] == 0
    assert row["game_version_floor"] == ">=0.5.12.13"
    assert row["usable_on_game_version_in_use"] is False
    assert "faceStyleMap" in row["notes"]


@pytest.mark.config
def test_real_4_1_14_payload_matches_the_matrix():
    if not HELD_414.exists():
        pytest.skip("official 4.1.14 payload is not present locally")

    facts = read_payload(HELD_414)
    result = classify_payload(facts, load_matrix(MATRIX_PATH))

    assert result["verdict"] == "consistent"
    assert result["matrix_version"] == "4.1.14"
    assert result["mismatches"] == []
    assert result["face_style_src_fn_export"] is True
    assert result["game_version_floor"] == ">=0.5.10.12"
    assert set(result["needle_hits"].values()) == {1}


@pytest.mark.config
def test_real_4_1_13_payload_is_contract_equivalent_but_byte_different():
    if not HELD_413.exists():
        pytest.skip("official 4.1.13 payload is not present locally")

    matrix = load_matrix(MATRIX_PATH)
    facts_413 = read_payload(HELD_413)
    result = classify_payload(facts_413, matrix)

    assert result["verdict"] == "consistent"
    assert result["matrix_version"] == "4.1.13"

    facts_414 = read_payload(HELD_414)
    assert facts_413["sha256"] != facts_414["sha256"]
    assert facts_413["bytes"] != facts_414["bytes"]
    for field in (
        "game_version_floor",
        "face_style_src_fn_export",
        "face_style_src_fn_count",
        "needle_hits",
    ):
        assert facts_413[field] == facts_414[field]


@pytest.mark.config
def test_self_check_verifies_every_held_asset():
    if not (HELD_413.exists() and HELD_414.exists()):
        pytest.skip("held payloads are not present locally")

    result = self_check(load_matrix(MATRIX_PATH), REPO_ROOT)

    assert result["required"] == 2
    assert result["checked"] == 2
    assert result["verdict"] == "consistent"
    assert {row["version"] for row in result["rows"]} == {"4.1.13", "4.1.14"}


@pytest.mark.config
def test_trap_payload_is_rejected_as_content_version_mismatch(tmp_path):
    """Metadata says 4.1.2 but the content is a 4.2.0-era removal commit."""
    payload = _write_payload(
        tmp_path / "maplebirch-0.5.10.12-v4.1.2.mod.zip",
        version="4.1.2",
        floor=">=0.5.11.9",
        script="class Character{faceStyleMap=new Map;}",
    )

    result = classify_payload(read_payload(payload), load_matrix(MATRIX_PATH))

    assert result["verdict"] == "content_version_mismatch"
    assert result["matrix_version"] == "4.1.2"
    assert result["content_verdict"] == "mislabeled"
    assert "4.2.0" in result["detail"]


@pytest.mark.config
def test_a_mislabeled_payload_is_never_accepted_as_matching_metadata(tmp_path):
    """The same file name with real 4.1.2 content would also be rejected."""
    payload = _write_payload(
        tmp_path / "maplebirch-0.5.10.12-v4.1.2.mod.zxip.still-named-4.1.2.mod.zip",
        version="4.1.2",
        floor=">=0.5.10.12",
        script=f"{RESOLVER_PROLOGUE}",
    )

    result = classify_payload(read_payload(payload), load_matrix(MATRIX_PATH))

    # A planted 4.1.2 floor contradicts both the registered trap and the real
    # deleted 4.1.x line, so this is a registered-row mismatch, not a pass.
    assert result["verdict"] == "matrix_mismatch"
    assert any("game_version_floor" in item for item in result["mismatches"])


@pytest.mark.config
def test_unregistered_metadata_version_fails_closed(tmp_path):
    payload = _write_payload(
        tmp_path / "maplebirch-unknown.mod.zip",
        version="6.6.6",
        floor=">=0.5.11.9",
        script="",
    )

    result = classify_payload(read_payload(payload), load_matrix(MATRIX_PATH))

    assert result["verdict"] == "unregistered_version"


@pytest.mark.config
def test_synthetic_5_1_3_content_resolves_consistently(tmp_path):
    payload = _write_payload(
        tmp_path / "maplebirch-5.1.3.mod.zip",
        version="5.1.3",
        floor=">=0.5.12.13",
        script="class Character{faceStyleMap=new Map;}",
    )

    result = classify_payload(read_payload(payload), load_matrix(MATRIX_PATH))

    assert result["verdict"] == "consistent"
    assert result["matrix_version"] == "5.1.3"
    assert result["face_style_src_fn_export"] is False


@pytest.mark.config
def test_tampered_payload_fails_on_the_registered_digest(tmp_path):
    if not HELD_414.exists():
        pytest.skip("official 4.1.14 payload is not present locally")

    tampered = tmp_path / "maplebirch-0.5.10.12-v4.1.14.mod.zip"
    with zipfile.ZipFile(HELD_414, "r") as source:
        members = [(item, source.read(item.filename)) for item in source.infolist()]
    with zipfile.ZipFile(tampered, "w") as target:
        for item, data in members:
            if item.filename == "README.md":
                data = data + b"\n# tampered\n"
            target.writestr(item, data)

    result = classify_payload(read_payload(tampered), load_matrix(MATRIX_PATH))

    assert result["verdict"] == "matrix_mismatch"
    assert any("asset_sha256" in item for item in result["mismatches"])


@pytest.mark.config
def test_expect_version_rejects_a_contract_equivalent_substitute(tmp_path):
    if not HELD_413.exists():
        pytest.skip("official 4.1.13 payload is not present locally")

    result = classify_payload(
        read_payload(HELD_413),
        load_matrix(MATRIX_PATH),
        expect_version="4.1.14",
    )

    assert result["verdict"] == "content_version_mismatch"
    assert "4.1.14" in result["detail"]


@pytest.mark.config
def test_payload_without_boot_json_is_an_infrastructure_failure(tmp_path):
    payload = _write_payload(
        tmp_path / "maplebirch-no-boot.mod.zip",
        version="4.1.14",
        floor=">=0.5.10.12",
        script="",
        omit_boot=True,
    )

    result = read_payload(payload)

    assert result["status"] == "infrastructure_fail"
    assert BOOT_MEMBER in result["error"]


@pytest.mark.config
def test_non_zip_input_is_an_infrastructure_failure(tmp_path):
    payload = tmp_path / "maplebirch.mod.zip"
    payload.write_bytes(b"definitely not a zip")

    result = read_payload(payload)

    assert result["status"] == "infrastructure_fail"
    assert "not a zip" in result["error"]


@pytest.mark.config
def test_needles_come_from_the_build_gates_themselves():
    from tools.framework_contract_check import _needles

    needles, error = _needles()

    assert error is None
    assert set(needles) == {
        "maplebirch_au_variant_dir_priority",
        "maplebirch_au_face_variant_insertion",
        "maplebirch_pet_remount",
    }


@pytest.mark.config
def test_find_asset_uses_the_matrix_search_dirs(tmp_path):
    matrix = load_matrix(MATRIX_PATH)
    pattern = (
        matrix["assets"]["search_dirs"][0]
    )
    target = tmp_path / pattern / "maplebirch-0.5.10.12-v4.1.14.mod.zip"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")
    row = next(
        item for item in matrix["candidates"] if item["version"] == "4.1.14"
    )

    assert find_asset(matrix, row, tmp_path) == target
    assert find_asset(matrix, {"asset_pattern": "missing.zip"}, tmp_path) is None


@pytest.mark.config
def test_report_and_cli_exit_codes(tmp_path):
    payload = _write_payload(
        tmp_path / "maplebirch-5.1.3.mod.zip",
        version="5.1.3",
        floor=">=0.5.12.13",
        script="class Character{faceStyleMap=new Map;}",
    )
    out_dir = tmp_path / "report"

    report = build_report(MATRIX_PATH, [payload], root=REPO_ROOT)

    assert report["schema"] == "dolx.framework_contract_check.v1"
    assert report["verdict"] == "consistent"
    assert report["failures"] == []
    assert main([str(payload), "--matrix", str(MATRIX_PATH), "--out", str(out_dir)]) == 0
    assert (out_dir / "framework-contract-check.json").exists()
    assert (out_dir / "framework-contract-check.md").exists()


@pytest.mark.config
def test_cli_fails_when_nothing_is_requested():
    assert main([]) == 2


@pytest.mark.config
def test_cli_returns_non_zero_for_a_mismatching_payload(tmp_path):
    payload = _write_payload(
        tmp_path / "maplebirch-0.5.10.12-v4.1.2.mod.zip",
        version="4.1.2",
        floor=">=0.5.11.9",
        script="class Character{faceStyleMap=new Map;}",
    )
    out_dir = tmp_path / "report"

    exit_code = main(
        [str(payload), "--matrix", str(MATRIX_PATH), "--out", str(out_dir)]
    )

    assert exit_code == 1
    report = json.loads(
        (out_dir / "framework-contract-check.json").read_text(encoding="utf-8")
    )
    assert report["verdict"] == "fail"
    assert report["failures"][0]["verdict"] == "content_version_mismatch"
