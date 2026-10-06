#!/usr/bin/env python3
"""DOL-X combat-axis sweep (engine A: local headless Chromium on the built HTML).

The story axis (``tools/scenario_sweep.py``) answers "does the debug menu walk
the story". This tool answers the orthogonal question: "does every combat
initiator in the artifact actually start a fight, and can the fight be driven
to an ending through the real DOM?"

Two tiers
---------

``--tier archetypes`` (daily, ~15-20 min)
    A static scan of the artifact builds one entry per enemy archetype
    (human / named NPC / dog..snake beasts / tentacle / swarm / wraith /
    stalk / vore / machine / possession / plant / hypno), then each archetype
    is driven through four intent paths (win / lose / flee / submit). The same
    run also exercises all four combat control modes (Radio / Radio (c) /
    Lists / List (w)) for >= 3 real rounds each.

``--tier initiators`` (release, 1.5-2.5 h)
    Every deduplicated initiator row from the static manifest is restored,
    entered, and - if ``$combat`` becomes 1 - driven to an ending with a
    per-round cap (default 80). Entries that cannot be entered are classified
    ``fixture_insufficient`` together with the missing symbols; nothing is
    silently skipped.

Entry strategy (measured, 2026-10-04)
-------------------------------------
Upstream guards every combat scene behind ``<<if $molestationstart is 1>>``
(rape flow) or ``<<if $sexstart is 1>>`` (consensual flow), and the synthetic
bootstrap fixture carries both at 0. Playing the initiator passage alone
therefore renders the scene but never starts combat. The driver sets the flow
flag first, then plays the passage; this is strictly stronger than the memo's
``Engine.play(passage)`` recipe and is recorded per result
(``entry_flag`` = the flag that actually produced ``$combat=1``).

Round driving (measured, 2026-10-04)
------------------------------------
* ``Radio`` / ``Radio (c)``: actions are ``#listContainer input.macro-radiobutton``
  grouped per body part; click the chosen input, then press Enter.
* ``Lists`` / ``List (w)``: after one turn renders under the new mode, actions
  are ``<select id="listbox-<action>">`` listboxes (no radiobuttons); pick the
  option, then press Enter.
* ``#cbtToggleMenu`` hosts ``#listbox-optionscombatcontrols`` whose option
  values are ``0..3`` and whose texts are ``Radio / Radio (c) / Lists /
  List (w)``. Switching the mode only re-renders the action DOM on the next
  turn, so the driver submits one turn after the switch and then asserts the
  new DOM kind. The default mode is restored at the end of the run.

Verdicts: ``ok / soft_fail / hard_fail / fixture_insufficient / not_applicable``.
Reports are JSON + Markdown under ``.local/sweep/combat-<tier>-<date>/`` and
can be sealed/diffed against ``.local/sweep/baselines/``. Nothing here touches
``lyra/``, ``config/`` or any build input: injection is runtime-only.

Usage:
    python tools/combat_sweep.py <target.html|zip> --tier archetypes --limit 2
    python tools/combat_sweep.py <target.html|zip> --tier initiators --resume
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html as html_mod
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import fixture_ladder as fl  # noqa: E402
from tools import passage_sweep as ps  # noqa: E402
from tools import sweep_flow_assertions as sfa  # noqa: E402
from tools import sweep_ledger as sl  # noqa: E402


TOOL = "combat_sweep"
DEFAULT_OUT_ROOT = Path(".local/sweep")
DEFAULT_BASELINE_DIR = Path(".local/sweep/baselines")
DEFAULT_FIXTURE = Path(".local/fixtures/base-1004.json")
DEFAULT_MANIFEST_OUT = Path(".local/sweep/combat-initiators.json")
DEFAULT_LEDGER_NAME = "combat-sweep-ledger.json"
DEFAULT_TIER = "archetypes"
TIERS = ("archetypes", "initiators")
DEFAULT_MAX_ROUNDS = 80
DEFAULT_MODE_ROUNDS = 3
DEFAULT_ENTRY_SETTLE_MS = 500
DEFAULT_TURN_SETTLE_MS = 900
# Upper bound for "a turn rendered something" waits. Combat actions submit on
# ``click``/``select``, so the render is usually already in flight when Enter
# lands. In-place combat updates do not bump ``renderSeq``, so this cap (plus
# ``DEFAULT_TURN_SETTLE_MS``) is the normal per-round cost.
TURN_WAIT_MS = 2000
STALL_ROUNDS = 3

VERDICTS = ("ok", "soft_fail", "hard_fail", "fixture_insufficient", "not_applicable")
VERDICT_SEVERITY = {
    "ok": 0,
    "not_applicable": 1,
    "fixture_insufficient": 2,
    "soft_fail": 3,
    "hard_fail": 4,
}

# The 2026-10-04 ground truth measured by the parent agent. Numbers/口径 drifted
# during re-measurement; the tool never absorbs them silently, it reports the
# difference in ``manifest.drift``.
EXPECTED_INITIATORS: dict[str, Any] = {
    "total": 1603,
    "by_kind": {
        "maninit": 897,
        "beastNEWinit": 223,
        "beastCombatInit": 211,
        "tentacle": 93,
        "hypno": 88,
        "wraith": 64,
        "machine": 27,
        "swarm": 25,
        "stalk": 25,
        "plant": 24,
        "vore": 17,
        "possession": 4,
    },
    "by_token": {
        "dog": 104,
        "wolf": 54,
        "horse": 52,
        "pig": 29,
        "cat": 21,
        "fox": 18,
        "lizard": 11,
        "hawk": 10,
        "cow": 8,
        "bear": 5,
        "spider": 3,
        "boar": 3,
        "dolphin": 2,
        "snake": 1,
    },
}

CONTROL_MODES = ("Radio", "Radio (c)", "Lists", "List (w)")
DEFAULT_CONTROL_MODE = "Radio"
# Measured on the artifact: the listbox option value is the index and the text
# is the UI label; the SugarCube variable receives the mode string below.
CONTROL_MODE_TEXTS = {
    "Radio": "Radio",
    "Radio (c)": "Radio (c)",
    "Lists": "Lists",
    "List (w)": "List (w)",
}
CONTROL_MODE_VALUES = {
    "Radio": "radio",
    "Radio (c)": "columnRadio",
    "Lists": "lists",
    "List (w)": "limitedLists",
}
CONTROL_MODE_DOM = {
    "Radio": "radio",
    "Radio (c)": "radio",
    "Lists": "select",
    "List (w)": "select",
}

ARCHETYPE_PATHS = ("win", "lose", "flee", "submit")
# Preference keyword tables (bilingual). First match wins; the driver falls back
# to the first available action and records ``fallback: true``.
PATH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "win": ("攻击", "击打", "踢", "拳", "咬", "attack", "hit", "kick", "punch", "strike"),
    "lose": ("承受", "忍耐", "不动", "endure", "bear", "wait", "rest"),
    "flee": ("逃跑", "逃离", "离开", "flee", "escape", "leave", "run"),
    "submit": ("顺从", "服从", "屈服", "接受", "submit", "accept", "yield"),
}


# --------------------------------------------------------------------------- #
# Static initiator scan
# --------------------------------------------------------------------------- #

PASSAGE_BLOCK_RE = re.compile(
    r'<tw-passagedata\b[^>]*name="([^"]*)"[^>]*>(.*?)</tw-passagedata>',
    re.DOTALL,
)

# kind -> concrete Twine macro names that count as that encounter's initiator.
# Kept as an explicit allowlist so the manifest口径 is auditable (the artifact
# names the helper widgets actionstentacles/statetentacles/... which are NOT
# entry points).
INITIATOR_MACROS: dict[str, tuple[str, ...]] = {
    "maninit": ("maninit",),
    "beastNEWinit": ("beastNEWinit",),
    "beastCombatInit": ("beastCombatInit",),
    "tentacle": ("tentaclestart", "tentacleinit", "tentacleworldintro"),
    "hypno": ("gwylanCombatInit", "AsylumHypnosisCommon", "shopHuntGwylanHypnotise"),
    "wraith": ("initWraith", "startWraith", "generateWraith", "rainWraith"),
    "machine": ("machine_init", "machine_combat", "machine_actions"),
    "swarm": ("swarminit", "swarmeffects", "swarm", "swarmactions"),
    "stalk": ("stalk_init", "stalk_pursuit", "gwylanStalkInit", "streetSoloStalk"),
    "plant": ("generatePlant1", "plantup", "plantupper", "plantlower", "clothesonplant"),
    "vore": ("vore", "seavore"),
    "possession": ("possessedWord",),
}
KIND_ORDER = tuple(INITIATOR_MACROS)
MACRO_TO_KIND = {
    macro: kind for kind, macros in INITIATOR_MACROS.items() for macro in macros
}
BEAST_KINDS = ("beastNEWinit", "beastCombatInit")

# Words that appear in beast initiator args but are not the beast type.
BEAST_ARG_NOISE = {
    "m", "f", "h", "w", "penis", "monster", "beast", "t", "true", "false",
    "and", "or", "is", "to", "the", "countwith", "count", "a", "args",
}

# Macros that actually flip ``$combat`` to 1 (verified against Widgets NPCs /
# Widgets Machine / Widgets Tentacles / Widgets Wraith / Widgets Swarm).
COMBAT_STARTER_MACROS = (
    "maninit",
    "beastCombatInit",
    "machine_init",
    "tentaclestart",
    "initWraith",
    "swarminit",
    "stalk_init",
    "vore",
    "generatePlant1",
    "possessedWord",
    "gwylanCombatInit",
)

ENTRY_FLAGS = ("molestationstart", "sexstart")
ENTRY_FLAG_ATTEMPTS: tuple[tuple[str, ...], ...] = (
    ("molestationstart",),
    ("sexstart",),
    ("molestationstart", "sexstart"),
)

MACRO_CALL_RE = re.compile(r"<<([A-Za-z_][A-Za-z0-9_]*)([^>]*)>>")
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
LINK_WIDGET_RE = re.compile(r"<<link\s+\[\[([^\]|]*)(?:\|([^\]]*))?\]\][^>]*>>")


def parse_beast_token(args: str) -> str:
    """Extract the beast type from a ``beastNEWinit`` / ``beastCombatInit`` arg list."""
    cleaned = str(args or "").strip()
    if not cleaned:
        return "unknown"
    if "`" in cleaned or "$" in cleaned:
        return "dynamic"
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
        low = token.lower()
        if low in BEAST_ARG_NOISE:
            continue
        return low
    return "unknown"


def initiator_key(kind: str, token: str | None, passage: str) -> str:
    return f"{kind}:{token or '-'}:{passage}"


def rows_passage_bodies(rows: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Read the ``_passage_bodies`` map injected by ``run`` (tests: empty)."""
    for row in rows:
        payload = row.get("_passage_bodies")
        if isinstance(payload, dict):
            result = {str(k): str(v) for k, v in payload.items()}
            return result
    return {}


