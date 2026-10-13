"""Pure tests for the conservative SugarCube source index."""

from __future__ import annotations

from pathlib import Path

from tools.source_index import build_index, scan_text


def test_scan_twee_passages_links_conditions_and_variables() -> None:
    source = (
        ":: Start\n"
        "<<set $money to 10>>\n"
        "<<if $money > 0>>\n"
        "<<link [[Go|Bedroom]]>><</link>>\n"
        "<<else>>Nope<</if>>\n"
        ":: Bedroom\n"
        "<<goto 'Sleep'>>\n"
    )
    result = scan_text("game/start.twee", source, owner="vanilla")
    assert [row["name"] for row in result.passages] == ["Start", "Bedroom"]
    targets = {row["target"] for row in result.edges if row["target"]}
    assert {"Bedroom", "Sleep"}.issubset(targets)
    assert any(row["kind"] == "condition" for row in result.symbols)
    assert any(row["name"] == "$money" and row["kind"] == "write" for row in result.variables)
    assert any(row["name"] == "$money" and row["kind"] == "read" for row in result.variables)


def test_scan_dynamic_engine_play_is_retained_as_dynamic_edge() -> None:
    result = scan_text("game/main.js", "SugarCube.Engine.play(nextPassage);\nConfig.navigation.override = fn;\n")
    dynamic = [row for row in result.edges if row["target_kind"] == "dynamic"]
    assert len(dynamic) == 2
    assert {row["kind"] for row in dynamic} == {"engine_play", "navigation_override"}


def test_dynamic_wiki_target_is_not_marked_static() -> None:
    result = scan_text("game/start.twee", ":: Start\n[[$nextPassage]]\n")
    edge = next(row for row in result.edges if row["kind"] == "wiki_link")
    assert edge["target_kind"] == "dynamic"


def test_build_index_is_deterministic_and_records_stats(tmp_path: Path) -> None:
    (tmp_path / "a.twee").write_text(":: A\n[[B]]\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("Engine.play('A');\n", encoding="utf-8")
    first = build_index(tmp_path, source_commit="abc")
    second = build_index(tmp_path, source_commit="abc")
    assert first == second
    assert first["source_commit"] == "abc"
    assert first["stats"]["passages"] == 1
    assert first["stats"]["dynamic_edges"] == 0


def test_html_passage_name_with_apostrophe_is_not_truncated() -> None:
    source = (
        "<tw-passagedata pid=\"1\" name=\"Men's Toilets\" tags=\"nosave\">"
        "<<link [[Next|Men]]>><</link>>"
        "</tw-passagedata>"
        "<tw-passagedata pid=\"2\" name='Single Quoted'>"
        "text"
        "</tw-passagedata>"
    )
    result = scan_text("game/game.html", source)
    assert [row["name"] for row in result.passages] == ["Men's Toilets", "Single Quoted"]
    edges = [row for row in result.edges if row["source"] == "Men's Toilets"]
    assert edges and edges[0]["target"] == "Men"


def test_link_arrow_syntax_and_expression_targets() -> None:
    source = (
        ":: Start\n"
        "[[Next->Bedroom]]\n"
        "[[Next->_comingFromLink]]\n"
        '[["Robin Cinema " + _theatreLink]]\n'
    )
    result = scan_text("game/start.twee", source)
    by_expression = {
        row["expression"]: row for row in result.edges if row["kind"] == "wiki_link"
    }
    arrow = by_expression["Next->Bedroom"]
    assert arrow["target"] == "Bedroom"
    assert arrow["target_kind"] == "static"
    temp = by_expression["Next->_comingFromLink"]
    assert temp["target"] == "_comingFromLink"
    assert temp["target_kind"] == "dynamic"
    expression = by_expression['"Robin Cinema " + _theatreLink']
    assert expression["target_kind"] == "dynamic"


def test_template_and_temporary_variable_targets_are_dynamic() -> None:
    source = (
        ":: Start\n"
        "<<button `'Save (' + _page + ')'`>>X<</button>>\n"
        "<<link \"DEBUG: <<=($opt ? 'A' : 'B')>> Code\">>X<</link>>\n"
        "[[Leave|_container.leaveLink]]\n"
    )
    result = scan_text("game/start.twee", source)
    assert result.edges
    assert all(row["target_kind"] == "dynamic" for row in result.edges)


def test_include_target_with_apostrophe_is_complete() -> None:
    source = ":: A\n<<include \"Doctor Harper's Office Intro\">>\n"
    result = scan_text("game/a.twee", source)
    edge = next(
        row for row in result.edges if row["kind"] == "macro" and row["macro"] == "include"
    )
    assert edge["target"] == "Doctor Harper's Office Intro"
    assert edge["target_kind"] == "static"


def test_concatenated_include_target_is_dynamic() -> None:
    source = (
        ":: A\n"
        '<<include "Asylum Hypnosis " + $phase>>\n'
        '<<include "Static Room">>\n'
    )
    result = scan_text("game/a.twee", source)
    includes = [row for row in result.edges if row.get("macro") == "include"]
    concatenated = next(row for row in includes if "$phase" in str(row.get("expression") or ""))
    static = next(row for row in includes if row.get("target") == "Static Room")

    assert concatenated["target_kind"] == "dynamic"
    assert not any(row.get("target") == "Asylum Hypnosis" for row in result.edges)
    assert static["target_kind"] == "static"
