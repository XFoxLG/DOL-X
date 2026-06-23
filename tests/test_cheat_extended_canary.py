"""cheatExtended/maplebirch canary planning tests."""

import json
import zipfile

import pytest

from lyra.build import BuildResult
from lyra.config import ModCode
from tools.cheat_extended_canary import (
    CANARY_CODES,
    COMBINED_PROFILE,
    MANUAL_RUNTIME_BLOCKERS,
    MAPLEBIRCH_IDB_PATCH_MEMBER,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED,
    MaplebirchPayloadOverride,
    REPLACEMENT_PROFILE,
    _patch_maplebirch_idb_schema_recovery,
    ensure_canary_payloads,
    main,
    make_canary_plan,
    validate_canary_code,
    validate_canary_build_result,
)


def _write_fake_maplebirch_payload(payload_path, version="3.1.13"):
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(payload_path, "w") as payload_zip:
        payload_zip.writestr("boot.json", json.dumps({"name": "maplebirch", "version": version}))
        payload_zip.writestr(
            MAPLEBIRCH_IDB_PATCH_MEMBER,
            f"before:{MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL}:after",
        )


@pytest.mark.config
def test_stable_replacement_canary_codes_match_manual_gate_matrix():
    assert CANARY_CODES["stable-replacement"] == {
        "base": 33024,
        "au-f": 34048,
        "au-m": 35072,
        "au-a": 37120,
    }


@pytest.mark.config
def test_combined_canary_codes_match_manual_gate_matrix():
    assert CANARY_CODES["combined"] == {
        "base": 499968,
        "au-f": 500992,
        "au-m": 502016,
        "au-a": 504064,
    }


@pytest.mark.config
@pytest.mark.parametrize("flavor", ["stable-replacement", "combined"])
def test_canary_codes_do_not_mix_legacy_cheat_bits(flavor):
    for code in CANARY_CODES[flavor].values():
        mod_code = ModCode(code)

        assert mod_code & ModCode.CHEAT_EXTENDED_MAPLEBIRCH
        assert mod_code & ModCode.UCB
        assert not mod_code & ModCode.CHEAT
        assert not mod_code & ModCode.CSD
        assert validate_canary_code(code, flavor) == []


@pytest.mark.config
def test_stable_replacement_plan_uses_separate_profile_and_manual_gate():
    plan = make_canary_plan("stable-replacement", "base")

    assert plan.code == 33024
    assert plan.smoke_profile == REPLACEMENT_PROFILE
    assert plan.expected_slug_tokens == ["ucb", "cheat-extended", "maplebirch"]
    assert plan.forbidden_slug_tokens == ["more-love", "custom-spellbook"]
    assert "CHEAT_EXTENDED_MANUAL_TEST_CHECKLIST.md" in plan.manual_checklist
    assert "maplebirchFrameworks is not defined" in plan.manual_runtime_blockers
    assert "--build" in plan.build_command
    assert "--ensure-payloads" in plan.build_command
    assert "tools/html_smoke_test.py" in plan.html_smoke_command
    assert "--output" in plan.html_smoke_command
    assert not any("--output-dir" == arg for arg in plan.html_smoke_command)
    assert "tools/browser_smoke_test.py" in plan.browser_smoke_command
    assert REPLACEMENT_PROFILE in plan.browser_smoke_command


@pytest.mark.config
def test_combined_plan_uses_experiment_profile_after_stable_issues_are_understood():
    plan = make_canary_plan("combined", "au-a")

    assert plan.code == 504064
    assert plan.smoke_profile == COMBINED_PROFILE
    assert plan.expected_slug_tokens == [
        "ucb",
        "cheat-extended",
        "maplebirch",
        "more-love",
        "custom-spellbook",
    ]
    assert plan.forbidden_slug_tokens == []


@pytest.mark.config
def test_validate_canary_code_rejects_legacy_cheat_stack_and_wrong_flavor():
    errors = validate_canary_code(33024 | int(ModCode.CHEAT), "stable-replacement")

    assert any("legacy cheat" in error for error in errors)

    combined_errors = validate_canary_code(33024, "combined")
    assert any("more_love" in error for error in combined_errors)
    assert any("custom_spellbook" in error for error in combined_errors)


@pytest.mark.config
def test_validate_canary_build_result_rejects_slug_only_fake_canary():
    plan = make_canary_plan("stable-replacement", "base")
    result = BuildResult(
        success=True,
        output_name="DoL-unknown-XFox-unknown-ucb-cheat-extended-maplebirch-0530.zip",
        applied_mods=["UCB"],
    )

    errors = validate_canary_build_result(plan, result)

    assert any("maplebirch" in error for error in errors)
    assert any("cheatExtended" in error for error in errors)