def find_combat_link_target(
    row: dict[str, Any],
    passage_bodies: Mapping[str, str],
    *,
    max_depth: int = 2,
) -> str | None:
    """Follow one in-passage link from ``row`` to a passage that starts combat.

    Weak static rows (e.g. ``beastNEWinit`` without ``beastCombatInit`` in
    ``Farmland Pigs``) only generate the beast; the fight starts on the linked
    passage. Deterministic: first link (document order) whose target passage
    contains a combat starter macro wins; the original row wins on ties.
    """
    source = str(row.get("passage") or "")
    body = passage_bodies.get(source)
    if not body:
        return None
    def link_targets(body: str) -> list[str]:
        targets: list[str] = []
        for pattern in (WIKI_LINK_RE, LINK_WIDGET_RE):
            for match in pattern.finditer(body):
                target_name = str(match.group(2) or match.group(1)).strip()
                if target_name:
                    targets.append(target_name)
        return targets

    def walk(current: str, depth: int, seen: frozenset[str]) -> str | None:
        if depth == 0:
            return None
        body = passage_bodies.get(current)
        if not body:
            return None
        for target_name in link_targets(body):
            if target_name == current or target_name in seen:
                continue
            target_body = passage_bodies.get(target_name)
            if target_body and _combat_starters_for(target_body):
                return target_name
            found = walk(target_name, depth - 1, seen | {current})
            if found:
                return found
        return None

    return walk(source, max_depth, frozenset())


def _is_named_beast_token(token: str) -> bool:
    """True for a concrete beast name (not empty / unknown / dynamic)."""
    return bool(token) and token not in ("unknown", "dynamic")


def _entry_flags_for(body: str) -> list[str]:
    return [flag for flag in ENTRY_FLAGS if f"${flag} is 1" in body]


def _combat_starters_for(body: str) -> list[str]:
    return [macro for macro in COMBAT_STARTER_MACROS if f"<<{macro}" in body]


def scan_initiators(html_text: str) -> dict[str, Any]:
    """Scan the raw artifact HTML for combat initiator macro calls.

    Input is the 82MB ``tw-passagedata`` document text (HTML-entity escaped,
    exactly what ``ps._html_payload`` returns). Output is JSON-safe and shallow,
    so it can be written straight to ``.local/sweep/combat-initiators.json``.
    """
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    passages: set[str] = set()
    for raw_name, raw_body in PASSAGE_BLOCK_RE.findall(html_text):
        name = html_mod.unescape(raw_name)
        body = html_mod.unescape(raw_body)
        entry_flags = _entry_flags_for(body)
        starters = _combat_starters_for(body)
        calls: list[tuple[str, str, str, str]] = []
        for match in MACRO_CALL_RE.finditer(body):
            kind = MACRO_TO_KIND.get(match.group(1))
            if kind is None:
                continue
            args = match.group(2).strip()
            token = parse_beast_token(args) if kind in BEAST_KINDS else ""
            calls.append((kind, match.group(1), args, token))

        # Token-less ``beastCombatInit`` / ``beastNEWinit`` read the upstream
        # ``$beasttype``: prefer the nearest preceding explicit beast token in
        # the same passage, then the passage's first explicit one.
        first_token = next((t for _, _, _, t in calls if _is_named_beast_token(t)), "")
        last_token = ""
        for kind, macro, args, token in calls:
            if kind in BEAST_KINDS:
                if token == "unknown":
                    token = last_token or first_token or token
                elif _is_named_beast_token(token):
                    last_token = token
            dedupe = (kind, token, name)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            rows.append(
                {
                    "key": initiator_key(kind, token, name),
                    "kind": kind,
                    "token": token,
                    "passage": name,
                    "macro": macro,
                    "args": args[:160],
                    "entry_flags": list(entry_flags),
                    "combat_starters": list(starters),
                }
            )
            passages.add(name)

    rows.sort(key=lambda r: (KIND_ORDER.index(r["kind"]), r["token"], r["passage"]))
    by_kind: dict[str, int] = collections.OrderedDict(
        (kind, 0) for kind in KIND_ORDER
    )
    by_token: dict[str, int] = collections.OrderedDict()
    for row in rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        if row["kind"] in BEAST_KINDS and row["token"]:
            by_token[row["token"]] = by_token.get(row["token"], 0) + 1

    drift = _initiator_drift(len(rows), by_kind, by_token)
    return {
        "ok": True,
        "rows": rows,
        "total": len(rows),
        "by_kind": by_kind,
        "by_token": by_token,
        "passages": len(passages),
        "expected": EXPECTED_INITIATORS,
        "drift": drift,
        "macro_names": {kind: list(macros) for kind, macros in INITIATOR_MACROS.items()},
    }


def _initiator_drift(
    total: int, by_kind: dict[str, int], by_token: dict[str, int]
) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    if total != EXPECTED_INITIATORS["total"]:
        differences.append(
            {"field": "total", "expected": EXPECTED_INITIATORS["total"], "actual": total}
        )
    for kind, expected in EXPECTED_INITIATORS["by_kind"].items():
        actual = int(by_kind.get(kind, 0))
        if actual != expected:
            differences.append(
                {"field": f"by_kind.{kind}", "expected": expected, "actual": actual}
            )
    for token, expected in EXPECTED_INITIATORS["by_token"].items():
        actual = int(by_token.get(token, 0))
        if actual != expected:
            differences.append(
                {"field": f"by_token.{token}", "expected": expected, "actual": actual}
            )
    return {"ok": not differences, "differences": differences, "count": len(differences)}


# --------------------------------------------------------------------------- #
# Archetype matrix
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ArchetypeSpec:
    key: str
    label: str
    category: str
    kind: str
    token: str | None = None
    passage_keywords: tuple[str, ...] = ()


# 28 archetypes: 1 human, 4 named NPC, 14 beasts, 9 specials.
ARCHETYPE_SPECS: tuple[ArchetypeSpec, ...] = (
    ArchetypeSpec("human-street", "街头男性", "human", "maninit"),
    ArchetypeSpec("named-bailey", "Bailey", "named", "maninit", passage_keywords=("Bailey",)),
    ArchetypeSpec("named-whitney", "Whitney", "named", "maninit", passage_keywords=("Whitney",)),
    ArchetypeSpec("named-kylar", "Kylar", "named", "maninit", passage_keywords=("Kylar",)),
    ArchetypeSpec("named-leighton", "Leighton", "named", "maninit", passage_keywords=("Leighton",)),
    ArchetypeSpec("beast-dog", "狗", "beast", "beastNEWinit", "dog"),
    ArchetypeSpec("beast-wolf", "狼", "beast", "beastNEWinit", "wolf"),
    ArchetypeSpec("beast-horse", "马", "beast", "beastNEWinit", "horse"),
    ArchetypeSpec("beast-pig", "猪", "beast", "beastNEWinit", "pig"),
    ArchetypeSpec("beast-cat", "猫", "beast", "beastNEWinit", "cat"),
    ArchetypeSpec("beast-fox", "狐", "beast", "beastNEWinit", "fox"),
    ArchetypeSpec("beast-lizard", "蜥蜴", "beast", "beastNEWinit", "lizard"),
    ArchetypeSpec("beast-hawk", "鹰", "beast", "beastNEWinit", "hawk"),
    ArchetypeSpec("beast-cow", "牛", "beast", "beastNEWinit", "cow"),
    ArchetypeSpec("beast-bear", "熊", "beast", "beastNEWinit", "bear"),
    ArchetypeSpec(
        "beast-spider",
        "蜘蛛",
        "beast",
        "beastNEWinit",
        "spider",
        passage_keywords=("Catacombs",),
    ),
    ArchetypeSpec("beast-boar", "野猪", "beast", "beastNEWinit", "boar"),
    ArchetypeSpec(
        "beast-dolphin",
        "海豚",
        "beast",
        "beastNEWinit",
        "dolphin",
        passage_keywords=("Widgets Sea", "Beast Train"),
    ),
    ArchetypeSpec("beast-snake", "蛇", "beast", "beastNEWinit", "snake"),
    ArchetypeSpec("special-tentacle", "触手", "special", "tentacle"),
    ArchetypeSpec("special-swarm", "蜂群", "special", "swarm"),
    ArchetypeSpec("special-wraith", "怨灵", "special", "wraith"),
    ArchetypeSpec("special-stalk", "潜行", "special", "stalk"),
    ArchetypeSpec("special-vore", "吞噬", "special", "vore"),
    ArchetypeSpec("special-machine", "机械", "special", "machine"),
    ArchetypeSpec("special-possession", "附身", "special", "possession"),
    ArchetypeSpec("special-plant", "植物", "special", "plant"),
    ArchetypeSpec("special-hypno", "催眠", "special", "hypno"),
)


def spec_matches(row: dict[str, Any], spec: ArchetypeSpec) -> bool:
    if str(row.get("kind")) != spec.kind:
        return False
    if spec.token is not None and str(row.get("token")) != spec.token:
        return False
    if spec.passage_keywords:
        passage = str(row.get("passage") or "")
        if not any(kw.lower() in passage.lower() for kw in spec.passage_keywords):
            return False
    return True


