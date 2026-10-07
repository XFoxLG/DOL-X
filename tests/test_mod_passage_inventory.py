"""Pure-logic tests for tools/mod_passage_inventory.py."""

from __future__ import annotations

import base64
import io
import json
import zipfile

from tools import mod_passage_inventory as mpi


def test_extract_twee_passage_names_handles_headers_tags_and_dupes() -> None:
    text = (
        ":: Start\n"
        "Body text\n"
        ":: Food Preference [widget]\n"
        "::  CE_Wardrobe  [widget]\n"
        ":: Start\n"
        "Prose about the :: operator is not a header.\n"
    )

    names = mpi.extract_twee_passage_names(text)

    assert names == ["Start", "Food Preference", "CE_Wardrobe"]


def test_extract_twee_passage_names_respects_limit() -> None:
    text = "".join(f":: P{i}\n" for i in range(10))

    assert mpi.extract_twee_passage_names(text, limit=3) == ["P0", "P1", "P2"]


def test_extract_twee_passages_and_widget_declaration() -> None:
    text = (
        ":: CE_moneyCheat [widget]\n"
        '<<widget "moneyCheat">>\n'
        "<<set _args[0]>>\n"
        "<</widget>>\n"
        ":: Plain Passage\n"
        "Just prose.\n"
    )

    blocks = mpi.extract_twee_passages(text)

    assert list(blocks) == ["CE_moneyCheat", "Plain Passage"]
    assert mpi.extract_widget_name(blocks["CE_moneyCheat"]) == "moneyCheat"
    assert mpi.extract_widget_name(blocks["Plain Passage"]) is None


def test_encryption_markers_detect_crypt_files() -> None:
    markers = mpi._encryption_markers(
        ["boot.json", "AU.zip.crypt", "AU.salt", "AU.nonce", "readme.txt"]
    )

    assert markers == ["AU.zip.crypt", "AU.salt", "AU.nonce"]


def test_attribute_passages_maps_names_to_sorted_mods() -> None:
    payloads = [
        mpi.ModPayload(index=0, name="More Love", version="1.0", twee_passages=["Food Preference"]),
        mpi.ModPayload(index=1, name="Cheat Extended", version="1.2", twee_passages=["Food Preference", "CE_Wardrobe"]),
    ]

    attribution = mpi.attribute_passages(payloads)

    assert attribution["Food Preference"] == ["Cheat Extended", "More Love"]
    assert attribution["CE_Wardrobe"] == ["Cheat Extended"]


def test_classify_mod_passages_splits_runtime_only_names() -> None:
    static = ["Start", "Bedroom"]
    dom = ["Start", "Bedroom", "Food Preference", "CE_Wardrobe", "CE_EnemyState"]
    classification = {
        "Food Preference": {"storyHas": True, "macroHas": False},
        "CE_Wardrobe": {"storyHas": False, "macroHas": True},
        "CE_EnemyState": {"storyHas": False, "macroHas": False},
    }

    split = mpi.classify_mod_passages(static, dom, classification)

    assert split["runtime_only"] == ["CE_EnemyState", "CE_Wardrobe", "Food Preference"]
    assert split["playable"] == ["Food Preference"]
    assert split["widget"] == ["CE_Wardrobe"]
    assert split["unregistered"] == ["CE_EnemyState"]


def test_classify_mod_passages_uses_declared_widgets_and_registry() -> None:
    split = mpi.classify_mod_passages(
        ["Start"],
        ["Start", "CE_moneyCheat", "CE_cheatExtendedMenu", "Food Preference"],
        {
            "CE_moneyCheat": {"storyHas": False, "macroHas": False, "tags": "widget"},
            "CE_cheatExtendedMenu": {"storyHas": False, "macroHas": False, "tags": ""},
            "Food Preference": {"storyHas": True, "macroHas": False, "tags": ""},
        },
        widget_names={
            "CE_moneyCheat": "moneyCheat",
            "CE_cheatExtendedMenu": "cheatExtendedMenu",
        },
        widget_registry={"moneyCheat": True, "cheatExtendedMenu": False},
    )

    assert split["playable"] == ["Food Preference"]
    assert split["widget"] == ["CE_cheatExtendedMenu", "CE_moneyCheat"]
    assert split["unregistered"] == []
    rows = {row["name"]: row for row in split["rows"]}
    assert rows["CE_moneyCheat"]["macro_registered"] is True
    assert rows["CE_cheatExtendedMenu"]["widget"] == "cheatExtendedMenu"
    assert rows["CE_cheatExtendedMenu"]["macro_registered"] is False


