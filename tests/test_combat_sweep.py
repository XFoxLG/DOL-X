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

import html
import json
from pathlib import Path

import pytest

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