def choose_entry(
    rows: Sequence[dict[str, Any]],
    spec: ArchetypeSpec,
    passage_bodies: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    """Deterministically pick the most enterable row for one archetype spec."""
    pool = [row for row in rows if spec_matches(row, spec)]
    if not pool:
        return None

    def link_depth(row: dict[str, Any]) -> int:
        if not passage_bodies:
            return 9
        for depth in (0, 1, 2, 3):
            if depth == 0:
                if row.get("combat_starters"):
                    return depth
                continue
            if find_combat_link_target(row, passage_bodies, max_depth=depth):
                return depth
        return 9

    def rank(row: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
        # ``Widgets *`` passages are the game's widget libraries: they carry many
        # initiator macros but only render when invoked from a real passage, so
        # ``Engine.play`` on them never flips ``$combat``.
        library = 1 if str(row.get("passage") or "").startswith("Widgets") else 0
        starters = len(row.get("combat_starters") or [])
        flags = len(row.get("entry_flags") or [])
        return (
            library,
            link_depth(row),
            -starters,
            -flags,
            len(str(row.get("passage") or "")),
            str(row.get("passage") or ""),
        )

    return sorted(pool, key=rank)[0]


def build_archetype_jobs(
    rows: Sequence[dict[str, Any]],
    *,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20261004,
    passage_bodies: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Expand the archetype matrix into (archetype x path) jobs.

    ``--limit`` / ``--sample`` act on archetypes, not on the expanded jobs, so
    ``--limit 2`` always means two enemies x four paths = eight combats.
    """
    specs = list(ARCHETYPE_SPECS)
    if sample is not None and 0 <= sample < len(specs):
        specs = random.Random(seed).sample(specs, sample)
        specs.sort(key=lambda spec: [s.key for s in ARCHETYPE_SPECS].index(spec.key))
    if limit is not None:
        specs = specs[: max(0, limit)]

    jobs: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    bodies = passage_bodies if passage_bodies is not None else rows_passage_bodies(rows)
    for spec in specs:
        row = choose_entry(rows, spec)
        row = choose_entry(rows, spec, bodies)
        if row is None:
            unresolved.append({"archetype": spec.key, "reason": "no static initiator row"})
            continue
        follow = None
        if not row.get("combat_starters"):
            follow = find_combat_link_target(row, bodies)
            if follow is None:
                unresolved.append(
                    {
                        "archetype": spec.key,
                        "reason": (
                            "chosen row has no combat starter and no link to one: "
                            f"{row.get('passage')}"
                        ),
                    }
                )
                continue
        for path in ARCHETYPE_PATHS:
            jobs.append(
                {
                    "key": f"{spec.key}:{path}",
                    "archetype": spec.key,
                    "label": spec.label,
                    "category": spec.category,
                    "path": path,
                    "kind": row["kind"],
                    "token": row["token"],
                    "passage": follow or row["passage"],
                    "entry_flags": list(row.get("entry_flags") or []),
                    "combat_starters": list(row.get("combat_starters") or []),
                    "initiator_key": row["key"],
                    **({"link_from": row["passage"]} if follow else {}),
                }
            )
    return {
        "jobs": jobs,
        "unresolved": unresolved,
        "archetypes": len(specs),
        "coverage": {
            "specs": len(ARCHETYPE_SPECS),
            "resolved": len(specs) - len(unresolved),
            "paths": list(ARCHETYPE_PATHS),
        },
    }


def pick_mode_entry(jobs: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer an enemy-health fight (beast/human) for the control-mode checks."""
    # Beast fights render their action widgets with the base fixture; ``maninit``
    # NPC fights need NPC bedsheet data the base fixture does not carry, so they
    # only serve as a last resort here.
    preferred_kinds = ("beastCombatInit", "beastNEWinit", "maninit")
    for kind in preferred_kinds:
        for job in jobs:
            if job.get("kind") == kind and job.get("path") == "win":
                return job
    return jobs[0] if jobs else None


# --------------------------------------------------------------------------- #
# Round semantics (pure logic)
# --------------------------------------------------------------------------- #


def action_text(action: dict[str, Any]) -> str:
    return str(action.get("text") or action.get("label") or "")


def choose_action(actions: Sequence[dict[str, Any]], path: str) -> tuple[int, bool]:
    """Pick an action index by path preference.

    Fallback prefers an *unchecked* radio: re-clicking the pre-checked default
    (``休息``) is a DOM no-op, so the turn never submits and the fight stalls.
    """
    keywords = PATH_KEYWORDS.get(path) or ()
    for index, action in enumerate(actions):
        low = action_text(action).casefold()
        if any(kw.casefold() in low for kw in keywords):
            return index, False
    if not actions:
        return -1, True
    for index, action in enumerate(actions):
        if action.get("kind") == "radio" and action.get("checked") is False:
            return index, True
    return 0, True


def round_digest(state: dict[str, Any]) -> str:
    """Meaningful state summary for stall detection (no render counters)."""
    keys = (
        "passage",
        "combat",
        "enemytype",
        "enemyhealth",
        "enemyhealthmax",
        "enemyarousal",
        "enemyarousalmax",
        "npcCount",
        "npcHealthTotal",
        "tentacleHealth",
        "swarmActive",
        "machineHealth",
        "arousal",
        "pain",
        "control",
    )
    return json.dumps({key: state.get(key) for key in keys}, ensure_ascii=False, sort_keys=True)


def detect_stall(digests: Sequence[str], threshold: int = STALL_ROUNDS) -> bool:
    if threshold <= 1:
        return bool(digests)
    if len(digests) < threshold:
        return False
    tail = list(digests)[-threshold:]
    return all(item == tail[0] for item in tail)


def classify_outcome(
    state: dict[str, Any],
    *,
    path: str,
    rounds: int,
    max_rounds: int,
    stalled: bool,
) -> tuple[str, str]:
    """Map the final state to an honest outcome; never guesses silently."""
    if stalled:
        return "unknown", f"stalled: {STALL_ROUNDS} consecutive rounds without state change"
    if state.get("combat") == 1:
        if rounds >= max_rounds:
            return "unknown", f"round limit {max_rounds} reached while $combat stayed 1"
        return "unknown", "combat still active (driver stopped early)"
    health = state.get("enemyhealth")
    arousal = state.get("enemyarousal")
    arousal_max = state.get("enemyarousalmax")
    if isinstance(health, (int, float)) and health <= 0:
        return "win", f"enemy health reached {health}"
    if (
        isinstance(arousal, (int, float))
        and isinstance(arousal_max, (int, float))
        and arousal_max > 0
        and arousal >= arousal_max
    ):
        if path == "submit":
            return "submit", f"enemy arousal reached max ({arousal}/{arousal_max}) on submit path"
        return "win", f"enemy arousal reached max ({arousal}/{arousal_max})"
    return (
        "unknown",
        f"$combat ended without enemy-defeat evidence (path={path}, "
        f"enemyhealth={health}, enemyarousal={arousal})",
    )


_DEFINED_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$.]*)\s+is not defined")
_NULL_READ_RE = re.compile(r"Cannot read propert(?:y|ies) of (?:null|undefined)")
_READING_RE = re.compile(r"reading '([^']+)'")


def classify_entry_errors(
    errors: Sequence[dict[str, Any]], *, timed_out: bool = False
) -> tuple[str, str, list[str]]:
    """Classify entry errors into (verdict, detail, missing symbols)."""
    if timed_out:
        return "soft_fail", "entry render did not finish within the timeout", []
    messages = " | ".join(str(err.get("message") or "") for err in errors)
    if not messages.strip():
        return "not_applicable", "passage rendered but $combat stayed 0", []
    low = messages.lower()
    fixture_hit = any(marker in low for marker in ps.FIXTURE_MARKERS) or "bad evaluation" in low
    if not fixture_hit:
        return "hard_fail", messages[:400], []
    missing: list[str] = []
    for name in _DEFINED_RE.findall(messages):
        if name not in missing:
            missing.append(name)
    if _NULL_READ_RE.search(messages):
        prop = _READING_RE.search(messages)
        missing.append(f"null.{prop.group(1)}" if prop else "null property read")
    return "fixture_insufficient", messages[:400], missing[:20]


def classify_round_errors(errors: Sequence[dict[str, Any]]) -> tuple[str, str, list[str]]:
    """Round-level errors: same rules as entry errors, no not_applicable branch."""
    verdict, detail, missing = classify_entry_errors(errors)
    if verdict == "not_applicable":
        return "ok", "", []
    return verdict, detail, missing


def classify_no_actions(
    actions_probe: dict[str, Any], state: dict[str, Any]
) -> tuple[str, str, list[str]]:
    """Verdict for ``$combat == 1`` with no action controls on screen.

    Upstream widget crashes are reported through ``console.warn``, which the JS
    error harness cannot see, so the *absence* of ``#listContainer`` is the
    fixture signal: the action widgets never produced anything for this scene.
    """
    state_errors = state.get("errors") or []
    if state_errors:
        verdict, detail, missing = classify_round_errors(state_errors)
        if verdict and verdict != "ok":
            return verdict, detail, missing
    if str(actions_probe.get("error") or "") == "no #listContainer":
        return (
            "fixture_insufficient",
            "combat active but #listContainer never rendered: action widgets "
            "produced nothing (fixture data insufficient)",
            ["#listContainer"],
        )
    return "soft_fail", "no action controls in #listContainer", []


# --------------------------------------------------------------------------- #
# Live combat driver (JS stays at module level, everything returns JSON strings)
# --------------------------------------------------------------------------- #

COMBAT_STATE_JS = r"""
() => {
  const SC = window.SugarCube;
  if (!SC || !SC.State) return JSON.stringify({ ok: false, error: "SugarCube.State missing" });
  let V = null;
  try { V = SC.State.variables; } catch (e) { return JSON.stringify({ ok: false, error: "variables unreadable" }); }
  if (!V) return JSON.stringify({ ok: false, error: "variables missing" });
  const num = (v) => (typeof v === "number" && isFinite(v)) ? v : null;
  const lc = document.querySelector("#listContainer");
  const sel = document.querySelector("#listbox-optionscombatcontrols");
  const S = window.__DOLX__ || {};
  const npc = Array.isArray(V.NPCList) ? V.NPCList : [];
  let npcHealthTotal = 0;
  for (let i = 0; i < npc.length; i++) {
    const h = npc[i] && npc[i].health;
    if (typeof h === "number" && isFinite(h)) npcHealthTotal += h;
  }
  let tentacleHealth = null;
  try {
    if (Array.isArray(V.tentacles)) {
      let sum = 0;
      for (const t of V.tentacles) { if (t && typeof t.health === "number") sum += t.health; }
      tentacleHealth = sum;
    } else if (V.tentacles && Array.isArray(V.tentacles.list)) {
      let sum = 0;
      for (const t of V.tentacles.list) { if (t && typeof t.health === "number") sum += t.health; }
      tentacleHealth = sum;
    }
  } catch (e) { tentacleHealth = null; }
  let swarmActive = null;
  try {
    if (V.swarm && V.swarm.amount && Array.isArray(V.swarm.amount.active)) swarmActive = num(V.swarm.amount.active[0]);
  } catch (e) { swarmActive = null; }
  let machineHealth = null;
  try {
    if (V.machine && typeof V.machine === "object") {
      let seen = false, sum = 0;
      for (const key of Object.keys(V.machine)) {
        const part = V.machine[key];
        if (part && typeof part === "object" && typeof part.health === "number") { seen = true; sum += part.health; }
      }
      machineHealth = seen ? sum : null;
    }
  } catch (e) { machineHealth = null; }
  const out = {
    ok: true,
    passage: (() => { try { return SC.State.passage; } catch (e) { return null; } })(),
    combat: num(V.combat),
    enemytype: V.enemytype === undefined || V.enemytype === null ? null : String(V.enemytype),
    enemyhealth: num(V.enemyhealth),
    enemyhealthmax: num(V.enemyhealthmax),
    enemyarousal: num(V.enemyarousal),
    enemyarousalmax: num(V.enemyarousalmax),
    arousal: num(V.arousal),
    pain: num(V.pain),
    control: num(V.control),
    npcCount: npc.length,
    npcHealthTotal: npcHealthTotal,
    tentacleHealth: tentacleHealth,
    swarmActive: swarmActive,
    machineHealth: machineHealth,
    listContainer: !!lc,
    radioCount: lc ? lc.querySelectorAll("input.macro-radiobutton").length : 0,
    selectCount: lc ? lc.querySelectorAll("select").length : 0,
    controlValue: sel ? String(sel.value) : null,
    controlOptions: sel ? [...sel.options].map(o => ({ value: String(o.value), text: String(o.text) })) : [],
    optionsCombatControls: (V.options && V.options.combatControls !== undefined) ? String(V.options.combatControls) : null,
    errorCount: (S.errors || []).length,
    errors: (S.errors || []).slice(-8),
    done: !!S.done,
    renderSeq: S.renderSeq || 0,
  };
  return JSON.stringify(out);
}
"""

COMBAT_ACTIONS_JS = r"""
() => {
  const lc = document.querySelector("#listContainer");
  if (!lc) return JSON.stringify({ ok: false, error: "no #listContainer", actions: [] });
  const out = [];
  const groupOf = (el) => { const g = el.closest("div[id]"); return g ? g.id : null; };
  lc.querySelectorAll("input.macro-radiobutton").forEach((el, i) => {
    const label = el.closest("label");
    out.push({
      kind: "radio", id: el.id || null, group: groupOf(el), index: i, checked: !!el.checked,
      text: label ? String(label.innerText || "").trim().replace(/\s+/g, " ") : "",
      value: String(el.value === undefined ? "" : el.value).slice(0, 80),
    });
  });
  if (!out.length) {
    lc.querySelectorAll("select").forEach((sel, i) => {
      const options = [...sel.options].map(o => ({ value: String(o.value), text: String(o.text || "").trim().replace(/\s+/g, " ") }));
      if (!options.length) return;
      out.push({
        kind: "select", id: sel.id || null, group: groupOf(sel), index: i, checked: false,
        text: options.map(o => o.text).join(" | ").slice(0, 240),
        value: String(sel.value), options: options,
      });
    });
  }
  const V = window.SugarCube && window.SugarCube.State ? window.SugarCube.State.variables : null;
  return JSON.stringify({
    ok: true, actions: out, count: out.length,
    control: (V && V.options && V.options.combatControls) ? String(V.options.combatControls) : null,
  });
}
"""

SET_MODE_JS = r"""
(payload) => {
  const sel = document.querySelector("#listbox-optionscombatcontrols");
  if (!sel) return JSON.stringify({ ok: false, error: "control select missing" });
  const norm = (s) => String(s).replace(/\s+/g, "").toLowerCase();
  const options = [...sel.options].map(o => ({ value: String(o.value), text: String(o.text) }));
  let opt = options.find(o => norm(o.text) === norm(payload.mode));
  if (!opt && payload.value) opt = options.find(o => o.value === String(payload.value));
  if (!opt) return JSON.stringify({ ok: false, error: "no option for mode", options: options });
  sel.value = opt.value;
  sel.dispatchEvent(new Event("change", { bubbles: true }));
  return JSON.stringify({ ok: true, value: opt.value, text: opt.text, options: options });
}
"""

SET_ENTRY_FLAGS_JS = r"""
(payload) => {
  const SC = window.SugarCube;
  if (!SC || !SC.State) return JSON.stringify({ ok: false, error: "State missing" });
  const V = SC.State.variables;
  const flags = payload.flags || [];
  for (const name of ["molestationstart", "sexstart"]) {
    V[name] = flags.includes(name) ? 1 : 0;
  }
  return JSON.stringify({ ok: true, molestationstart: V.molestationstart, sexstart: V.sexstart });
}
"""

TURN_RESET_JS = r"""
() => {
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  S.done = false;
  S.errors = [];
  return S.renderSeq || 0;
}
"""

SELECT_RADIO_JS = r"""
(payload) => {
  const lc = document.querySelector("#listContainer");
  if (!lc) return JSON.stringify({ ok: false, error: "no #listContainer" });
  let el = payload.id ? document.getElementById(payload.id) : null;
  if (!el) {
    const all = lc.querySelectorAll("input.macro-radiobutton");
    el = all[payload.index || 0] || null;
  }
  if (!el) return JSON.stringify({ ok: false, error: "radio not found" });
  el.click();
  return JSON.stringify({ ok: true, kind: "radio", id: el.id, checked: !!el.checked });
}
"""


def _state(page: Any) -> dict[str, Any]:
    raw = page.evaluate(COMBAT_STATE_JS)
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:  # noqa: BLE001 - surface as a broken state probe
        return {"ok": False, "error": f"state payload unreadable: {exc}"}
    return data if isinstance(data, dict) else {"ok": False, "error": "state payload not a dict"}


def _actions(page: Any) -> dict[str, Any]:
    raw = page.evaluate(COMBAT_ACTIONS_JS)
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"action payload unreadable: {exc}", "actions": []}
    return data if isinstance(data, dict) else {"ok": False, "error": "action payload not a dict", "actions": []}


