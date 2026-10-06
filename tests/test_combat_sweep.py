"""tools/combat_sweep.py（战斗轴扫描）的单元测试。

这些测试刻意不依赖浏览器、网络与 82MB 产物，只覆盖纯逻辑：
- initiator 静态扫描（合成小 HTML、实体转义、按 passage 去重、总数/分类/兽类 token）
- archetype 矩阵构造（28 规格 × 4 路径、入口选择偏好、limit/sample）
- 路径偏好选择（赢/输/逃/屈服关键词、无匹配 fallback）
- 卡死判定（连续 3 回合状态摘要无变化）与终局判定
- fixture_insufficient 错误分类（合成 is not defined / Cannot read properties）
- initiator 选取（resume 跳过 / limit / sample）
- JSON+MD 报告写出、基线 diff、CLI 默认值
"""

from __future__ import annotations

import dataclasses
import html
import json
from pathlib import Path

import pytest

from tools import combat_sweep
from tools.combat_sweep import (
    ARCHETYPE_PATHS,
    ARCHETYPE_SPECS,
    CONTROL_MODES,
    COMBAT_STATE_JS,
    DEFAULT_FIXTURE,
    DEFAULT_MANIFEST_OUT,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_MODE_ROUNDS,
    ENTRY_FLAGS,
    INITIATOR_MACROS,
    PATH_KEYWORDS,
    begin_turn,
    build_archetype_jobs,
    choose_action,
    choose_entry,
    classify_entry_errors,
    classify_no_actions,
    classify_outcome,
    detect_stall,
    diff_against_baseline,
    find_combat_link_target,
    initiator_key,
    parse_args,
    parse_beast_token,
    pick_mode_entry,
    round_digest,
    scan_initiators,
    select_initiator_rows,
    spec_matches,
    _press_turn,
    write_report,
)


# --------------------------------------------------------------------------- #
# Static initiator scan
# --------------------------------------------------------------------------- #


def _synthetic_html(passages: list[tuple[str, str]], *, escape: bool = True) -> str:
    body = []
    for name, text in passages:
        raw_name = html.escape(name, quote=True) if escape else name
        raw_text = html.escape(text, quote=False) if escape else text
        body.append(f'<tw-passagedata pid="1" name="{raw_name}">{raw_text}</tw-passagedata>')
    return "<html><body><tw-storydata>" + "".join(body) + "</tw-storydata></body></html>"


def test_scan_initiators_extracts_kind_token_and_passage() -> None:
    doc = _synthetic_html(
        [
            ("Dog Park", "<<if $molestationstart is 1>><<beastNEWinit 1 dog>><<beastCombatInit>><</if>>"),
            ("Tutorial", "<<maninit>>"),
            ("Forest Tentacles", "<<tentaclestart 3 300>>"),
        ]
    )

    manifest = scan_initiators(doc)

    rows = {(row["kind"], row["token"], row["passage"]) for row in manifest["rows"]}
    assert ("beastNEWinit", "dog", "Dog Park") in rows
    assert ("beastCombatInit", "dog", "Dog Park") in rows
    assert ("maninit", "", "Tutorial") in rows
    assert ("tentacle", "", "Forest Tentacles") in rows
    assert manifest["total"] == 4
    assert manifest["by_kind"]["beastNEWinit"] == 1
    assert manifest["by_kind"]["maninit"] == 1
    assert manifest["by_kind"]["tentacle"] == 1
    assert manifest["by_token"]["dog"] == 2
    assert manifest["passages"] == 3
    assert manifest["ok"] is True

    dog_row = next(row for row in manifest["rows"] if row["kind"] == "beastNEWinit")
    assert dog_row["key"] == "beastNEWinit:dog:Dog Park"
    assert dog_row["entry_flags"] == ["molestationstart"]
    assert "beastCombatInit" in dog_row["combat_starters"]


def test_scan_initiators_dedupes_by_kind_token_passage() -> None:
    doc = _synthetic_html(
        [
            ("A", "<<maninit>><<maninit>>"),
            ("B", "<<maninit>>"),
            ("C", "<<beastNEWinit 1 dog>><<beastNEWinit 2 dog>>"),
        ],
        escape=False,
    )

    manifest = scan_initiators(doc)

    keys = [row["key"] for row in manifest["rows"]]
    assert keys == ["maninit:-:A", "maninit:-:B", "beastNEWinit:dog:C"]
    assert manifest["total"] == 3
    assert manifest["by_kind"]["maninit"] == 2
    assert manifest["by_token"]["dog"] == 1


def test_scan_initiators_reports_drift_against_ground_truth() -> None:
    doc = _synthetic_html([("A", "<<maninit>>")])

    manifest = scan_initiators(doc)

    drift = manifest["drift"]
    assert drift["ok"] is False
    assert drift["count"] > 0
    assert drift["differences"][0]["field"] == "total"
    assert manifest["expected"]["total"] > manifest["total"]


def test_scan_initiators_ignores_helper_macros() -> None:
    doc = _synthetic_html(
        [("A", "<<statetentacles>><<actionstentacles>><<hypnosisText 'x'>>")]
    )

    manifest = scan_initiators(doc)

    assert manifest["total"] == 0
    assert manifest["by_token"] == {}


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("1 dog m", "dog"),
        ("2 wolf f", "wolf"),
        ("1 horse f penis monster", "horse"),
        ("", "unknown"),
        ("`$NPCList.countWith(a = 1)", "dynamic"),
    ],
)
def test_parse_beast_token(args: str, expected: str) -> None:
    assert parse_beast_token(args) == expected


def test_initiator_key_shape() -> None:
    assert initiator_key("maninit", "", "Tutorial") == "maninit:-:Tutorial"
    assert initiator_key("beastNEWinit", "dog", "Dog Park") == "beastNEWinit:dog:Dog Park"


# --------------------------------------------------------------------------- #
# Archetype matrix
# --------------------------------------------------------------------------- #


def _synthetic_rows() -> list[dict]:
    rows: list[dict] = []
    for spec in ARCHETYPE_SPECS:
        if spec.passage_keywords:
            passage = f"{spec.passage_keywords[0]} Confrontation"
        elif spec.token:
            passage = f"{spec.key} scene"
        else:
            passage = f"{spec.key} scene"
        rows.append(
            {
                "key": initiator_key(spec.kind, spec.token or "", passage),
                "kind": spec.kind,
                "token": spec.token or "",
                "passage": passage,
                "macro": spec.kind,
                "args": "",
                "entry_flags": ["molestationstart"],
                "combat_starters": ["maninit", "beastCombatInit"],
            }
        )
    return rows


def test_archetype_specs_cover_the_plan() -> None:
    keys = [spec.key for spec in ARCHETYPE_SPECS]
    assert len(keys) == len(set(keys))
    assert 25 <= len(ARCHETYPE_SPECS) <= 30
    beasts = {spec.token for spec in ARCHETYPE_SPECS if spec.category == "beast"}
    assert beasts == {
        "dog", "wolf", "horse", "pig", "cat", "fox", "lizard", "hawk",
        "cow", "bear", "spider", "boar", "dolphin", "snake",
    }
    specials = {spec.kind for spec in ARCHETYPE_SPECS if spec.category == "special"}
    assert specials == {
        "tentacle", "swarm", "wraith", "stalk", "vore", "machine",
        "possession", "plant", "hypno",
    }
    assert any(spec.kind == "maninit" for spec in ARCHETYPE_SPECS if spec.category == "human")
    assert sum(1 for spec in ARCHETYPE_SPECS if spec.category == "named") == 4
    assert ARCHETYPE_PATHS == ("win", "lose", "flee", "submit")
    assert set(INITIATOR_MACROS) == {
        "maninit", "beastNEWinit", "beastCombatInit", "tentacle", "hypno",
        "wraith", "machine", "swarm", "stalk", "plant", "vore", "possession",
    }


def test_build_archetype_jobs_expands_every_path() -> None:
    matrix = build_archetype_jobs(_synthetic_rows())

    assert matrix["unresolved"] == []
    assert matrix["archetypes"] == len(ARCHETYPE_SPECS)
    assert len(matrix["jobs"]) == len(ARCHETYPE_SPECS) * len(ARCHETYPE_PATHS)
    paths = {job["path"] for job in matrix["jobs"]}
    assert paths == set(ARCHETYPE_PATHS)
    keys = [job["key"] for job in matrix["jobs"]]
    assert len(keys) == len(set(keys))
    dog_jobs = [job for job in matrix["jobs"] if job["archetype"] == "beast-dog"]
    assert len(dog_jobs) == 4
    assert all(job["kind"] == "beastNEWinit" and job["token"] == "dog" for job in dog_jobs)


def test_build_archetype_jobs_records_unresolved_specs() -> None:
    rows = [row for row in _synthetic_rows() if row["token"] != "dog"]

    matrix = build_archetype_jobs(rows)

    assert {"archetype": "beast-dog", "reason": "no static initiator row"} in matrix["unresolved"]
    assert len(matrix["jobs"]) == (len(ARCHETYPE_SPECS) - 1) * len(ARCHETYPE_PATHS)


def test_build_archetype_jobs_limit_and_sample_act_on_archetypes() -> None:
    rows = _synthetic_rows()

    limited = build_archetype_jobs(rows, limit=2)
    assert limited["archetypes"] == 2
    assert len(limited["jobs"]) == 8

    first = build_archetype_jobs(rows, sample=5, seed=7)
    second = build_archetype_jobs(rows, sample=5, seed=7)
    other = build_archetype_jobs(rows, sample=5, seed=8)
    assert first["archetypes"] == 5
    assert [job["archetype"] for job in first["jobs"]][::4] == [job["archetype"] for job in second["jobs"]][::4]
    assert [job["archetype"] for job in first["jobs"]][::4] != [job["archetype"] for job in other["jobs"]][::4]


