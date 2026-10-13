"""Symbolic bounded playtrace reachability tests."""

import json

import pytest

from tools.static_reachability_solver import (
    DEFAULT_BOUND,
    SCHEMA,
    VERDICT_BOUNDED_NEGATIVE,
    VERDICT_INVALID,
    VERDICT_NO_SOLVER,
    VERDICT_REACHABLE,
    VERDICT_UNKNOWN_DYNAMIC,
    build_graph,
    build_report,
    encode,
    filter_executable_edges,
    main,
    non_executable_line_ranges,
)


clingo = pytest.importorskip(
    "clingo",
    reason="clingo is a declared release dependency for the symbolic solver",
)


def _index(passages, edges, *, root=None):
    return {
        "schema": "dolx.source-index.v1",
        "source_commit": "deadbeef",
        "root": root,
        "files": [],
        "passages": [{"name": name, "path": "story.twee", "line": 1} for name in passages],
        "symbols": [],
        "edges": edges,
        "variables": [],
        "stats": {},
    }


def _edge(source, target, *, path="story.twee", line=1, kind="wiki_link"):
    return {
        "kind": kind,
        "source": source,
        "target": target,
        "target_kind": "static",
        "path": path,
        "line": line,
    }


def _chain_index(length):
    passages = [f"P{index}" for index in range(length + 1)]
    edges = [_edge(f"P{index}", f"P{index + 1}") for index in range(length)]
    return _index(passages, edges)


@pytest.mark.config
def test_reachable_target_returns_a_concrete_witness():
    index = _index(
        ["Start", "Hall", "Kitchen"],
        [_edge("Start", "Hall"), _edge("Hall", "Kitchen")],
    )

    report = build_report(index, start="Start", targets=["Kitchen"])
    row = report["targets"][0]

    assert row["verdict"] == VERDICT_REACHABLE
    assert row["steps"] == 2
    assert [
        (hop["source"], hop["target"]) for hop in row["witness"]
    ] == [("Start", "Hall"), ("Hall", "Kitchen")]
    assert report["verdict"] == VERDICT_REACHABLE


@pytest.mark.config
def test_shortest_mode_finds_the_minimal_witness():
    index = _index(
        ["Start", "A", "B", "C", "Target"],
        [
            _edge("Start", "A"),
            _edge("A", "B"),
            _edge("B", "C"),
            _edge("C", "Target"),
            _edge("Start", "Target"),
        ],
    )

    report = build_report(
        index, start="Start", targets=["Target"], shortest=True
    )
    row = report["targets"][0]

    assert row["verdict"] == VERDICT_REACHABLE
    assert row["steps"] == 1
    assert [(hop["source"], hop["target"]) for hop in row["witness"]] == [
        ("Start", "Target")
    ]


@pytest.mark.config
def test_missing_target_is_a_bounded_result_never_plainly_unreachable():
    index = _chain_index(3)

    report = build_report(index, start="P0", targets=["NoSuchPassage"])
    row = report["targets"][0]

    assert row["verdict"] == VERDICT_BOUNDED_NEGATIVE
    assert row["verdict"] != "unreachable"
    assert row["bound_is_not_proof"] is True
    assert row["bound_exhausted"] is True
    assert row["witness"] is None
    assert "bound" in row["detail"]
    assert report["bound_is_not_proof"] is True


@pytest.mark.config
def test_bound_is_respected():
    index = _chain_index(10)

    report = build_report(index, start="P0", targets=["P10"], bound=5)
    row = report["targets"][0]

    assert row["verdict"] == VERDICT_BOUNDED_NEGATIVE
    assert row["bound"] == 5

    report = build_report(index, start="P0", targets=["P10"], bound=10)
    assert report["targets"][0]["verdict"] == VERDICT_REACHABLE
    assert report["targets"][0]["steps"] == 10


@pytest.mark.config
def test_default_bound_matches_the_plan(monkeypatch):
    monkeypatch.setattr("sys.argv", ["solver", "index.json"])
    from tools.static_reachability_solver import parse_args

    assert parse_args(["index.json"]).bound == DEFAULT_BOUND == 120


@pytest.mark.config
def test_missing_solver_is_reported_never_as_unreachable(monkeypatch):
    monkeypatch.setattr(
        "tools.static_reachability_solver._import_clingo",
        lambda: (None, "ModuleNotFoundError: No module named 'clingo'", ""),
    )
    index = _chain_index(2)

    report = build_report(index, start="P0", targets=["P2"])

    assert report["verdict"] == VERDICT_NO_SOLVER
    assert report["targets"][0]["verdict"] == VERDICT_NO_SOLVER
    assert report["targets"][0]["witness"] is None
    assert report["solver"]["available"] is False
    assert "clingo" in report["targets"][0]["error"]