def set_control_mode(page: Any, mode: str) -> dict[str, Any]:
    raw = page.evaluate(
        SET_MODE_JS, {"mode": CONTROL_MODE_TEXTS.get(mode, mode), "value": CONTROL_MODE_VALUES.get(mode)}
    )
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def set_entry_flags(page: Any, flags: Iterable[str]) -> dict[str, Any]:
    raw = page.evaluate(SET_ENTRY_FLAGS_JS, {"flags": list(flags)})
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def play_passage(page: Any, name: str, *, timeout_ms: int) -> tuple[dict[str, Any], bool]:
    """Engine.play + wait for the :passagedisplay hook. Returns (probe, timed_out)."""
    page.evaluate(ps.PLAY_PASSAGE, {"name": name})
    timed_out = False
    try:
        page.wait_for_function(
            "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
            timeout=min(timeout_ms, 20000),
        )
    except Exception:  # noqa: BLE001 - a slow render is recorded, not fatal
        timed_out = True
    return _state(page), timed_out


def enter_row(page: Any, row: dict[str, Any], *, timeout_ms: int, settle_ms: int = DEFAULT_ENTRY_SETTLE_MS) -> dict[str, Any]:
    """Restore the fixture, arm the flow flag, play the initiator passage."""
    order: list[tuple[str, ...]] = []
    if row.get("entry_flags"):
        order.append(tuple(str(flag) for flag in row["entry_flags"]))
    order.extend(attempt for attempt in ENTRY_FLAG_ATTEMPTS if attempt not in order)
    attempts: list[dict[str, Any]] = []
    last_state: dict[str, Any] = {}
    last_timed_out = False
    for flags in order:
        restore = page.evaluate(ps.RESTORE_FIXTURE)
        armed = set_entry_flags(page, flags)
        state, timed_out = play_passage(page, str(row.get("passage") or ""), timeout_ms=timeout_ms)
        if settle_ms:
            page.wait_for_timeout(settle_ms)
            state = _state(page)
        attempts.append(
            {
                "flags": list(flags),
                "restore": restore if isinstance(restore, dict) else str(restore),
                "armed": armed,
                "combat": state.get("combat"),
                "passage": state.get("passage"),
                "timed_out": timed_out,
                "error_count": state.get("errorCount"),
            }
        )
        last_state, last_timed_out = state, timed_out
        if state.get("combat") == 1:
            return {
                "ok": True,
                "state": state,
                "flags": list(flags),
                "attempts": attempts,
                "timed_out": timed_out,
            }
    verdict, detail, missing = classify_entry_errors(
        last_state.get("errors") or [], timed_out=last_timed_out
    )
    return {
        "ok": False,
        "state": last_state,
        "attempts": attempts,
        "verdict": verdict,
        "detail": detail,
        "missing": missing,
        "timed_out": last_timed_out,
    }