def test_choose_entry_prefers_passages_with_combat_starters() -> None:
    spec = next(spec for spec in ARCHETYPE_SPECS if spec.key == "beast-dog")
    bare = {
        "key": "beastNEWinit:dog:aaa",
        "kind": "beastNEWinit",
        "token": "dog",
        "passage": "aaa",
        "entry_flags": [],
        "combat_starters": [],
    }
    armed = {
        "key": "beastNEWinit:dog:zzz",
        "kind": "beastNEWinit",
        "token": "dog",
        "passage": "zzz",
        "entry_flags": ["molestationstart"],
        "combat_starters": ["beastCombatInit"],
    }

    assert choose_entry([bare, armed], spec)["passage"] == "zzz"
    assert choose_entry([bare], spec)["passage"] == "aaa"
    assert choose_entry([], spec) is None


def test_choose_entry_deprioritizes_widget_library_passages() -> None:
    """``Widgets *`` passages carry many initiators but never start combat."""
    spec = next(spec for spec in ARCHETYPE_SPECS if spec.key == "human-street")
    library = {
        "key": "maninit:-:Widgets Wraith",
        "kind": "maninit",
        "token": "",
        "passage": "Widgets Wraith",
        "entry_flags": [],
        "combat_starters": ["maninit", "machine_init", "swarminit", "initWraith"],
    }
    real = {
        "key": "maninit:-:Alleyways Capture Rape",
        "kind": "maninit",
        "token": "",
        "passage": "Alleyways Capture Rape",
        "entry_flags": ["molestationstart"],
        "combat_starters": ["maninit"],
    }

    assert choose_entry([library, real], spec)["passage"] == "Alleyways Capture Rape"
    assert choose_entry([library], spec)["passage"] == "Widgets Wraith"


def test_spec_matches_requires_keywords_for_named_npcs() -> None:
    spec = next(spec for spec in ARCHETYPE_SPECS if spec.key == "named-bailey")
    hit = {"kind": "maninit", "token": "", "passage": "Bailey Punishment"}
    miss = {"kind": "maninit", "token": "", "passage": "Whitney Bully"}

    assert spec_matches(hit, spec) is True
    assert spec_matches(miss, spec) is False


def test_pick_mode_entry_prefers_beast_combat_init() -> None:
    jobs = [
        {"key": "a", "kind": "maninit", "path": "lose"},
        {"key": "b", "kind": "beastCombatInit", "path": "win"},
        {"key": "c", "kind": "maninit", "path": "win"},
    ]

    assert pick_mode_entry(jobs)["key"] == "b"
    assert pick_mode_entry([]) is None


def test_pick_mode_entry_prefers_beast_over_maninit() -> None:
    jobs = [
        {"key": "a", "kind": "maninit", "path": "win"},
        {"key": "b", "kind": "beastNEWinit", "path": "win"},
    ]

    assert pick_mode_entry(jobs)["key"] == "b"


def test_find_combat_link_target_follows_first_starter_link() -> None:
    bodies = {
        "Source": '<<beastNEWinit 1 pig>>\n[[Next|Fight Start]]\n[[Else|Other]]',
        "Fight Start": "<<beastCombatInit>>",
        "Other": "<<no combat here>>",
    }
    row = {"key": "beastNEWinit:pig:Source", "passage": "Source"}

    assert find_combat_link_target(row, bodies) == "Fight Start"


def test_find_combat_link_target_follows_two_links_deep() -> None:
    bodies = {
        "Source": '<<beastNEWinit 1 pig>>\n[[Next|Middle]]',
        "Middle": "[[Continue|Fight Start]]",
        "Fight Start": "<<beastCombatInit>>",
    }
    row = {"key": "beastNEWinit:pig:Source", "passage": "Source"}

    assert find_combat_link_target(row, bodies) == "Fight Start"


def test_find_combat_link_target_returns_none_without_starters() -> None:
    bodies = {
        "Source": '<<beastNEWinit 1 pig>>\n[[Next|Dead End]]',
        "Dead End": "<<no combat>>",
    }
    row = {"key": "beastNEWinit:pig:Source", "passage": "Source"}

    assert find_combat_link_target(row, bodies) is None


def test_build_archetype_jobs_follows_links_for_starterless_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snake_spec = next(s for s in combat_sweep.ARCHETYPE_SPECS if s.key == "beast-pig")
    monkeypatch.setattr(combat_sweep, "ARCHETYPE_SPECS", (snake_spec,))
    bodies = {
        "Farmland Pigs": '<<beastNEWinit 2 pig>>\n[[Next|Farmland Pigs Rape]]',
        "Farmland Pigs Rape": "<<beastCombatInit>>",
    }
    rows = [
        {
            "key": "beastNEWinit:pig:Farmland Pigs",
            "kind": "beastNEWinit",
            "token": "pig",
            "passage": "Farmland Pigs",
            "entry_flags": [],
            "combat_starters": [],
            "_passage_bodies": bodies,
        }
    ]

    matrix = build_archetype_jobs(rows)

    assert matrix["unresolved"] == []
    assert {job["passage"] for job in matrix["jobs"]} == {"Farmland Pigs Rape"}
    assert all(job["link_from"] == "Farmland Pigs" for job in matrix["jobs"])


def test_build_archetype_jobs_unresolved_when_no_starter_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dolphin_spec = next(
        s for s in combat_sweep.ARCHETYPE_SPECS if s.key == "beast-dolphin"
    )
    unrestricted_spec = dataclasses.replace(dolphin_spec, passage_keywords=())
    monkeypatch.setattr(combat_sweep, "ARCHETYPE_SPECS", (unrestricted_spec,))
    bodies = {"Dead": "<<beastNEWinit 1 dolphin>>"}
    rows = [
        {
            "key": "beastNEWinit:dolphin:Dead",
            "kind": "beastNEWinit",
            "token": "dolphin",
            "passage": "Dead",
            "entry_flags": [],
            "combat_starters": [],
            "_passage_bodies": bodies,
        }
    ]

    matrix = build_archetype_jobs(rows)

    assert matrix["jobs"] == []
    assert len(matrix["unresolved"]) == 1
    assert "no link" in matrix["unresolved"][0]["reason"]


def test_build_archetype_jobs_accepts_explicit_passage_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pig_spec = next(s for s in combat_sweep.ARCHETYPE_SPECS if s.key == "beast-pig")
    monkeypatch.setattr(combat_sweep, "ARCHETYPE_SPECS", (pig_spec,))
    bodies = {
        "Brothel Show": '<<beastNEWinit 1 pig>>\n[[Next|Brothel Show Pig]]',
        "Brothel Show Pig": "<<beastCombatInit>>",
    }
    rows = [
        {
            "key": "beastNEWinit:pig:Brothel Show",
            "kind": "beastNEWinit",
            "token": "pig",
            "passage": "Brothel Show",
            "entry_flags": [],
            "combat_starters": [],
        }
    ]

    matrix = build_archetype_jobs(rows, passage_bodies=bodies)

    assert matrix["unresolved"] == []
    assert {job["passage"] for job in matrix["jobs"]} == {"Brothel Show Pig"}


# --------------------------------------------------------------------------- #
# Round semantics
# --------------------------------------------------------------------------- #


def _actions(*texts: str, kind: str = "radio") -> list[dict]:
    return [{"kind": kind, "id": f"radiobutton-leftaction-{i}", "text": text} for i, text in enumerate(texts)]


def test_choose_action_matches_bilingual_keywords() -> None:
    actions = _actions("躲避", "击打", "踢", "逃跑")

    assert choose_action(actions, "win") == (1, False)
    assert choose_action(actions, "flee") == (3, False)
    assert choose_action(_actions("亲吻", "顺从"), "submit") == (1, False)
    assert choose_action(_actions("wait", "endure"), "lose") == (0, False)


def test_choose_action_falls_back_to_first_available() -> None:
    actions = _actions("抚摸", "微笑")

    index, fallback = choose_action(actions, "win")

    assert (index, fallback) == (0, True)
    assert choose_action([], "win") == (-1, True)
    assert all(kw for keywords in PATH_KEYWORDS.values() for kw in keywords)


def test_choose_action_fallback_skips_the_prechecked_rest_radio() -> None:
    actions = [
        {"kind": "radio", "id": "r0", "text": "Zzz", "checked": True},
        {"kind": "radio", "id": "r1", "text": "Qqq", "checked": False},
    ]

    assert choose_action(actions, "win") == (1, True)
    assert choose_action([dict(action, checked=True) for action in actions], "win") == (0, True)


def test_detect_stall_needs_three_identical_digests() -> None:
    assert detect_stall(["a", "a", "a"]) is True
    assert detect_stall(["a", "a"]) is False
    assert detect_stall(["a", "b", "a"]) is False
    assert detect_stall(["a", "a", "a", "a"], threshold=4) is True
    assert detect_stall([], ) is False


def test_round_digest_ignores_render_counters_and_tracks_hp() -> None:
    base = {"passage": "Dog Park", "combat": 1, "enemyhealth": 200, "renderSeq": 1, "done": True}
    same_but_rendered = {"passage": "Dog Park", "combat": 1, "enemyhealth": 200, "renderSeq": 99, "done": True}
    hurt = {"passage": "Dog Park", "combat": 1, "enemyhealth": 194.8, "renderSeq": 2, "done": True}

    assert round_digest(base) == round_digest(same_but_rendered)
    assert round_digest(base) != round_digest(hurt)