def _payload_zip(*, boot: dict, entries: dict[str, str | bytes]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("boot.json", json.dumps(boot))
        for name, content in entries.items():
            zf.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_scan_mod_payloads_reads_boot_and_twee_and_flags_encryption() -> None:
    plain = _payload_zip(
        boot={"name": "More Love Interests Mod", "version": "1.4.2"},
        entries={
            "twee/extra.twee": (
                ":: Food Preference\nBody\n"
                ":: More Love Interests UI\n"
                '<<widget "moreLoveInterestsUI">>\n<</widget>>\n'
            )
        },
    )
    encrypted = _payload_zip(
        boot={"name": "AU面部扩展", "version": "1.2.8"},
        entries={
            "SimpleCryptWrapper.js": "// wrapper",
            "pack.zip.crypt": b"\x00\x01\x02",
            "pack.salt": b"\x00" * 16,
        },
    )
    html = "window.modDataValueZipList = " + json.dumps([plain, encrypted]) + ";"

    payloads, errors = mpi.scan_mod_payloads(html)

    assert errors == []
    assert [p.name for p in payloads] == ["More Love Interests Mod", "AU面部扩展"]
    assert payloads[0].version == "1.4.2"
    assert payloads[0].twee_passages == ["Food Preference", "More Love Interests UI"]
    assert payloads[0].widget_by_passage == {"More Love Interests UI": "moreLoveInterestsUI"}
    assert payloads[0].encrypted is False
    assert payloads[1].encrypted is True
    assert payloads[1].encryption_markers == ["pack.zip.crypt", "pack.salt"]
    assert payloads[1].twee_passages == []


def test_scan_mod_payloads_reports_missing_payload_list() -> None:
    payloads, errors = mpi.scan_mod_payloads("<html><body>vanilla only</body></html>")

    assert payloads == []
    assert errors and "modDataValueZipList" in errors[0]


def test_render_markdown_lists_counts_and_opaque_mods() -> None:
    report = {
        "target": "Degrees of Lewdity.html",
        "html_sha256": "abc",
        "generated_at": "2026-10-07T00:00:00+00:00",
        "counts": {
            "static": 15627,
            "runtime_dom": 15663,
            "runtime_story": 15219,
            "runtime_only": 36,
            "playable": 4,
            "widget": 12,
            "unregistered": 20,
            "encrypted_mods": 1,
        },
        "mod_passages": [
            {"name": "Food Preference", "status": "playable", "source_mods": ["More Love Interests Mod"]}
        ],
        "opaque_mods": [
            {"name": "AU面部扩展", "version": "1.2.8", "encryption_markers": ["pack.zip.crypt"]}
        ],
        "errors": [],
    }

    md = mpi.render_markdown(report)

    assert "| 静态文件 passage | 15627 |" in md
    assert "| 运行时独有（mod 合并） | 36 |" in md
    assert "Food Preference" in md
    assert "AU面部扩展" in md
    assert "pack.zip.crypt" in md


def test_write_passage_list_handles_empty_and_named_lists(tmp_path) -> None:
    empty = mpi.write_passage_list(tmp_path / "empty.txt", [])
    named = mpi.write_passage_list(
        tmp_path / "nested" / "mods.txt", ["Food Preference", "CE_Wardrobe"]
    )

    # 空列表必须是 0 字节文件：CI 用 `test -s` 判定“没有可游玩 mod passage”
    assert empty.read_bytes() == b""
    assert named.read_text(encoding="utf-8") == "Food Preference\nCE_Wardrobe\n"
