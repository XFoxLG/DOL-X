"""Pure tests for the networkx story-graph integrity audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.story_graph_audit import AuditError, audit, load_accepted, main


def _index(passages: list[str], edges: list[dict]) -> dict:
    return {
        "schema": "dolx.source-index.v1",
        "source_commit": "a" * 40,
        "root": "game.html",
        "passages": [
            {"name": name, "path": "game.html", "line": 1, "owner": None} for name in passages
        ],
        "edges": edges,
        "stats": {"passages": len(passages), "edges": len(edges)},
    }


def _edge(source: str, target: str | None, kind: str = "static", line: int = 1) -> dict:
    return {
        "kind": "macro",
        "macro": "link",
        "source": source,
        "target": target,
        "target_kind": kind,
        "expression": f"[[{target}]]",
        "path": "game.html",
        "line": line,
        "owner": None,
    }


def _html(tmp_path: Path, bodies: dict[str, str]) -> Path:
    parts = []
    for position, (name, body) in enumerate(bodies.items(), 1):
        parts.append(f'<tw-passagedata pid="{position}" name="{name}">{body}</tw-passagedata>')
    path = tmp_path / "game.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def _accepted(category: str, key: str) -> dict:
    return {
        "category": category,
        "reason": "vanilla shows the same defect",
        "evidence": ["docs/PROOF.md:1"],
        **({"passage": key} if category != "undefined_target" else {"target": key}),
    }


def test_sealed_dead_end_and_accepted_matching(tmp_path: Path) -> None:
    index = _index(["Start", "B"], [_edge("Start", "B")])
    html = _html(tmp_path, {"Start": "", "B": "no exits here"})
    report = audit(
        index,
        source_index_sha256="0" * 64,
        html_path=html,
        accepted=[_accepted("dead_end", "B")],
    )
    dead = {row["passage"]: row for row in report["dead_ends"]}
    assert dead["B"]["class"] == "sealed"
    assert dead["B"]["status"] == "accepted"
    assert report["blocking"]["unclassified_dead_ends"] == []


def test_dangling_exit_and_undefined_target(tmp_path: Path) -> None:
    index = _index(["Start", "D"], [_edge("Start", "D"), _edge("D", "Missing", line=9)])
    html = _html(tmp_path, {"Start": "", "D": "text"})
    report = audit(index, source_index_sha256="0" * 64, html_path=html)
    dead = {row["passage"]: row for row in report["dead_ends"]}
    assert dead["D"]["class"] == "dangling_exit"
    assert dead["D"]["status"] == "unclassified"
    targets = {row["target"]: row for row in report["undefined_targets"]}
    assert targets["Missing"]["source_passages"] == ["D"]
    assert report["blocking"]["unclassified_undefined_targets"] == ["Missing"]


def test_navigation_macro_and_widget_exemption(tmp_path: Path) -> None:
    index = _index(
        ["Start", "MacroExit", "WidgetExit", "StateExit", "Widgets"],
        [
            _edge("Start", "MacroExit"),
            _edge("Start", "WidgetExit"),
            _edge("Start", "StateExit"),
            _edge("Start", "Widgets"),
        ],
    )
    html = _html(
        tmp_path,
        {
            "Start": "",
            "MacroExit": "<<pass>>",
            "WidgetExit": "<<travelquick>>",
            "StateExit": "<<endcombat>>",
            "Widgets": (
                '<<widget "travelquick">><<goto "Start">><</widget>>'
                '<<widget "endcombat">><<goto "Start">><</widget>>'
            ),
        },
    )
    report = audit(index, source_index_sha256="0" * 64, html_path=html)
    classes = report["counts"]["dead_end_exit_classes"]
    assert classes.get("navigation_macro_exit") == 1
    assert classes.get("widget_exit") == 1
    # endcombat is a state widget: it is classified but never masks a defect.
    assert classes.get("state_widget_exit") == 1
    assert classes.get("widget_definition") == 1
    assert report["blocking"]["unclassified_dead_ends"] == []


def test_dynamic_edge_exempts_candidate(tmp_path: Path) -> None:
    index = _index(
        ["Start", "H"],
        [_edge("Start", "H"), _edge("H", None, kind="dynamic")],
    )
    html = _html(tmp_path, {"Start": "", "H": "text"})
    report = audit(index, source_index_sha256="0" * 64, html_path=html)
    assert all(row["passage"] != "H" for row in report["dead_ends"])


def test_hyphenated_and_chained_navigation_widgets(tmp_path: Path) -> None:
    index = _index(
        ["Start", "HyphenShop", "Chained"],
        [_edge("Start", "HyphenShop"), _edge("Start", "Chained")],
    )
    html = _html(
        tmp_path,
        {
            "Start": "",
            "HyphenShop": "<<stallShop-main>>",
            "Chained": "<<outerEnd>>",
            "Widgets": (
                '<<widget "stallShop-main">>text<<goto "Start">><</widget>>'
                '<<widget "outerEnd">><<innerEnd>><</widget>>'
                '<<widget "innerEnd">><<goto "Start">><</widget>>'
            ),
        },
    )
    report = audit(index, source_index_sha256="0" * 64, html_path=html)

    assert report["blocking"]["unclassified_dead_ends"] == []
    assert report["counts"]["dead_end_exit_classes"].get("widget_exit") == 2


def test_accepted_entry_requires_reason_and_evidence(tmp_path: Path) -> None:
    path = tmp_path / "accepted.toml"
    path.write_text(
        'schema = "dolx.accepted-graph-defects.v1"\n'
        "[[accepted]]\n"
        'category = "dead_end"\n'
        'passage = "B"\n'
        'reason = ""\n'
        'evidence = []\n',
        encoding="utf-8",
    )
    with pytest.raises(AuditError):
        load_accepted(path)


def test_index_only_mode_flags_unclassified(tmp_path: Path) -> None:
    index = _index(["Start", "B"], [_edge("Start", "B")])
    report = audit(index, source_index_sha256="0" * 64)
    assert report["mode"] == "index_only"
    assert report["blocking"]["html_provided"] is False
    assert report["blocking"]["unclassified_dead_ends"] == ["B"]


def test_invalid_schema_exit_code(tmp_path: Path) -> None:
    bad = tmp_path / "index.json"
    bad.write_text(json.dumps({"schema": "not-dolx"}), encoding="utf-8")
    assert main([str(bad), "--out", str(tmp_path / "out")]) == 2


def test_self_loop_and_inbound_counts(tmp_path: Path) -> None:
    index = _index(
        ["Start", "Loop", "Orphan"],
        [_edge("Start", "Loop"), _edge("Loop", "Loop")],
    )
    html = _html(tmp_path, {"Start": "", "Loop": "", "Orphan": ""})
    report = audit(index, source_index_sha256="0" * 64, html_path=html)
    assert report["counts"]["self_loops"] == 1
    assert "Orphan" in [row["passage"] for row in report["defined_without_inbound"]["samples"]]
    assert report["counts"]["statically_reachable_from_entry"] == 2


def test_near_match_hints(tmp_path: Path) -> None:
    index = _index(
        ["Start", "High Exposed", "Forest Trunk Run", "Src"],
        [
            _edge("Start", "Src"),
            _edge("Src", "high Exposed", line=3),
            _edge("Src", "Forest Trunks Run", line=4),
        ],
    )
    html = _html(tmp_path, {"Start": "", "Src": "", "High Exposed": "", "Forest Trunk Run": ""})
    report = audit(index, source_index_sha256="0" * 64, html_path=html)
    hints = {row["target"]: row["near_match_hint"] for row in report["undefined_targets"]}
    assert hints["high Exposed"] == "case_mismatch:High Exposed"
    assert hints["Forest Trunks Run"] == "near_match:Forest Trunk Run"


def _index_with_root(root: str, passages: list[str], edges: list[dict]) -> dict:
    index = _index(passages, edges)
    index["root"] = root
    return index


def test_block_comment_edges_are_removed_from_graph(tmp_path: Path) -> None:
    html = tmp_path / "game.html"
    html.write_text(
        '<tw-passagedata pid="1" name="Start"></tw-passagedata>'
        '<tw-passagedata pid="2" name="Src">text\n'
        "/*\n"
        '<<link "Missing">>\n'
        "*/\n"
        "</tw-passagedata>",
        encoding="utf-8",
    )
    index = _index_with_root(
        str(html),
        ["Start", "Src"],
        [_edge("Start", "Src"), _edge("Src", "Missing", line=3)],
    )
    report = audit(index, source_index_sha256="0" * 64, html_path=html)

    assert report["undefined_targets"] == []
    assert report["counts"]["non_executable_edges"] == 1
    sample = report["non_executable_edges"]["samples"][0]
    assert sample["target"] == "Missing"
    assert sample["non_executable"] == "block_comment"


def test_false_conditional_edges_are_removed_from_graph(tmp_path: Path) -> None:
    html = tmp_path / "game.html"
    html.write_text(
        '<tw-passagedata pid="1" name="Start"></tw-passagedata>'
        '<tw-passagedata pid="2" name="Src">a\n'
        "<<if false>>\n"
        '<<link "Ghost">>\n'
        "<</if>>\n"
        "b</tw-passagedata>",
        encoding="utf-8",
    )
    index = _index_with_root(
        str(html),
        ["Start", "Src"],
        [_edge("Start", "Src"), _edge("Src", "Ghost", line=3)],
    )
    report = audit(index, source_index_sha256="0" * 64, html_path=html)

    assert report["undefined_targets"] == []
    assert report["counts"]["non_executable_edges"] == 1
    assert report["non_executable_edges"]["samples"][0]["non_executable"] == (
        "false_conditional"
    )