@pytest.mark.config
def test_validate_canary_build_result_accepts_real_payload_injection():
    plan = make_canary_plan("stable-replacement", "base")
    result = BuildResult(
        success=True,
        output_name="DoL-0.5.8.10-XFox-3.1.3a-ucb-cheat-extended-maplebirch-0530.zip",
        applied_mods=["UCB", "maplebirch", "cheatExtended"],
    )

    assert validate_canary_build_result(plan, result) == []


@pytest.mark.config
def test_patch_maplebirch_idb_schema_recovery_wraps_missing_store_and_null_db_retry(tmp_path):
    payload_path = tmp_path / "maplebirch.mod.zip"
    _write_fake_maplebirch_payload(payload_path)

    result = _patch_maplebirch_idb_schema_recovery(payload_path)

    assert result["status"] == "patched"
    assert result["applied"] is True
    assert result["payload_name"] == "maplebirch"
    assert result["payload_version"] == "3.1.13"
    assert result["recovery"] == "missing_store_or_null_db"

    with zipfile.ZipFile(payload_path, "r") as payload_zip:
        patched_script = payload_zip.read(MAPLEBIRCH_IDB_PATCH_MEMBER).decode("utf-8")

    assert MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL not in patched_script
    assert MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED in patched_script
    assert "IDB database handle missing before transaction" in patched_script
    assert "IDB unavailable; rebuilding database before retry" in patched_script
    assert "reading ['\"]transaction['\"]" in patched_script
    assert "await this.resetDatabase();this.ready||await this.init();continue" in patched_script


@pytest.mark.config
def test_patch_maplebirch_idb_schema_recovery_is_idempotent_for_null_db_patch(tmp_path):
    payload_path = tmp_path / "maplebirch.mod.zip"
    _write_fake_maplebirch_payload(payload_path)

    first = _patch_maplebirch_idb_schema_recovery(payload_path)
    second = _patch_maplebirch_idb_schema_recovery(payload_path)

    assert first["status"] == "patched"
    assert second["status"] == "already_patched"
    assert second["applied"] is False
    assert second["recovery"] == "missing_store_or_null_db"


@pytest.mark.config
def test_ensure_canary_payloads_downloads_only_canary_mods(tmp_path, monkeypatch):
    plan = make_canary_plan("stable-replacement", "base")
    downloaded: list[tuple[str, str]] = []

    def fake_download(url, dest_path, quiet=False):
        downloaded.append((url, dest_path.name))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"payload")

    monkeypatch.setattr("tools.cheat_extended_canary.download_file", fake_download)

    payloads = ensure_canary_payloads(plan, tmp_path)

    assert {payload["cache_name"] for payload in payloads} == {"maplebirch", "cheat_extended"}
    assert {payload["path"] for payload in payloads} == {
        str(tmp_path / "workspace" / "temp" / "maplebirch.mod.zip"),
        str(tmp_path / "workspace" / "temp" / "cheat_extended.mod.zip"),
    }
    assert {name for _, name in downloaded} == {"maplebirch.mod.zip", "cheat_extended.mod.zip"}


@pytest.mark.config
def test_ensure_canary_payloads_override_only_replaces_maplebirch_payload(tmp_path, monkeypatch):
    plan = make_canary_plan("stable-replacement", "base")
    downloaded: list[tuple[str, str]] = []

    def fake_download(url, dest_path, quiet=False):
        downloaded.append((url, dest_path.name))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(f"payload:{url}".encode("utf-8"))

    monkeypatch.setattr("tools.cheat_extended_canary.download_file", fake_download)

    payloads = ensure_canary_payloads(
        plan,
        tmp_path,
        MaplebirchPayloadOverride(
            download_url="https://example.invalid/maplebirch-0.5.8.10-v3.2.3.modpack",
            cache_label="maplebirch-release-v3.2.3",
        ),
    )

    by_cache_name = {payload["cache_name"]: payload for payload in payloads}
    maplebirch_payload = by_cache_name["maplebirch"]
    cheat_payload = by_cache_name["cheat_extended"]

    assert maplebirch_payload["path"] == str(tmp_path / "workspace" / "temp" / "maplebirch.mod.zip")
    assert maplebirch_payload["source"] == "https://example.invalid/maplebirch-0.5.8.10-v3.2.3.modpack"
    assert maplebirch_payload["override"] is True
    assert maplebirch_payload["override_cache_label"] == "maplebirch-release-v3.2.3"
    assert "override" not in cheat_payload
    assert {name for _, name in downloaded} == {"maplebirch.mod.zip", "cheat_extended.mod.zip"}


