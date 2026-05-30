"""cheatExtended/maplebirch canary planning tests."""

import json

import pytest

from lyra.build import BuildResult
from lyra.config import ModCode
from tools.cheat_extended_canary import (
    CANARY_CODES,
    COMBINED_PROFILE,
    MANUAL_RUNTIME_BLOCKERS,
    REPLACEMENT_PROFILE,
    ensure_canary_payloads,
    main,
    make_canary_plan,
    validate_canary_code,
    validate_canary_build_result,
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
        "base": 57600,
        "au-f": 58624,
        "au-m": 59648,
        "au-a": 61696,
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

    assert plan.code == 61696
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
        lambda plan, workspace: [
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