def _select_action(
    page: Any,
    action: dict[str, Any],
    *,
    keyword_path: str,
    fallback: bool = False,
) -> dict[str, Any]:
    """Perform one real DOM selection; returns the selection record."""
    record: dict[str, Any] = {
        "kind": action.get("kind"),
        "fallback": fallback,
        "text": action_text(action)[:120],
        "group": action.get("group"),
    }
    if action.get("kind") == "radio":
        if action.get("id"):
            try:
                page.click(f"#{action['id']}", timeout=4000)
                record["selected"] = action["id"]
                return record
            except Exception as exc:  # noqa: BLE001 - fall back to the JS click
                record["click_error"] = str(exc)[:160]
        raw = page.evaluate(SELECT_RADIO_JS, {"id": action.get("id"), "index": action.get("index")})
        try:
            record["selected"] = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:  # noqa: BLE001
            record["selected"] = {"ok": False, "raw": str(raw)[:120]}
        return record
    # Lists / List (w): a SugarCube listbox <select>.
    options = action.get("options") or []
    picked = None
    for option in options:
        low = str(option.get("text") or "").casefold()
        if any(kw.casefold() in low for kw in PATH_KEYWORDS.get(keyword_path, ())):
            picked = option
            break
    if picked is None and options:
        picked = options[min(1, len(options) - 1)]
        record["fallback"] = True
    if picked is None:
        record["selected"] = {"ok": False, "error": "empty option list"}
        return record
    record["option"] = picked.get("text")
    try:
        page.select_option(f"#{action['id']}", value=picked["value"])
        record["selected"] = {"ok": True, "id": action.get("id"), "value": picked["value"]}
    except Exception as exc:  # noqa: BLE001
        record["selected"] = {"ok": False, "error": str(exc)[:160]}
    return record


def begin_turn(page: Any) -> int:
    """Clear the per-turn flags and record the render counter before acting.

    The action click itself usually submits the turn in DoL, so the render must
    be measured from *before* the click; waiting for ``done`` alone makes every
    round burn its whole timeout.
    """
    raw = page.evaluate(TURN_RESET_JS)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _press_turn(
    page: Any,
    *,
    timeout_ms: int,
    before_render: int = 0,
    settle_ms: int = DEFAULT_TURN_SETTLE_MS,
) -> dict[str, Any]:
    page.keyboard.press("Enter")
    timed_out = False
    try:
        page.wait_for_function(
            "(before) => {"
            "  const S = window.__DOLX__;"
            "  return !!S && (S.done === true || (S.renderSeq || 0) > before);"
            "}",
            before_render,
            timeout=max(1000, min(timeout_ms, TURN_WAIT_MS)),
        )
    except Exception:  # noqa: BLE001
        timed_out = True
    if settle_ms:
        page.wait_for_timeout(settle_ms)
    return {"timed_out": timed_out, "state": _state(page)}


def drive_combat(page: Any, *, path: str, max_rounds: int, timeout_ms: int) -> dict[str, Any]:
    """Drive one combat from $combat=1 to an ending (or the round cap)."""
    result: dict[str, Any] = {
        "path": path,
        "rounds": 0,
        "actions": [],
        "digests": [],
        "hp_evidence": [],
        "errors": [],
        "stalled": False,
        "outcome": "unknown",
        "outcome_detail": "",
        "verdict": "ok",
        "detail": "",
        "landed": None,
    }
    state = _state(page)
    for round_no in range(1, max_rounds + 1):
        if state.get("combat") != 1:
            break
        actions_probe = _actions(page)
        actions = actions_probe.get("actions") or []
        if not actions:
            verdict, detail, missing = classify_no_actions(actions_probe, state)
            result["verdict"] = verdict
            result["detail"] = detail
            result["errors"].append(
                {"round": round_no, "verdict": verdict, "detail": detail, "missing": missing}
            )
            break
        index, fallback = choose_action(actions, path)
        action = actions[max(0, index)]
        before = state
        before_render = begin_turn(page)
        selection = _select_action(page, action, keyword_path=path, fallback=fallback)
        turn = _press_turn(page, timeout_ms=timeout_ms, before_render=before_render)
        state = turn["state"]
        digest = round_digest(state)
        result["digests"].append(digest)
        result["rounds"] += 1
        result["actions"].append(
            {
                "round": round_no,
                "kind": action.get("kind"),
                "group": action.get("group"),
                "text": action_text(action)[:120],
                "fallback": fallback,
                "selection": selection,
                "timed_out": turn["timed_out"],
            }
        )
        result["hp_evidence"].append(
            {
                "round": round_no,
                "enemyhealth": [before.get("enemyhealth"), state.get("enemyhealth")],
                "enemyarousal": [before.get("enemyarousal"), state.get("enemyarousal")],
                "tentacleHealth": [before.get("tentacleHealth"), state.get("tentacleHealth")],
                "swarmActive": [before.get("swarmActive"), state.get("swarmActive")],
                "machineHealth": [before.get("machineHealth"), state.get("machineHealth")],
                "combat": state.get("combat"),
                "passage": state.get("passage"),
            }
        )
        round_errors = state.get("errors") or []
        if round_errors:
            verdict, detail, missing = classify_round_errors(round_errors)
            result["errors"].append(
                {"round": round_no, "verdict": verdict, "detail": detail, "missing": missing}
            )
            if verdict == "hard_fail":
                result["verdict"] = "hard_fail"
                result["detail"] = detail
                break
            if verdict == "fixture_insufficient":
                result["verdict"] = "fixture_insufficient"
                result["detail"] = detail
                break
        if detect_stall(result["digests"]):
            result["stalled"] = True
            result["verdict"] = "soft_fail"
            result["detail"] = f"stalled: {STALL_ROUNDS} rounds without state change"
            break
        if turn["timed_out"] and not state.get("done", True):
            result["verdict"] = "soft_fail"
            result["detail"] = "turn render timed out"
            break
    result["landed"] = state.get("passage")
    outcome, outcome_detail = classify_outcome(
        state,
        path=path,
        rounds=result["rounds"],
        max_rounds=max_rounds,
        stalled=result["stalled"],
    )
    result["outcome"] = outcome
    result["outcome_detail"] = outcome_detail
    if result["verdict"] == "ok" and outcome == "unknown" and state.get("combat") != 1:
        result["verdict"] = "soft_fail"
        result["detail"] = outcome_detail
    if result["verdict"] == "ok" and state.get("combat") == 1 and result["rounds"] >= max_rounds:
        result["verdict"] = "soft_fail"
        result["detail"] = f"round limit {max_rounds} reached"
    result["final_state"] = {
        key: state.get(key)
        for key in (
            "combat",
            "passage",
            "enemytype",
            "enemyhealth",
            "enemyarousal",
            "enemyarousalmax",
            "tentacleHealth",
            "swarmActive",
            "machineHealth",
            "npcCount",
        )
    }
    return result