class _FakeTurnPage:
    """Minimal Playwright stand-in for ``begin_turn`` / ``_press_turn``."""

    class _Keyboard:
        def __init__(self, owner: "_FakeTurnPage") -> None:
            self._owner = owner

        def press(self, _key: str) -> None:
            self._owner.presses += 1

    def __init__(self, render_seq: int = 5, *, wait_raises: bool = False) -> None:
        self.render_seq = render_seq
        self.wait_raises = wait_raises
        self.presses = 0
        self.waited_with: object = None
        self.wait_timeout: int | None = None
        self.settle_ms: int | None = None
        self.keyboard = self._Keyboard(self)

    def evaluate(self, script: str, arg: object = None) -> object:
        if script == COMBAT_STATE_JS:
            return json.dumps({"ok": True, "combat": 1, "enemyhealth": 90})
        return self.render_seq

    def wait_for_function(self, _expr: str, arg: object = None, timeout: int | None = None) -> None:
        self.waited_with = arg
        self.wait_timeout = timeout
        if self.wait_raises:
            raise RuntimeError("Timeout exceeded")

    def wait_for_timeout(self, ms: int) -> None:
        self.settle_ms = ms


def test_begin_turn_returns_render_counter_from_before_the_click() -> None:
    assert begin_turn(_FakeTurnPage(render_seq=11)) == 11
    assert begin_turn(_FakeTurnPage(render_seq=0)) == 0


def test_press_turn_waits_on_the_pre_click_render_counter() -> None:
    page = _FakeTurnPage()

    turn = _press_turn(page, timeout_ms=20000, before_render=3)

    assert page.waited_with == 3
    assert page.wait_timeout is not None and page.wait_timeout < 20000
    assert page.presses == 1
    assert turn["timed_out"] is False
    assert turn["state"]["combat"] == 1


def test_press_turn_flags_a_missing_render_as_timed_out() -> None:
    page = _FakeTurnPage(wait_raises=True)

    turn = _press_turn(page, timeout_ms=20000, before_render=1)

    assert turn["timed_out"] is True


def test_classify_outcome_covers_win_submit_limit_and_unknown() -> None:
    assert classify_outcome({"combat": 0, "enemyhealth": 0}, path="win", rounds=4, max_rounds=80, stalled=False)[0] == "win"
    assert classify_outcome(
        {"combat": 0, "enemyhealth": 50, "enemyarousal": 10, "enemyarousalmax": 10},
        path="submit",
        rounds=6,
        max_rounds=80,
        stalled=False,
    )[0] == "submit"
    assert classify_outcome(
        {"combat": 0, "enemyhealth": 50, "enemyarousal": 10, "enemyarousalmax": 10},
        path="win",
        rounds=6,
        max_rounds=80,
        stalled=False,
    )[0] == "win"
    limit_outcome, limit_detail = classify_outcome(
        {"combat": 1, "enemyhealth": 12}, path="win", rounds=80, max_rounds=80, stalled=False
    )
    assert limit_outcome == "unknown"
    assert "round limit" in limit_detail
    stalled_outcome, stalled_detail = classify_outcome(
        {"combat": 1, "enemyhealth": 12}, path="win", rounds=5, max_rounds=80, stalled=True
    )
    assert stalled_outcome == "unknown"
    assert "stalled" in stalled_detail
    unknown, detail = classify_outcome(
        {"combat": 0, "enemyhealth": 40, "enemyarousal": 1, "enemyarousalmax": 10},
        path="win",
        rounds=5,
        max_rounds=80,
        stalled=False,
    )
    assert unknown == "unknown"
    assert "enemyhealth=40" in detail


def test_classify_outcome_uses_last_active_snapshot_after_finish_reset() -> None:
    # Beach-dog style ending: the Finish passage resets $enemyarousal to 26.66
    # while the last combat-active round already showed the beast orgasming
    # (573.66/500). The verdict must follow the evidence, not the reset value.
    final = {
        "combat": 0,
        "passage": "Beach Phallus Dog Handjob Finish",
        "enemyhealth": 200,
        "enemyarousal": 26.66,
        "enemyarousalmax": 500,
    }
    last_active = {
        "combat": 1,
        "enemyhealth": 200,
        "enemyarousal": 573.66,
        "enemyarousalmax": 500,
    }

    outcome, detail = classify_outcome(
        final, path="win", rounds=15, max_rounds=80, stalled=False, last_active=last_active
    )

    assert outcome == "win"
    assert "last combat-active round" in detail


def test_classify_outcome_reads_endcombat_landing_as_terminal_end() -> None:
    state = {
        "combat": 0,
        "passage": "Underground Film Molestation Finish",
        "enemyhealth": 37.5714285714286,
        "enemyarousal": 493.66,
        "enemyarousalmax": 500,
    }

    outcome, detail = classify_outcome(
        state,
        path="win",
        rounds=24,
        max_rounds=80,
        stalled=False,
        landing_body="<<tearful>> you gather yourself.\n<<endcombat>>\n<<link [[Next|Bog]]>>",
        landing_passage="Underground Film Molestation Finish",
    )

    assert outcome == "end"
    assert "endcombat" in detail
    assert "Underground Film Molestation Finish" in detail


def test_classify_outcome_flags_pc_orgasm_ending() -> None:
    state = {
        "combat": 0,
        "passage": "Beach Exhibit Molestation Orgasm",
        "enemyhealth": 1069.1428571428573,
        "enemyarousal": 984.66,
        "enemyarousalmax": 2500,
    }

    outcome, detail = classify_outcome(
        state,
        path="win",
        rounds=12,
        max_rounds=80,
        stalled=False,
        last_active={
            "combat": 1,
            "enemyhealth": 1069.1428571428573,
            "enemyarousal": 984.66,
            "enemyarousalmax": 2500,
        },
        landing_body="<<endcombat>>",
        landing_passage="Beach Exhibit Molestation Orgasm",
    )

    assert outcome == "end_player_orgasm"
    assert "PC orgasm" in detail


def test_classify_outcome_without_landing_evidence_stays_unknown() -> None:
    state = {
        "combat": 0,
        "passage": "Somewhere",
        "enemyhealth": 40,
        "enemyarousal": 1,
        "enemyarousalmax": 10,
    }

    outcome, _detail = classify_outcome(
        state, path="win", rounds=3, max_rounds=80, stalled=False
    )

    assert outcome == "unknown"


def test_expected_outcome_map_only_asserts_unambiguous_paths() -> None:
    assert combat_sweep.EXPECTED_OUTCOME_ACCEPTS["win"] == ("win",)
    assert "win" in combat_sweep.EXPECTED_OUTCOME_ACCEPTS["submit"]
    assert "end" not in combat_sweep.EXPECTED_OUTCOME_ACCEPTS["win"]
    assert "end_player_orgasm" not in combat_sweep.EXPECTED_OUTCOME_ACCEPTS["win"]


# --------------------------------------------------------------------------- #
# Error classification
# --------------------------------------------------------------------------- #


def test_classify_entry_errors_marks_missing_variables_as_fixture_insufficient() -> None:
    verdict, detail, missing = classify_entry_errors(
        [{"message": "ReferenceError: $wolfpack is not defined"}]
    )

    assert verdict == "fixture_insufficient"
    assert any(name.endswith("wolfpack") for name in missing)
    assert "is not defined" in detail


def test_classify_entry_errors_marks_null_property_reads_as_fixture_insufficient() -> None:
    verdict, _detail, missing = classify_entry_errors(
        [{"message": "TypeError: Cannot read properties of null (reading 'type')"}]
    )

    assert verdict == "fixture_insufficient"
    assert "null.type" in missing


def test_classify_entry_errors_keeps_real_errors_as_hard_fail() -> None:
    verdict, detail, missing = classify_entry_errors(
        [{"message": "Boom: widget exploded"}]
    )

    assert verdict == "hard_fail"
    assert "Boom" in detail
    assert missing == []


def test_classify_entry_errors_without_errors_is_not_applicable() -> None:
    assert classify_entry_errors([]) == (
        "not_applicable",
        "passage rendered but $combat stayed 0",
        [],
    )
    assert classify_entry_errors([], timed_out=True)[0] == "soft_fail"


def test_classify_no_actions_flags_missing_list_container_as_fixture_insufficient() -> None:
    verdict, detail, missing = classify_no_actions({"error": "no #listContainer"}, {"errors": []})

    assert verdict == "fixture_insufficient"
    assert missing == ["#listContainer"]
    assert "#listContainer" in detail


def test_classify_no_actions_prefers_captured_state_errors() -> None:
    verdict, _detail, missing = classify_no_actions(
        {"error": "no #listContainer"},
        {"errors": [{"message": "ReferenceError: $beast is not defined"}]},
    )

    assert verdict == "fixture_insufficient"
    assert any(name.endswith("beast") for name in missing)


def test_classify_no_actions_stays_soft_fail_when_container_rendered_empty() -> None:
    verdict, detail, missing = classify_no_actions({"ok": True, "actions": []}, {"errors": []})

    assert verdict == "soft_fail"
    assert missing == []
    assert "no action controls" in detail


# --------------------------------------------------------------------------- #
# initiator row selection (resume / limit / sample)
# --------------------------------------------------------------------------- #


def _initiator_rows(count: int = 6) -> list[dict]:
    return [
        {
            "key": f"maninit:-:Passage {i}",
            "kind": "maninit",
            "token": "",
            "passage": f"Passage {i}",
        }
        for i in range(count)
    ]


def test_select_initiator_rows_skips_resume_keys() -> None:
    rows = _initiator_rows()

    selection = select_initiator_rows(rows, resume_keys={"maninit:-:Passage 1", "maninit:-:Passage 3"})

    assert selection["skipped_resume"] == 2
    assert [row["key"] for row in selection["selected"]] == [
        "maninit:-:Passage 0",
        "maninit:-:Passage 2",
        "maninit:-:Passage 4",
        "maninit:-:Passage 5",
    ]


