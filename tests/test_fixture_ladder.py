"""tools/fixture_ladder.py（夹具阶梯）的单元测试。

不依赖浏览器与网络，只覆盖纯逻辑：
- build_fixture()/verify_fixture()：结构、必需键与 sha256 完整性
- strip_personal()/sanitize_fixture()：绝对路径、显式取值与姓名路径的脱敏
- find_name_candidates()/find_personal_paths()：只报告路径不报告取值
- update_index()/default_fixture_name()：清单自愈与命名
- CLI verify/sanitize：真实文件级行为
- from-save 的 --allow-real 前置：未确认时必须 fail-closed
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import fixture_ladder as fl


def _variables(count: int = 120) -> dict:
    return {f"var{index}": index for index in range(count)}


def _fixture(**overrides) -> dict:
    kwargs = {
        "label": "unit",
        "source": "synthetic",
        "game_version": "0.5.11.9",
        "snapshot_meta": {"dates": 1},
    }
    kwargs.update(overrides)
    return fl.build_fixture(_variables(), **kwargs)


# --------------------------------------------------------------------------- #
# build / verify
# --------------------------------------------------------------------------- #


def test_build_fixture_is_verifiable() -> None:
    fixture = _fixture()
    assert fixture["meta"]["sha256"] == fl.fixture_digest(fixture["variables"])
    assert fixture["meta"]["schema"] == fl.FIXTURE_SCHEMA_VERSION
    verdict = fl.verify_fixture(fixture)
    assert verdict["ok"], verdict["errors"]


def test_verify_detects_digest_mismatch() -> None:
    fixture = _fixture()
    fixture["meta"]["sha256"] = "0" * 64
    verdict = fl.verify_fixture(fixture)
    assert not verdict["ok"]
    assert any("sha256 mismatch" in error for error in verdict["errors"])


def test_verify_rejects_empty_payload() -> None:
    fixture = _fixture()
    fixture["variables"] = {"only": 1}
    fixture["meta"]["sha256"] = fl.fixture_digest(fixture["variables"])
    verdict = fl.verify_fixture(fixture)
    assert not verdict["ok"]
    assert any("top-level keys" in error for error in verdict["errors"])


def test_verify_rejects_unknown_source() -> None:
    fixture = _fixture()
    fixture["meta"]["source"] = "made-up"
    verdict = fl.verify_fixture(fixture)
    assert not verdict["ok"]
    assert any("meta.source" in error for error in verdict["errors"])


def test_verify_flags_personal_paths_even_with_valid_digest() -> None:
    variables = _variables()
    variables["modPath"] = "E:" + "\\projects\\" + "DOL-X\\workspace"
    fixture = fl.build_fixture(
        variables, label="leaky", source="synthetic", game_version="0.5.11.9"
    )
    verdict = fl.verify_fixture(fixture)
    assert not verdict["ok"]
    assert any("personal paths still present" in error for error in verdict["errors"])


def test_real_fixture_must_be_marked_sanitized() -> None:
    fixture = fl.build_fixture(
        _variables(), label="real", source="real-sanitized", game_version="0.5.11.9"
    )
    assert fl.verify_fixture(fixture)["ok"]
    fixture["meta"]["sanitized"] = False
    verdict = fl.verify_fixture(fixture)
    assert not verdict["ok"]
    assert any("not marked sanitized" in error for error in verdict["errors"])


def test_build_fixture_rejects_unknown_source() -> None:
    with pytest.raises(ValueError):
        fl.build_fixture(_variables(), label="x", source="nope", game_version="1")


# --------------------------------------------------------------------------- #
# sanitize
# --------------------------------------------------------------------------- #


def test_strip_personal_redacts_paths_and_values() -> None:
    payload = {
        "modPath": "C:" + "\\Users\\" + "L\\AppData\\Roaming\\DoL",
        "posixPath": "/home/" + "alice/games/dol",
        "secret": "my-private-nickname",
        "nested": [{"deep": "E:" + "\\projects\\" + "DOL-X\\workspace"}],
    }
    clean, stats = fl.strip_personal(
        payload, redact_values=["my-private-nickname"]
    )
    assert clean["modPath"] == fl.REDACTED_PATH
    assert clean["posixPath"] == fl.REDACTED_PATH
    assert clean["secret"] == fl.REDACTED_VALUE
    assert clean["nested"][0]["deep"] == fl.REDACTED_PATH
    assert stats["paths"] == 3
    assert stats["values"] == 1
    assert fl.find_personal_paths(clean) == []


def test_strip_personal_name_redaction_is_opt_in() -> None:
    payload = {"player": {"name": "Robin"}, "wardrobe": {"upper": {"name": "Shirt"}}}
    untouched, stats = fl.strip_personal(payload)
    assert untouched["player"]["name"] == "Robin"
    assert stats["names"] == 0

    clean, stats = fl.strip_personal(
        payload, redact_name_paths=["player.name"], redact_names=True
    )
    assert clean["player"]["name"] == fl.REDACTED_NAME
    assert clean["wardrobe"]["upper"]["name"] == "Shirt"
    assert stats["names"] == 1


def test_sanitize_fixture_recomputes_digest_and_marks_sanitized() -> None:
    variables = _variables()
    variables["modPath"] = "C:" + "\\Users\\" + "L\\x"
    fixture = fl.build_fixture(
        variables, label="dirty", source="real-sanitized", game_version="0.5.11.9"
    )
    clean, counts = fl.sanitize_fixture(fixture, note="unit")
    assert counts["paths"] == 1
    assert clean["meta"]["sanitized"] is True
    assert clean["meta"]["sanitize_note"] == "unit"
    assert clean["meta"]["sha256"] == fl.fixture_digest(clean["variables"])
    assert fl.verify_fixture(clean)["ok"]


def test_find_name_candidates_reports_paths_not_values() -> None:
    payload = {"player": {"name": "SecretName"}, "wardrobe": {"upper": {"name": "Shirt"}}}
    candidates = fl.find_name_candidates(payload)
    paths = {item["path"] for item in candidates}
    assert paths == {"player.name", "wardrobe.upper.name"}
    blob = json.dumps(candidates)
    assert "SecretName" not in blob
    assert "Shirt" not in blob


def test_find_personal_paths_reports_preview_but_truncates() -> None:
    payload = {"a": "C:" + "\\Users\\" + "L\\" + "x" * 400}
    found = fl.find_personal_paths(payload)
    assert len(found) == 1
    assert found[0]["path"] == "a"
    assert len(found[0]["preview"]) <= 80


# --------------------------------------------------------------------------- #
# index / naming
# --------------------------------------------------------------------------- #


def test_update_index_lists_and_verifies_fixtures(tmp_path: Path) -> None:
    directory = tmp_path / "fixtures"
    fl.save_fixture(_fixture(), directory / "one.json")
    broken = _fixture()
    broken["meta"]["sha256"] = "0" * 64
    fl.save_fixture(broken, directory / "two.json")
    fl.update_index(directory)
    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    records = {record["file"]: record for record in index["fixtures"]}
    assert records["one.json"]["verified"] is True
    assert records["two.json"]["verified"] is False
    assert records["one.json"]["top_level_keys"] == 120

    # Self-healing: a second call must not duplicate existing records.
    fl.update_index(directory, entries=index["fixtures"])
    again = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    assert len(again["fixtures"]) == 2


def test_default_fixture_name_is_sanitized() -> None:
    name = fl.default_fixture_name("base 1004/../x", "synthetic")
    assert name.endswith(".json")
    assert "/" not in name and ".." not in name and " " not in name


# --------------------------------------------------------------------------- #
# CLI + fail-closed gates
# --------------------------------------------------------------------------- #


def test_cli_verify_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = fl.save_fixture(_fixture(), tmp_path / "good.json")
    bad = _fixture()
    bad["meta"]["sha256"] = "0" * 64
    bad_path = fl.save_fixture(bad, tmp_path / "bad.json")

    assert fl.main(["verify", str(good)]) == 0
    assert fl.main(["verify", str(good), str(bad_path)]) == 1
    output = capsys.readouterr().out
    assert "FAILED" in output


def test_cli_sanitize_writes_sibling_by_default(tmp_path: Path) -> None:
    source = fl.save_fixture(_fixture(), tmp_path / "dirty.json")
    assert fl.main(["sanitize", str(source)]) == 0
    sibling = tmp_path / "dirty-sanitized.json"
    assert sibling.exists()
    assert fl.verify_fixture(fl.load_fixture(sibling))["ok"]


def test_cli_capture_and_from_save_are_browser_commands() -> None:
    args = fl.parse_args(["capture", "target.html"])
    assert args.command == "capture" and args.headful is False
    args = fl.parse_args(["from-save", "target.html", "x.save"])
    assert args.allow_real is False


def test_from_save_refuses_without_allow_real(tmp_path: Path) -> None:
    save_file = tmp_path / "discardable.save"
    save_file.write_text("N4IglgJiBcIC4FMDO", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        fl.capture_from_save(
            tmp_path / "target.html",
            save_file,
            label=None,
            out=None,
            headless=True,
            timeout_ms=1000,
            settle_ms=0,
            allow_real=False,
        )
    assert "--allow-real" in str(excinfo.value)


def test_from_save_refuses_empty_file_even_with_allow_real(tmp_path: Path) -> None:
    save_file = tmp_path / "empty.save"
    save_file.write_text("   \n", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        fl.capture_from_save(
            tmp_path / "target.html",
            save_file,
            label=None,
            out=None,
            headless=True,
            timeout_ms=1000,
            settle_ms=0,
            allow_real=True,
        )
    assert "empty" in str(excinfo.value)


def test_manifest_records_source_and_digest() -> None:
    fixture = _fixture(source="real-sanitized")
    fixture["meta"]["sanitized"] = True
    assert fixture["meta"]["source"] == "real-sanitized"
    assert len(fixture["meta"]["sha256"]) == 64