@pytest.mark.config
def test_dynamic_edges_block_a_negative_but_not_a_witness():
    dynamic = {
        "kind": "engine_play",
        "source": "Start",
        "target": "secretTarget",
        "target_kind": "dynamic",
        "path": "story.twee",
        "line": 1,
    }
    index = _index(["Start", "Hall"], [_edge("Start", "Hall"), dynamic])

    report = build_report(index, start="Start", targets=["Nowhere"])
    assert report["targets"][0]["verdict"] == VERDICT_UNKNOWN_DYNAMIC
    assert report["verdict"] == VERDICT_UNKNOWN_DYNAMIC
    assert report["dynamic_edge_count"] == 1

    witness_report = build_report(index, start="Start", targets=["Hall"])
    assert witness_report["targets"][0]["verdict"] == VERDICT_REACHABLE
    assert witness_report["verdict"] == VERDICT_REACHABLE


@pytest.mark.config
def test_comment_and_false_conditional_edges_are_not_executable(tmp_path):
    source = tmp_path / "story.twee"
    source.write_text(
        ":: Start\n"
        "/* [[Hall]] */\n"
        "<<if false>>\n"
        "[[Kitchen]]\n"
        "<</if>>\n"
        "<!-- [[Cellar]] -->\n"
        "[[Garden]]\n",
        encoding="utf-8",
    )
    index = _index(
        ["Start", "Hall", "Kitchen", "Cellar", "Garden"],
        [
            _edge("Start", "Hall", line=2),
            _edge("Start", "Kitchen", line=4),
            _edge("Start", "Cellar", line=6),
            _edge("Start", "Garden", line=7),
        ],
        root=str(tmp_path),
    )

    graph = build_graph(index)
    traversable = {edge["target"] for edge in graph["edges"]}

    assert traversable == {"Garden"}
    assert {edge["target"] for edge in graph["non_executable"]} == {
        "Hall",
        "Kitchen",
        "Cellar",
    }
    assert {
        edge["non_executable"] for edge in graph["non_executable"]
    } == {"block_comment", "false_conditional", "html_comment"}
    # Reachability must not be manufactured from dead text.
    report = build_report(index, start="Start", targets=["Hall", "Kitchen", "Cellar"])
    assert all(
        row["verdict"] == VERDICT_BOUNDED_NEGATIVE for row in report["targets"]
    )


@pytest.mark.config
def test_non_executable_line_ranges_cover_all_three_forms():
    ranges = non_executable_line_ranges(
        "a\n/* x\ny */\nb\n<!-- z -->\n<<if 0>>\nq\n<</if>>\n"
    )
    labels = {label for _start, _end, label in ranges}

    assert labels == {"block_comment", "html_comment", "false_conditional"}


@pytest.mark.config
def test_inline_comment_does_not_kill_a_live_edge(tmp_path):
    source = tmp_path / "story.twee"
    source.write_text(
        ":: Start\n"
        "text /* inline */ [[Hall]]\n"
        "/* [[Ghost]] */\n"
        "[[Kitchen]]\n",
        encoding="utf-8",
    )
    index = _index(
        ["Start", "Hall", "Ghost", "Kitchen"],
        [
            _edge("Start", "Hall", line=2),
            _edge("Start", "Ghost", line=3),
            _edge("Start", "Kitchen", line=4),
        ],
        root=str(tmp_path),
    )

    graph = build_graph(index)

    assert {edge["target"] for edge in graph["edges"]} == {"Hall", "Kitchen"}
    assert [edge["target"] for edge in graph["non_executable"]] == ["Ghost"]


@pytest.mark.config
def test_dangling_targets_are_reported_and_never_traversed(tmp_path):
    index = _index(
        ["Start"],
        [_edge("Start", "Ghost")],
        root=str(tmp_path),
    )

    graph = build_graph(index)

    assert graph["edges"] == []
    assert [edge["target"] for edge in graph["dangling"]] == ["Ghost"]
    report = build_report(index, start="Start", targets=["Ghost"])
    assert report["targets"][0]["verdict"] == VERDICT_BOUNDED_NEGATIVE
    assert report["dangling_edge_count"] == 1


@pytest.mark.config
def test_report_carries_schema_identity_and_is_json_round_trippable(tmp_path):
    index = _chain_index(2)

    report = build_report(index, start="P0", targets=["P2"], bound=4)
    restored = json.loads(json.dumps(report))
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    assert restored["schema"] == SCHEMA == "dolx.symbolic_reachability.v1"
    assert restored["source_commit"] == "deadbeef"
    assert restored["bound"] == 4
    assert restored["solver"]["available"] is True
    assert restored["stats"]["passages"] == 3
    assert restored["stats"]["static_edges"] == 2


@pytest.mark.config
def test_encode_marks_the_target_self_loop_and_the_bound():
    program = encode(
        ["Start", "Target"],
        [_edge("Start", "Target")],
        start="Start",
        target="Target",
        bound=7,
    )

    assert "time(0..7)." in program
    assert "at(0,S) :- start(S)." in program
    assert 'edge("Target","Target").' in program
    assert "T < 7." in program
    assert ":- not ok." in program


@pytest.mark.config
def test_invalid_index_schema_is_rejected_by_the_cli(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")

    assert main([str(bad), "--out", str(tmp_path / "out")]) == 2


@pytest.mark.config
def test_filter_executable_edges_survives_a_missing_source_file(tmp_path):
    edges = [_edge("Start", "Hall", path="missing.twee", line=3)]

    executable, non_executable = filter_executable_edges(edges, root=tmp_path)

    assert len(executable) == 1
    assert non_executable == []