def test_select_initiator_rows_limit_and_seed_stable_sample() -> None:
    rows = _initiator_rows(10)

    limited = select_initiator_rows(rows, limit=3)
    assert [row["key"] for row in limited["selected"]] == [
        "maninit:-:Passage 0",
        "maninit:-:Passage 1",
        "maninit:-:Passage 2",
    ]

    first = select_initiator_rows(rows, sample=4, seed=7)
    second = select_initiator_rows(rows, sample=4, seed=7)
    other = select_initiator_rows(rows, sample=4, seed=8)
    assert [row["key"] for row in first["selected"]] == [row["key"] for row in second["selected"]]
    assert len(first["selected"]) == 4
    assert [row["key"] for row in first["selected"]] != [row["key"] for row in other["selected"]]


def test_select_initiator_rows_shards_are_disjoint_and_reassemble_plan() -> None:
    rows = _initiator_rows(11)
    shards = [
        select_initiator_rows(rows, shard_index=index, shard_count=4)["planned"]
        for index in range(4)
    ]
    keys = [row["key"] for shard in shards for row in shard]
    assert sorted(keys) == sorted(row["key"] for row in rows)
    assert len(keys) == len(set(keys))
    assert [row["key"] for row in shards[0]] == [
        "maninit:-:Passage 0",
        "maninit:-:Passage 4",
        "maninit:-:Passage 8",
    ]


def test_select_initiator_rows_keeps_planned_keys_when_resuming() -> None:
    rows = _initiator_rows(5)
    selection = select_initiator_rows(
        rows,
        resume_keys={"maninit:-:Passage 1", "maninit:-:Passage 3"},
        shard_index=0,
        shard_count=1,
    )
    assert [row["key"] for row in selection["planned"]] == [row["key"] for row in rows]
    assert [row["key"] for row in selection["selected"]] == [
        "maninit:-:Passage 0",
        "maninit:-:Passage 2",
        "maninit:-:Passage 4",
    ]
    assert selection["skipped_resume"] == 2


# --------------------------------------------------------------------------- #
# Baseline diff + report
# --------------------------------------------------------------------------- #


def test_diff_against_baseline_classifies_regressions_fixed_and_unseen() -> None:
    baseline = {
        "results": [
            {"key": "a", "verdict": "ok"},
            {"key": "b", "verdict": "hard_fail"},
            {"key": "c", "verdict": "ok"},
        ],
        "manifest": {"by_kind": {"maninit": 2}, "total": 3},
    }
    report = {
        "results": [
            {"key": "a", "verdict": "hard_fail"},
            {"key": "b", "verdict": "ok"},
            {"key": "d", "verdict": "soft_fail"},
        ],
        "manifest": {"by_kind": {"maninit": 3}, "total": 4},
    }

    diff = diff_against_baseline(report, baseline)

    assert diff["regressions"] == [{"key": "a", "was": "ok", "now": "hard_fail"}]
    assert diff["fixed"] == [{"key": "b", "was": "hard_fail", "now": "ok"}]
    assert diff["unseen_in_baseline"] == [{"key": "d", "verdict": "soft_fail"}]
    assert diff["manifest"]["total"] == {"baseline": 3, "current": 4}


def _sample_report() -> dict:
    return {
        "tool": "combat_sweep",
        "target": "artifact.html",
        "html_path": "artifact.html",
        "tier": "archetypes",
        "fixture": {"path": str(DEFAULT_FIXTURE), "top_level_keys": 780, "digest": "abc123"},
        "manifest": {
            "path": ".local/sweep/combat-initiators.json",
            "total": 1601,
            "by_kind": {"maninit": 897, "beastNEWinit": 222, "tentacle": 93},
            "by_token": {"dog": 104},
            "passages": 1500,
            "drift": {"ok": False, "count": 2, "differences": []},
        },
        "expected": {"total": 1603},
        "results": [
            {
                "key": "beast-dog:win",
                "archetype": "beast-dog",
                "kind": "beastNEWinit",
                "token": "dog",
                "passage": "Dog Park",
                "verdict": "ok",
                "detail": "",
                "missing": [],
                "combat": {
                    "rounds": 4,
                    "outcome": "win",
                    "hp_evidence": [
                        {"round": 1, "enemyhealth": [200, 194.857], "enemyarousal": [0, 5]},
                        {"round": 2, "enemyhealth": [194.857, 182], "enemyarousal": [5, 9]},
                    ],
                },
            },
            {
                "key": "special-hypno:win",
                "archetype": "special-hypno",
                "kind": "hypno",
                "token": "",
                "passage": "Gwylan Fight",
                "verdict": "hard_fail",
                "detail": "boom",
                "missing": [],
                "combat": None,
            },
        ],
        "modes": [
            {
                "mode": "Radio",
                "verdict": "ok",
                "rounds": 3,
                "dom_kinds": ["radio", "radio", "radio"],
                "selections": [{"kind": "radio", "text": "击打"}],
                "hp_evidence": [{"round": 1, "enemyhealth": [200, 194.857]}],
                "detail": "",
            },
            {
                "mode": "Lists",
                "verdict": "ok",
                "rounds": 3,
                "dom_kinds": ["select", "select", "select"],
                "selections": [{"kind": "select", "text": "击打"}],
                "hp_evidence": [{"round": 1, "enemyhealth": [200, 194.857]}],
                "detail": "",
            },
        ],
        "verdict_counts": {"ok": 1, "soft_fail": 0, "hard_fail": 1, "fixture_insufficient": 0, "not_applicable": 0},
        "started_at": "2026-10-04T10:00:00",
        "finished_at": "2026-10-04T10:05:00",
        "fatal_error": None,
    }


def test_write_report_writes_json_and_markdown(tmp_path: Path) -> None:
    report = _sample_report()
    diff = {
        "regressions": [{"key": "special-hypno:win", "was": "ok", "now": "hard_fail"}],
        "fixed": [],
        "changed": [],
        "unseen_in_baseline": [],
        "manifest": {"total": {"baseline": 1603, "current": 1601}},
    }

    md_path = write_report(report, tmp_path, diff)

    json_path = tmp_path / "combat-sweep.json"
    assert json_path.exists()
    assert md_path.exists()
    assert md_path.name == "combat-sweep.md"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["tool"] == "combat_sweep"
    assert payload["results"][0]["key"] == "beast-dog:win"

    markdown = md_path.read_text(encoding="utf-8")
    assert "# DOL-X combat sweep report" in markdown
    assert "| hard_fail | 1 |" in markdown
    assert "## control modes" in markdown
    assert "| Radio | ok | 3 |" in markdown
    assert "## enemyhealth evidence" in markdown
    assert "200->194.857" in markdown
    assert "## hard_fail (1)" in markdown
    assert "## baseline diff" in markdown
    assert "regressions: **1**" in markdown


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_parse_args_defaults() -> None:
    args = parse_args(["artifact.html"])

    assert args.target == Path("artifact.html")
    assert args.tier == "archetypes"
    assert args.out is None
    assert args.fixture == DEFAULT_FIXTURE
    assert args.manifest_out == DEFAULT_MANIFEST_OUT
    assert args.limit is None
    assert args.sample is None
    assert args.seed == 20261004
    assert args.max_rounds == DEFAULT_MAX_ROUNDS == 80
    assert args.mode_rounds == DEFAULT_MODE_ROUNDS == 3
    assert args.timeout_ms == 20000
    assert args.resume is False
    assert args.baseline is None
    assert args.save_baseline is False
    assert args.skip_modes is False
    assert args.modes_only is False
    assert args.headful is False
    assert args.shard_index == 0
    assert args.shard_count == 1


def test_parse_args_overrides() -> None:
    args = parse_args(
        [
            "artifact.html",
            "--tier",
            "initiators",
            "--limit",
            "5",
            "--sample",
            "3",
            "--seed",
            "1",
            "--max-rounds",
            "12",
            "--mode-rounds",
            "4",
            "--resume",
            "--shard-index",
            "3",
            "--shard-count",
            "8",
            "--modes-only",
            "--save-baseline",
            "--out",
            "reports/combat",
        ]
    )

    assert args.tier == "initiators"
    assert args.limit == 5
    assert args.sample == 3
    assert args.seed == 1
    assert args.max_rounds == 12
    assert args.mode_rounds == 4
    assert args.resume is True
    assert args.shard_index == 3
    assert args.shard_count == 8
    assert args.modes_only is True
    assert args.save_baseline is True
    assert args.out == Path("reports/combat")


def test_parse_args_rejects_unknown_tier() -> None:
    with pytest.raises(SystemExit):
        parse_args(["artifact.html", "--tier", "nonsense"])


def test_entry_flags_and_control_modes_contract() -> None:
    assert ENTRY_FLAGS == ("molestationstart", "sexstart")
    assert CONTROL_MODES == ("Radio", "Radio (c)", "Lists", "List (w)")
    assert PATH_KEYWORDS["win"] and PATH_KEYWORDS["flee"]


# --------------------------------------------------------------------------- #
# Entry precursors (game-side generation preamble)
# --------------------------------------------------------------------------- #


def test_derive_precursor_maninit_generic() -> None:
    row = {"kind": "maninit", "passage": "Balloon Sex", "token": "-"}
    info = combat_sweep.derive_precursor(row, passage_bodies={})
    assert info["widgets"] == "<<generate1>><<person1>>"
    assert info["basis"].startswith("debug-menu")


def test_derive_precursor_maninit_multi_enemy_counts_npcs() -> None:
    row = {"kind": "maninit", "passage": "StreetEx4 Rape", "token": "-"}
    bodies = {"StreetEx4 Rape": "<<set $enemyno to 2>><<set $enemynomax to 2>><<maninit>>"}
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"] == "<<generate1>><<generate2>><<person1>><<person2>>"
    assert info["basis"] == "debug-menu:generate1..2+person1..2"