@pytest.mark.config
def test_ensure_canary_payloads_applies_idb_patch_to_v313_override(tmp_path, monkeypatch):
    plan = make_canary_plan("stable-replacement", "base")

    def fake_download(url, dest_path, quiet=False):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.name == "maplebirch.mod.zip":
            _write_fake_maplebirch_payload(dest_path, version="3.1.13")
        else:
            dest_path.write_bytes(f"payload:{url}".encode("utf-8"))

    monkeypatch.setattr("tools.cheat_extended_canary.download_file", fake_download)

    payloads = ensure_canary_payloads(
        plan,
        tmp_path,
        MaplebirchPayloadOverride(
            download_url="https://example.invalid/maplebirch-0.5.8.10-v3.1.13.mod.zip",
            cache_label="maplebirch-release-v3.1.13",
        ),
    )

    by_cache_name = {payload["cache_name"]: payload for payload in payloads}
    patch_result = by_cache_name["maplebirch"]["maplebirch_idb_schema_patch"]

    assert patch_result["status"] == "patched"
    assert patch_result["payload_version"] == "3.1.13"
    assert patch_result["recovery"] == "missing_store_or_null_db"
    assert "maplebirch_idb_schema_patch" not in by_cache_name["cheat_extended"]

    with zipfile.ZipFile(tmp_path / "workspace" / "temp" / "maplebirch.mod.zip", "r") as payload_zip:
        patched_script = payload_zip.read(MAPLEBIRCH_IDB_PATCH_MEMBER).decode("utf-8")
    assert MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED in patched_script


@pytest.mark.config
def test_canary_plan_cli_can_ensure_payloads_before_build(tmp_path, monkeypatch):
    output = tmp_path / "canary-build.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "cheat_extended_canary.py",
            "--flavor",
            "stable-replacement",
            "--variant",
            "base",
            "--workspace",
            str(tmp_path),
            "--ensure-payloads",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(
        "tools.cheat_extended_canary.ensure_canary_payloads",
        lambda plan, workspace, maplebirch_override=None: [
            {"name": "maplebirch", "cache_name": "maplebirch", "path": "cached", "cached": False},
            {
                "name": "cheatExtended",
                "cache_name": "cheat_extended",
                "path": "cached",
                "cached": False,
            },
        ],
    )

    assert main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["payload_cache"]
    assert payload["default_matrix_mutated"] is False


@pytest.mark.config
def test_canary_plan_cli_passes_maplebirch_override_without_mutating_defaults(tmp_path, monkeypatch):
    output = tmp_path / "canary-build.json"
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "sys.argv",
        [
            "cheat_extended_canary.py",
            "--flavor",
            "stable-replacement",
            "--variant",
            "base",
            "--workspace",
            str(tmp_path),
            "--ensure-payloads",
            "--maplebirch-release-tag",
            "maplebirch-release-v3.2.3",
            "--maplebirch-asset-pattern",
            "maplebirch-0.5.8.10-v3.2.3.modpack",
            "--maplebirch-cache-label",
            "v3.2.3-static-candidate",
            "--output",
            str(output),
        ],
    )

    def fake_ensure(plan, workspace, maplebirch_override=None):
        captured["override"] = maplebirch_override
        return [
            {
                "name": "maplebirch",
                "cache_name": "maplebirch",
                "path": "cached",
                "cached": False,
                "override": True,
            }
        ]

    monkeypatch.setattr("tools.cheat_extended_canary.ensure_canary_payloads", fake_ensure)

    assert main() == 0

    override = captured["override"]
    assert isinstance(override, MaplebirchPayloadOverride)
    assert override.release_tag == "maplebirch-release-v3.2.3"
    assert override.asset_pattern == "maplebirch-0.5.8.10-v3.2.3.modpack"
    assert override.cache_label == "v3.2.3-static-candidate"

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["default_matrix_mutated"] is False
    assert payload["maplebirch_override"]["release_tag"] == "maplebirch-release-v3.2.3"


@pytest.mark.config
def test_canary_plan_cli_writes_dry_run_payload(tmp_path, monkeypatch):
    output = tmp_path / "canary-plan.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "cheat_extended_canary.py",
            "--flavor",
            "stable-replacement",
            "--variant",
            "base",
            "--output",
            str(output),
        ],
    )

    assert main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["manual_gate_required"] is True
    assert payload["default_matrix_mutated"] is False
    assert payload["plan"]["code"] == 33024
    assert payload["plan"]["smoke_profile"] == REPLACEMENT_PROFILE
    assert payload["plan"]["manual_runtime_blockers"] == list(MANUAL_RUNTIME_BLOCKERS)
