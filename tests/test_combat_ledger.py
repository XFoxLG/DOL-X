"""``tools/combat_ledger.py``（战斗覆盖台账）的单元测试。

只覆盖纯逻辑，不依赖浏览器与 82MB 产物：
- basis -> derivation_kind 映射
- macro 调用点是否落在 ``<<widget>>`` 定义内
- 六种 entry shape 的分类
- JSON+MD 写出与 runtime report 关联（不凭空造判定）
- work list 排序/截断 与 ``--fail-on-unresolved`` 退出码
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest

from tools import combat_ledger
from tools.combat_ledger import (
    DERIVATION_KINDS,
    ENTRY_SHAPES,
    call_site,
    classify_row,
    derivation_kind,
    main,
    not_covered,
    render_markdown,
    summarise,
    work_list,
    write_outputs,
)


def _synthetic_html(passages: list[tuple[str, str]], *, escape: bool = True) -> str:
    body = []
    for name, text in passages:
        raw_name = html.escape(name, quote=True) if escape else name
        raw_text = html.escape(text, quote=False) if escape else text
        body.append(f'<tw-passagedata pid="1" name="{raw_name}">{raw_text}</tw-passagedata>')
    return "<html><body><tw-storydata>" + "".join(body) + "</tw-storydata></body></html>"


PASSAGES = [
    ("Courtyard Crush Fight", "<<maninit>>"),
    (
        "Test Sex",
        "<<if $sexstart is 1>><<consensual>><<maninit>><</if>><<actionsman>><<if _combatend>><</if>>",
    ),
    ("Widgets NPC Generation", '<<widget "generateDog">><<beastNEWinit 1 dog>><</widget>>'),
    ("Farmland Pigs", "<<beastNEWinit 1 pig>>\n[[Fight|Pig Fight]]"),
    ("Pig Fight", "<<beastCombatInit 1 pig>>"),
    ("Mystery Beast", "<<beastNEWinit>>"),
]


def _rows() -> list[dict]:
    from tools import combat_sweep as cs

    return [dict(row) for row in cs.scan_initiators(_synthetic_html(PASSAGES))["rows"]]


def _bodies() -> dict[str, str]:
    return {name: text for name, text in PASSAGES}


def test_derivation_kind_maps_every_basis_family() -> None:
    assert derivation_kind(None, None) == "not_needed"
    assert derivation_kind(None, "no beast token derivable") == "unresolved"
    assert (
        derivation_kind(None, "kind 'wraith' has no NPC hand/frontarm dependency")
        == "not_needed"
    )
    assert (
        derivation_kind("deep-predecessor:Far:body:depth2", None)
        == "deep_predecessor"
    )
    assert (
        derivation_kind("deep-predecessor:Parent:widget:callDog:depth1", None)
        == "deep_predecessor"
    )
    assert (
        derivation_kind("predecessor:Intro:slots2(person2)|link-body:Intro", None)
        == "upstream_predecessor"
    )
    assert (
        derivation_kind("debug-menu:generate1..2+person1..2(person2)", None)
        == "synthetic_generator"
    )
    assert derivation_kind("title-npc:Robin", None) == "named_npc"
    assert (
        derivation_kind("title-npc:Robin+generate2..4(person4)", None)
        == "named_npc_plus_generator"
    )
    assert derivation_kind("row-token:pig", None) == "beast_token"
    assert derivation_kind("row-token-nnpc:BlackWolf", None) == "named_beast_npc"
    assert derivation_kind("title-nnpc:Robin", None) == "named_beast_npc"
    assert derivation_kind("self-generation:farm_gen(pig)", None) == "self_generation"
    assert derivation_kind("something-new", None) == "other"
    # 每个分支都必须落在受审计的枚举里
    for basis in (
        None,
        "deep-predecessor:Far:body:depth2",
        "predecessor:X:depth1",
        "debug-menu:generate1+person1",
        "title-npc:A",
        "title-npc:A+generate2(person2)",
        "row-token:dog",
        "row-token-nnpc:A",
        "title-nnpc:A",
        "self-generation:farm_gen(pig)",
        "whatever",
    ):
        assert derivation_kind(basis, None) in DERIVATION_KINDS


def test_call_site_marks_macros_inside_widget_definitions() -> None:
    body = '<<widget "generateDog">><<beastNEWinit 1 dog>><</widget>>\n<<beastNEWinit 1 pig>>'
    widget_row = {"macro": "beastNEWinit", "args": "1 dog"}
    free_row = {"macro": "beastNEWinit", "args": "1 pig"}

    assert call_site(widget_row, body) == ("widget", "generateDog")
    assert call_site(free_row, body) == ("passage", None)


def test_classify_row_covers_all_six_entry_shapes() -> None:
    rows = {row["key"]: row for row in _rows()}
    bodies = _bodies()

    def classify(key: str) -> dict:
        return classify_row(
            rows[key], passage_bodies=bodies, widget_bodies={}, named_npcs=[]
        )

    maninit = classify("maninit:-:Courtyard Crush Fight")
    assert maninit["entry_shape"] == "entry"
    assert maninit["combat_starters"] == ["maninit"]
    assert maninit["derivation_kind"] == "synthetic_generator"
    assert maninit["precursor_widgets"]

    sexual = classify("maninit:-:Test Sex")
    assert sexual["entry_shape"] == "sexual_encounter"
    assert "consensual sexual encounter" in str(sexual["sexual_scene_reason"])

    widget = classify("beastNEWinit:dog:Widgets NPC Generation")
    assert widget["entry_shape"] == "widget_definition"
    assert widget["widget"] == "generateDog"

    linked = classify("beastNEWinit:pig:Farmland Pigs")
    assert linked["entry_shape"] == "entry_via_link"
    assert linked["link_target"] == "Pig Fight"
    assert linked["derivation_kind"] == "beast_token"

    mystery = classify("beastNEWinit:unknown:Mystery Beast")
    assert mystery["entry_shape"] == "unresolved"
    assert mystery["derivation_kind"] == "unresolved"
    assert "no beast token" in str(mystery["precursor_reason"])

    # 入口自带 starter 但 beast token 推不出来：shape 是 entry，derivation 如实记 unresolved
    starter = classify("beastCombatInit:pig:Pig Fight")
    assert starter["entry_shape"] == "entry"


def test_classify_row_helper_only_when_no_starter_or_link() -> None:
    row = {
        "key": "beastNEWinit:wolf:Backwoods",
        "kind": "beastNEWinit",
        "token": "wolf",
        "passage": "Backwoods",
        "macro": "beastNEWinit",
        "args": "1 wolf",
    }
    result = classify_row(
        row, passage_bodies={"Backwoods": "<<beastNEWinit 1 wolf>>"}, widget_bodies={}, named_npcs=[]
    )
    assert result["entry_shape"] == "helper_only"
    assert result["derivation_kind"] == "beast_token"


def test_classify_row_records_saved_npc_and_beasttype_evidence() -> None:
    body = (
        "<<set $enemyno to 1>>\n"
        "the <<beasttype>> fucks you\n"
        "<<beastCombatInit>>"
    )
    from tools import combat_sweep as cs

    row = dict(
        cs.scan_initiators(_synthetic_html([("Docks Watch Dog", body)]))["rows"][0]
    )
    assert row["key"] == "beastCombatInit:unknown:Docks Watch Dog"
    assert row["combat_starters"] == ["beastCombatInit"]
    # 上游在上一跳把 clone 存进 $dock_dog、再在这里还原，证据要跟着 link 前驱一起找
    parent_body = (
        "<<set $NPCList[0] to $dock_dog>>\n"
        "they watch as the <<beasttype>> fucks you\n"
        "[[Next|Docks Watch Dog]]"
    )
    result = classify_row(
        row,
        passage_bodies={"Docks Watch Dog": body, "Docks Watch": parent_body},
        widget_bodies={},
        named_npcs=[],
    )
    assert result["entry_shape"] == "entry"
    assert result["derivation_kind"] == "unresolved"
    assert result["saved_npc_refs"] == ["dock_dog"]
    assert result["saved_npc_sources"] == {"dock_dog": "Docks Watch"}
    assert result["uses_beasttype"] is True
    assert "no beast token" in str(result["precursor_reason"])


def test_not_covered_lists_only_unresolved_derivation() -> None:
    rows = [
        classify_row(row, passage_bodies=_bodies(), widget_bodies={}, named_npcs=[])
        for row in _rows()
    ]
    uncovered = not_covered(rows)
    assert [row["passage"] for row in uncovered] == ["Mystery Beast"]
    md = render_markdown(
        {
            "tool": "combat_ledger",
            "target": "t",
            "html_path": "h",
            "html_sha256": "0" * 64,
            "generated_at": "now",
            "drift": {"ok": True, "count": 0},
            "runtime_join": {"report": None},
            "summary": {
                "total": len(rows),
                "entry_shapes": {item: 0 for item in ENTRY_SHAPES},
                "derivation_kinds": {item: 0 for item in DERIVATION_KINDS},
                "work_total": 0,
                "not_covered_total": len(uncovered),
                "verdict_by_derivation": {},
            },
            "work_list": [],
            "not_covered": uncovered,
        }
    )
    assert "Not covered (no static derivation): 1" in md
    assert "`beastNEWinit:unknown:Mystery Beast`" in md


def test_candidate_precursors_are_hypotheses_with_provenance() -> None:
    from tools.combat_ledger import candidate_precursors

    bodies = {
        "Entry": "the <<beasttype>> mounts you\n<<beastCombatInit>>",
        "Parent": "a dog waits\n[[Next|Entry]]",
        "Grandparent": "<<beastNEWinit 1 dog>>\n[[Next|Parent]]",
    }
    candidates = candidate_precursors("Entry", passage_bodies=bodies, widget_bodies={})
    assert candidates[0]["token"] == "dog"
    assert candidates[0]["source"] == "Grandparent"
    assert candidates[0]["depth"] == 2
    assert candidates[0]["verified"] is False
    assert "beastNEWinit" in candidates[0]["widgets"]


def test_candidate_precursors_finds_beast_inside_called_widget() -> None:
    from tools.combat_ledger import candidate_precursors

    bodies = {
        "Entry": "<<beastCombatInit>>",
        "Parent": "<<callTheDog>>\n[[Next|Entry]]",
    }
    widgets = {"callTheDog": "<<beastNEWinit 1 wolf>>"}
    candidates = candidate_precursors("Entry", passage_bodies=bodies, widget_bodies=widgets)
    assert candidates[0]["token"] == "wolf"
    assert candidates[0]["via"] == "widget:callTheDog"


def test_candidate_precursors_respects_limit() -> None:
    from tools.combat_ledger import candidate_precursors

    bodies = {"Entry": "<<beastCombatInit>>"}
    for index in range(6):
        bodies[f"Parent{index}"] = f"<<beastNEWinit 1 dog>>\n[[Next|Entry]]"
    candidates = candidate_precursors(
        "Entry", passage_bodies=bodies, widget_bodies={}, limit=2
    )
    assert len(candidates) == 2
    assert all(item["verified"] is False for item in candidates)


def test_deep_derivations_split_from_not_covered_and_render() -> None:
    from tools import combat_sweep as cs
    from tools.combat_ledger import deep_derivations

    bodies = {
        "Entry": "<<beastCombatInit>>",
        "Near": "[[Next|Entry]]",
        "Mid": "[[Next|Near]]",
        "Far": "<<beastNEWinit 1 dog>>\n[[Next|Mid]]",
    }
    row = dict(
        cs.scan_initiators(_synthetic_html([("Entry", "<<beastCombatInit>>")]))["rows"][0]
    )
    classified = [
        classify_row(row, passage_bodies=bodies, widget_bodies={}, named_npcs=[])
    ]

    assert classified[0]["derivation_kind"] == "deep_predecessor"
    assert classified[0]["precursor_basis"].startswith("deep-predecessor:Far:body:depth3")
    assert classified[0]["candidate_precursors"]
    # 深度推导有依据，不再算“未覆盖”；它单独进低置信清单
    assert not_covered(classified) == []
    assert [item["key"] for item in deep_derivations(classified)] == [row["key"]]

    md = render_markdown(
        {
            "tool": "combat_ledger",
            "target": "t",
            "html_path": "h",
            "html_sha256": "0" * 64,
            "generated_at": "now",
            "drift": {"ok": True, "count": 0},
            "runtime_join": {"report": None},
            "summary": {
                "total": 1,
                "entry_shapes": {item: 0 for item in ENTRY_SHAPES},
                "derivation_kinds": {item: 0 for item in DERIVATION_KINDS},
                "work_total": 0,
                "not_covered_total": 0,
                "deep_total": 1,
                "verdict_by_derivation": {},
            },
            "work_list": [],
            "not_covered": [],
            "deep_derivations": deep_derivations(classified),
        }
    )
    assert "Deep (low-confidence) derivations: 1" in md
    assert "deep-predecessor:Far:body:depth3" in md
    assert "`dog` @ `Far`(d3/body)" in md


def test_summarise_and_work_list_order_stable() -> None:
    rows = [
        classify_row(
            row, passage_bodies=_bodies(), widget_bodies={}, named_npcs=[]
        )
        for row in _rows()
    ]
    summary = summarise(rows)
    assert summary["total"] == len(rows)
    assert set(summary["entry_shapes"]) == set(ENTRY_SHAPES)
    assert summary["entry_shapes"]["entry"] >= 2
    assert summary["entry_shapes"]["widget_definition"] == 1
    assert summary["entry_shapes"]["unresolved"] == 1

    todo = work_list(rows, limit=100)
    keys = [(row["derivation_kind"], row["passage"]) for row in todo]
    assert keys == sorted(keys)
    assert any(row["passage"] == "Mystery Beast" for row in todo)
    # maninit 入口仍用合成 generate1+person1 链，属于要补齐前驱的一类
    maninit_todo = next(row for row in todo if row["passage"] == "Courtyard Crush Fight")
    assert maninit_todo["derivation_kind"] == "synthetic_generator"


def test_join_report_never_invents_verdicts(tmp_path: Path) -> None:
    target = tmp_path / "game.html"
    target.write_text(_synthetic_html(PASSAGES), encoding="utf-8")
    report = tmp_path / "combat-sweep.json"
    report.write_text(
        json.dumps(
            {
                "target": str(target),
                "tier": "initiators",
                "started_at": "2026-10-07T00:00:00",
                "finished_at": "2026-10-07T00:10:00",
                "verdict_counts": {"ok": 1},
                "results": [
                    {
                        "key": "maninit:-:Courtyard Crush Fight",
                        "verdict": "ok",
                        "detail": "enemy arousal reached max",
                        "combat": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    ledger = combat_ledger.build_ledger(target, report_path=report)

    joined = ledger["runtime_join"]
    assert joined["joined"] == 1
    assert joined["unknown"] == ledger["summary"]["total"] - 1
    by_key = {row["key"]: row for row in ledger["rows"]}
    assert by_key["maninit:-:Courtyard Crush Fight"]["runtime"]["verdict"] == "ok"
    assert by_key["beastNEWinit:unknown:Mystery Beast"]["runtime"] is None
    md = render_markdown(ledger)
    assert "Runtime join" in md
    assert "`synthetic_generator`" in md


def test_write_outputs_and_fail_on_unresolved(tmp_path: Path) -> None:
    target = tmp_path / "game.html"
    target.write_text(_synthetic_html(PASSAGES), encoding="utf-8")
    out = tmp_path / "ledger"
    rc = main([str(target), "--out", str(out), "--fail-on-unresolved"])
    assert rc == 1
    assert (out / "combat-ledger.json").exists()
    assert (out / "combat-ledger.md").exists()
    payload = json.loads((out / "combat-ledger.json").read_text(encoding="utf-8"))
    assert payload["tool"] == "combat_ledger"
    assert payload["summary"]["total"] == len(_rows())
    assert payload["rows"][0]["call_site"] in ("passage", "widget")

    clean = tmp_path / "clean.html"
    clean.write_text(
        _synthetic_html([("Courtyard Crush Fight", "<<maninit>>")]), encoding="utf-8"
    )
    clean_out = tmp_path / "ledger-clean"
    assert main([str(clean), "--out", str(clean_out), "--fail-on-unresolved"]) == 0
    assert (clean_out / "combat-ledger.md").exists()


def test_main_rejects_missing_target(tmp_path: Path) -> None:
    assert main([str(tmp_path / "nope.html")]) == 2


def test_write_outputs_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "game.html"
    target.write_text(_synthetic_html(PASSAGES), encoding="utf-8")
    ledger = combat_ledger.build_ledger(target)
    first = write_outputs(ledger, tmp_path / "out")
    second = write_outputs(ledger, tmp_path / "out")
    assert first == second
    assert first[0].exists() and first[1].exists()


@pytest.mark.parametrize("shape", ENTRY_SHAPES)
def test_entry_shapes_are_renderable(shape: str) -> None:
    assert shape in render_markdown(
        {
            "tool": "combat_ledger",
            "target": "t",
            "html_path": "h",
            "html_sha256": "0" * 64,
            "generated_at": "now",
            "drift": {"ok": True, "count": 0},
            "runtime_join": {"report": None},
            "summary": {
                "total": 0,
                "entry_shapes": {item: 0 for item in ENTRY_SHAPES},
                "derivation_kinds": {item: 0 for item in DERIVATION_KINDS},
                "work_total": 0,
                "verdict_by_derivation": {},
            },
            "work_list": [],
        }
    )