def test_derive_precursor_maninit_named_npc_in_title() -> None:
    row = {"kind": "maninit", "passage": "Underground Robin Kiss Molestation", "token": "-"}
    info = combat_sweep.derive_precursor(row, passage_bodies={}, named_npcs=["Robin", "Kylar"])
    assert info["widgets"] == '<<npc "Robin">><<person1>>'
    assert info["basis"] == "title-npc:Robin"


def test_derive_precursor_maninit_ignores_partial_name_matches() -> None:
    row = {"kind": "maninit", "passage": "Robbing the store", "token": "-"}
    info = combat_sweep.derive_precursor(row, passage_bodies={}, named_npcs=["Rob"])
    assert info["widgets"] == "<<generate1>><<person1>>"


def test_derive_precursor_maninit_named_npc_extends_to_referenced_slots() -> None:
    row = {"kind": "maninit", "passage": "Rent First Robin Fight", "token": "-"}
    bodies = {
        "Rent First Robin Fight": (
            "<<if $fightstart is 1>><<maninit>><</if>>"
            "The <<person2>><<person>> and <<person3>><<person>> hold <<person1>><<person>>."
        )
    }

    info = combat_sweep.derive_precursor(
        row, passage_bodies=bodies, named_npcs=["Robin", "Bailey"]
    )

    assert info["widgets"] == (
        '<<npc "Robin">><<generate2>><<generate3>>'
        "<<person1>><<person2>><<person3>>"
    )
    assert "title-npc:Robin" in info["basis"]
    assert "generate2..3" in info["basis"]


def test_derive_precursor_named_row_uses_successor_slots_from_named_path() -> None:
    """A title-named row still needs the slots its *sequel* renders.

    No real predecessor chain exists here, so the named NPC stays in slot 1 and
    the missing slot comes from the game's own generator.
    """
    row = {
        "kind": "maninit",
        "passage": "Underground Robin Stage Molestation",
        "token": "-",
    }
    bodies = {
        "Underground Robin Stage Molestation": (
            "<<set $enemyno to 1>><<set $enemynomax to 1>><<maninit>>"
            "<<if _combatend>><<link [[Next|Underground Robin Stage Molestation Finish]]>>"
            "<</link>><</if>>"
        ),
        "Underground Robin Stage Molestation Finish": (
            "The <<person1>><<person>> tumbles. The <<person2>><<person>> looks over."
        ),
    }

    info = combat_sweep.derive_precursor(
        row, passage_bodies=bodies, named_npcs=["Robin", "Kylar"]
    )

    assert info["widgets"] == (
        '<<npc "Robin">><<generate2>><<person1>><<person2>>'
    )
    assert info["basis"].startswith("title-npc:Robin")
    assert "person2" in info["basis"]


def test_derive_precursor_named_row_prefers_real_chain_over_named_npc() -> None:
    """The game's own branch beats the synthetic title-named NPC.

    ``Underground Robin Stage Intro`` generates the aggressor group with
    ``<<generate1>><<generate2>>`` before linking in; Robin is on stage, not in
    ``$NPCList``. Replaying only ``<<npc "Robin">>`` left slot 1 undefined and
    the ``… Finish`` passage died on "Undefined NPC in personselect 1".
    """
    row = {
        "kind": "maninit",
        "passage": "Underground Robin Stage Molestation",
        "token": "-",
    }
    bodies = {
        "Underground Robin Stage Intro": (
            "<<beastNEWinit 1 pig>>"
            "<<link [[Next|Underground Robin Stage Pig]]>><<set $molestationstart to 1>><</link>>"
            "<<endevent>><<generate1>><<generate2>>"
            "There's a <<fullGroup>> already waiting for you. "
            "<<link [[Next|Underground Robin Stage Molestation]]>><<set $molestationstart to 1>><</link>>"
        ),
        "Underground Robin Stage Molestation": (
            "<<set $enemyno to 1>><<set $enemynomax to 1>><<maninit>>"
            "<<if _combatend>><<link [[Next|Underground Robin Stage Molestation Finish]]>>"
            "<</link>><</if>>"
        ),
        "Underground Robin Stage Molestation Finish": (
            "The <<person1>><<person>> recoils. The <<person2>><<person>> startles."
        ),
    }

    info = combat_sweep.derive_precursor(
        row, passage_bodies=bodies, named_npcs=["Robin", "Kylar"]
    )

    assert info["widgets"] == (
        "<<generate1>><<generate2>><<set $molestationstart to 1>>"
    )
    assert info["basis"].startswith("predecessor:Underground Robin Stage Intro")
    assert "link-body:Underground Robin Stage Intro" in info["basis"]


def test_maninit_slot_chain_reads_generate_role_as_zero_based_slot() -> None:
    """``generateRole N`` fills ``$NPCList[N]``, not ``$NPCList[N-1]``.

    The widget documents "Slot one would be 0" and calls ``generateNPC N + 1``.
    """
    covered = combat_sweep._maninit_slot_chain(
        '<<generateRole 0 0 "thug">><<generateRole 1 0 "thug">>'
        '<<generateRole 2 0 "thug">><<generateRole 3 0 "thug">>',
        None,
        3,
    )
    assert covered is not None
    assert covered["slots"] == 4
    assert covered["widgets"].startswith('<<generateRole 0 0 "thug">>')

    # A lone ``<<generateRole 1 …>>`` leaves slot 0 untouched, so it can never
    # satisfy a one-slot scene on its own.
    assert combat_sweep._maninit_slot_chain('<<generateRole 1 0 "x">>', None, 1) is None


def test_maninit_slot_chain_recognises_glued_generate_variants() -> None:
    """``generatecf1``/``generatey3``/``generatep2`` all funnel into ``generateNPC N``."""
    covered = combat_sweep._maninit_slot_chain("<<generatecf1>><<generatey2>>", None, 2)
    assert covered is not None
    assert covered["widgets"] == "<<generatecf1>><<generatey2>>"
    assert covered["slots"] == 2

    # ``<<generatel>>`` picks ``$enemyno + 1`` dynamically: it bumps the count
    # but can never prove which slot it filled.
    assert combat_sweep._maninit_slot_chain("<<generatel>>", None, 1) is None


def test_maninit_slot_chain_never_spans_a_clear() -> None:
    """``<<clearnpc>>`` wipes the slots generated before it."""
    # Rows 0 and 1 are generated on opposite sides of a clear: neither run may
    # borrow coverage from the other, so this cannot satisfy a two-slot scene.
    assert (
        combat_sweep._maninit_slot_chain(
            "<<generate1>><<clearnpc 0>><<generate2>>", None, 2
        )
        is None
    )
    # The clear itself is never replayed -- the fixture is restored first, so
    # there is nothing stale to wipe -- and the run before it stays usable.
    covered = combat_sweep._maninit_slot_chain(
        "<<generate1>><<generate2>><<clearnpc 0>><<generate1>>", None, 2
    )
    assert covered == {"widgets": "<<generate1>><<generate2>>", "slots": 2}