def run_archetype_jobs(
    page: Any,
    jobs: Sequence[dict[str, Any]],
    *,
    max_rounds: int,
    timeout_ms: int,
    progress: Any | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for position, job in enumerate(jobs, 1):
        t0 = time.time()
        # The matrix runs four paths back-to-back; a previous job can leave
        # ``$combat == 1`` behind (e.g. a submit path that keeps the fight
        # alive). Force a clean entry so each job measures its own fight.
        if _state(page).get("combat") == 1:
            page.evaluate(ps.RESTORE_FIXTURE)
        entry = enter_row(page, job, timeout_ms=timeout_ms)
        if entry.get("ok"):
            drive = drive_combat(
                page, path=str(job.get("path") or "win"), max_rounds=max_rounds, timeout_ms=timeout_ms
            )
            verdict = drive["verdict"]
            detail = drive.get("detail") or drive.get("outcome_detail") or ""
            record = {
                "key": job["key"],
                "archetype": job["archetype"],
                "label": job.get("label"),
                "category": job.get("category"),
                "path": job.get("path"),
                "kind": job.get("kind"),
                "token": job.get("token"),
                "passage": job.get("passage"),
                "verdict": verdict,
                "detail": str(detail)[:400],
                "entry_flag": entry.get("flags"),
                "entry_timed_out": entry.get("timed_out"),
                "combat": drive,
                "missing": [],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
        else:
            record = {
                "key": job["key"],
                "archetype": job["archetype"],
                "label": job.get("label"),
                "category": job.get("category"),
                "path": job.get("path"),
                "kind": job.get("kind"),
                "token": job.get("token"),
                "passage": job.get("passage"),
                "verdict": entry.get("verdict", "hard_fail"),
                "detail": str(entry.get("detail") or "")[:400],
                "entry_flag": None,
                "entry_timed_out": entry.get("timed_out"),
                "combat": None,
                "missing": entry.get("missing") or [],
                "entry_attempts": entry.get("attempts") or [],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
        results.append(record)
        if progress is not None:
            progress(record, position, len(jobs))
    return results


def run_control_modes(
    page: Any,
    entry: dict[str, Any],
    *,
    rounds: int = DEFAULT_MODE_ROUNDS,
    timeout_ms: int,
    max_reentries: int = 4,
) -> list[dict[str, Any]]:
    """Exercise every control mode for >= ``rounds`` real DOM rounds each."""
    results: list[dict[str, Any]] = []
    for mode in CONTROL_MODES:
        expected_dom = CONTROL_MODE_DOM[mode]
        record: dict[str, Any] = {
            "mode": mode,
            "expected_dom": expected_dom,
            "rounds": 0,
            "ok_rounds": 0,
            "dom_kinds": [],
            "selections": [],
            "hp_evidence": [],
            "reentries": 0,
            "errors": [],
            "verdict": "ok",
            "detail": "",
        }
        state = _state(page)
        if state.get("combat") != 1:
            reentry = enter_row(page, entry, timeout_ms=timeout_ms)
            record["reentries"] += 1
            if not reentry.get("ok"):
                record["verdict"] = reentry.get("verdict", "soft_fail")
                record["detail"] = f"could not re-enter combat: {reentry.get('detail', '')}"[:300]
                record["entry_attempts"] = reentry.get("attempts") or []
                results.append(record)
                continue
            state = reentry["state"]
        switch = set_control_mode(page, mode)
        record["switch"] = switch
        if not switch.get("ok"):
            record["verdict"] = "soft_fail"
            record["detail"] = f"control mode switch failed: {switch.get('error')}"
            results.append(record)
            continue
        attempts = 0
        while record["rounds"] < rounds and attempts < rounds * 3 + 2:
            attempts += 1
            if state.get("combat") != 1:
                if record["reentries"] >= max_reentries:
                    break
                reentry = enter_row(page, entry, timeout_ms=timeout_ms)
                record["reentries"] += 1
                if not reentry.get("ok"):
                    record["errors"].append({"reentry": reentry.get("detail", "")[:200]})
                    break
                state = reentry["state"]
                set_control_mode(page, mode)
            actions_probe = _actions(page)
            actions = actions_probe.get("actions") or []
            if not actions:
                verdict, detail, missing = classify_no_actions(actions_probe, state)
                record["errors"].append(
                    {"round": attempts, "verdict": verdict, "detail": detail, "missing": missing}
                )
                if record["verdict"] == "ok" and verdict != "ok":
                    record["verdict"] = verdict
                    record["detail"] = detail
                break
            index, fallback = choose_action(actions, "win")
            action = actions[max(0, index)]
            dom_kind = str(action.get("kind"))
            record["dom_kinds"].append(dom_kind)
            before = state
            before_render = begin_turn(page)
            selection = _select_action(page, action, keyword_path="win", fallback=fallback)
            turn = _press_turn(page, timeout_ms=timeout_ms, before_render=before_render)
            state = turn["state"]
            record["selections"].append(
                {
                    "kind": dom_kind,
                    "text": action_text(action)[:100],
                    "selection": selection.get("selected"),
                    "timed_out": turn["timed_out"],
                }
            )
            record["hp_evidence"].append(
                {
                    "mode": mode,
                    "round": attempts,
                    "enemyhealth": [before.get("enemyhealth"), state.get("enemyhealth")],
                    "enemyarousal": [before.get("enemyarousal"), state.get("enemyarousal")],
                    "combat": state.get("combat"),
                }
            )
            errors = state.get("errors") or []
            if errors:
                verdict, detail, missing = classify_round_errors(errors)
                record["errors"].append(
                    {"round": attempts, "verdict": verdict, "detail": detail, "missing": missing}
                )
                if verdict == "hard_fail":
                    record["verdict"] = "hard_fail"
                    record["detail"] = detail
                    break
            if dom_kind == expected_dom:
                record["ok_rounds"] += 1
                record["rounds"] += 1
        if record["verdict"] == "ok" and record["rounds"] < rounds:
            record["verdict"] = "soft_fail"
            record["detail"] = (
                f"only {record['rounds']}/{rounds} {expected_dom}-kind rounds "
                f"(combat ended or DOM never switched)"
            )
        results.append(record)
    restore = set_control_mode(page, DEFAULT_CONTROL_MODE)
    if results:
        results[-1]["restored_default"] = restore
    return results


# --------------------------------------------------------------------------- #
# Initiator tier selection / resume
# --------------------------------------------------------------------------- #


def select_initiator_rows(
    rows: Sequence[dict[str, Any]],
    *,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20261004,
    resume_keys: Iterable[str] | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
) -> dict[str, Any]:
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must satisfy 0 <= shard_index < shard_count")
    planned = list(rows)
    if sample is not None and 0 <= sample < len(planned):
        planned = random.Random(seed).sample(planned, sample)
        planned.sort(key=lambda row: (KIND_ORDER.index(row["kind"]), row["token"], row["passage"]))
    if limit is not None:
        planned = planned[: max(0, limit)]
    planned = planned[shard_index::shard_count]
    done = set(str(key) for key in (resume_keys or ()))
    selected = [row for row in planned if str(row.get("key")) not in done]
    return {
        "planned": planned,
        "selected": selected,
        "skipped_resume": len(planned) - len(selected),
        "pool": len(rows),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_initiator_rows(
    page: Any,
    rows: Sequence[dict[str, Any]],
    *,
    max_rounds: int,
    timeout_ms: int,
    progress: Any | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for position, row in enumerate(rows, 1):
        t0 = time.time()
        entry = enter_row(page, row, timeout_ms=timeout_ms)
        if entry.get("ok"):
            drive = drive_combat(page, path="win", max_rounds=max_rounds, timeout_ms=timeout_ms)
            record = {
                "key": row["key"],
                "kind": row.get("kind"),
                "token": row.get("token"),
                "passage": row.get("passage"),
                "macro": row.get("macro"),
                "verdict": drive["verdict"],
                "detail": str(drive.get("detail") or drive.get("outcome_detail") or "")[:400],
                "entry_flag": entry.get("flags"),
                "entry_timed_out": entry.get("timed_out"),
                "combat": drive,
                "missing": [],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
        else:
            record = {
                "key": row["key"],
                "kind": row.get("kind"),
                "token": row.get("token"),
                "passage": row.get("passage"),
                "macro": row.get("macro"),
                "verdict": entry.get("verdict", "hard_fail"),
                "detail": str(entry.get("detail") or "")[:400],
                "entry_flag": None,
                "entry_timed_out": entry.get("timed_out"),
                "combat": None,
                "missing": entry.get("missing") or [],
                "entry_attempts": entry.get("attempts") or [],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
        results.append(record)
        if progress is not None:
            progress(record, position, len(rows))
    return results


# --------------------------------------------------------------------------- #
# Baseline diff + reporting
# --------------------------------------------------------------------------- #


def diff_against_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    old = {str(r.get("key")): str(r.get("verdict")) for r in baseline.get("results") or []}
    new = {str(r.get("key")): str(r.get("verdict")) for r in report.get("results") or []}
    regressions: list[dict[str, Any]] = []
    fixed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unseen: list[dict[str, Any]] = []
    for key, verdict in new.items():
        previous = old.get(key)
        if previous is None:
            unseen.append({"key": key, "verdict": verdict})
            continue
        if previous == verdict:
            continue
        if VERDICT_SEVERITY.get(verdict, 3) > VERDICT_SEVERITY.get(previous, 3):
            regressions.append({"key": key, "was": previous, "now": verdict})
        elif verdict == "ok":
            fixed.append({"key": key, "was": previous, "now": verdict})
        else:
            changed.append({"key": key, "was": previous, "now": verdict})
    manifest_diff = None
    old_manifest = (baseline.get("manifest") or {}).get("by_kind")
    new_manifest = (report.get("manifest") or {}).get("by_kind")
    if old_manifest or new_manifest:
        manifest_diff = {
            "by_kind": {
                kind: {"baseline": (old_manifest or {}).get(kind), "current": (new_manifest or {}).get(kind)}
                for kind in sorted(set(list((old_manifest or {}).keys()) + list((new_manifest or {}).keys())))
            },
            "total": {
                "baseline": (baseline.get("manifest") or {}).get("total"),
                "current": (report.get("manifest") or {}).get("total"),
            },
        }
    return {
        "regressions": regressions,
        "fixed": fixed,
        "changed": changed,
        "unseen_in_baseline": unseen,
        "manifest": manifest_diff,
    }


def default_out_dir(tier: str, day: str | None = None) -> Path:
    stamp = day or time.strftime("%Y%m%d")
    return DEFAULT_OUT_ROOT / f"combat-{tier}-{stamp}"


def baseline_path(fixture: Path | None, tier: str) -> Path:
    stem = Path(fixture).stem if fixture else "nofx"
    return DEFAULT_BASELINE_DIR / f"combat-{tier}-{stem}.json"


def _verdict_counts(results: Sequence[dict[str, Any]], key: str = "verdict") -> dict[str, int]:
    counts = collections.Counter(str(r.get(key)) for r in results)
    return {verdict: counts.get(verdict, 0) for verdict in VERDICTS}


def write_report(report: dict[str, Any], out_dir: Path, diff: dict[str, Any] | None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "combat-sweep.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = report.get("verdict_counts") or {}
    manifest = report.get("manifest") or {}
    fixture = report.get("fixture") or {}
    lines = [
        "# DOL-X combat sweep report",
        "",
        f"- target: `{report.get('target')}`",
        f"- html: `{report.get('html_path')}`",
        f"- tier: **{report.get('tier')}** / fixture: `{fixture.get('path')}` "
        f"({fixture.get('top_level_keys')} keys, digest {str(fixture.get('digest'))[:12]})",
        f"- initiator manifest: {manifest.get('total')} rows across {manifest.get('passages')} passages "
        f"(expected {report.get('expected', {}).get('total')}, drift {manifest.get('drift', {}).get('count')})",
        f"- started: {report.get('started_at')} / finished: {report.get('finished_at')}",
        "",
        "## verdicts",
        "",
        "| verdict | count |",
        "| --- | --- |",
    ]
    for verdict in VERDICTS:
        lines.append(f"| {verdict} | {counts.get(verdict, 0)} |")

    by_kind = manifest.get("by_kind") or {}
    if by_kind:
        lines += ["", "## initiators by kind", "", "| kind | count |", "| --- | --- |"]
        for kind in KIND_ORDER:
            lines.append(f"| {kind} | {by_kind.get(kind, 0)} |")

    modes = report.get("modes") or []
    if modes:
        lines += [
            "",
            "## control modes",
            "",
            "| mode | verdict | rounds | dom kind | selections | hp evidence | detail |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for mode in modes:
            kinds = collections.Counter(mode.get("dom_kinds") or [])
            hp = mode.get("hp_evidence") or []
            hp_text = "; ".join(
                f"{item.get('round')}: {item.get('enemyhealth', [None, None])[0]} -> {item.get('enemyhealth', [None, None])[1]}"
                for item in hp[:4]
            ) or "-"
            lines.append(
                f"| {mode.get('mode')} | {mode.get('verdict')} | {mode.get('rounds')} | "
                f"{dict(kinds)} | {len(mode.get('selections') or [])} | {hp_text[:120]} | "
                f"{str(mode.get('detail') or '')[:160]} |"
            )

    with_hp = [
        r
        for r in report.get("results") or []
        if (r.get("combat") or {}).get("hp_evidence")
    ]
    if with_hp:
        lines += [
            "",
            "## enemyhealth evidence (first 20 result rows)",
            "",
            "| key | rounds | hp sequence | outcome |",
            "| --- | --- | --- | --- |",
        ]
        for row in with_hp[:20]:
            combat = row.get("combat") or {}
            seq = [
                f"{item.get('enemyhealth', [None, None])[0]}->{item.get('enemyhealth', [None, None])[1]}"
                for item in (combat.get("hp_evidence") or [])[:6]
            ]
            lines.append(
                f"| `{row.get('key')}` | {combat.get('rounds')} | {'; '.join(seq)} | {combat.get('outcome')} |"
            )

    for verdict in ("hard_fail", "soft_fail", "fixture_insufficient", "not_applicable"):
        bad = [r for r in report.get("results") or [] if r.get("verdict") == verdict]
        if not bad:
            continue
        lines += ["", f"## {verdict} ({len(bad)})", ""]
        for row in bad[:60]:
            missing = f" missing={row.get('missing')}" if row.get("missing") else ""
            lines.append(
                f"- `{row.get('key')}` ({row.get('kind')}/{row.get('token')}) — "
                f"{str(row.get('detail') or '')[:200]}{missing}"
            )
        if len(bad) > 60:
            lines.append(f"- ... and {len(bad) - 60} more")

    if diff:
        lines += ["", "## baseline diff", ""]
        lines.append(f"- regressions: **{len(diff.get('regressions') or [])}**")
        lines.append(f"- fixed: {len(diff.get('fixed') or [])}")
        lines.append(f"- changed: {len(diff.get('changed') or [])}")
        lines.append(f"- unseen in baseline: {len(diff.get('unseen_in_baseline') or [])}")
        for item in (diff.get("regressions") or [])[:40]:
            lines.append(f"  - `{item.get('key')}`: {item.get('was')} -> {item.get('now')}")
        for item in (diff.get("fixed") or [])[:20]:
            lines.append(f"  - fixed `{item.get('key')}`: {item.get('was')} -> ok")

    if report.get("fatal_error"):
        lines += ["", "## fatal error", "", f"`{report['fatal_error']}`", ""]

    md_path = out_dir / "combat-sweep.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def fixture_digest(variables: dict[str, Any]) -> str:
    canonical = json.dumps(variables, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_fixture_payload(fixture_path: Path) -> tuple[dict[str, Any], str]:
    fixture = fl.load_fixture(fixture_path)
    variables = fixture.get("variables") if isinstance(fixture, dict) else None
    if not isinstance(variables, dict) or not variables:
        raise SystemExit(f"fixture has no 'variables' object: {fixture_path}")
    payload = json.dumps(fixture, ensure_ascii=False, separators=(",", ":"))
    return fixture, payload


def run(
    target: Path,
    *,
    tier: str = DEFAULT_TIER,
    fixture_path: Path = DEFAULT_FIXTURE,
    out_dir: Path | None = None,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 20261004,
    timeout_ms: int = 20000,
    bootstrap_settle_ms: int = 1500,
    headless: bool = True,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    run_modes: bool = True,
    modes_only: bool = False,
    resume: bool = False,
    shard_index: int = 0,
    shard_count: int = 1,
    baseline_path_in: Path | None = None,
    save_baseline: bool = False,
    manifest_out: Path | None = DEFAULT_MANIFEST_OUT,
    mode_rounds: int = DEFAULT_MODE_ROUNDS,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    html_path = ps.resolve_html_path(target)
    fixture, fixture_json = load_fixture_payload(fixture_path)
    variables = fixture.get("variables") or {}

    t0 = time.time()
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    manifest = scan_initiators(html_text)
    # Static archetype rows without a combat starter macro (e.g. ``Farmland
    # Pigs``) only *generate* the beast; the fight itself starts on a later
    # passage reached through an in-passage link. Resolve those links here so
    # the matrix enters real combat instead of reporting not_applicable.
    passage_bodies: dict[str, str] = {}
    for passage in ps.extract_passages(html_path)[0]:
        passage_bodies[passage.name] = passage.body
    scan_ms = int((time.time() - t0) * 1000)
    manifest["scan_ms"] = scan_ms
    if manifest_out is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(
            json.dumps(
                {
                    "tool": TOOL,
                    "target": str(target),
                    "html_path": str(html_path),
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "passages": manifest["passages"],
                    "total": manifest["total"],
                    "by_kind": manifest["by_kind"],
                    "by_token": manifest["by_token"],
                    "expected": manifest["expected"],
                    "drift": manifest["drift"],
                    "macro_names": manifest["macro_names"],
                    "rows": manifest["rows"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest["path"] = str(manifest_out)

    out = out_dir or default_out_dir(tier)
    ledger_path = out / DEFAULT_LEDGER_NAME
    legacy_resume_path = out / "combat-sweep-resume.json"
    strategy = {
        "tier": tier,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "seed": seed,
        "limit": limit,
        "sample": sample,
        "max_rounds": max_rounds,
        "timeout_ms": timeout_ms,
        "run_modes": run_modes,
        "modes_only": modes_only,
    }
    identity = sl.run_identity(
        TOOL,
        html_sha256=file_sha256(html_path),
        fixture_digest=fixture_digest(variables),
        tool_version="combat-sweep-v2",
        plan_digest="",
        strategy=strategy,
    )
    report: dict[str, Any] = {
        "tool": TOOL,
        "target": str(target),
        "html_path": str(html_path),
        "tier": tier,
        "fixture": {
            "path": str(fixture_path),
            "top_level_keys": len(variables),
            "digest": fixture_digest(variables),
        },
        "manifest": {
            "path": manifest.get("path"),
            "total": manifest["total"],
            "by_kind": manifest["by_kind"],
            "by_token": manifest["by_token"],
            "passages": manifest["passages"],
            "drift": manifest["drift"],
            "scan_ms": scan_ms,
        },
        "expected": {"total": EXPECTED_INITIATORS["total"]},
        "entry_strategy": {
            "flags": list(ENTRY_FLAGS),
            "attempts": [list(item) for item in ENTRY_FLAG_ATTEMPTS],
            "reason": "upstream guards combat scenes behind $molestationstart/$sexstart; the fixture carries both at 0",
        },
        "selection": None,
        "results": [],
        "modes": [],
        "verdict_counts": {},
        "baseline": {"path": str(baseline_path_in) if baseline_path_in else None},
        "baseline_diff": None,
        "resume": {
            "enabled": resume,
            "path": str(ledger_path),
            "legacy_path": str(legacy_resume_path),
            "skipped": 0,
            "loaded_results": 0,
            "diagnostics": [],
        },
        "ledger": {
            "path": str(ledger_path),
            "identity": identity,
            "complete": None,
            "validation": None,
        },
        "started_at": started,
        "finished_at": None,
        "boot": None,
        "console_tail": [],
        "fatal_error": None,
    }

    selected_jobs: list[dict[str, Any]] = []
    selection: dict[str, Any] = {}
    initiator_plan: list[dict[str, Any]] = []
    expected_keys: list[str] = []
    resume_results: list[dict[str, Any]] = []
    if tier == "archetypes":
        matrix = build_archetype_jobs(
            manifest["rows"],
            limit=limit,
            sample=sample,
            seed=seed,
            passage_bodies=passage_bodies,
        )
        selection = {
            "archetypes": matrix["archetypes"],
            "jobs": len(matrix["jobs"]),
            "unresolved": matrix["unresolved"],
            "coverage": matrix["coverage"],
            "limit": limit,
            "sample": sample,
            "seed": seed,
        }
        selected_jobs = matrix["jobs"]
        if modes_only:
            selected_jobs = []
    else:
        initiator_plan = select_initiator_rows(
            manifest["rows"],
            limit=limit,
            sample=sample,
            seed=seed,
            shard_index=shard_index,
            shard_count=shard_count,
        )["planned"]
        expected_keys = [str(row.get("key")) for row in initiator_plan]
        plan_hash = sl.plan_digest(expected_keys, strategy)
        identity["plan_digest"] = plan_hash
        report["ledger"]["identity"] = identity
        checkpoint = sl.load_ledger(ledger_path)
        if resume:
            usable, diagnostics, resume_results = sl.validate_resume(
                identity, plan_hash, expected_keys, checkpoint
            )
            report["resume"]["diagnostics"] = diagnostics
            report["resume"]["loaded_results"] = len(resume_results) if usable else 0
            if not usable and checkpoint.get("status") not in {"missing", "corrupt"}:
                report["resume"]["error"] = "checkpoint rejected: " + "; ".join(diagnostics[:4])
        elif legacy_resume_path.exists():
            report["resume"]["legacy_ignored"] = (
                "legacy completed-only checkpoint is not valid resume evidence"
            )

        resumed_keys = {str(item.get("key")) for item in resume_results}
        selected_rows = [
            row for row in initiator_plan if str(row.get("key")) not in resumed_keys
        ]
        selection = select_initiator_rows(
            initiator_plan,
            resume_keys=resumed_keys,
            shard_index=0,
            shard_count=1,
        )
        selection.pop("planned", None)
        selection["limit"] = limit
        selection["sample"] = sample
        selection["seed"] = seed
        selection["shard_index"] = shard_index
        selection["shard_count"] = shard_count
        selection["planned_count"] = len(initiator_plan)
        selection["resume_keys"] = len(resumed_keys)
        selection["selected_count"] = len(selected_rows)
        selection["selected_preview"] = [row["key"] for row in selected_rows[:10]]
        selection["planned_preview"] = expected_keys[:10]
        selection["plan_digest"] = plan_hash
        selected_jobs = selected_rows
        report["resume"]["skipped"] = selection.get("skipped_resume", 0)
        report["results"] = list(resume_results)
    report["selection"] = selection

    try:
        with sfa._session(
            html_path,
            headless=headless,
            timeout_ms=timeout_ms,
            bootstrap_settle_ms=bootstrap_settle_ms,
        ) as (page, boot, console):
            report["boot"] = boot
            report["console_tail"] = console[-120:]
            boot_error = sfa._boot_failed(boot)
            if boot_error:
                report["fatal_error"] = f"bootstrap failed: {boot_error}"
            else:
                load_ok = page.evaluate(ps.LOAD_FIXTURE, fixture_json)
                report["fixture_load"] = load_ok

                def _progress(record: dict[str, Any], position: int, total: int) -> None:
                    if position % 5 == 0 or position == total:
                        print(
                            f"[combat] {position}/{total} {record.get('key')}: "
                            f"{record.get('verdict')} {str(record.get('detail') or '')[:80]}",
                            flush=True,
                        )

                if tier == "archetypes" and selected_jobs:
                    print(
                        f"[combat] archetypes: {selection['archetypes']} specs -> "
                        f"{len(selected_jobs)} jobs",
                        flush=True,
                    )
                    report["results"] = run_archetype_jobs(
                        page,
                        selected_jobs,
                        max_rounds=max_rounds,
                        timeout_ms=timeout_ms,
                        progress=_progress,
                    )
                if tier == "initiators" and selected_jobs:
                    print(
                        f"[combat] initiators: sweeping {len(selected_jobs)}/"
                        f"{len(initiator_plan)} rows in shard {shard_index}/{shard_count} "
                        f"(resume skipped {selection['skipped_resume']})",
                        flush=True,
                    )
                    total_jobs = len(selected_jobs)
                    checkpoint: dict[str, Any] = {
                        "status": "running",
                        "identity": identity,
                        "plan_digest": plan_hash,
                        "planned_keys": list(expected_keys),
                        "results": list(report["results"]),
                        "completed": [
                            str(item.get("key")) for item in report["results"] if item.get("key")
                        ],
                    }
                    for position, row in enumerate(selected_jobs, 1):
                        chunk = run_initiator_rows(
                            page,
                            [row],
                            max_rounds=max_rounds,
                            timeout_ms=timeout_ms,
                            progress=None,
                        )
                        result = chunk[0]
                        report["results"].append(result)
                        sl.merge_result(checkpoint, expected_keys, result)
                        _progress(result, position, total_jobs)
                        if position % 25 == 0:
                            sl.save_ledger(ledger_path, checkpoint)
                    sl.save_ledger(ledger_path, checkpoint)
                    report["resume"]["completed"] = len(checkpoint.get("completed") or [])

                if run_modes and not modes_only:
                    mode_entry = pick_mode_entry(selected_jobs)
                    if mode_entry is None:
                        report["modes"] = [
                            {
                                "mode": mode,
                                "verdict": "not_applicable",
                                "rounds": 0,
                                "detail": "no archetype job available for the control-mode check",
                            }
                            for mode in CONTROL_MODES
                        ]
                    else:
                        print(
                            f"[combat] control modes: {', '.join(CONTROL_MODES)} x {mode_rounds} rounds "
                            f"on {mode_entry.get('key')}",
                            flush=True,
                        )
                    if mode_entry is not None:
                        # A stale fight left over from the matrix (or any
                        # prior state) poisons the mode check: force a fresh
                        # entry before running the mode rounds.
                        if _state(page).get("combat") == 1:
                            page.evaluate(ps.RESTORE_FIXTURE)
                        report["modes"] = run_control_modes(
                            page,
                            mode_entry,
                            rounds=mode_rounds,
                            timeout_ms=timeout_ms,
                        )
                elif modes_only:
                    jobs_for_mode = build_archetype_jobs(
                        manifest["rows"],
                        limit=limit,
                        sample=sample,
                        seed=seed,
                        passage_bodies=passage_bodies,
                    )["jobs"]
                    mode_entry = pick_mode_entry(jobs_for_mode)
                    report["selection"]["modes_only"] = True
                    if mode_entry is not None:
                        report["modes"] = run_control_modes(
                            page, mode_entry, rounds=mode_rounds, timeout_ms=timeout_ms
                        )
                report["console_tail"] = console[-120:]
    except Exception as exc:  # noqa: BLE001 - always emit a report
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:600]

    mode_failures = [
        str(mode.get("mode"))
        for mode in report.get("modes") or []
        if mode.get("verdict") != "ok"
    ]
    if tier == "initiators":
        order = {key: index for index, key in enumerate(expected_keys)}
        report["results"].sort(key=lambda item: order.get(str(item.get("key")), len(order)))
        report["resume"]["completed"] = len(report["results"])
        complete, completeness_diagnostics, completeness_summary = sl.validate_complete(
            expected_keys, report["results"]
        )
        if mode_failures:
            complete = False
            completeness_diagnostics.append(
                "control mode failures: " + ", ".join(mode_failures)
            )
        report["completeness"] = {
            "ok": complete,
            "diagnostics": completeness_diagnostics,
            "summary": completeness_summary,
            "expected_keys": len(expected_keys),
            "actual_results": len(report["results"]),
        }
        report["ledger"]["complete"] = complete
        report["ledger"]["validation"] = report["completeness"]
        merged_checkpoint = {
            "status": "complete" if complete else "incomplete",
            "identity": identity,
            "plan_digest": plan_hash,
            "planned_keys": list(expected_keys),
            "results": list(report["results"]),
            "completed": [
                str(item.get("key")) for item in report["results"] if item.get("key")
            ],
        }
        try:
            sl.save_ledger(ledger_path, merged_checkpoint)
        except Exception as exc:  # noqa: BLE001 - report remains the primary evidence
            report["ledger"]["save_error"] = f"{type(exc).__name__}: {exc}"[:300]
    else:
        report["completeness"] = {
            "ok": not mode_failures,
            "diagnostics": (
                ["control mode failures: " + ", ".join(mode_failures)]
                if mode_failures
                else []
            ),
            "summary": {"status": "complete" if not mode_failures else "incomplete"},
        }

    console_errors = [
        line
        for line in (report.get("console_tail") or [])
        if "pageerror:" in line or "出错" in line or line[:6].lower() == "error:"
    ]
    report["console_errors"] = {"count": len(console_errors), "sample": console_errors[-10:]}

    report["verdict_counts"] = _verdict_counts(report["results"])
    mode_counts = collections.Counter(
        str(mode.get("verdict")) for mode in report["modes"] or []
    )
    for verdict, count in mode_counts.items():
        report["verdict_counts"][f"mode:{verdict}"] = count
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    if baseline_path_in and baseline_path_in.exists():
        try:
            baseline = json.loads(baseline_path_in.read_text(encoding="utf-8"))
            report["baseline_diff"] = diff_against_baseline(report, baseline)
        except Exception as exc:  # noqa: BLE001
            report["baseline_diff"] = {"error": f"baseline unreadable: {exc}"}

    out = out_dir or default_out_dir(tier)
    write_report(report, out, report.get("baseline_diff"))
    if save_baseline:
        target_path = baseline_path_in or baseline_path(fixture_path, tier)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[combat] baseline sealed -> {target_path}", flush=True)
    return report


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DOL-X combat sweep (combat axis, engine A)"
    )
    parser.add_argument("target", type=Path, help="built .html or .zip to sweep")
    parser.add_argument("--tier", choices=TIERS, default=DEFAULT_TIER)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="report directory (default .local/sweep/combat-<tier>-<date>)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="fixture json (default .local/fixtures/base-1004.json)",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=DEFAULT_MANIFEST_OUT,
        help="where the freshly scanned initiator manifest is written",
    )
    parser.add_argument("--limit", type=int, default=None, help="first N archetypes / initiator rows")
    parser.add_argument("--sample", type=int, default=None, help="random N archetypes / initiator rows")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS, help="per-combat turn cap")
    parser.add_argument("--mode-rounds", type=int, default=DEFAULT_MODE_ROUNDS, help="rounds per control mode")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument("--bootstrap-settle-ms", type=int, default=1500)
    parser.add_argument("--headful", action="store_true", help="show the browser window")
    parser.add_argument("--resume", action="store_true", help="skip entry keys already in the resume file")
    parser.add_argument("--shard-index", type=int, default=0, help="zero-based shard index")
    parser.add_argument("--shard-count", type=int, default=1, help="total shard count")
    parser.add_argument("--baseline", type=Path, default=None, help="baseline json to diff against")
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="seal this run as the baseline (default .local/sweep/baselines/)",
    )
    parser.add_argument(
        "--skip-modes",
        action="store_true",
        help="skip the four control-mode checks in the archetypes tier",
    )
    parser.add_argument(
        "--modes-only",
        action="store_true",
        help="run only the four control-mode checks (fast subset for the modes acceptance)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.target.exists():
        print(f"[combat] target does not exist: {args.target}")
        return 2
    if not args.fixture.exists():
        print(f"[combat] fixture does not exist: {args.fixture}")
        return 2
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        print("[combat] invalid shard: require count >= 1 and 0 <= index < count")
        return 2
    report = run(
        args.target,
        tier=args.tier,
        fixture_path=args.fixture,
        out_dir=args.out,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        timeout_ms=args.timeout_ms,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
        headless=not args.headful,
        max_rounds=args.max_rounds,
        run_modes=not args.skip_modes,
        modes_only=args.modes_only,
        resume=args.resume,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        baseline_path_in=args.baseline,
        save_baseline=args.save_baseline,
        manifest_out=args.manifest_out,
        mode_rounds=args.mode_rounds,
    )
    print(f"[combat] verdicts={report['verdict_counts']}")
    print(f"[combat] manifest={report['manifest']['total']} rows; drift={report['manifest']['drift']['count']}")
    out_dir = args.out or default_out_dir(args.tier)
    print(f"[combat] report -> {out_dir / 'combat-sweep.md'}")
    hard = int((report.get("verdict_counts") or {}).get("hard_fail") or 0)
    if report.get("fatal_error"):
        return 1
    if not (report.get("completeness") or {}).get("ok", True):
        return 1
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
