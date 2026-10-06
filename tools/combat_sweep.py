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
# Only the unambiguous matrix paths are asserted: a "win" run must actually
# defeat the enemy, and a "submit" run may win by enemy orgasm (DoL resolves
# submission scenes through the same arousal-max branch). The lose/flee paths
# accept any confirmed terminal state and record which ending happened.
EXPECTED_OUTCOME_ACCEPTS: dict[str, tuple[str, ...]] = {
    "win": ("win",),
    "submit": ("submit", "win"),
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
# ``<<personN>>`` renders ``$NPCList[N-1]`` directly, so a passage that prints
# ``<<person4>>`` needs four slots even when ``$enemyno`` only covers 2.
PERSON_INDEX_RE = re.compile(r"<<\s*person\s*(\d+)\s*>>")

# --------------------------------------------------------------------------- #
# Entry precursors (game-side generation preamble)
# --------------------------------------------------------------------------- #
#
# Measured 2026-10-07 against the 1.0.0a build: entering a combat scene with
# only ``$molestationstart`` / ``$sexstart`` armed leaves ``$NPCList[0]`` as a
# 5-key shell (``chastity/location/pronouns/skills/traits``), so scenes that
# upstream only reaches *after* its own ``<<generate1>>`` / ``<<generateBEAST>>``
# chain crash inside ``hand_section`` ("NPC hand action unaccounted for") or the
# combat renderer's ``frontarm`` layer. The game's own debug menu
# (``setup.debugMenu.eventList``) records the canonical preambles, e.g.
# ``<<endcombat>> <<generate1>> <<person1>> <<set $sexstart to 1>>`` for men and
# ``<<beastNNPCinit>> <<npc "Black Wolf">>`` for named beasts. The driver
# replays those game-side widgets before arming the flow flag and records the
# derivation basis in every result; nothing is silently patched.
# v2 (2026-10-07): token-less beast rows may now fall back to a *deep*
# predecessor/wider-graph chain (``deep-predecessor:`` basis, confidence
# ``low``); v1 runs never produced those, so run identity must differ.
PRECURSOR_SCHEMA = "combat-precursor-v2"
BEAST_PRECURSOR_KINDS = ("beastCombatInit", "beastNEWinit", "beastNNPCinit")
BEAST_GEN_RE = re.compile(
    r"<<\s*(beastNEWinit|generateBEAST)\s+\d+\s+\"?([A-Za-z][A-Za-z ]*?)\"?(?=\s|>>)"
)
BEAST_CHAIN_RE = re.compile(
    r"<<\s*(beastNEWinit|generateBEAST)\s+(\d+)\s+\"?([A-Za-z][A-Za-z ]*?)\"?(?=\s|>>)"
)
CHAIN_CLEAR_RE = re.compile(r"<<\s*clearnpc\s*>>")
CHAIN_TRAILING_RE = re.compile(r"<<\s*(?:generate|generatep|person)(\d+)\s*>>")
CHAIN_AFTER_WINDOW = 400
CHAIN_CLEAR_WINDOW = 150
CHAIN_BEFORE_WINDOW = 1400
LINK_TO_RE_TEMPLATE = r"\[\[[^\]|]*\|\s*{target}\s*\]\]"


def named_npc_in_title(passage: str, named_npcs: Sequence[str]) -> str | None:
    """Longest ``$NPCNameList`` entry that appears as a whole word in the title."""
    text = str(passage or "")
    best: str | None = None
    for name in named_npcs:
        token = str(name).strip()
        if len(token) < 3:
            continue
        if re.search(
            r"(?<![A-Za-z])" + re.escape(token) + r"(?![A-Za-z])", text, flags=re.IGNORECASE
        ):
            if best is None or len(token) > len(best):
                best = token
    return best


def _link_predecessors(target: str, passage_bodies: Mapping[str, str]) -> list[str]:
    pattern = re.compile(LINK_TO_RE_TEMPLATE.format(target=re.escape(str(target or ""))))
    return [
        str(name)
        for name, body in passage_bodies.items()
        if str(name) != target and pattern.search(str(body or ""))
    ]


def _beast_token_from_body(body: str, target: str | None = None) -> str | None:
    """First plausible beast type in ``body`` (preferring the link vicinity)."""
    text = str(body or "")
    windows: list[str] = []
    if target:
        match = re.search(LINK_TO_RE_TEMPLATE.format(target=re.escape(str(target))), text)
        if match:
            windows.append(text[max(0, match.start() - CHAIN_BEFORE_WINDOW) : match.start()])
    windows.append(text)
    for window in windows:
        for match in BEAST_GEN_RE.finditer(window):
            token = str(match.group(2) or "").strip().lower()
            if token and token not in {"the", "a", "an"}:
                return token
    return None


def _beast_chain_from_body(body: str, target: str | None = None) -> dict[str, Any] | None:
    """Ordered generation chain the game itself runs before ``target``.

    Returns ``{"widgets", "token"}`` or ``None``. The game's own events spell
    out the canonical preambles, e.g. ``Widgets Events Beach`` documents
    ``<<clearnpc>><<beastNEWinit 1 dog>><<generate2>>``: ``beastNEWinit``
    requires no existing NPCs, so the slot reset comes first and any human
    owner must be generated afterwards. Replaying the ordered chain (instead
    of only the beast init) keeps ``$NPCList[0]`` as the beast and satisfies
    both the ``bhim`` index and the ``frontarm`` layer renderer.
    """
    text = str(body or "")
    windows: list[str] = []
    if target:
        match = re.search(LINK_TO_RE_TEMPLATE.format(target=re.escape(str(target))), text)
        if match:
            windows.append(text[max(0, match.start() - CHAIN_BEFORE_WINDOW) : match.start()])
    windows.append(text)
    for window in windows:
        matches = [
            item
            for item in BEAST_CHAIN_RE.finditer(window)
            if str(item.group(3) or "").strip().lower() not in {"", "the", "a", "an"}
        ]
        if not matches:
            continue
        last = matches[-1]
        token = str(last.group(3) or "").strip().lower()
        prefix = ""
        clears = list(CHAIN_CLEAR_RE.finditer(window[: last.start()]))
        if clears and last.start() - clears[-1].end() <= CHAIN_CLEAR_WINDOW:
            prefix = "<<clearnpc>>"
        chain = f"{prefix}<<{last.group(1)} {last.group(2)} {token}>>"
        cursor = last.end()
        if window.startswith(">>", cursor):
            cursor += 2
        end = min(len(window), cursor + CHAIN_AFTER_WINDOW)
        while cursor < end:
            gap = re.match(r"\s*", window[cursor:end])
            cursor += gap.end() if gap else 0
            trailing = CHAIN_TRAILING_RE.match(window, cursor)
            if not trailing:
                break
            chain += trailing.group(0)
            cursor = trailing.end()
        return {"widgets": chain, "token": token}
    return None


# Token-less ``<<beastCombatInit>>`` reads ``$beasttype``, which the real
# playthrough set in an earlier scene. Some entries only reach that scene
# through 3-4 link hops, or through a widget the parent passage calls.
# Measured 2026-10-07 (``.local/sweep/candidate-probe-1007.json``): replaying
# the deep candidate chain took ``Docks Watch Dog`` / ``Pound Deviant Sex`` /
# ``Wolf Patrol Sex`` / ``Street Collar Dog 2`` from ``leftActionInit`` DOM
# errors to clean 19-25 round wins, while no precursor kept them broken. The
# basis is tagged ``deep-predecessor:`` and the record carries
# ``confidence: low`` so a pass stays auditable.
DEEP_PRECURSOR_DEPTH = 4


def beast_widget_chains(
    body: str, widget_bodies: Mapping[str, str]
) -> list[tuple[str, dict[str, Any]]]:
    """``(widget name, chain)`` for every called widget whose body generates a beast."""
    found: list[tuple[str, dict[str, Any]]] = []
    for match in MACRO_CALL_RE.finditer(str(body or "")):
        widget_body = widget_bodies.get(match.group(1))
        if not widget_body or "beast" not in widget_body:
            continue
        chain = _beast_chain_from_body(widget_body)
        if chain:
            found.append((match.group(1), chain))
    return found


def deep_beast_precursors(
    passage: str,
    *,
    passage_bodies: Mapping[str, str],
    widget_bodies: Mapping[str, str] | None = None,
    max_depth: int = DEEP_PRECURSOR_DEPTH,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Beast generation chains found in the wider upstream link graph.

    Breadth-first over link predecessors (document order per depth). Each
    parent contributes its own body chain first, then any beast-generating
    widget it calls. Results are *candidates*: a token found this far from the
    entry is evidence, not proof, so ``derive_precursor`` tags the chosen one
    ``deep-predecessor`` and the ledger keeps the full list for audit.
    """
    widgets = widget_bodies or {}
    seen: set[str] = {str(passage)}
    frontier: list[str] = [str(passage)]
    candidates: list[dict[str, Any]] = []
    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for parent in _link_predecessors(current, passage_bodies):
                if parent in seen:
                    continue
                seen.add(parent)
                next_frontier.append(parent)
                parent_body = str(passage_bodies.get(parent) or "")
                chain = _beast_chain_from_body(parent_body)
                if chain:
                    candidates.append(
                        {
                            "token": chain.get("token"),
                            "source": parent,
                            "via": "body",
                            "widget_name": None,
                            "depth": depth,
                            "widgets": chain.get("widgets"),
                            "verified": False,
                        }
                    )
                for widget_name, widget_chain in beast_widget_chains(parent_body, widgets):
                    candidates.append(
                        {
                            "token": widget_chain.get("token"),
                            "source": parent,
                            "via": f"widget:{widget_name}",
                            "widget_name": widget_name,
                            "depth": depth,
                            "widgets": widget_chain.get("widgets"),
                            "verified": False,
                        }
                    )
                if len(candidates) >= limit:
                    return candidates[:limit]
        frontier = next_frontier
        if not frontier:
            break
    return candidates[:limit]


# Human encounters allocate ``$NPCList`` slots with ``<<generateN>>`` and
# ``<<npc Name N>>``. Some passages then print ``<<personN>>`` for slots beyond
# their own ``$enemyno`` (Underground Robin Kiss Molestation renders
# ``<<person4>>`` while ``<<maninit>>`` only makes 2), because upstream reaches
# them through a predecessor that ran the full chain itself
# (``Underground Robin Kiss Intro``: ``<<generate1>><<npc Robin 2>><<generate3>><<generate4>>``).
# Replaying that predecessor run keeps the entry synthetic but game-authored.
#
# Measured 2026-10-07: every slot macro takes a 1-based number and fills
# ``$NPCList[N-1]`` (``<<generate2>>`` -> ``generateNPC 2`` -> index 1,
# ``<<npc Robin 2>>`` -> ``_npcno = 2 - 1``, ``<<generatePolice 1>>`` ->
# ``generateNPC 1`` -> index 0, ``<<beastNEWinit 2 wolf>>`` -> slots 1-2).
# A chain is only usable when it fills *every* slot the passage prints: a
# ``<<generate2>>``-only chain leaves ``$NPCList[0]`` a fixture shell, and
# ``combatinit`` then marks that shell ``active``, so ``leftgrabnew`` dies on
# ``$NPCList[$lefttarget].penis`` (Courtyard/Docks/Home/Soup Kitchen/Street
# Collar). Chains that do not cover 1..need are rejected in favour of the debug
# menu's own contiguous ``<<generate1>>...`` preamble.
MANINIT_SLOT_MACRO_RE = re.compile(
    r"<<\s*(?P<macro>clearnpc(?:\s+[^>]*?)?"
    r"|generateRole\s+(?P<role>\d+)(?:\s+[^>]*?)?"
    r"|generatel(?:\s+[^>]*?)?"
    r"|generate[A-Za-z_]*\s+(?P<slotarg>\d+)(?:\s+[^>]*?)?"
    r"|generate[A-Za-z_]*?(?P<glued>\d+)(?:\s+[^>]*?)?"
    r"|beastNEWinit\s+(?P<beastnew>\d+)(?:\s+[^>]*?)?"
    r"|npc\s+[^>]+?\s+(?P<npcrow>\d+)(?:\s+[^>]*?)?"
    r")\s*>>"
)


def _maninit_slot_range(match: re.Match[str]) -> range:
    """0-based ``$NPCList`` indices one slot macro fills.

    The 1-based/0-based split comes from the widgets themselves (measured
    2026-10-07 against ``Widgets NPC Generation``): ``generateNPC N`` sets
    ``_n = N - 1`` and bumps ``$enemyno``, and every wrapper funnels into it --
    ``<<generateN>>``, glued variants (``<<generatecf1>>``, ``<<generatey3>>``,
    ``<<generatep2>>``, ``<<generatePlant1>>``), and argument variants
    (``<<generatePolice N>>``, ``<<generateTemple N>>``, ``<<generateDemon N>>``,
    ``<<generateBEAST N>>``, ``<<generateNPC N>>``) are therefore 1-based slots.
    ``<<generateRole N ...>>`` is the exception: its own docs say "Slot one
    would be 0" and it calls ``generateNPC N + 1``, so it fills index ``N``.
    ``<<generatel>>`` picks ``$enemyno + 1`` dynamically: it bumps the count but
    can never prove which slot it filled, so it never satisfies coverage alone.
    """
    macro = str(match.group("macro") or "")
    if macro.startswith("clearnpc") or macro.startswith("generatel"):
        return range(0)
    if match.group("role") is not None:
        value = int(match.group("role"))
        return range(value, value + 1)
    if macro.startswith("beastNEWinit"):
        count = int(match.group("beastnew") or 1)
        return range(0, max(1, min(6, count)))
    value = match.group("slotarg") or match.group("glued") or match.group("npcrow")
    if value:
        return range(int(value) - 1, int(value))
    return range(0)


def _maninit_run_covers(run: Sequence[re.Match[str]], need: int) -> bool:
    """A run is usable only when it fills 1..need *and* bumps ``$enemyno``.

    ``<<npc Name N>>`` writes a row but never increments ``$enemyno``, so a
    chain made only of named calls leaves ``combatinit`` with ``$enemynomax`` 0
    and the action widgets then read ``$NPCList[undefined]``.
    """
    covered: set[int] = set()
    bumps = False
    for item in run:
        covered.update(_maninit_slot_range(item))
        if not str(item.group("macro") or "").startswith("clearnpc") and not str(
            item.group("macro") or ""
        ).startswith("npc"):
            bumps = True
    return bumps and set(range(need)) <= covered


def _maninit_slot_chain(body: str, target: str | None, need: int) -> dict[str, Any] | None:
    """Contiguous slot-generation run in ``body`` that fills slots 1..``need``."""
    text = str(body or "")
    windows: list[str] = []
    if target:
        # Each occurrence of the link gets its own vicinity: event-body records
        # hold several branches side by side (night ``<<generate2>><<generate3>>``
        # vs. day ``<<generate1>><<generate2>>`` in ``Widgets Street``), and only
        # the branch that actually links here should be replayed.
        for match in re.finditer(LINK_TO_RE_TEMPLATE.format(target=re.escape(str(target))), text):
            windows.append(text[max(0, match.start() - CHAIN_BEFORE_WINDOW) : match.start()])
    windows.append(text)
    for window in windows:
        matches = list(MANINIT_SLOT_MACRO_RE.finditer(window))
        if not matches:
            continue
        runs: list[list[re.Match[str]]] = []
        current: list[re.Match[str]] = []
        previous_end: int | None = None
        for item in matches:
            # A clear wipes every slot generated before it, so no chain may
            # span one: cut the run and drop the clear itself (the fixture is
            # restored before each row, so there is nothing stale to clear).
            if str(item.group("macro") or "").startswith("clearnpc"):
                if current:
                    runs.append(current)
                current = []
                previous_end = None
                continue
            if (
                current
                and previous_end is not None
                and window[previous_end : item.start()].strip() != ""
            ):
                runs.append(current)
                current = []
            current.append(item)
            previous_end = item.end()
        if current:
            runs.append(current)
        for run in reversed(runs):
            if _maninit_run_covers(run, need):
                covered: set[int] = set()
                for item in run:
                    covered.update(_maninit_slot_range(item))
                return {
                    "widgets": "".join(item.group(0) for item in run),
                    "slots": max(covered) + 1 if covered else 0,
                }
    return None


def _maninit_predecessor_chain(
    passage: str,
    need: int,
    passage_bodies: Mapping[str, str],
    *,
    max_depth: int = 2,
) -> dict[str, Any] | None:
    """Find the predecessor whose own slot chain fills ``need`` NPCs."""
    frontier = [passage]
    seen = {passage}
    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for target in frontier:
            for parent in _link_predecessors(target, passage_bodies):
                if parent in seen:
                    continue
                seen.add(parent)
                chain = _maninit_slot_chain(
                    str(passage_bodies.get(parent) or ""), target, need
                )
                if chain is not None:
                    return {
                        "widgets": chain["widgets"],
                        "slots": chain["slots"],
                        "parent": parent,
                        "depth": depth,
                    }
                next_frontier.append(parent)
        frontier = next_frontier
    return None


# The game's own click path: event scenes set their start flags inside the
# ``<<link>>`` body (``<<link [[Fight them both|Courtyard Crush Fight]]>><<set
# $fightstart to 1>><</link>>``). Measured 2026-10-07: replaying only the slot
# chain leaves ``$fightstart`` 0, the scene skips ``<<maninit>>``, ``$combat``
# and ``$enemynomax`` stay 0 and ``leftgrabnew`` then reads
# ``$NPCList[undefined].penis`` (Courtyard Crush / Docks / Home Intervene /
# Soup Kitchen / Rent First Robin / Street Bully Orphan Fight). Only the
# immediate predecessors' link bodies are replayed, and only macros on the
# allowlist: ``<<endevent>>`` (which clears the freshly generated NPCs) and
# scene-specific macros are deliberately left out.
LINK_BODY_RE = re.compile(
    r"<<link\s+\[\[([^\]|]*)(?:\|([^\]]*))?\]\]\s*>>(.*?)<</link>>", re.S
)
LINK_BODY_ALLOWED_MACROS = frozenset(
    {"set", "def", "sub", "pass", "stress", "npcincr", "wolfDefiant", "generatePolice"}
)


def _maninit_link_candidates(
    passage: str, passage_bodies: Mapping[str, str]
) -> list[dict[str, Any]]:
    """Every game link that leads to ``passage``, with its own start-flag run.

    Each candidate carries the text right before the link (``window``) and the
    allowlisted macros inside the link body (``widgets``); slot-generation
    macros are dropped here -- the derivation chain already owns ``$NPCList``
    and replaying both would generate every NPC twice (``$enemyno`` would count
    4 for two rows, so ``combatinit`` marks shells active).
    """
    candidates: list[dict[str, Any]] = []
    for parent in _link_predecessors(passage, passage_bodies):
        body = str(passage_bodies.get(parent) or "")
        for match in LINK_BODY_RE.finditer(body):
            target = str(match.group(2) or match.group(1) or "").strip()
            if target != passage:
                continue
            widgets: list[str] = []
            for macro in MACRO_CALL_RE.finditer(match.group(3)):
                if macro.group(1) not in LINK_BODY_ALLOWED_MACROS:
                    continue
                text = macro.group(0)
                if MANINIT_SLOT_MACRO_RE.fullmatch(text):
                    continue
                if text not in widgets:
                    widgets.append(text)
            candidates.append(
                {
                    "parent": parent,
                    "window": body[max(0, match.start() - CHAIN_BEFORE_WINDOW) : match.start()],
                    "widgets": "".join(widgets),
                }
            )
    return candidates


def link_body_precursors(passage: str, passage_bodies: Mapping[str, str]) -> dict[str, Any]:
    """Start-flag macros the first contributing game link runs for ``passage``.

    A body often holds two branches to the same scene (fight / walk away), and
    mixing their flags would build a path upstream never takes.
    """
    for candidate in _maninit_link_candidates(passage, passage_bodies):
        if candidate["widgets"]:
            return {"widgets": str(candidate["widgets"]), "parents": [candidate["parent"]]}
    return {"widgets": "", "parents": []}


# ``<<personN>>`` also hides inside widgets reached from a sequel passage:
# Balloon Sex renders ``<<balloonRobinHelped>>`` on ``Balloon Sex Finish``,
# which prints ``<<person2>>`` -- so the entry's own body alone under-counts the
# slots the scene will need.
WIDGET_DEF_RE = re.compile(r"<<widget\s+\"([^\"]+)\">>(.*?)<</widget>>", re.S)


def build_widget_index(passage_bodies: Mapping[str, str]) -> dict[str, str]:
    """Map ``<<widget "name">>`` bodies from the artifact's passage store."""
    index: dict[str, str] = {}
    for body in passage_bodies.values():
        text = str(body or "")
        if "<<widget" not in text:
            continue
        for match in WIDGET_DEF_RE.finditer(text):
            index.setdefault(match.group(1), match.group(2))
    return index


def named_slot_chain(named: str, need: int, reference: int) -> tuple[str, str]:
    """``<<npc "Name">>`` for the primary slot plus the game's generator for the rest.

    Used when the scene title names an NPC but no real predecessor chain is
    derivable: the named NPC takes the first slot and every slot the scene (or
    its sequel) renders beyond ``$enemyno`` is filled by ``<<generateN>>``.
    Returns ``(widgets, basis)``.
    """
    widgets = (
        f'<<npc "{named}">>'
        + "".join(f"<<generate{index}>>" for index in range(2, need + 1))
        + "".join(f"<<person{index}>>" for index in range(1, need + 1))
    )
    basis = f"title-npc:{named}"
    if need > 1:
        basis += f"+generate2..{need}(person{max(reference, need)})"
    return widgets, basis


def person_reference_closure(
    passage: str,
    body: str,
    passage_bodies: Mapping[str, str],
    widget_bodies: Mapping[str, str],
    *,
    max_successors: int = 8,
    widget_depth: int = 2,
) -> int:
    """Deepest ``<<personN>>`` the entry and its immediate successors render."""
    successors: list[str] = []
    for match in WIKI_LINK_RE.finditer(str(body or "")):
        target = str(match.group(2) or match.group(1) or "").strip()
        if target and target != passage and target not in successors:
            successors.append(target)
        if len(successors) >= max_successors:
            break
    bodies = [str(body or "")]
    bodies.extend(str(passage_bodies.get(name) or "") for name in successors)
    refs: set[int] = set()
    frontier = bodies
    for _ in range(widget_depth + 1):
        next_frontier: list[str] = []
        for item in frontier:
            refs.update(int(value) for value in PERSON_INDEX_RE.findall(item))
            for macro in MACRO_CALL_RE.finditer(item):
                widget = widget_bodies.get(macro.group(1))
                if widget:
                    next_frontier.append(widget)
        frontier = next_frontier
        if not frontier:
            break
    return max(refs, default=0)


def _derive_precursor_core(
    row: Mapping[str, Any],
    *,
    passage_bodies: Mapping[str, str],
    named_npcs: Sequence[str] = (),
    widget_bodies: Mapping[str, str] | None = None,
    max_depth: int = 2,
) -> dict[str, Any]:
    """Pick the game-side generation preamble for one initiator row.

    Returns ``{"widgets": str|None, "basis": str|None, "reason": str|None}``;
    ``widgets`` is the exact wiki markup replayed through
    ``Wikifier.wikifyEval`` before the flow flags are armed.

    ``confidence`` is only set to ``"low"`` for the deep fallback
    (``deep-predecessor:`` bases); an absent value is the standard derivation.

    ``derive_precursor`` wraps this with the area-state bootstrap; call the
    wrapper unless the raw chain is what you want.
    """
    kind = str(row.get("kind") or "")
    passage = str(row.get("passage") or "")
    token = str(row.get("token") or "")
    info: dict[str, Any] = {
        "schema": PRECURSOR_SCHEMA,
        "kind": kind,
        "widgets": None,
        "basis": None,
        "reason": None,
    }
    if kind == "maninit":
        named = named_npc_in_title(passage, named_npcs)
        body = str(passage_bodies.get(passage) or "")
        count = 1
        enemy_match = re.search(r"<<\s*set\s+\$enemyno\s+to\s+(\d+)\s*>>", body)
        if enemy_match:
            count = max(1, min(6, int(enemy_match.group(1))))
        slot_refs = [int(item) for item in PERSON_INDEX_RE.findall(body)]
        reference = max(slot_refs) if slot_refs else 0
        # The entry passage itself may never print the extra slots; its finish
        # passage (or a widget it calls) does. ``Underground Robin Stage
        # Molestation`` only sets ``$enemyno`` to 1, yet its ``… Finish``
        # renders ``<<person2>>`` in *every* branch, so slot 1 must exist or
        # the landing passage dies on "Undefined NPC in personselect 1".
        # Run the closure for named rows too: a title-named NPC alone is not
        # evidence that the scene needs no generated slot (the named NPC can
        # be a bystander, as in that stage scene where Robin is on stage while
        # a generated group is the aggressor).
        reference = max(
            reference,
            person_reference_closure(
                passage, body, passage_bodies, widget_bodies or {}
            ),
        )
        need = max(1, min(6, max(count, reference)))
        candidates = _maninit_link_candidates(passage, passage_bodies)
        # Fallback flags: the first game link that carries any. Used when the
        # chain has to come from somewhere else (debug menu / target search);
        # scene start flags such as ``<<set $fightstart to 1>>`` live only in
        # these link bodies.
        link_widgets = ""
        link_parent = None
        for candidate in candidates:
            if candidate["widgets"]:
                link_widgets = str(candidate["widgets"])
                link_parent = str(candidate["parent"])
                break
        if reference > count:
            # The passage prints ``<<personN>>`` itself, so slot N-1 must exist
            # even when ``$enemyno`` only covers the aggressors
            # (``Underground Robin Kiss Molestation`` renders ``<<person4>>``
            # with ``$enemyno`` 2 and dies on "Undefined NPC in personselect 3").
            # The game's own predecessor chain wins over the synthetic
            # title-named NPC: when a scene needs more slots than ``$enemyno``
            # covers, the real branch that links into it is the faithful
            # fixture (``Underground Robin Stage Intro`` generates the group
            # with ``<<generate1>><<generate2>>``; Robin is never in the list).
            chain: dict[str, Any] | None = None
            chain_parent: str | None = None
            for candidate in candidates:
                # Prefer the chain that sits in the same branch as the link we
                # emulate: replaying the day ``<<generate1>><<generate2>>`` run
                # together with the night branch's ``$phase`` mismatch made
                # Street Collar Molestation clone a fixture shell into row 2.
                candidate_chain = _maninit_slot_chain(str(candidate["window"]), None, need)
                if candidate_chain is not None:
                    chain = candidate_chain
                    chain_parent = str(candidate["parent"])
                    link_widgets = str(candidate["widgets"] or "")
                    link_parent = chain_parent
                    break
            if chain is None:
                chain = _maninit_predecessor_chain(passage, need, passage_bodies)
                if chain is not None:
                    chain_parent = str(chain["parent"])
            if chain is not None:
                info["widgets"] = chain["widgets"]
                info["basis"] = (
                    f"predecessor:{chain_parent}:slots{chain['slots']}(person{reference})"
                )
            elif named:
                # No real chain derivable: keep the named NPC as the primary
                # slot and fill the remaining slots with the game's generator.
                info["widgets"], info["basis"] = named_slot_chain(named, need, reference)
            else:
                info["widgets"] = "".join(
                    f"<<generate{i}>>" for i in range(1, need + 1)
                ) + "".join(f"<<person{i}>>" for i in range(1, need + 1))
                info["basis"] = f"debug-menu:generate1..{need}+person1..{need}(person{reference})"
        elif named:
            info["widgets"], info["basis"] = named_slot_chain(named, need, reference)
        elif need > 1:
            info["widgets"] = "".join(f"<<generate{i}>>" for i in range(1, need + 1)) + "".join(
                f"<<person{i}>>" for i in range(1, need + 1)
            )
            info["basis"] = f"debug-menu:generate1..{need}+person1..{need}"
        else:
            info["widgets"] = "<<generate1>><<person1>>"
            info["basis"] = "debug-menu:generate1+person1"
        if link_widgets:
            info["widgets"] = str(info["widgets"] or "") + link_widgets
            info["basis"] = f"{info['basis']}|link-body:{link_parent}"
        return info
    if kind not in BEAST_PRECURSOR_KINDS:
        info["reason"] = f"kind {kind!r} has no NPC hand/frontarm dependency"
        return info
    named = named_npc_in_title(passage, named_npcs)
    if named:
        info["widgets"] = f'<<beastNNPCinit>><<npc "{named}">>'
        info["basis"] = f"title-nnpc:{named}"
        return info
    if token and token not in {"unknown", "dynamic"}:
        if any(token.casefold() == str(item).strip().casefold() for item in named_npcs):
            info["widgets"] = f'<<beastNNPCinit>><<npc "{token}">>'
            info["basis"] = f"row-token-nnpc:{token}"
        else:
            info["widgets"] = f"<<generateBEAST 1 {token}>>"
            info["basis"] = f"row-token:{token}"
        return info
    body = str(passage_bodies.get(passage) or "")
    if "$farm_work." in body:
        # "Farm Pigs Hand" self-generates through ``beastNEWinit 1 pig
        # $farm_work.pig.gender ...``; the fixture has no ``$farm_work`` yet,
        # so run the game's own farm generator for the pig slot.
        info["widgets"] = (
            "<<set $farm_work to {}>>"
            "<<set $farm_work.pig to {monster_roll: false}>>"
            "<<farm_gen pig>>"
        )
        info["basis"] = "self-generation:farm_gen(pig)"
        return info
    frontier = [passage]
    seen = {passage}
    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for target in frontier:
            for parent in _link_predecessors(target, passage_bodies):
                if parent in seen:
                    continue
                seen.add(parent)
                parent_body = str(passage_bodies.get(parent) or "")
                chain = _beast_chain_from_body(parent_body, target)
                if chain is not None:
                    info["widgets"] = chain["widgets"]
                    info["basis"] = f"predecessor:{parent}:depth{depth}"
                    return info
                derived = _beast_token_from_body(parent_body, target)
                if derived:
                    info["widgets"] = f"<<beastNEWinit 1 {derived}>>"
                    info["basis"] = f"predecessor:{parent}:depth{depth}"
                    return info
                next_frontier.append(parent)
        frontier = next_frontier
        if not frontier:
            break
    deep = deep_beast_precursors(
        passage,
        passage_bodies=passage_bodies,
        widget_bodies=widget_bodies,
        max_depth=DEEP_PRECURSOR_DEPTH,
        limit=1,
    )
    if deep:
        candidate = deep[0]
        info["widgets"] = candidate.get("widgets")
        via = str(candidate.get("via") or "body")
        info["basis"] = (
            f"deep-predecessor:{candidate.get('source')}:{via}:depth{candidate.get('depth')}"
        )
        info["confidence"] = "low"
        info["token"] = candidate.get("token")
        return info
    info["reason"] = "no beast token derivable from row, passage body, or predecessor chain"
    return info


# State a real playthrough already carries when these passages run. The
# synthetic rows jump straight into the fight, so the exit passage dies on the
# area's (or event chain's) own state reads. Measured 2026-10-07:
#
# * ``combat-deep-1007j`` — of the 16 deep rows, the 5 that still failed all
#   died *after* the fight: ``<<setTowerTemp>>`` reads ``$bird.upgrades.shelter``,
#   ``<<pound_status>>`` reads ``$pound.status`` and the prison Finish reads
#   ``$prison.attention`` / ``$prison.schedule``. Fix: replay the game's own
#   area init widget (``bird_init`` / ``pound_init`` / ``prison_init``) ahead of
#   the beast chain.
# * ``combat-personn-1007i`` — the remaining fixture_insufficient rows are
#   mid-event entries whose Finish reads state the parent event chain had
#   already built (``$pubfame`` favour tasks, ``$farm_assault``, ``$island``,
#   ``$bus``, ``C.npc.Sydney.init``). Fix: replay the chain's own initializer or
#   seed the exact field the Finish writes, and nothing else.
AREA_BOOTSTRAPS: tuple[dict[str, str], ...] = (
    {
        "pattern": r"^Bird\b",
        "widgets": "<<bird_init>>",
        "tag": "area-bootstrap:bird_init",
        "evidence": (
            "bird_init sets $bird.upgrades + $bird.hunts (tower and hunt scenes)"
        ),
    },
    {
        "pattern": r"^Pound\b",
        "widgets": "<<pound_init>>",
        "tag": "area-bootstrap:pound_init",
        "evidence": "pound_init sets $pound.status/sneak/progress/tasks",
    },
    {
        "pattern": r"^Prison\b",
        "widgets": (
            "<<prison_init>><<set $prison_intro to 1>>"
            '<<generateRole 0 "anxious" "guard">><<saveNPC 0 "anxious_guard">>'
        ),
        "tag": "area-bootstrap:prison_init+anxious_guard",
        "evidence": (
            "prison_init sets $prison.*; $prison_intro=1 makes "
            "generate_anxious_guard load slot 0 (its else-branch writes slot 1)"
        ),
    },
    {
        "pattern": r"^Bailey Sheet Fight\b",
        "widgets": (
            "<<set $pubfame to {seen: [], tasksDone: []}>>"
            '<<set $pubfame.status to "accepted">>'
            '<<set $pubfame.task to "bailey">>'
            "<<set $pubfame.bailey to {}>>"
            '<<set $pubfame.bailey.fight to "ready">>'
        ),
        "tag": "status-bootstrap:pubfame-bailey",
        "evidence": (
            "pubfame favour system seeds {seen, tasksDone} at Pub Fame Intro and "
            "creates $pubfame[task] on accept; Bailey Sheet Fight Finish writes "
            "$pubfame.bailey.fight"
        ),
    },
    {
        "pattern": r"^Farm Assault\b",
        "widgets": (
            '<<set $bus to "yard">>'
            "<<if $farm is undefined>><<set $farm to {}>><</if>>"
            "<<farm_assault_init>>"
        ),
        "tag": "status-bootstrap:farm_assault_init",
        "evidence": (
            "Farm Assault Start runs <<set $bus to 'yard'>><<farm_assault_init>>; "
            "farm_assault_init reads $farm.kennel, so seed $farm first"
        ),
    },
    {
        "pattern": r"^Hospital Keycard\b",
        "widgets": (
            "<<set $pubfame to {seen: [], tasksDone: []}>>"
            '<<set $pubfame.status to "accepted">>'
            '<<set $pubfame.task to "hospital">>'
            "<<set $pubfame.hospital to {}>>"
        ),
        "tag": "status-bootstrap:pubfame-hospital",
        "evidence": (
            "Hospital Keycard Seduce Sex Finish reads $pubfame.status; the "
            "hospital favour is created by the pubfame accept flow"
        ),
    },
    {
        "pattern": r"^Island Wood\b",
        "widgets": (
            "<<island_init>>"
            "<<if $island.wood is undefined>><<set $island.wood to 0>><</if>>"
        ),
        "tag": "status-bootstrap:island_init",
        "evidence": (
            "Island Wood Rape Finish does $island.wood += 3 and then "
            "island_explore_end; island_init seeds $island (wood included)"
        ),
    },
    {
        "pattern": r"^Street Car\b",
        "widgets": (
            '<<if $bus is undefined>><<set $bus to "commercial">><</if>>'
            '<<if $location isnot "alley">><<set $location to "alley">><</if>>'
        ),
        "tag": "status-bootstrap:street-bus",
        "evidence": (
            "Street Car Sex Finish builds its leave target from "
            "$bus.toUpperFirst() plus ($location is 'alley' ? ' Alleyways' : "
            "' Street'); the event triggers from alley street encounters"
        ),
    },
    {
        "pattern": r"^Temple Confess Sydney\b",
        "widgets": (
            "<<set C.npc.Sydney.init to 1>>"
            "<<if $sydneySeen is undefined>><<set $sydneySeen to []>><</if>>"
        ),
        "tag": "status-bootstrap:sydney-init",
        "evidence": (
            "statusCheck('Sydney') only runs sydneyStatusCheck (which sets "
            "_sydneyStatus / _sydneyChastity) when C.npc.Sydney.init is 1; the "
            "game's own cheat scenes use <<set C.npc.X.init to 1>> and seed "
            "$sydneySeen to [] (sydneyFinish does $sydneySeen.pushUnique)"
        ),
    },
)


def area_bootstrap(passage: str) -> dict[str, str] | None:
    """The area init entry whose passage pattern matches, if any."""
    for entry in AREA_BOOTSTRAPS:
        if re.search(entry["pattern"], str(passage or "")):
            return entry
    return None


def derive_precursor(
    row: Mapping[str, Any],
    *,
    passage_bodies: Mapping[str, str],
    named_npcs: Sequence[str] = (),
    widget_bodies: Mapping[str, str] | None = None,
    max_depth: int = 2,
) -> dict[str, Any]:
    """``_derive_precursor_core`` plus the area/event-state bootstrap prefix.

    Only rows that already produced a beast chain are touched: without a chain
    the bootstrap state alone cannot start the fight. The basis keeps both
    parts (``<chain basis>|area-bootstrap:<widget>`` /
    ``<chain basis>|status-bootstrap:<name>``) so a pass stays auditable.
    """
    info = _derive_precursor_core(
        row,
        passage_bodies=passage_bodies,
        named_npcs=named_npcs,
        widget_bodies=widget_bodies,
        max_depth=max_depth,
    )
    boot = area_bootstrap(str(row.get("passage") or ""))
    if boot and info.get("widgets"):
        info["widgets"] = f"{boot['widgets']}{info['widgets']}"
        if info.get("basis"):
            info["basis"] = f"{info['basis']}|{boot['tag']}"
    return info


def resolve_only_keys(value: str | None) -> list[str] | None:
    """``--only-keys`` accepts a comma list or a file (one key per line / JSON list)."""
    if not value:
        return None
    candidate = Path(str(value))
    if candidate.exists():
        text = candidate.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001 - plain line list
            data = None
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
        return [line.strip() for line in text.splitlines() if line.strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


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
    """Prefer a beast fight for the control-mode checks.

    Beast entries render their action widgets without NPC bedsheet data, so they
    survive the base fixture most reliably. The win-path preference applies only
    when the caller supplies paths (archetype matrix); the initiator tier's rows
    carry no path, so a second pass without that filter keeps the pick usable.
    """
    preferred_kinds = ("beastCombatInit", "beastNEWinit", "maninit")
    for require_win in (True, False):
        for kind in preferred_kinds:
            for job in jobs:
                if job.get("kind") != kind:
                    continue
                if require_win and job.get("path") != "win":
                    continue
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


# Upstream ending passages reset ``$enemyarousal`` (the beach dog ``Finish``
# sets it back to 26.66) and can land on an aftermath passage whose source
# carries the game's own ``<<endcombat>>``. Both markers are evidence; the
# passage body may be stored raw or HTML-escaped depending on the extractor.
ENDCOMBAT_MARKERS = ("<<endcombat>>", "&lt;&lt;endcombat&gt;&gt;")


def _enemy_defeat_evidence(snapshot: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return ``(outcome, detail)`` when a snapshot shows the enemy defeated."""
    health = snapshot.get("enemyhealth")
    if isinstance(health, (int, float)) and health <= 0:
        return "win", f"enemy health reached {health}"
    arousal = snapshot.get("enemyarousal")
    arousal_max = snapshot.get("enemyarousalmax")
    if (
        isinstance(arousal, (int, float))
        and isinstance(arousal_max, (int, float))
        and arousal_max > 0
        and arousal >= arousal_max
    ):
        return "win", f"enemy arousal reached max ({arousal}/{arousal_max})"
    return None


def scripted_end_evidence(
    last_active: Mapping[str, Any] | None,
    landing_passage: str | None,
    passage_bodies: Mapping[str, str] | None,
    *,
    window: int = 600,
) -> str | None:
    """Return evidence when the combat passage itself routed to ``landing_passage``.

    Some upstream fights end without ``<<endcombat>>``: the combat passage gates
    its own exit, e.g. ``<<if _combatend or $timer lte 0>>`` -> ``... Finish``.
    Reading that guard from the *last combat-active* passage proves the scene
    reached its own terminal branch instead of stopping mid-render.
    """
    if not last_active or not landing_passage or not passage_bodies:
        return None
    source = str(last_active.get("passage") or "")
    target = str(landing_passage)
    if not source or source == target:
        return None
    body = str(passage_bodies.get(source) or "")
    if not body:
        return None
    index = -1
    for marker in (f"|{target}]]", f"[[{target}]]", f'"{target}"'):
        index = body.find(marker)
        if index >= 0:
            break
    if index < 0:
        return None
    head = body[max(0, index - window) : index]
    guards = re.findall(r"<<if\s+(.+?)>>", head, re.S)
    if not guards:
        return None
    guard = re.sub(r"\s+", " ", str(guards[-1])).strip()
    if not re.search(r"_combatend|\btimer\b", guard, re.I):
        return None
    return f"{source} exits under <<if {guard[:160]}>>"


def classify_outcome(
    state: dict[str, Any],
    *,
    path: str,
    rounds: int,
    max_rounds: int,
    stalled: bool,
    last_active: Mapping[str, Any] | None = None,
    landing_body: str = "",
    landing_passage: str | None = None,
    scripted_end: str | None = None,
) -> tuple[str, str]:
    """Map the final state to an honest outcome; never guesses silently.

    The *last combat-active snapshot* is consulted as well, because ending
    passages overwrite ``$enemyarousal`` while finishing the scene. When the
    landing passage's source carries ``<<endcombat>>`` the scene reached a
    confirmed terminal state even without an enemy defeat; that is recorded as
    ``end`` (or ``end_player_orgasm`` for a PC climax ending). A scene that ends
    through its own ``_combatend``/``$timer`` guard is recorded as ``scene_end``;
    neither is a win, and both keep the undefeated state in the detail.
    """
    if stalled:
        return "unknown", f"stalled: {STALL_ROUNDS} consecutive rounds without state change"
    if state.get("combat") == 1:
        if rounds >= max_rounds:
            return "unknown", f"round limit {max_rounds} reached while $combat stayed 1"
        return "unknown", "combat still active (driver stopped early)"
    evidence = (
        last_active
        if isinstance(last_active, Mapping) and last_active.get("combat") == 1
        else state
    )
    found = _enemy_defeat_evidence(state)
    if found is None and evidence is not state:
        found = _enemy_defeat_evidence(evidence)
        label = " (last combat-active round)"
    else:
        label = ""
    if found is not None:
        outcome, detail = found
        if path == "submit" and outcome == "win":
            return "submit", f"{detail} on submit path{label}"
        return outcome, f"{detail}{label}"
    landing = str(landing_passage or state.get("passage") or "")
    if landing_body and any(marker in landing_body for marker in ENDCOMBAT_MARKERS):
        health = evidence.get("enemyhealth") if isinstance(evidence, Mapping) else None
        arousal = evidence.get("enemyarousal") if isinstance(evidence, Mapping) else None
        arousal_max = (
            evidence.get("enemyarousalmax") if isinstance(evidence, Mapping) else None
        )
        tail = (
            f"last active: enemyhealth={health}, "
            f"enemyarousal={arousal}/{arousal_max}"
        )
        if "orgasm" in landing.casefold():
            return (
                "end_player_orgasm",
                f"scene ended via PC orgasm at {landing} "
                f"(source carries <<endcombat>>); {tail}",
            )
        return (
            "end",
            f"scene ended at {landing} (source carries <<endcombat>>); {tail}",
        )
    if scripted_end:
        health = state.get("enemyhealth")
        arousal = state.get("enemyarousal")
        arousal_max = state.get("enemyarousalmax")
        return (
            "scene_end",
            f"scene ended at {landing} through its own exit guard ({scripted_end}); "
            f"enemy not defeated (enemyhealth={health}, enemyarousal={arousal}/{arousal_max})",
        )
    return (
        "unknown",
        f"$combat ended without enemy-defeat evidence (path={path}, "
        f"enemyhealth={state.get('enemyhealth')}, enemyarousal={state.get('enemyarousal')})",
    )


_DEFINED_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$.]*)\s+is not defined")
_NULL_READ_RE = re.compile(r"Cannot read propert(?:y|ies) of (?:null|undefined)")
_READING_RE = re.compile(r"reading '([^']+)'")
# SugarCube renders the game's own slot guard as
# ``Undefined NPC in personselect 3.`` (``<<person4>>`` with no ``$NPCList[3]``).
# ``personselect`` receives the raw array index (its own note: "calls are 0-5
# corresponding to NPCs 1-6"), so the number in the message is already the
# ``$NPCList`` index -- ``personselect 0`` is ``$NPCList[0]``.
_PERSONSELECT_RE = re.compile(r"undefined npc in personselect\s+(\d+)", re.IGNORECASE)


def classify_entry_errors(
    errors: Sequence[dict[str, Any]], *, timed_out: bool = False
) -> tuple[str, str, list[str]]:
    """Classify entry errors into (verdict, detail, missing symbols)."""
    if timed_out:
        return "soft_fail", "entry render did not finish within the timeout", []
    messages = " | ".join(str(err.get("message") or "") for err in errors)
    if not messages.strip():
        return "not_applicable", "passage rendered but $combat stayed 0", []
    missing = _missing_symbols(messages)
    low = messages.lower()
    fixture_hit = any(marker in low for marker in ps.FIXTURE_MARKERS) or "bad evaluation" in low
    if not fixture_hit:
        return "hard_fail", messages[:400], missing[:20]
    return "fixture_insufficient", messages[:400], missing[:20]


def _missing_symbols(messages: str) -> list[str]:
    """Machine-readable symbols a failing render wanted but could not find."""
    missing: list[str] = []
    for name in _DEFINED_RE.findall(messages):
        if name not in missing:
            missing.append(name)
    if _NULL_READ_RE.search(messages):
        prop = _READING_RE.search(messages)
        missing.append(f"null.{prop.group(1)}" if prop else "null property read")
    for slot in _PERSONSELECT_RE.findall(messages):
        try:
            entry = f"NPCList[{int(slot)}]"
        except ValueError:
            continue
        if entry not in missing:
            missing.append(entry)
    return missing


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
  // SugarCube renders widget/macro failures as an inline error view
  // (``.error-view`` / ``span.error``); the JS error harness never sees them,
  // so a scene dying on "Undefined NPC in personselect 3" would otherwise look
  // like a plain stall. Capture the rendered text verbatim.
  const domErrors = [];
  try {
    document.querySelectorAll("#passages .error-view, #passages span.error").forEach((node) => {
      const text = String(node.innerText || "").trim().replace(/\s+/g, " ");
      if (text && !domErrors.includes(text)) domErrors.push(text.slice(0, 800));
    });
  } catch (e) { /* ignore */ }
  const harnessErrors = (S.errors || []).slice(-8);
  const errors = harnessErrors.concat(
    domErrors.map((message) => ({ kind: "sugarcube.dom", message: message, source: "dom" }))
  );
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
    errorCount: errors.length,
    errors: errors,
    domErrors: domErrors,
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

RUN_WIDGETS_JS = r"""
(text) => {
  const SC = window.SugarCube;
  if (!SC || !SC.Wikifier || typeof SC.Wikifier.wikifyEval !== "function") {
    return JSON.stringify({ ok: false, error: "wikifyEval unavailable" });
  }
  try {
    SC.Wikifier.wikifyEval(text);
    return JSON.stringify({ ok: true });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String((e && e.message) || e).slice(0, 240) });
  }
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

# DoL's helpless states (bound arms + pain overwhelmed, suffocation, fade-in
# sequences) render no action radios on purpose: the intended play is to click
# the passage's own Next/continue link and let the scene resolve. Prefer the
# ``#next`` span, then next/continue-labelled links, then the last visible link
# (DoL appends the continue link at the end of the passage).
ADVANCE_LINK_JS = r"""
() => {
  const visible = (el) => {
    if (!el) return false;
    if (el.closest("[hidden]")) return false;
    const st = window.getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const links = [...document.querySelectorAll("#passages a[data-passage]")].filter(visible);
  if (!links.length) return JSON.stringify({ ok: false, error: "no visible passage link" });
  const labelled = links.find((a) => {
    const t = (a.textContent || "").trim().toLowerCase();
    return t.includes("next") || t.includes("继续") || t.includes("下一个");
  });
  const pick = links.find((a) => a.closest("#next")) || labelled || links[links.length - 1];
  const target = pick.getAttribute("data-passage") || "";
  const text = (pick.textContent || "").trim().slice(0, 40);
  pick.click();
  return JSON.stringify({ ok: true, target, text });
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


def enter_row(
    page: Any,
    row: dict[str, Any],
    *,
    timeout_ms: int,
    settle_ms: int = DEFAULT_ENTRY_SETTLE_MS,
    precursor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Restore the fixture, replay the game-side precursor, arm the flag, play."""
    order: list[tuple[str, ...]] = []
    if row.get("entry_flags"):
        order.append(tuple(str(flag) for flag in row["entry_flags"]))
    order.extend(attempt for attempt in ENTRY_FLAG_ATTEMPTS if attempt not in order)
    attempts: list[dict[str, Any]] = []
    last_state: dict[str, Any] = {}
    last_timed_out = False
    precursor_widgets = str((precursor or {}).get("widgets") or "")
    for flags in order:
        restore = page.evaluate(ps.RESTORE_FIXTURE)
        precursor_record = None
        if precursor_widgets:
            raw_precursor = page.evaluate(RUN_WIDGETS_JS, precursor_widgets)
            try:
                precursor_record = (
                    json.loads(raw_precursor) if isinstance(raw_precursor, str) else (raw_precursor or {})
                )
            except Exception as exc:  # noqa: BLE001 - surface a broken precursor payload
                precursor_record = {"ok": False, "error": f"precursor payload unreadable: {exc}"}
        armed = set_entry_flags(page, flags)
        state, timed_out = play_passage(page, str(row.get("passage") or ""), timeout_ms=timeout_ms)
        if settle_ms:
            page.wait_for_timeout(settle_ms)
            state = _state(page)
        attempts.append(
            {
                "flags": list(flags),
                "restore": restore if isinstance(restore, dict) else str(restore),
                "precursor": precursor_record,
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


def _advance_passage(
    page: Any,
    *,
    timeout_ms: int,
    attempts: int = 8,
    wait_ms: int = 800,
) -> dict[str, Any]:
    """Follow the passage's own continue link when no action controls exist.

    Retries while the link is still hidden (DoL reveals some continue links
    through ~1.5 s fade-in timeouts) and waits for the render afterwards.
    """
    last: dict[str, Any] = {"ok": False, "error": "no visible passage link"}
    for attempt in range(1, attempts + 1):
        before_render = begin_turn(page)
        raw = page.evaluate(ADVANCE_LINK_JS)
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception as exc:  # noqa: BLE001
            payload = {"ok": False, "error": f"advance payload unreadable: {exc}"}
        if not isinstance(payload, dict):
            payload = {"ok": False, "error": "advance payload not a dict"}
        if payload.get("ok"):
            try:
                page.wait_for_function(
                    "(before) => {"
                    "  const S = window.__DOLX__;"
                    "  return !!S && (S.done === true || (S.renderSeq || 0) > before);"
                    "}",
                    before_render,
                    timeout=max(1000, min(timeout_ms, TURN_WAIT_MS)),
                )
            except Exception:  # noqa: BLE001 - a slow render is recorded, not fatal
                pass
            page.wait_for_timeout(DEFAULT_TURN_SETTLE_MS)
            payload["attempt"] = attempt
            payload["state"] = _state(page)
            return payload
        last = payload
        page.wait_for_timeout(wait_ms)
    return {
        "ok": False,
        "error": str(last.get("error") or "no visible passage link"),
        "attempts": attempts,
    }


def drive_combat(
    page: Any,
    *,
    path: str,
    max_rounds: int,
    timeout_ms: int,
    passage_bodies: Mapping[str, str] | None = None,
    expected_outcome: str | None = None,
) -> dict[str, Any]:
    """Drive one combat from $combat=1 to an ending (or the round cap)."""
    result: dict[str, Any] = {
        "path": path,
        "rounds": 0,
        "endure_rounds": 0,
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
    last_active: dict[str, Any] | None = state if state.get("combat") == 1 else None
    for round_no in range(1, max_rounds + 1):
        if state.get("combat") != 1:
            break
        actions_probe = _actions(page)
        actions = actions_probe.get("actions") or []
        if not actions:
            advance = _advance_passage(page, timeout_ms=timeout_ms)
            if advance.get("ok"):
                advance_state = advance.get("state") or _state(page)
                state = advance_state
                if state.get("combat") == 1:
                    last_active = state
                result["endure_rounds"] += 1
                result["rounds"] += 1
                result["digests"].append(round_digest(state))
                result["actions"].append(
                    {
                        "round": round_no,
                        "kind": "advance",
                        "text": advance.get("text"),
                        "target": advance.get("target"),
                        "attempt": advance.get("attempt"),
                        "fallback": False,
                    }
                )
                if detect_stall(result["digests"]):
                    result["stalled"] = True
                    result["verdict"] = "soft_fail"
                    result["detail"] = (
                        f"stalled: {STALL_ROUNDS} rounds without state change"
                    )
                    break
                continue
            verdict, detail, missing = classify_no_actions(actions_probe, state)
            detail = (
                f"{detail} (no continuation link after "
                f"{result['endure_rounds']} advance rounds: "
                f"{str(advance.get('error') or 'unknown')[:120]})"
            )
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
        if state.get("combat") == 1:
            last_active = state
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
    landing_body = ""
    if passage_bodies:
        landing_body = str(passage_bodies.get(str(result["landed"])) or "")
    scripted_end = scripted_end_evidence(last_active, result["landed"], passage_bodies)
    result["landing_evidence"] = {
        "passage": result["landed"],
        "source": "static" if landing_body else "none",
        "length": len(landing_body),
        "has_endcombat": any(marker in landing_body for marker in ENDCOMBAT_MARKERS),
        "scripted_end": scripted_end,
    }
    outcome, outcome_detail = classify_outcome(
        state,
        path=path,
        rounds=result["rounds"],
        max_rounds=max_rounds,
        stalled=result["stalled"],
        last_active=last_active,
        landing_body=landing_body,
        landing_passage=result["landed"],
        scripted_end=scripted_end,
    )
    result["outcome"] = outcome
    result["outcome_detail"] = outcome_detail
    if result["verdict"] == "ok" and outcome == "unknown" and state.get("combat") != 1:
        result["verdict"] = "soft_fail"
        result["detail"] = outcome_detail
    if result["verdict"] == "ok" and state.get("combat") == 1 and result["rounds"] >= max_rounds:
        result["verdict"] = "soft_fail"
        result["detail"] = f"round limit {max_rounds} reached"
    if (
        result["verdict"] == "ok"
        and expected_outcome
        and outcome not in EXPECTED_OUTCOME_ACCEPTS.get(expected_outcome, (expected_outcome,))
    ):
        result["verdict"] = "soft_fail"
        result["detail"] = f"{path} path ended as {outcome}: {outcome_detail}"
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
    passage_bodies: Mapping[str, str] | None = None,
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
            expected = EXPECTED_OUTCOME_ACCEPTS.get(str(job.get("path") or ""))
            drive = drive_combat(
                page,
                path=str(job.get("path") or "win"),
                max_rounds=max_rounds,
                timeout_ms=timeout_ms,
                passage_bodies=passage_bodies,
                expected_outcome=str(job.get("path") or "") if expected else None,
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
    precursor: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Exercise every control mode for >= ``rounds`` real DOM rounds each.

    Re-entries replay the same game-side generation preamble as the row sweep:
    entering a fight without its ``<<generate1>><<person1>>`` /
    ``<<generateBEAST>>`` chain leaves ``$NPCList`` a 5-key shell and the hand
    renderer raises ``NPC hand action unaccounted for`` — a tool artifact, not a
    game defect, so the check must not run without it.
    """
    results: list[dict[str, Any]] = []
    if precursor is None and isinstance(entry.get("precursor"), Mapping):
        precursor = entry["precursor"]
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
            reentry = enter_row(page, entry, timeout_ms=timeout_ms, precursor=precursor)
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
                    reentry = enter_row(page, entry, timeout_ms=timeout_ms, precursor=precursor)
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
    passage_bodies: Mapping[str, str] | None = None,
    named_npcs: Sequence[str] = (),
    widget_bodies: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for position, row in enumerate(rows, 1):
        t0 = time.time()
        precursor = derive_precursor(
            row,
            passage_bodies=passage_bodies or {},
            named_npcs=named_npcs,
            widget_bodies=widget_bodies or {},
        )
        entry = enter_row(
            page,
            row,
            timeout_ms=timeout_ms,
            precursor=precursor if precursor.get("widgets") else None,
        )
        if entry.get("ok"):
            drive = drive_combat(
                page,
                path="win",
                max_rounds=max_rounds,
                timeout_ms=timeout_ms,
                passage_bodies=passage_bodies,
            )
            record = {
                "key": row["key"],
                "kind": row.get("kind"),
                "token": row.get("token"),
                "passage": row.get("passage"),
                "macro": row.get("macro"),
                "precursor": precursor,
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
                "precursor": precursor,
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

    outcomes = report.get("outcome_counts") or {}
    if outcomes:
        lines += ["", "## outcomes", "", "| outcome | count |", "| --- | --- |"]
        for outcome, count in outcomes.items():
            lines.append(f"| {outcome} | {count} |")

    modes_entry = report.get("modes_entry") or {}
    if modes_entry:
        mode_precursor = modes_entry.get("precursor") or {}
        lines += [
            "",
            f"- control-mode entry: `{modes_entry.get('key')}` (kind {modes_entry.get('kind')}, "
            f"precursor {mode_precursor.get('basis') or 'none'})",
        ]

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
    only_keys: str | None = None,
) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    html_path = ps.resolve_html_path(target)
    fixture, fixture_json = load_fixture_payload(fixture_path)
    variables = fixture.get("variables") or {}
    named_npcs = [str(item) for item in (variables.get("NPCNameList") or []) if str(item).strip()]

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
    widget_bodies = build_widget_index(passage_bodies)
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
    resolved_only_keys = resolve_only_keys(only_keys)
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
        "only_keys": sorted(resolved_only_keys) if resolved_only_keys else None,
        "precursor_schema": PRECURSOR_SCHEMA,
    }
    identity = sl.run_identity(
        TOOL,
        html_sha256=file_sha256(html_path),
        fixture_digest=fixture_digest(variables),
        tool_version="combat-sweep-v3",
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
            "precursor_schema": PRECURSOR_SCHEMA,
            "precursor_reason": "upstream combat scenes assume their own <<generate1>>/<<generateBEAST>>/<<npc X>>"
            " chain already ran; direct jumps leave $NPCList[0] as a 5-key shell and crash hand_section"
            "/frontarm. The driver replays the game's debug-menu generation preambles and records the basis.",
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
        if resolved_only_keys:
            wanted = set(resolved_only_keys)
            available = {str(row.get("key")) for row in initiator_plan}
            initiator_plan = [
                row for row in initiator_plan if str(row.get("key")) in wanted
            ]
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
        selection["only_keys"] = list(resolved_only_keys) if resolved_only_keys else None
        if resolved_only_keys and not expected_keys:
            selection["error"] = "no initiator row matched --only-keys"
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
                        passage_bodies=passage_bodies,
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
                            passage_bodies=passage_bodies,
                            named_npcs=named_npcs,
                            widget_bodies=widget_bodies,
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
                        mode_precursor = derive_precursor(
                            mode_entry,
                            passage_bodies=passage_bodies,
                            named_npcs=named_npcs,
                            widget_bodies=widget_bodies,
                        )
                        report["modes_entry"] = {
                            "key": mode_entry.get("key"),
                            "kind": mode_entry.get("kind"),
                            "path": mode_entry.get("path"),
                            "precursor": mode_precursor,
                        }
                        report["modes"] = run_control_modes(
                            page,
                            mode_entry,
                            rounds=mode_rounds,
                            timeout_ms=timeout_ms,
                            precursor=mode_precursor if mode_precursor.get("widgets") else None,
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
                        mode_precursor = derive_precursor(
                            mode_entry,
                            passage_bodies=passage_bodies,
                            named_npcs=named_npcs,
                            widget_bodies=widget_bodies,
                        )
                        report["modes_entry"] = {
                            "key": mode_entry.get("key"),
                            "kind": mode_entry.get("kind"),
                            "path": mode_entry.get("path"),
                            "precursor": mode_precursor,
                        }
                        report["modes"] = run_control_modes(
                            page,
                            mode_entry,
                            rounds=mode_rounds,
                            timeout_ms=timeout_ms,
                            precursor=mode_precursor if mode_precursor.get("widgets") else None,
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
    report["outcome_counts"] = dict(
        sorted(
            collections.Counter(
                str((item.get("combat") or {}).get("outcome"))
                for item in report["results"]
                if item.get("combat")
            ).items()
        )
    )
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
    parser.add_argument(
        "--only-keys",
        default=None,
        help="comma-separated initiator keys or a path to a file (one key per line / JSON list)",
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
        only_keys=args.only_keys,
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