def test_derive_precursor_replays_generate_role_chain() -> None:
    """The Bailey street ambush generates four ``thug`` slots with ``generateRole``."""
    row = {"kind": "maninit", "passage": "Bailey Sheet Fight", "token": "-"}
    bodies = {
        "Harvest Street": (
            '<<generateRole 0 0 "thug">><<generateRole 1 0 "thug">>'
            '<<generateRole 2 0 "thug">><<generateRole 3 0 "thug">>'
            "A group of <<group>> approaches you. The leader, a <<person1>><<person>>, grins. "
            "<<link [[Next|Bailey Sheet Fight]]>><<set $fightstart to 1>><</link>>"
        ),
        "Bailey Sheet Fight": (
            "<<if $fightstart is 1>><<maninit>><</if>>"
            "<<link [[Next|Bailey Sheet Fight Finish]]>><</link>>"
        ),
        "Bailey Sheet Fight Finish": "The <<person1>><<person>> staggers. The <<person3>><<person>> runs.",
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["widgets"] == (
        "<<set $pubfame to {seen: [], tasksDone: []}>>"
        '<<set $pubfame.status to "accepted">>'
        '<<set $pubfame.task to "bailey">>'
        "<<set $pubfame.bailey to {}>>"
        '<<set $pubfame.bailey.fight to "ready">>'
        '<<generateRole 0 0 "thug">><<generateRole 1 0 "thug">>'
        '<<generateRole 2 0 "thug">><<generateRole 3 0 "thug">>'
        "<<set $fightstart to 1>>"
    )
    assert info["basis"].startswith("predecessor:Harvest Street:slots4")
    assert "link-body:Harvest Street" in info["basis"]
    assert info["basis"].endswith("|status-bootstrap:pubfame-bailey")


def test_link_body_precursors_replays_start_flags_only() -> None:
    bodies = {
        "Courtyard Crush Robin Angry": (
            "<<link [[Fight them both|Courtyard Crush Fight]]>>"
            "<<set $fightstart to 1>><<def 1>><</link>>\n"
            "<<link [[Walk away|Courtyard Crush Fight]]>>"
            "<<endevent>><<set $molestationstart to 1>><</link>>"
        ),
        "Courtyard Crush Fight": "<<set $fightstart to 1>>",
    }

    info = combat_sweep.link_body_precursors("Courtyard Crush Fight", bodies)

    # Only the first link from a parent is replayed (the walk-away branch would
    # mix its own flags into the fight path), and ``<<endevent>>`` is never
    # replayed: it would clear the generated NPCs.
    assert info["widgets"] == "<<set $fightstart to 1>><<def 1>>"
    assert info["parents"] == ["Courtyard Crush Robin Angry"]


def test_derive_precursor_appends_link_body_start_flags() -> None:
    row = {"kind": "maninit", "passage": "Courtyard Crush Fight", "token": "-"}
    bodies = {
        "Courtyard Crush Robin Angry": (
            "<<link [[Fight them both|Courtyard Crush Fight]]>>"
            "<<set $fightstart to 1>><</link>>"
        ),
        "Courtyard Crush Fight": (
            "<<if $fightstart is 1>><<maninit>><</if>>"
            "You lunge at the <<person1>><<person>>, and the <<person2>><<person>> joins in."
        ),
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["widgets"] == (
        "<<generate1>><<generate2>><<person1>><<person2>><<set $fightstart to 1>>"
    )
    assert info["basis"].endswith("|link-body:Courtyard Crush Robin Angry")


def test_derive_precursor_keeps_chain_and_flags_in_one_branch() -> None:
    row = {"kind": "maninit", "passage": "Street Collar Molestation", "token": "-"}
    bodies = {
        "Widgets Street": (
            "<<beastNEWinit 1 dog>>\n"
            "<<if $rng gte 51>><<generate2>><<generate3>>"
            "<<link [[Refuse|Street Collar Molestation]]>>"
            "<<set $molestationstart to 1>><<set $phase to 1>><</link>><</if>>\n"
            "<<else>><<generate1>><<generate2>>"
            "<<link [[Next|Street Collar Molestation]]>>"
            "<<set $molestationstart to 1>><<set $phase to 2>><</link>><</if>>"
        ),
        "Street Collar Molestation": "<<maninit>>The <<person2>><<person>> grins.",
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    # The night branch fills rows 2-3 only; the day branch fills rows 1-2 and
    # brings its own ``$phase to 2``. Mixing them re-indexes a fixture shell.
    assert info["widgets"] == (
        "<<generate1>><<generate2>><<set $molestationstart to 1>><<set $phase to 2>>"
    )
    assert "|link-body:Widgets Street" in info["basis"]


def test_build_widget_index_and_person_closure_read_widget_refs() -> None:
    bodies = {
        "Widgets Robin": (
            '<<widget "balloonRobinHelped">>'
            "Robin blushes. <<person2>> smiles."
            "<</widget>>"
        ),
        "Balloon Sex": (
            "<<maninit>>You float. <<link [[Continue|Balloon Sex Finish]]>><</link>>"
        ),
        "Balloon Sex Finish": "<<balloonRobinHelped>>",
    }

    widget_bodies = combat_sweep.build_widget_index(bodies)
    assert "balloonRobinHelped" in widget_bodies

    row = {"kind": "maninit", "passage": "Balloon Sex", "token": "-"}
    info = combat_sweep.derive_precursor(
        row, passage_bodies=bodies, widget_bodies=widget_bodies
    )

    assert info["widgets"] == "<<generate1>><<generate2>><<person1>><<person2>>"
    assert "person2" in info["basis"]


def test_derive_precursor_beast_row_token() -> None:
    row = {"kind": "beastNEWinit", "passage": "Farmland Pigs", "token": "pig"}
    info = combat_sweep.derive_precursor(row, passage_bodies={})
    assert info["widgets"] == "<<generateBEAST 1 pig>>"
    assert info["basis"] == "row-token:pig"


def test_derive_precursor_beast_named_token() -> None:
    row = {"kind": "beastNNPCinit", "passage": "Cave", "token": "Black Wolf"}
    info = combat_sweep.derive_precursor(row, passage_bodies={}, named_npcs=["Black Wolf"])
    assert info["widgets"] == '<<beastNNPCinit>><<npc "Black Wolf">>'
    assert info["basis"] == "row-token-nnpc:Black Wolf"


def test_derive_precursor_beast_farm_self_generation() -> None:
    row = {"kind": "beastCombatInit", "passage": "Farm Pigs Hand", "token": "unknown"}
    bodies = {
        "Farm Pigs Hand": (
            "<<beastNEWinit 1 pig $farm_work.pig.gender $farm_work.pig.genitals beast>>"
        )
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert "farm_gen pig" in str(info["widgets"])
    assert info["basis"] == "self-generation:farm_gen(pig)"


def test_derive_precursor_beast_predecessor_chain() -> None:
    row = {"kind": "beastCombatInit", "passage": "Wolf Cave Accept", "token": "unknown"}
    bodies = {
        "Wolf Cave": (
            "The pack circles you. <<beastNEWinit 1 wolf>>"
            "<<link [[Accept|Wolf Cave Accept]]>><</link>>"
        ),
        "Wolf Cave Accept": "<<beastCombatInit>>",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"] == "<<beastNEWinit 1 wolf>>"
    assert "predecessor:Wolf Cave" in info["basis"]


def test_beast_chain_from_body_replays_clear_init_and_generate() -> None:
    # Verbatim shape of ``Widgets Events Beach`` inline event
    # ``beach_phallus_dog`` (author comment: beastNEWinit requires no existing
    # NPCs, the human owner must be generated afterwards).
    body = (
        "<<addinlineevent \"beach_phallus_dog\">>"
        "<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>"
        "You see a <<person2>><<person>> walking <<his>> <<beasttype>> along the beach."
        "<<link [[Ask to measure <<personpenis>>|Beach Phallus Dog]]>><</link>>"
        "<</addinlineevent>>"
    )
    chain = combat_sweep._beast_chain_from_body(body, "Beach Phallus Dog")
    assert chain is not None
    assert chain["widgets"] == "<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>"
    assert chain["token"] == "dog"


def test_beast_chain_from_body_without_clearnpc_keeps_generate_run() -> None:
    body = "<<beastNEWinit 1 dog>>\n\n<<generate2>><<person2>>"
    chain = combat_sweep._beast_chain_from_body(body)
    assert chain is not None
    assert chain["widgets"] == "<<beastNEWinit 1 dog>><<generate2>><<person2>>"


def test_derive_precursor_beast_predecessor_replays_ordered_chain() -> None:
    row = {
        "kind": "beastCombatInit",
        "passage": "Beach Phallus Dog Handjob",
        "token": "unknown",
    }
    bodies = {
        "Widgets Events Beach": (
            "<<addinlineevent \"beach_phallus_dog\">>"
            "<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>"
            "<<link [[Ask to measure|Beach Phallus Dog]]>><</link>>"
            "<</addinlineevent>>"
        ),
        "Beach Phallus Dog": "<<link [[Do more than just measure|Beach Phallus Dog Handjob]]>><</link>>",
        "Beach Phallus Dog Handjob": "<<beastCombatInit>>",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"] == "<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>"
    assert "predecessor:Widgets Events Beach" in info["basis"]


def test_derive_precursor_beast_unresolved_records_reason() -> None:
    row = {"kind": "beastCombatInit", "passage": "Mystery Scene", "token": "unknown"}
    info = combat_sweep.derive_precursor(
        row, passage_bodies={"Mystery Scene": "<<beastCombatInit>>"}
    )
    assert info["widgets"] is None
    assert "no beast token" in str(info["reason"])


def test_derive_precursor_deep_fallback_marks_low_confidence() -> None:
    """3 跳之外的 `$beasttype` 来源也要能重放，但必须标记为低置信。"""
    row = {"kind": "beastCombatInit", "passage": "Entry", "token": "unknown"}
    # 浅搜索（max_depth=2）只覆盖 Near/Mid；Far 在 depth3，只有 deep fallback 能看到。
    bodies = {
        "Entry": "<<beastCombatInit>>",
        "Near": "[[Next|Entry]]",
        "Mid": "[[Next|Near]]",
        "Far": "<<beastNEWinit 1 dog>>\n[[Next|Mid]]",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["widgets"] == "<<beastNEWinit 1 dog>>"
    assert info["basis"].startswith("deep-predecessor:Far:body:depth3")
    assert info["confidence"] == "low"
    assert info["token"] == "dog"


def test_derive_precursor_deep_fallback_finds_widget_chain() -> None:
    row = {"kind": "beastCombatInit", "passage": "Entry", "token": "unknown"}
    bodies = {"Entry": "<<beastCombatInit>>", "Parent": "<<callDog>>\n[[Next|Entry]]"}
    widgets = {"callDog": "<<beastNEWinit 1 wolf>>"}

    info = combat_sweep.derive_precursor(
        row, passage_bodies=bodies, widget_bodies=widgets
    )

    assert info["widgets"] == "<<beastNEWinit 1 wolf>>"
    assert info["basis"].startswith("deep-predecessor:Parent:widget:callDog:depth1")
    assert info["confidence"] == "low"


def test_derive_precursor_deep_fallback_skips_npc_free_kinds() -> None:
    row = {"kind": "wraith", "passage": "Wraith Intro", "token": ""}
    bodies = {
        "Wraith Intro": "<<initWraith>>",
        "Far": "<<beastNEWinit 1 dog>>\n[[Next|Wraith Intro]]",
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["basis"] is None
    assert info["widgets"] is None
    assert "no NPC hand/frontarm dependency" in str(info["reason"])
    assert info.get("confidence") is None


def test_deep_beast_precursors_returns_provenance_and_limit() -> None:
    bodies = {
        "Entry": "<<beastCombatInit>>",
        "Mid": "[[Next|Entry]]",
        "Far": "<<beastNEWinit 1 dog>>\n[[Next|Mid]]",
        "Other": "<<beastNEWinit 1 wolf>>\n[[Next|Entry]]",
    }
    candidates = combat_sweep.deep_beast_precursors(
        "Entry", passage_bodies=bodies, widget_bodies={}, limit=1
    )

    assert len(candidates) == 1
    assert candidates[0]["verified"] is False
    assert candidates[0]["via"] == "body"
    assert candidates[0]["depth"] == 1
    assert candidates[0]["source"] in ("Mid", "Other") or candidates[0]["source"] == "Far"
    assert candidates[0]["token"] in ("dog", "wolf")


def test_area_bootstrap_prefixes_pound_and_bird_chains() -> None:
    """Pound / Bird Tower 的出口 widget 需要区域状态，前驱链要先重放区域 init。"""
    row = {
        "kind": "beastCombatInit",
        "passage": "Pound Assault Rape",
        "token": "unknown",
    }
    bodies = {
        "Pound Assault Rape": "<<beastCombatInit>>",
        "Pound": "<<beastNEWinit 1 dog>>\n[[Next|Pound Assault Rape]]",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"].startswith("<<pound_init>>")
    assert info["basis"].endswith("|area-bootstrap:pound_init")

    row2 = {
        "kind": "beastCombatInit",
        "passage": "Bird Tower Sleep Sex",
        "token": "unknown",
    }
    bodies2 = {
        "Bird Tower Sleep Sex": "<<beastCombatInit>>",
        "Bird Tower": "<<beastNEWinit 1 wolf>>\n[[Next|Bird Tower Sleep Sex]]",
    }
    info2 = combat_sweep.derive_precursor(row2, passage_bodies=bodies2)
    assert info2["widgets"].startswith("<<bird_init>>")
    assert info2["basis"].endswith("|area-bootstrap:bird_init")

    # Bird Hunt 系列同样依赖 $bird.hunts（flight_hunt_return 读 duo）
    row3 = {
        "kind": "maninit",
        "passage": "Bird Hunt Tent Steal Group Fight",
        "token": "",
    }
    bodies3 = {
        "Bird Hunt Tent Steal Group Fight": "<<maninit>>",
        "Bird Hunt Tent Steal Run": "<<generate1>><<generate2>><<set $fightstart to 1>>\n[[Next|Bird Hunt Tent Steal Group Fight]]",
    }
    info3 = combat_sweep.derive_precursor(row3, passage_bodies=bodies3, named_npcs=[])
    assert info3["widgets"].startswith("<<bird_init>>")
    assert info3["basis"].endswith("|area-bootstrap:bird_init")


def test_area_bootstrap_prison_seeds_anxious_guard() -> None:
    """Prison 行要带 $prison_intro=1 与 slot 0 的 anxious guard 存档。"""
    row = {
        "kind": "beastCombatInit",
        "passage": "Prison Spire Work Fight",
        "token": "unknown",
    }
    bodies = {
        "Prison Spire Work Fight": "<<beastCombatInit>>",
        "Prison Spire Work": "<<beastNEWinit 2 hawk>>\n[[Next|Prison Spire Work Fight]]",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"].startswith("<<prison_init>><<set $prison_intro to 1>>")
    assert '<<generateRole 0 "anxious" "guard">>' in info["widgets"]
    assert info["basis"].endswith("|area-bootstrap:prison_init+anxious_guard")


def test_area_bootstrap_skips_unmatched_passages() -> None:
    row = {"kind": "beastCombatInit", "passage": "Docks Watch Dog", "token": "unknown"}
    bodies = {
        "Docks Watch Dog": "<<beastCombatInit>>",
        "Docks": "<<beastNEWinit 1 dog>>\n[[Next|Docks Watch Dog]]",
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"] == "<<beastNEWinit 1 dog>>"
    assert "area-bootstrap" not in (info["basis"] or "")


def test_area_bootstrap_requires_chain() -> None:
    """没有野兽链时只加区域状态没有意义，不能给出假前驱。"""
    row = {"kind": "beastCombatInit", "passage": "Pound Mystery", "token": "unknown"}
    info = combat_sweep.derive_precursor(
        row, passage_bodies={"Pound Mystery": "<<beastCombatInit>>"}
    )
    assert info["widgets"] is None
    assert info["basis"] is None


def test_status_bootstrap_replays_event_chain_state() -> None:
    """1007i 剩余 fi 行：Finish 依赖的事件链状态由游戏自身初始化重放补齐。"""
    row = {"kind": "maninit", "passage": "Bailey Sheet Fight", "token": ""}
    bodies = {
        "Bailey Sheet Fight": "<<maninit>>",
        "Harvest Street": (
            '<<generateRole 0 0 "thug">><<set $fightstart to 1>>\n'
            "[[Next|Bailey Sheet Fight]]"
        ),
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert info["widgets"].startswith(
        "<<set $pubfame to {seen: [], tasksDone: []}>>"
        '<<set $pubfame.status to "accepted">>'
    )
    assert "<<set $pubfame.bailey to {}>>" in info["widgets"]
    assert '<<set $pubfame.bailey.fight to "ready">>' in info["widgets"]
    assert info["basis"].endswith("|status-bootstrap:pubfame-bailey")

    row2 = {"kind": "maninit", "passage": "Hospital Keycard Seduce Sex", "token": ""}
    bodies2 = {
        "Hospital Keycard Seduce Sex": "<<maninit>>",
        "Hospital Keycard Seduce": (
            "<<generate1>><<generate2>><<set $sexstart to 1>>\n"
            "[[Next|Hospital Keycard Seduce Sex]]"
        ),
    }
    info2 = combat_sweep.derive_precursor(row2, passage_bodies=bodies2)
    assert info2["widgets"].startswith("<<set $pubfame to {seen: [], tasksDone: []}>>")
    assert '<<set $pubfame.task to "hospital">>' in info2["widgets"]
    assert "<<set $pubfame.hospital to {}>>" in info2["widgets"]
    assert info2["basis"].endswith("|status-bootstrap:pubfame-hospital")

    row3 = {"kind": "maninit", "passage": "Farm Assault Fight Bailey", "token": ""}
    bodies3 = {
        "Farm Assault Fight Bailey": "<<maninit>>",
        "Farm Assault Intercept Bailey": (
            "<<generate1>><<generate2>><<set $fightstart to 1>>\n"
            "[[Next|Farm Assault Fight Bailey]]"
        ),
    }
    info3 = combat_sweep.derive_precursor(row3, passage_bodies=bodies3)
    assert info3["widgets"].startswith(
        '<<set $bus to "yard">><<if $farm is undefined>><<set $farm to {}>><</if>>'
        "<<farm_assault_init>>"
    )
    assert info3["basis"].endswith("|status-bootstrap:farm_assault_init")

    row4 = {"kind": "maninit", "passage": "Island Wood Rape", "token": ""}
    bodies4 = {
        "Island Wood Rape": "<<maninit>>",
        "Widgets Island": (
            "<<generateRole 0 0 \"islander\">><<set $molestationstart to 1>>\n"
            "[[Next|Island Wood Rape]]"
        ),
    }
    info4 = combat_sweep.derive_precursor(row4, passage_bodies=bodies4)
    assert info4["widgets"].startswith(
        "<<island_init>><<if $island.wood is undefined>><<set $island.wood to 0>><</if>>"
    )
    assert info4["basis"].endswith("|status-bootstrap:island_init")

    row5 = {"kind": "maninit", "passage": "Street Car Sex", "token": ""}
    bodies5 = {
        "Street Car Sex": "<<maninit>>",
        "Widgets Street": (
            "<<generatey1>><<generatey2>><<set $sexstart to 1>>\n"
            "[[Next|Street Car Sex]]"
        ),
    }
    info5 = combat_sweep.derive_precursor(row5, passage_bodies=bodies5)
    assert info5["widgets"].startswith(
        '<<if $bus is undefined>><<set $bus to "commercial">><</if>>'
    )
    assert '<<set $location to "alley">>' in info5["widgets"]
    assert info5["basis"].endswith("|status-bootstrap:street-bus")

    row6 = {"kind": "maninit", "passage": "Temple Confess Sydney Sex", "token": ""}
    bodies6 = {
        "Temple Confess Sydney Sex": "<<maninit>>",
        "Temple Confess": (
            "<<generatey1>><<generateyp2>><<set $sexstart to 1>>\n"
            "[[Next|Temple Confess Sydney Sex]]"
        ),
    }
    info6 = combat_sweep.derive_precursor(row6, passage_bodies=bodies6)
    assert info6["widgets"].startswith(
        "<<set C.npc.Sydney.init to 1>>"
        "<<if $sydneySeen is undefined>><<set $sydneySeen to []>><</if>>"
    )
    assert info6["basis"].endswith("|status-bootstrap:sydney-init")


def test_status_bootstrap_street_car_word_boundary() -> None:
    """``^Street Car\\b`` 不能误匹配 Street Cardboard Box 系列。"""
    row = {
        "kind": "beastCombatInit",
        "passage": "Street Cardboard Box Cat Sex",
        "token": "unknown",
    }
    bodies = {
        "Street Cardboard Box Cat Sex": "<<beastCombatInit>>",
        "Street Cardboard Box": (
            "<<beastNEWinit 1 cat>>\n[[Next|Street Cardboard Box Cat Sex]]"
        ),
    }
    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)
    assert "status-bootstrap" not in (info["basis"] or "")


def test_resolve_only_keys_accepts_file_and_csv(tmp_path: Path) -> None:
    key_file = tmp_path / "keys.json"
    key_file.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert combat_sweep.resolve_only_keys(str(key_file)) == ["a", "b"]
    line_file = tmp_path / "keys.txt"
    line_file.write_text("a\nb\n", encoding="utf-8")
    assert combat_sweep.resolve_only_keys(str(line_file)) == ["a", "b"]
    assert combat_sweep.resolve_only_keys("a,b") == ["a", "b"]
    assert combat_sweep.resolve_only_keys(None) is None


# --------------------------------------------------------------------------- #
# Control-mode entry fidelity and scripted scene endings
# --------------------------------------------------------------------------- #


def test_pick_mode_entry_falls_back_when_rows_carry_no_path() -> None:
    """Initiator rows have no path; the beast preference must still win."""
    jobs = [
        {"key": "a", "kind": "maninit"},
        {"key": "b", "kind": "beastCombatInit"},
    ]

    assert pick_mode_entry(jobs)["key"] == "b"
    assert pick_mode_entry(jobs[:1])["key"] == "a"


def test_run_control_modes_replays_the_entry_precursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the generation chain the mode check would read a 5-key NPCList."""
    calls: list[object] = []

    def fake_enter_row(page, row, *, timeout_ms, settle_ms=500, precursor=None):  # noqa: ANN001
        calls.append(precursor)
        return {"ok": False, "verdict": "fixture_insufficient", "detail": "stub"}

    monkeypatch.setattr(combat_sweep, "enter_row", fake_enter_row)
    monkeypatch.setattr(combat_sweep, "_state", lambda page: {"combat": 0})
    monkeypatch.setattr(combat_sweep, "set_control_mode", lambda page, mode: {"ok": True})

    precursor = {"widgets": "<<generate1>><<person1>>", "basis": "debug-menu:generate1+person1"}
    entry = {"key": "maninit:-:Balloon Sex", "kind": "maninit", "precursor": precursor}
    records = combat_sweep.run_control_modes(object(), entry, rounds=3, timeout_ms=1000)

    assert len(records) == len(CONTROL_MODES)
    assert calls == [precursor] * len(CONTROL_MODES)


def test_run_control_modes_prefers_an_explicit_precursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def fake_enter_row(page, row, *, timeout_ms, settle_ms=500, precursor=None):  # noqa: ANN001
        calls.append(precursor)
        return {"ok": False, "verdict": "fixture_insufficient", "detail": "stub"}

    monkeypatch.setattr(combat_sweep, "enter_row", fake_enter_row)
    monkeypatch.setattr(combat_sweep, "_state", lambda page: {"combat": 0})
    monkeypatch.setattr(combat_sweep, "set_control_mode", lambda page, mode: {"ok": True})

    entry = {"key": "k", "kind": "maninit", "precursor": {"widgets": "<<generate1>>"}}
    explicit = {"widgets": "<<beastNEWinit 1 dog>>"}
    combat_sweep.run_control_modes(
        object(), entry, rounds=1, timeout_ms=1000, precursor=explicit
    )

    assert calls == [explicit] * len(CONTROL_MODES)


def test_scripted_end_evidence_reads_the_combat_passage_guard() -> None:
    bodies = {
        "Underground Film Molestation": (
            "<<if _combatend or $timer lte 0>>\n"
            '\t<span id="next"><<link [[Next|Underground Film Molestation Finish]]>><</link>></span>\n'
            "<<else>>\n"
            '\t<span id="next"><<link [[Next|Underground Film Molestation]]>><</link>></span>\n'
            "<</if>>"
        ),
    }

    evidence = combat_sweep.scripted_end_evidence(
        {"combat": 1, "passage": "Underground Film Molestation"},
        "Underground Film Molestation Finish",
        bodies,
    )

    assert evidence is not None
    assert "_combatend or $timer lte 0" in evidence


def test_scripted_end_evidence_ignores_unguarded_and_missing_sources() -> None:
    bodies = {"A": '<<link [[Next|B]]>><</link>>', "B": "<<endcombat>>"}

    assert combat_sweep.scripted_end_evidence({"combat": 1, "passage": "A"}, "B", bodies) is None
    assert combat_sweep.scripted_end_evidence({"combat": 1, "passage": "A"}, "B", {}) is None
    assert combat_sweep.scripted_end_evidence(None, "B", bodies) is None
    assert combat_sweep.scripted_end_evidence({"combat": 1, "passage": "B"}, "B", bodies) is None


def test_classify_outcome_records_scene_end_without_enemy_defeat() -> None:
    state = {
        "combat": 0,
        "passage": "Underground Film Molestation Finish",
        "enemyhealth": 158.8571428571429,
        "enemyarousal": 410.66,
        "enemyarousalmax": 500,
    }

    outcome, detail = classify_outcome(
        state,
        path="win",
        rounds=24,
        max_rounds=80,
        stalled=False,
        last_active={"combat": 1, "passage": "Underground Film Molestation"},
        landing_passage="Underground Film Molestation Finish",
        scripted_end="Underground Film Molestation exits under <<if _combatend or $timer lte 0>>",
    )

    assert outcome == "scene_end"
    assert "enemy not defeated" in detail
    assert "Underground Film Molestation Finish" in detail
    assert "scene_end" not in combat_sweep.EXPECTED_OUTCOME_ACCEPTS["win"]


def test_derive_precursor_replays_the_predecessor_slot_chain() -> None:
    """Underground Robin Kiss prints <<person4>> with $enemyno 2."""
    row = {
        "kind": "maninit",
        "passage": "Underground Robin Kiss Molestation",
        "token": "",
    }
    bodies = {
        "Underground Robin Kiss Molestation": (
            "<<set $enemyno to 2>><<maninit>>\nThe <<person4>><<person>> films you.\n"
        ),
        "Underground Robin Kiss Intro": (
            "<<generate1>><<npc Robin 2>><<generate3>><<generate4>>"
            "<<link [[Next|Underground Robin Kiss Molestation]]>><</link>>"
        ),
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["widgets"] == "<<generate1>><<npc Robin 2>><<generate3>><<generate4>>"
    assert "predecessor:Underground Robin Kiss Intro" in info["basis"]
    assert "(person4)" in info["basis"]


def test_derive_precursor_falls_back_when_no_chain_exists() -> None:
    row = {"kind": "maninit", "passage": "Lonely Room", "token": ""}
    bodies = {
        "Lonely Room": (
            "<<set $enemyno to 1>><<maninit>>The <<person3>><<person>> watches."
        )
    }

    info = combat_sweep.derive_precursor(row, passage_bodies=bodies)

    assert info["widgets"] == (
        "<<generate1>><<generate2>><<generate3>>"
        "<<person1>><<person2>><<person3>>"
    )
    assert info["basis"] == "debug-menu:generate1..3+person1..3(person3)"


def test_derive_precursor_keeps_single_slot_default_without_person_refs() -> None:
    row = {"kind": "maninit", "passage": "Plain Fight", "token": ""}
    info = combat_sweep.derive_precursor(
        row, passage_bodies={"Plain Fight": "<<maninit>>"}
    )

    assert info["widgets"] == "<<generate1>><<person1>>"
    assert info["basis"] == "debug-menu:generate1+person1"


def test_maninit_slot_chain_requires_a_contiguous_run() -> None:
    body = "<<generate1>><<person1>>\nprose in between\n<<generate2>>"

    assert combat_sweep._maninit_slot_chain(body, None, 1) == {
        "widgets": "<<generate1>>",
        "slots": 1,
    }
    # ``<<generate2>>`` alone fills index 1; index 0 would stay a fixture shell,
    # and ``combatinit`` marks that shell ``active`` before ``personselect 0``
    # reads it.
    assert combat_sweep._maninit_slot_chain("<<generate2>>", None, 2) is None
    assert combat_sweep._maninit_slot_chain(body, None, 3) is None


def test_maninit_slot_chain_reads_npc_name_indices() -> None:
    body = "<<generate1>><<npc Robin 2>>"
    assert combat_sweep._maninit_slot_chain(body, None, 2) == {
        "widgets": "<<generate1>><<npc Robin 2>>",
        "slots": 2,
    }
    # ``<<npc Robin 2>>`` writes row 2 (index 1); on its own row 1 stays a shell.
    assert combat_sweep._maninit_slot_chain("<<clearnpc>><<npc Robin 2>>", None, 2) is None


def test_maninit_slot_chain_counts_beast_and_police_generators() -> None:
    assert combat_sweep._maninit_slot_chain(
        "<<beastNEWinit 1 dog>><<generate2>><<generate3>>", None, 3
    ) == {
        "widgets": "<<beastNEWinit 1 dog>><<generate2>><<generate3>>",
        "slots": 3,
    }
    assert combat_sweep._maninit_slot_chain(
        "<<generatePolice 1>><<generatePolice 2>>", None, 2
    ) == {
        "widgets": "<<generatePolice 1>><<generatePolice 2>>",
        "slots": 2,
    }


def test_maninit_slot_chain_prefers_the_contiguous_branch() -> None:
    body = (
        "<<beastNEWinit 1 dog>>\n"
        "<<if $rng gte 51>><<generate2>><<generate3>><<person2>>night<</if>>\n"
        "<<else>><<generate1>><<generate2>><<person1>>day<</if>>"
        "<<link [[Next|Street Collar Molestation]]>><</link>>"
    )

    chain = combat_sweep._maninit_slot_chain(body, "Street Collar Molestation", 2)

    # The night run fills indices 1-2 only; the day run fills 0-1 and wins.
    assert chain == {"widgets": "<<generate1>><<generate2>>", "slots": 2}


def test_classify_entry_errors_names_the_missing_npc_slot() -> None:
    errors = [
        {
            "kind": "sugarcube.dom",
            "message": (
                "0.5.11.9 出错 (:: Underground Robin Kiss Molestation): "
                "<<person4>>: errors within widget code "
                "(<<personselect>>: errors within widget code "
                "(Undefined NPC in personselect 3.))"
            ),
        }
    ]

    verdict, detail, missing = classify_entry_errors(errors)

    assert verdict == "hard_fail"
    assert "Undefined NPC" in detail
    # ``personselect`` receives the raw ``$NPCList`` index (0-5 for NPCs 1-6),
    # so ``personselect 3`` is ``$NPCList[3]`` (rendered by ``<<person4>>``).
    assert "NPCList[3]" in missing


def test_classify_entry_errors_maps_personselect_zero_to_first_slot() -> None:
    errors = [
        {
            "kind": "sugarcube.dom",
            "message": "<<person1>>: Undefined NPC in personselect 0.",
        }
    ]

    verdict, _detail, missing = classify_entry_errors(errors)

    assert verdict == "hard_fail"
    assert "NPCList[0]" in missing
