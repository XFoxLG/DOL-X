#!/usr/bin/env python3
"""DOL-X environment matrix sweep (engine A): every env-sensitive passage under
a named time/weather/holiday context.

Why this exists
---------------
``tools/passage_sweep.py`` renders every passage once, in whatever environment
the freshly bootstrapped game happens to be in. DoL branches heavily on the
in-game clock, season, weather and holiday state (`Time.season`,
`Weather.isSnow`, `Time.isBloodMoon()`, `V.halloween`, `V.christmas`, ...), so
that single baseline environment only ever executes one arm of those branches.
This tool fixes that:

    1. the **static** env-sensitive passage set is derived from the real
       artifact's own passage source (``passage_sweep.extract_passages``) with a
       documented, case-insensitive regex rule (see
       ``ENV_SENSITIVE_PATTERNS`` and the ``meta.env_sensitive_rule`` block of
       every report);
    2. every execution restores the fixture, injects one named context through
       the game's own runtime APIs (``Time.timeTravel`` / ``Weather.set`` /
       ``Weather.setTemperature`` / ``V.halloween`` / ``V.christmas`` /
       ``V.moonstate``), and **reads the state back** — a context that does not
       verify is fail-closed: that execution is ``hard_fail``, never played in a
       wrong environment;
    3. the passage is then entered through ``Engine.play(name)`` and judged with
       the same five-tier vocabulary as the rest of the stack
       (``ok / soft_fail / hard_fail / fixture_insufficient / not_applicable``),
       including a landing assertion (a redirect is recorded as ``soft_fail``);
    4. a sealed baseline (``--save-baseline``) makes later runs report only NEW
       regressions.

Context matrix
--------------
``--tier daily`` pairs each env-sensitive passage with 8 named contexts
(春晨晴 / 夏午雷暴 / 秋昏雨 / 冬夜雪 / 万圣节夜 / 圣诞晨 / 血月夜 / 上课日);
``--tier full`` pairs every passage of the artifact with 4 contexts
(白天晴 / 夜雨 / 冬雪 / 血月夜). ``--dry-plan`` expands the matrix without
starting a browser so the numbers can be checked cheaply.

Runtime API evidence (read directly from the 2026-10-05 artifact
``workspace/prepare_package/zip/Degrees of Lewdity.html``; the tool never edits
it):

* ``Time.timeTravel(date)`` / ``Time.setDate`` / ``Time.setTime`` live in the
  ``Time = (() => {...})()`` closure (lines ~74720-75066); ``timeTravel`` is the
  game's own debug-menu path for jumping to Halloween / Christmas / a blood
  moon and regenerates weather + fog keypoints. ``Time.set()`` re-syncs the
  closure's ``currentDate`` from ``V.timeStamp`` and is called after the
  fixture restore so a stale module clock can never leak between contexts.
* ``Time.isBloodMoon(date)`` is pure date math:
  ``day === lastDayOfMonth && hour >= 21 || day === 1 && hour < 6``
  (line ~74914); the debug menu reaches it with
  ``Time.timeTravel(new DateTime(Time.year, Time.month, Time.lastDayOfMonth, 21, 0))``
  plus ``$moonstate to "evening"`` (line ~58198), which this tool mirrors.
* ``Weather.set(type, instant, minutes)`` exists on the ``Weather`` facade
  (line ~83527) and delegates to ``setWeather`` (line ~84813), which accepts
  exactly the 7 canonical names found at lines 82864-83084:
  ``clear / lightClouds / heavyClouds / lightPrecipitation /
  heavyPrecipitation / storm / thunderstorm``. It bails out (console.warn)
  when ``V.weatherObj.keypointsArr`` is empty, so the readback is required.
* ``Weather.isSnow`` is ``V.weatherObj.snow > tempSettings.snow.minAccumulation``
  (line ~83590) and ``Weather.precipitation`` returns ``"snow"`` only while
  ``Weather.isFreezing`` (line ~83571), so the winter-snow context sets both a
  freezing temperature and above-threshold snow accumulation.
* ``V.halloween`` is set by the game when ``Time.monthName === "October" &&
  Time.monthDay >= 21`` (line ~76636) and ``V.christmas`` when
  ``Time.monthName === "December" && 18 <= Time.monthDay <= 25`` (line ~76663).
  Those hooks run on day/month transitions, which a direct ``timeTravel`` does
  NOT trigger, so the holiday contexts set the flags explicitly — exactly the
  state the game would have reached had the day passed naturally — and verify
  them before playing anything.
* ``Time.season`` is ``getSeason`` (line ~74919): months 3-5 spring, 6-8
  summer, 9-11 autumn, 12/1/2 winter.

Nothing here touches ``lyra/``, ``config/`` or any build input: the whole tool
is runtime-only, and reuses ``tools/passage_sweep.py`` helpers (fixture loader,
patch, browser launcher, server, hooks, probe, classifier) instead of copying
them.

Usage:
    python tools/env_matrix.py --target <built.html|zip> --tier daily --dry-plan
    python tools/env_matrix.py --target <built.html|zip> --tier daily --limit 8
    python tools/env_matrix.py --target <built.html|zip> --tier full --save-baseline
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import passage_sweep as ps  # noqa: E402


TOOL = "env_matrix"
DEFAULT_OUT_ROOT = Path(".local/sweep")
DEFAULT_BASELINE_DIR = Path(".local/sweep/baselines")
DEFAULT_FIXTURE = Path(".local/fixtures/base-1004.json")
DEFAULT_SEED = 20261004
TIERS = ("daily", "full")

VERDICTS = ("ok", "soft_fail", "hard_fail", "fixture_insufficient", "not_applicable")
# Same severity ladder as tools/scenario_sweep.py so a baseline diff means the
# same thing across the engine-A tools.
VERDICT_SEVERITY = {
    "ok": 0,
    "not_applicable": 1,
    "fixture_insufficient": 2,
    "soft_fail": 3,
    "hard_fail": 4,
}

# --------------------------------------------------------------------------- #
# Static env-sensitivity rule
#
# The rule is deliberately code-shaped (API / state names), not prose-shaped:
# a passage that merely *mentions* the weather in flavour text is not a branch
# target. Each pattern is case-insensitive and applied to the passage body
# exactly as stored in the artifact.
#
# Measured on the 2026-10-05 artifact
# (workspace/prepare_package/zip/Degrees of Lewdity.html, 15,627 passages):
# this rule hits 1,378 passages (pattern hits: time_clock 943, weather 481,
# day_state 435, holiday 270, season 116, storm_snow_ice 91, sun_cycle 21,
# time_distortion 1 — a passage may match several patterns). The recon
# estimate behind the "886" figure is not reproducible from any single token
# set: a brief-literal variant (weather/isStorm/isSnow/season +
# `Time.(date|time|day|month|year)` + `.(sunrise|sunset|night)` +
# timeDistortion) measures 599, adding only `dayState` measures 870, adding
# the wider clock surface measures 958, and everything together measures
# 1,368 of the 1,378 (the last 10 come from pattern overlap only). The rule —
# not the estimate — decides the daily set; the estimate is recorded in
# meta.env_sensitive_rule purely as drift and is never used to trim or pad.
# --------------------------------------------------------------------------- #

ENV_SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("weather", r"\bweather\b"),
    ("storm_snow_ice", r"\b(isStorm|isSnow|isFog|isFoggy|isFrozen|isFreezing)\b"),
    ("season", r"\bseason\b"),
    (
        "time_clock",
        r"\bTime\.(date|day|days|month|monthName|monthDay|year|hour|minute|timeStamp|"
        r"lastDayOfMonth|dayOfYear|dayState|season|sunrise|sunset|timeTravel|setTime|"
        r"setDate|setTimeRelative|isBloodMoon|currentMoonPhase)\b",
    ),
    ("day_state", r"\bdayState\b"),
    ("sun_cycle", r"\b(sunrise|sunset)\b"),
    ("time_distortion", r"\btimeDistortion\b"),
    ("holiday", r"\b(halloween|christmas|bloodMoon)\b"),
)

ENV_SENSITIVE_RULE_DESCRIPTION = (
    "case-insensitive regex over the passage source stored in the artifact: "
    "references to weather/storm/snow/fog (weather, isStorm, isSnow, ...), "
    "season, the game clock (Time.date|day|month|year|hour|minute|timeStamp|"
    "dayState|timeTravel|setTime|setDate|isBloodMoon|...), dayState, sunrise/"
    "sunset, timeDistortion, and the holiday flags (halloween/christmas/"
    "bloodMoon). Matching is on state/API names, not prose."
)

# Static recon estimate from the task brief (2026-10-05). Stored only so the
# report can surface drift; it is never used to trim or pad the hit list.
ENV_SENSITIVE_REFERENCE_HITS = 886
# Drift beyond this fraction of the reference is called out explicitly in
# meta.env_sensitive_rule.drift_note (never silently absorbed).
ENV_SENSITIVE_DRIFT_TOLERANCE = 0.10

# Passages SugarCube/DoL owns: ``Engine.play`` on them is either a no-op or an
# engine error, so they are honestly reported as not_applicable instead of being
# counted as failures.
NON_SCENE_PASSAGES = frozenset(
    {
        "StoryInit",
        "PassageHeader",
        "PassageFooter",
        "PassageReady",
        "PassageDone",
        "StoryTitle",
        "StorySubtitle",
        "StoryAuthor",
        "StoryDisplayTitle",
        "StoryMenu",
        "StoryCaption",
        "StoryBanner",
    }
)

MISSING_VAR_PATTERNS = (
    re.compile(r"'([^']+)' is not defined"),
    re.compile(r'"([^"]+)" is not defined'),
    re.compile(r"\b([A-Za-z_$][\w$]*)\s+is not defined"),
    re.compile(r"Cannot read propert(?:y|ies) of (?:undefined|null) \(reading '([^']+)'\)"),
)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Check:
    """One read-back assertion against the injected context (fail-closed)."""

    label: str
    path: tuple[str, ...]
    op: str = "eq"  # eq | truthy | in
    value: Any = None


@dataclass(frozen=True)
class ContextSpec:
    key: str
    label: str
    tiers: tuple[str, ...]
    summary: str
    hour: int
    minute: int = 0
    month: int | None = None
    day: int | None = None
    weather: str | None = None
    temperature: float | None = None
    snow: bool = False
    last_day_of_month: bool = False
    next_school_term: bool = False
    set_vars: tuple[tuple[str, Any], ...] = ()
    checks: tuple[Check, ...] = ()


@dataclass
class Execution:
    name: str
    context: str


# --------------------------------------------------------------------------- #
# Static scan
# --------------------------------------------------------------------------- #


_COMPILED_RULE = tuple(
    (ident, re.compile(pattern, re.IGNORECASE)) for ident, pattern in ENV_SENSITIVE_PATTERNS
)


def scan_env_sensitive(passages: Sequence[ps.Passage]) -> tuple[list[ps.Passage], dict[str, Any]]:
    """Return (env-sensitive passages in document order, rule stats).

    ``stats`` carries the per-pattern hit counts plus the per-passage matched
    pattern ids, so a report can explain *why* a passage is in the daily set.
    """
    kept: list[ps.Passage] = []
    per_pattern: dict[str, int] = {ident: 0 for ident, _re in _COMPILED_RULE}
    reasons: dict[str, list[str]] = {}
    for passage in passages:
        matched = [ident for ident, regex in _COMPILED_RULE if regex.search(passage.body)]
        if not matched:
            continue
        kept.append(passage)
        reasons[passage.name] = matched
        for ident in matched:
            per_pattern[ident] += 1
    stats = {
        "scanned": len(passages),
        "hit_count": len(kept),
        "per_pattern": per_pattern,
        "matches": reasons,
    }
    return kept, stats


def rule_meta(stats: dict[str, Any]) -> dict[str, Any]:
    """Report-facing description of the rule + drift vs the recon estimate."""
    hits = int(stats.get("hit_count", 0))
    drift = hits - ENV_SENSITIVE_REFERENCE_HITS
    tolerance = ENV_SENSITIVE_REFERENCE_HITS * ENV_SENSITIVE_DRIFT_TOLERANCE
    note = ""
    if abs(drift) > tolerance:
        top = sorted(
            (stats.get("per_pattern") or {}).items(),
            key=lambda item: (-int(item[1]), item[0]),
        )[:4]
        note = (
            f"hit count {hits} differs from the 2026-10-05 recon estimate "
            f"{ENV_SENSITIVE_REFERENCE_HITS} by {drift:+d} "
            f"(> {int(tolerance)} = {int(ENV_SENSITIVE_DRIFT_TOLERANCE * 100)}%). "
            "The brief-literal token set measures 599 and a +dayState variant 870, "
            "so the recon number sampled a different token set; the dominant "
            "patterns here are " + ", ".join(f"{ident}={count}" for ident, count in top)
            + ". The rule (not the estimate) decides the daily set; this note records "
            "the drift instead of hard-coding the estimate."
        )
    else:
        note = (
            f"hit count {hits} is within {int(tolerance)} of the 2026-10-05 recon "
            f"estimate {ENV_SENSITIVE_REFERENCE_HITS}."
        )
    return {
        "description": ENV_SENSITIVE_RULE_DESCRIPTION,
        "patterns": [{"id": ident, "regex": pattern} for ident, pattern in ENV_SENSITIVE_PATTERNS],
        "hit_count": hits,
        "scanned_passages": int(stats.get("scanned", 0)),
        "per_pattern_hits": dict(stats.get("per_pattern", {})),
        "reference_hit_count": ENV_SENSITIVE_REFERENCE_HITS,
        "drift": drift,
        "drift_note": note,
    }


# --------------------------------------------------------------------------- #
# Named contexts
# --------------------------------------------------------------------------- #


def _time_checks(
    *,
    season: str | None,
    hour: int,
    month: int | None = None,
    day: int | None = None,
    day_state: str | None = None,
    blood_moon: bool = False,
    school: bool = False,
    last_day_of_month: bool = False,
) -> list[Check]:
    checks: list[Check] = [Check("hour", ("time", "hour"), "eq", hour)]
    if season is not None:
        checks.append(Check("season", ("time", "season"), "eq", season))
    if month is not None:
        checks.append(Check("month", ("time", "month"), "eq", month))
    if day is not None:
        checks.append(Check("day", ("time", "day"), "eq", day))
    if last_day_of_month:
        checks.append(Check("last_day_of_month", ("time", "isLastDayOfMonth"), "truthy"))
    if day_state is not None:
        checks.append(Check("day_state", ("time", "dayState"), "eq", day_state))
    if blood_moon:
        checks.append(Check("time_is_blood_moon", ("time", "isBloodMoon"), "truthy"))
        checks.append(Check("weather_is_blood_moon", ("weather", "bloodMoon"), "truthy"))
    if school:
        checks.append(Check("school_day", ("time", "schoolDay"), "truthy"))
        checks.append(Check("school_time", ("time", "schoolTime"), "truthy"))
    return checks


def _weather_checks(weather: str, *, snow: bool = False) -> list[Check]:
    checks = [Check("weather_name", ("weather", "name"), "eq", weather)]
    if snow:
        checks.append(Check("weather_is_snow", ("weather", "isSnow"), "truthy"))
        checks.append(Check("precipitation", ("weather", "precipitation"), "eq", "snow"))
    return checks


SPRING_CLEAR = ContextSpec(
    key="spring-morning-clear",
    label="春晨晴",
    tiers=("daily",),
    summary="April 15, 08:00, clear sky, spring",
    month=4,
    day=15,
    hour=8,
    weather="clear",
    checks=tuple(
        _time_checks(season="spring", hour=8, month=4, day=15) + _weather_checks("clear")
    ),
)

SUMMER_NOON_THUNDERSTORM = ContextSpec(
    key="summer-noon-thunderstorm",
    label="夏午雷暴",
    tiers=("daily",),
    summary="July 15, 13:00, thunderstorm, summer",
    month=7,
    day=15,
    hour=13,
    weather="thunderstorm",
    checks=tuple(
        _time_checks(season="summer", hour=13, month=7, day=15)
        + _weather_checks("thunderstorm")
    ),
)

AUTUMN_DUSK_RAIN = ContextSpec(
    key="autumn-dusk-rain",
    label="秋昏雨",
    tiers=("daily",),
    summary="October 15, 18:00, light precipitation (rain), 10C, autumn",
    month=10,
    day=15,
    hour=18,
    weather="lightPrecipitation",
    temperature=10.0,
    checks=tuple(
        _time_checks(season="autumn", hour=18, month=10, day=15)
        + _weather_checks("lightPrecipitation")
        + [Check("precipitation", ("weather", "precipitation"), "eq", "rain")]
    ),
)

WINTER_NIGHT_SNOW = ContextSpec(
    key="winter-night-snow",
    label="冬夜雪",
    tiers=("daily",),
    summary="January 15, 22:00, freezing precipitation, snow on the ground, winter",
    month=1,
    day=15,
    hour=22,
    weather="lightPrecipitation",
    temperature=-5.0,
    snow=True,
    checks=tuple(
        _time_checks(season="winter", hour=22, month=1, day=15, day_state="night")
        + _weather_checks("lightPrecipitation", snow=True)
    ),
)

HALLOWEEN_NIGHT = ContextSpec(
    key="halloween-night",
    label="万圣节夜",
    tiers=("daily",),
    summary="October 31, 21:00, cloudy, V.halloween=1 (flag set explicitly: a direct timeTravel does not run the day-pass hooks)",
    month=10,
    day=31,
    hour=21,
    weather="heavyClouds",
    set_vars=(
        ("halloween", 1),
        ("halloweenClothesMessage", 1),
    ),
    checks=tuple(
        _time_checks(season="autumn", hour=21, month=10, day=31)
        + _weather_checks("heavyClouds")
        + [
            Check("V.halloween", ("vars", "halloween"), "truthy"),
            Check("month_name", ("time", "monthName"), "eq", "October"),
            Check("month_day", ("time", "monthDay"), "eq", 31),
        ]
    ),
)

CHRISTMAS_MORNING = ContextSpec(
    key="christmas-morning",
    label="圣诞晨",
    tiers=("daily",),
    summary="December 25, 08:00, clear, V.christmas=1 (flag set explicitly: a direct timeTravel does not run the day-pass hooks)",
    month=12,
    day=25,
    hour=8,
    weather="clear",
    set_vars=(
        ("christmas", 1),
        ("christmasClothesMessage", 1),
    ),
    checks=tuple(
        _time_checks(season="winter", hour=8, month=12, day=25)
        + _weather_checks("clear")
        + [
            Check("V.christmas", ("vars", "christmas"), "truthy"),
            Check("month_name", ("time", "monthName"), "eq", "December"),
            Check("month_day", ("time", "monthDay"), "eq", 25),
        ]
    ),
)

BLOOD_MOON_NIGHT = ContextSpec(
    key="bloodmoon-night",
    label="血月夜",
    tiers=("daily", "full"),
    summary=(
        "July, last day of the month, 22:00, V.moonstate=\"evening\"; mirrors the "
        "game's own debug-menu blood moon jump (Time.timeTravel to lastDayOfMonth 21:00)"
    ),
    month=7,
    hour=22,
    last_day_of_month=True,
    set_vars=(("moonstate", "evening"),),
    checks=tuple(
        _time_checks(
            season="summer",
            hour=22,
            blood_moon=True,
            last_day_of_month=True,
        )
        + [Check("V.moonstate", ("vars", "moonstate"), "eq", "evening")]
    ),
)

SCHOOL_DAY = ContextSpec(
    key="school-day",
    label="上课日",
    tiers=("daily",),
    summary="next school-term start date, 10:00, clear, school day/time asserted",
    hour=10,
    weather="clear",
    next_school_term=True,
    checks=tuple(
        # The school term can start in any season (autumn/winter/spring), so the
        # season is deliberately NOT pinned here; schoolDay + schoolTime are.
        _time_checks(season=None, hour=10, school=True)
        + _weather_checks("clear")
    ),
)

DAY_CLEAR = ContextSpec(
    key="day-clear",
    label="白天晴",
    tiers=("full",),
    summary="April 15, 13:00, clear, spring",
    month=4,
    day=15,
    hour=13,
    weather="clear",
    checks=tuple(
        _time_checks(season="spring", hour=13, month=4, day=15) + _weather_checks("clear")
    ),
)

NIGHT_RAIN = ContextSpec(
    key="night-rain",
    label="夜雨",
    tiers=("full",),
    summary="October 15, 22:00, light precipitation (rain), 10C, night",
    month=10,
    day=15,
    hour=22,
    weather="lightPrecipitation",
    temperature=10.0,
    checks=tuple(
        _time_checks(season="autumn", hour=22, month=10, day=15, day_state="night")
        + _weather_checks("lightPrecipitation")
        + [Check("precipitation", ("weather", "precipitation"), "eq", "rain")]
    ),
)

WINTER_SNOW = ContextSpec(
    key="winter-snow",
    label="冬雪",
    tiers=("full",),
    summary="January 15, 14:00, freezing precipitation, snow on the ground, winter",
    month=1,
    day=15,
    hour=14,
    weather="lightPrecipitation",
    temperature=-5.0,
    snow=True,
    checks=tuple(
        _time_checks(season="winter", hour=14, month=1, day=15)
        + _weather_checks("lightPrecipitation", snow=True)
    ),
)

ALL_CONTEXTS: tuple[ContextSpec, ...] = (
    SPRING_CLEAR,
    SUMMER_NOON_THUNDERSTORM,
    AUTUMN_DUSK_RAIN,
    WINTER_NIGHT_SNOW,
    HALLOWEEN_NIGHT,
    CHRISTMAS_MORNING,
    BLOOD_MOON_NIGHT,
    SCHOOL_DAY,
    DAY_CLEAR,
    NIGHT_RAIN,
    WINTER_SNOW,
)


def contexts_for_tier(tier: str) -> list[ContextSpec]:
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}; expected one of {TIERS}")
    contexts = [ctx for ctx in ALL_CONTEXTS if tier in ctx.tiers]
    if tier == "daily":
        assert len(contexts) == 8, f"daily tier must expand to 8 contexts, got {len(contexts)}"
    elif tier == "full":
        assert len(contexts) == 4, f"full tier must expand to 4 contexts, got {len(contexts)}"
    return contexts


# --------------------------------------------------------------------------- #
# Matrix expansion / dry plan
# --------------------------------------------------------------------------- #


def expand_matrix(
    passages: Sequence[ps.Passage],
    contexts: Sequence[ContextSpec],
    *,
    limit: int | None = None,
    seed: int = DEFAULT_SEED,
) -> list[Execution]:
    """Expand passages x contexts, then cap with a seeded random sample.

    Like ``passage_sweep --sample``, ``--limit`` picks a reproducible random
    subset of the full matrix rather than truncating it, so a small run still
    covers every context. The result is re-sorted context-major to keep the
    in-page state churn low and make progress logs readable.
    """
    ctx_order = {ctx.key: idx for idx, ctx in enumerate(contexts)}
    passage_order = {p.name: idx for idx, p in enumerate(passages)}
    rows: list[tuple[str, str]] = [
        (ctx.key, passage.name) for ctx in contexts for passage in passages
    ]
    if limit is not None and limit < len(rows):
        rng = random.Random(seed)
        rows = rng.sample(rows, limit)
    rows.sort(key=lambda row: (ctx_order[row[0]], passage_order[row[1]]))
    return [Execution(name=name, context=ctx) for ctx, name in rows]


def plan_summary(
    *,
    tier: str,
    passages: Sequence[ps.Passage],
    contexts: Sequence[ContextSpec],
    executions: Sequence[Execution],
) -> dict[str, Any]:
    per_context = collections.Counter(execution.context for execution in executions)
    per_passage = collections.Counter(execution.name for execution in executions)
    return {
        "tier": tier,
        "passage_count": len(passages),
        "context_count": len(contexts),
        "matrix_size": len(passages) * len(contexts),
        "execution_count": len(executions),
        "per_context": {ctx.key: per_context.get(ctx.key, 0) for ctx in contexts},
        "distinct_passages": len(per_passage),
    }


def dry_plan_lines(
    *,
    tier: str,
    all_passages: Sequence[ps.Passage],
    env_passages: Sequence[ps.Passage],
    env_stats: dict[str, Any],
    contexts: Sequence[ContextSpec],
    executions: Sequence[Execution],
    limit: int | None,
    seed: int,
) -> list[str]:
    """Human-readable ``--dry-plan`` output; no browser, no report files."""
    summary = plan_summary(
        tier=tier, passages=env_passages if tier == "daily" else all_passages,
        contexts=contexts, executions=executions,
    )
    lines = [
        f"[env-matrix] dry-plan tier={tier}",
        (
            f"[env-matrix] artifact passages={len(all_passages)} "
            f"env-sensitive={len(env_passages)} (rule hits, reference "
            f"{ENV_SENSITIVE_REFERENCE_HITS})"
        ),
        (
            f"[env-matrix] matrix={summary['passage_count']} passages x "
            f"{summary['context_count']} contexts = {summary['matrix_size']} executions"
        ),
        (
            f"[env-matrix] limit={limit} seed={seed} -> "
            f"{summary['execution_count']} executions over "
            f"{summary['distinct_passages']} distinct passages"
        ),
    ]
    for ctx in contexts:
        lines.append(
            f"[env-matrix]   context {ctx.key} ({ctx.label}): "
            f"{summary['per_context'].get(ctx.key, 0)} executions"
        )
    lines.append("[env-matrix] rule hits per pattern: " + json.dumps(
        {k: v for k, v in sorted(env_stats.get("per_pattern", {}).items())},
        ensure_ascii=False,
    ))
    return lines


# --------------------------------------------------------------------------- #
# Runtime injection / read-back (Playwright)
# --------------------------------------------------------------------------- #


SETUP_JS = r"""
(payload) => {
  const S = (window.__DOLX__ = window.__DOLX__ || {});
  const out = { applied: [], errors: [] };
  const TimeMod = window.Time, W = window.Weather;
  const V = window.SugarCube && window.SugarCube.State
    ? window.SugarCube.State.variables : null;
  // SugarCube's temporary state (`T`) is NOT part of the restored fixture, so
  // any override injected by a previous context would leak into this one
  // unless it is cleared here. Deliberately avoid naming this `T`: the page
  // defines a global `T`, and a local const would shadow it into the TDZ.
  const tempState = window.T || null;
  const DT = (typeof DateTime !== "undefined") ? DateTime : window.DateTime;
  if (!TimeMod || !W || !V || !DT) {
    out.errors.push("Time/Weather/V/DateTime missing");
    return out;
  }
  if (tempState) delete tempState.temperatureOverride;
  try {
    // Re-sync the Time closure with the just-restored fixture timestamp before
    // deriving any date from Time.year / Time.lastDayOfMonth.
    TimeMod.set();
    let date;
    if (payload.last_day_of_month) {
      // Time.lastDayOfMonth is the last day of the CURRENT month; the target
      // month may differ (e.g. fixture in November, blood moon in July), so the
      // last day must be read off the target month itself.
      const firstOfMonth = new DT(TimeMod.year, payload.month, 1, payload.hour, payload.minute);
      date = new DT(
        TimeMod.year, payload.month, firstOfMonth.lastDayOfMonth, payload.hour, payload.minute
      );
    } else if (payload.next_school_term) {
      const d = TimeMod.getNextSchoolTermStartDate();
      date = new DT(d.year, d.month, d.day, payload.hour, payload.minute);
    } else {
      date = new DT(TimeMod.year, payload.month, payload.day, payload.hour, payload.minute);
    }
    TimeMod.timeTravel(date);
    out.applied.push("timeTravel:" + date.year + "-" + date.month + "-" + date.day +
      "T" + date.hour + ":" + date.minute);
    if (payload.weather) {
      W.set(payload.weather, true);
      out.applied.push("weather:" + payload.weather);
    }
    if (payload.temperature !== null && payload.temperature !== undefined) {
      // Temperature.set() writes the day's *base* temperature and then
      // interpolates toward the next day, so the actual current temperature is
      // not stable. The game's own override (used by portals/schism events) is
      // honored verbatim by getCelsius(); use it and verify the read-back.
      if (W.Temperature && W.Temperature.override) {
        W.Temperature.override.outside = payload.temperature;
        out.applied.push("temperatureOverride:" + payload.temperature);
      } else {
        W.setTemperature(payload.temperature);
        out.applied.push("setTemperature:" + payload.temperature);
      }
    }
    if (payload.snow) {
      const min = (W.tempSettings && W.tempSettings.snow &&
        W.tempSettings.snow.minAccumulation) || 1;
      V.weatherObj.snow = Math.max(V.weatherObj.snow || 0, min * 2 + 1);
      out.applied.push("snow:" + V.weatherObj.snow);
    }
    for (const key of Object.keys(payload.set_vars || {})) {
      V[key] = payload.set_vars[key];
      out.applied.push("V." + key);
    }
  } catch (e) {
    out.errors.push(String(e && e.message ? e.message : e));
  }
  return out;
}
"""


READ_CONTEXT_JS = r"""
() => {
  const out = { ok: true, errors: [], time: null, weather: null, vars: null };
  try {
    const T = window.Time, W = window.Weather;
    const V = window.SugarCube.State.variables;
    const date = T.date;
    out.time = {
      year: date.year, month: date.month, day: date.day,
      hour: T.hour, minute: T.minute,
      monthName: T.monthName, monthDay: T.monthDay,
      lastDayOfMonth: T.lastDayOfMonth,
      // Time has no `day` getter (only `days`, elapsed); read it off the date.
      isLastDayOfMonth: date.day === T.lastDayOfMonth,
      dayState: T.dayState, season: T.season,
      isBloodMoon: T.isBloodMoon(),
      schoolDay: T.schoolDay, schoolTime: T.schoolTime,
      timeStamp: V.timeStamp,
    };
    out.weather = {
      name: W.name, value: W.value,
      precipitation: W.precipitation,
      isSnow: W.isSnow, isFreezing: W.isFreezing,
      temperature: W.temperature,
      bloodMoon: W.bloodMoon, skyState: W.skyState,
    };
    out.vars = {
      halloween: (V.halloween === undefined ? null : V.halloween),
      christmas: (V.christmas === undefined ? null : V.christmas),
      moonstate: (V.moonstate === undefined ? null : V.moonstate),
    };
  } catch (e) {
    out.ok = false;
    out.errors.push(String(e && e.message ? e.message : e));
  }
  return out;
}
"""


def context_payload(spec: ContextSpec) -> dict[str, Any]:
    return {
        "month": spec.month,
        "day": spec.day,
        "hour": spec.hour,
        "minute": spec.minute,
        "weather": spec.weather,
        "temperature": spec.temperature,
        "snow": spec.snow,
        "last_day_of_month": spec.last_day_of_month,
        "next_school_term": spec.next_school_term,
        "set_vars": {key: value for key, value in spec.set_vars},
    }


def _read_path(readback: Any, path: tuple[str, ...]) -> Any:
    node = readback
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _check_ok(actual: Any, op: str, expected: Any) -> bool:
    if op == "truthy":
        return bool(actual)
    if op == "in":
        return actual in (expected or [])
    return actual == expected


def evaluate_checks(readback: dict[str, Any] | None, spec: ContextSpec) -> tuple[bool, list[dict[str, Any]]]:
    """Fail-closed read-back evaluation: every required check must pass."""
    if not isinstance(readback, dict) or not readback.get("ok"):
        errors = (readback or {}).get("errors") if isinstance(readback, dict) else None
        return False, [
            {
                "check": "readback",
                "path": "readback.ok",
                "op": "truthy",
                "expected": True,
                "actual": errors or "missing/false",
            }
        ]
    unmet: list[dict[str, Any]] = []
    for check in spec.checks:
        actual = _read_path(readback, check.path)
        if not _check_ok(actual, check.op, check.value):
            unmet.append(
                {
                    "check": check.label,
                    "path": ".".join(check.path),
                    "op": check.op,
                    "expected": check.value,
                    "actual": actual,
                }
            )
    return (not unmet), unmet


def read_context(page: Any) -> dict[str, Any]:
    """Evaluate READ_CONTEXT_JS; kept thin so tests can pass a fake page."""
    result = page.evaluate(READ_CONTEXT_JS)
    return result if isinstance(result, dict) else {"ok": False, "errors": ["readback not an object"]}


def apply_context(page: Any, spec: ContextSpec) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    """Inject the context and read it back. Returns (ok, unmet, readback)."""
    setup = page.evaluate(SETUP_JS, context_payload(spec))
    if not isinstance(setup, dict) or setup.get("errors"):
        detail = setup.get("errors") if isinstance(setup, dict) else setup
        return False, [
            {
                "check": "setup",
                "path": "setup.errors",
                "op": "empty",
                "expected": [],
                "actual": detail,
            }
        ], {}
    readback = read_context(page)
    ok, unmet = evaluate_checks(readback, spec)
    return ok, unmet, readback


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #


def is_not_applicable(passage_name: str) -> bool:
    return passage_name in NON_SCENE_PASSAGES


def extract_missing_vars(errors: Iterable[dict[str, Any]]) -> list[str]:
    """Pull the referenced variable/property names out of JS error messages."""
    found: list[str] = []
    for error in errors or []:
        message = str(error.get("message", ""))
        for pattern in MISSING_VAR_PATTERNS:
            for match in pattern.finditer(message):
                name = match.group(1)
                if name not in found:
                    found.append(name)
    return found


def classify_result(
    passage_name: str,
    target: str,
    probe: dict[str, Any],
    *,
    timed_out: bool,
) -> tuple[str, str, list[str], bool]:
    """Five-tier verdict + reason + missing vars + redirect flag.

    Wraps ``passage_sweep.classify`` (same error vocabulary) and adds the
    landing assertion: landing somewhere other than the requested passage is a
    recorded redirect and therefore ``soft_fail``.
    """
    if is_not_applicable(passage_name):
        return "not_applicable", "engine/system passage is not a playable scene", [], False

    landed = probe.get("passage")
    if landed is None or not str(landed).strip():
        return "hard_fail", "actual passage missing from runtime probe", [], False
    status, detail = ps.classify(probe, landed is not None, timed_out=timed_out)
    missing_vars = extract_missing_vars(probe.get("errors") or [])

    if status in ("hard_fail", "fixture_insufficient"):
        return status, detail, missing_vars, False

    if landed is not None and str(landed) != target:
        return (
            "soft_fail",
            f"redirected: {target} -> {landed}"[:400],
            missing_vars,
            True,
        )
    if status == "soft_fail":
        return status, detail, missing_vars, False
    return "ok", detail, missing_vars, False


# --------------------------------------------------------------------------- #
# Sweep
# --------------------------------------------------------------------------- #


def sweep(
    html_path: Path,
    executions: Sequence[Execution],
    *,
    contexts: Sequence[ContextSpec],
    tier: str,
    per_passage_timeout_ms: int,
    headless: bool,
    bootstrap_settle_ms: int,
    fixture_vars: dict[str, Any] | None = None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    bst = ps._bst()
    by_key = {ctx.key: ctx for ctx in contexts}
    context_state: dict[str, dict[str, Any]] = {
        ctx.key: {
            "key": ctx.key,
            "label": ctx.label,
            "summary": ctx.summary,
            "verified": None,
            "reads_ok": 0,
            "reads_failed": 0,
            "last_unmet": [],
        }
        for ctx in contexts
    }

    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    report: dict[str, Any] = {
        "tool": TOOL,
        "tier": tier,
        "started_at": started,
        "results": [],
        "contexts": [],
        "bootstrap": {},
        "fixture_bytes": 0,
        "console_tail": [],
        "fatal_error": None,
    }
    t_start = time.time()

    serve_dir = html_path.parent
    with bst._serve_directory(serve_dir) as server, sync_playwright() as pw:
        url = bst._relative_url(server, serve_dir, html_path)
        browser = ps._launch_browser(pw, headless)
        page_context = browser.new_context()
        page_context.add_init_script(ps.INIT_HARNESS)
        page = page_context.new_page()
        console: list[str] = []

        def _push_console(line: str) -> None:
            console.append(line[:400])
            if len(console) > 4000:
                del console[:2000]

        page.on("console", lambda m: _push_console(f"{m.type}:{m.text[:300]}"))
        page.on("pageerror", lambda e: _push_console(f"pageerror:{str(e)[:300]}"))
        page.set_default_timeout(per_passage_timeout_ms + 5000)

        page.goto(url, wait_until="load", timeout=180_000)
        page.wait_for_function(ps._ready_js(), timeout=180_000)
        report["runtime_overrides"] = page.evaluate(
            "(() => { try { const C = window.SugarCube.Config;"
            " C.saves.autosave = false; C.passages.transitionOut = undefined;"
            " return { autosave: C.saves.autosave, transitionOut: C.passages.transitionOut }; }"
            " catch (e) { return { error: String(e) }; } })()"
        )

        boot = ps._reach_gameplay(page, steps=60)
        if not boot.get("passage") or str(boot["passage"]).lower() in ps.STARTUP_PASSAGES:
            raise SystemExit(
                "bootstrap did not reach gameplay; last passage="
                f"{boot.get('passage')!r} after {boot.get('steps')} steps; "
                f"last actions={boot.get('actions')[-4:]}"
            )
        page.wait_for_timeout(bootstrap_settle_ms)
        page.evaluate("(() => { const S = window.__DOLX__; if (S) S.hooked = false; return true; })()")
        hooked = False
        for _ in range(40):
            if page.evaluate(ps.install_passage_hook()):
                hooked = True
                break
            page.wait_for_timeout(250)
        if not hooked:
            raise SystemExit("could not install the :passagedisplay hook; aborting")

        if fixture_vars is not None:
            fixture = fixture_vars
            fixture_json = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"))
            report["bootstrap"] = {
                "source": "fixture-file",
                "steps": boot["steps"],
                "passage": boot["passage"],
                "fixture": fixture_meta,
                "fixture_vars": len(fixture),
            }
            report["fixture_bytes"] = len(fixture_json)
            load_ok = page.evaluate(ps.LOAD_FIXTURE, fixture_json)
            report["bootstrap"]["load_fixture"] = load_ok
            if not load_ok.get("ok"):
                raise SystemExit(f"fixture load failed: {load_ok}")
            first_restore = page.evaluate(ps.RESTORE_FIXTURE)
            report["bootstrap"]["first_restore"] = first_restore
            if not (isinstance(first_restore, dict) and first_restore.get("ok")):
                raise SystemExit(f"fixture restore failed (fail-closed): {first_restore}")
        else:
            snap = json.loads(page.evaluate(ps.FIXTURE_SNAPSHOT))
            fixture = snap.get("variables") if isinstance(snap.get("variables"), dict) else {}
            fixture_json = json.dumps(fixture, ensure_ascii=True, separators=(",", ":"))
            report["bootstrap"] = {
                "source": "bootstrap-snapshot",
                "steps": boot["steps"],
                "passage": boot["passage"],
                "actions": boot.get("actions"),
                "snapshot_ok": snap.get("ok"),
                "snapshot_meta": snap.get("meta"),
                "fixture_vars": len(fixture),
            }
            report["fixture_bytes"] = len(fixture_json)
            load_ok = page.evaluate(ps.LOAD_FIXTURE, fixture_json)
            report["bootstrap"]["load_fixture"] = load_ok
            if not load_ok.get("ok"):
                raise SystemExit(f"fixture load failed: {load_ok}")
            report["bootstrap"]["first_restore"] = page.evaluate(ps.RESTORE_FIXTURE)

        try:
            for idx, execution in enumerate(executions, 1):
                spec = by_key[execution.context]
                t0 = time.time()
                result: dict[str, Any] = {
                    "name": execution.name,
                    "context": execution.context,
                    "status": "hard_fail",
                    "reason": "",
                    "duration_ms": 0,
                    "missing_vars": [],
                    "landed": None,
                    "text_len": 0,
                    "redirect": False,
                    "errors": [],
                }
                try:
                    restore = page.evaluate(ps.RESTORE_FIXTURE)
                    if not (isinstance(restore, dict) and restore.get("ok")):
                        result["reason"] = f"fixture restore failed: {restore}"[:400]
                        report["results"].append(result)
                        continue

                    ctx_ok, unmet, readback = apply_context(page, spec)
                    state = context_state[spec.key]
                    if state["verified"] is None:
                        state["verified"] = bool(ctx_ok)
                    if ctx_ok:
                        state["reads_ok"] += 1
                    else:
                        state["reads_failed"] += 1
                        state["last_unmet"] = unmet
                    if not ctx_ok:
                        result["reason"] = (
                            "context verify failed: "
                            + "; ".join(
                                f"{item.get('path')}={item.get('actual')!r} (expected "
                                f"{item.get('op')} {item.get('expected')!r})"
                                for item in unmet[:4]
                            )
                        )[:400]
                        result["readback"] = readback
                        report["results"].append(result)
                        continue

                    if is_not_applicable(execution.name):
                        result["status"] = "not_applicable"
                        result["reason"] = "engine/system passage is not a playable scene"
                    else:
                        timed_out = False
                        try:
                            page.evaluate(ps.PLAY_PASSAGE, {"name": execution.name})
                            try:
                                page.wait_for_function(
                                    "(() => !!(window.__DOLX__ && window.__DOLX__.done))()",
                                    timeout=per_passage_timeout_ms,
                                )
                            except Exception:
                                timed_out = True
                        except Exception as exc:  # noqa: BLE001
                            page.evaluate(
                                "(() => { const S = window.__DOLX__; if (S) { S.done = true; "
                                "S.errors.push({kind:'error', message:'sweep-driver: ' + "
                                + json.dumps(str(exc)[:200])
                                + ", source:'driver'}); } return true; })()"
                            )
                        probe = page.evaluate(ps.PROBE)
                        status, reason, missing_vars, redirect = classify_result(
                            execution.name,
                            execution.name,
                            probe,
                            timed_out=timed_out,
                        )
                        result.update(
                            {
                                "status": status,
                                "reason": reason,
                                "missing_vars": missing_vars,
                                "redirect": redirect,
                                "landed": probe.get("passage"),
                                "text_len": int(probe.get("textLen") or 0),
                                "errors": (probe.get("errors") or [])[:20],
                            }
                        )
                except Exception as exc:  # noqa: BLE001 - keep the partial report
                    result["reason"] = f"{type(exc).__name__}: {exc}"[:400]
                finally:
                    result["duration_ms"] = int((time.time() - t0) * 1000)
                report["results"].append(result)
                if idx % 25 == 0:
                    print(f"  ... {idx}/{len(executions)}", flush=True)
        except Exception as exc:  # noqa: BLE001 - keep the partial report
            report["fatal_error"] = f"{type(exc).__name__}: {exc}"[:500]
            print(
                f"[env-matrix] fatal after {len(report['results'])} executions: "
                f"{report['fatal_error']}",
                flush=True,
            )

        report["console_tail"] = console[-500:]
        browser.close()

    counts = collections.Counter(str(r["status"]) for r in report["results"])
    report["verdict_counts"] = {verdict: counts.get(verdict, 0) for verdict in VERDICTS}
    report["contexts"] = [context_state[ctx.key] for ctx in contexts]
    report["summary"] = {
        "executed": len(report["results"]),
        "verdict_counts": dict(report["verdict_counts"]),
        "total_ms": int((time.time() - t_start) * 1000),
    }
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return report


# --------------------------------------------------------------------------- #
# Baseline + reporting
# --------------------------------------------------------------------------- #


def _result_key(result: dict[str, Any]) -> str:
    return f"{result.get('context')}#{result.get('name')}"


def diff_against_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Baseline diff keyed by (context, passage); only new regressions are flagged.

    Same output shape as ``passage_sweep.diff_against_baseline`` (regressions /
    fixed / changed / unseen_in_baseline), with the context folded into the key
    so the same passage may legitimately be ok in one context and broken in
    another.
    """
    old = {
        _result_key(r): str(r.get("verdict") or r.get("status"))
        for r in baseline.get("results") or []
        if isinstance(r, dict)
    }
    new = {
        _result_key(r): str(r.get("verdict") or r.get("status"))
        for r in report.get("results") or []
        if isinstance(r, dict)
    }
    regressions: list[dict[str, Any]] = []
    fixed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unseen: list[dict[str, Any]] = []
    for key, status in new.items():
        previous = old.get(key)
        if previous is None:
            unseen.append({"key": key, "verdict": status})
            continue
        if previous == status:
            continue
        if VERDICT_SEVERITY.get(status, 3) > VERDICT_SEVERITY.get(previous, 3):
            regressions.append({"key": key, "was": previous, "now": status})
        elif status == "ok":
            fixed.append({"key": key, "was": previous, "now": status})
        else:
            changed.append({"key": key, "was": previous, "now": status})
    return {
        "regressions": regressions,
        "fixed": fixed,
        "changed": changed,
        "unseen_in_baseline": unseen,
    }


def default_out_dir(tier: str, day: str | None = None) -> Path:
    """``.local/sweep/env-<MMDD>/`` as promised by the tool contract."""
    stamp = day or time.strftime("%m%d")
    return DEFAULT_OUT_ROOT / f"env-{stamp}"


def baseline_path(tier: str) -> Path:
    return DEFAULT_BASELINE_DIR / f"env-{tier}.json"


def _fixture_summary(fixture: dict[str, Any] | None) -> str:
    if not fixture:
        return "`bootstrap` (snapshot taken in this run)"
    source = str(fixture.get("source", "?"))
    digest = str(fixture.get("sha256", ""))[:12]
    keys = fixture.get("keys", "?")
    return f"`{source}` keys={keys} sha256={digest}"


def write_report(report: dict[str, Any], out_dir: Path, diff: dict[str, Any] | None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tier = str(report.get("tier") or "daily")
    json_path = out_dir / f"env-{tier}-report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = report.get("meta") or {}
    counts = report.get("verdict_counts") or {}
    lines = [
        "# DOL-X environment matrix report",
        "",
        f"- tier: **{tier}**",
        f"- target: `{report.get('target')}`",
        f"- sha256: `{meta.get('sha256', '?')}`",
        f"- fixture: {_fixture_summary(report.get('fixture'))}",
        f"- contexts: {', '.join(str(c.get('key')) for c in report.get('contexts') or [])}",
        (
            f"- env-sensitive rule: {meta.get('env_sensitive_rule', {}).get('hit_count', '?')} hits "
            f"(reference {meta.get('env_sensitive_rule', {}).get('reference_hit_count', '?')})"
        ),
        (
            f"- plan: {meta.get('plan', {}).get('passage_count', '?')} passages x "
            f"{meta.get('plan', {}).get('context_count', '?')} contexts -> "
            f"{meta.get('plan', {}).get('execution_count', '?')} executions"
        ),
        f"- started: {report.get('started_at')} / finished: {report.get('finished_at')}",
        "",
        "## verdicts",
        "",
        "| verdict | count |",
        "| --- | --- |",
    ]
    for verdict in VERDICTS:
        lines.append(f"| {verdict} | {counts.get(verdict, 0)} |")

    if diff is not None:
        lines += ["", "## baseline diff", ""]
        lines.append(f"- new regressions: **{len(diff.get('regressions') or [])}**")
        lines.append(f"- fixed: {len(diff.get('fixed') or [])}")
        lines.append(f"- changed (non-regression): {len(diff.get('changed') or [])}")
        lines.append(f"- unseen in baseline: {len(diff.get('unseen_in_baseline') or [])}")
        for item in (diff.get("regressions") or [])[:40]:
            lines.append(f"  - `{item.get('key')}`: {item.get('was')} -> {item.get('now')}")

    contexts = report.get("contexts") or []
    if contexts:
        lines += [
            "",
            "## contexts",
            "",
            "| context | label | verified | reads ok | reads failed |",
            "| --- | --- | --- | --- | --- |",
        ]
        for ctx in contexts:
            lines.append(
                f"| {ctx.get('key')} | {ctx.get('label')} | {ctx.get('verified')} | "
                f"{ctx.get('reads_ok')} | {ctx.get('reads_failed')} |"
            )

    for kind in ("hard_fail", "soft_fail", "fixture_insufficient"):
        bad = [r for r in report.get("results") or [] if r.get("status") == kind]
        if not bad:
            continue
        title = {"hard_fail": "hard failures", "soft_fail": "soft failures"}.get(kind, kind)
        lines += ["", f"## {title} ({len(bad)})", ""]
        for item in bad[:60]:
            missing = ""
            if item.get("missing_vars"):
                missing = " [missing: " + ", ".join(str(v) for v in item["missing_vars"][:6]) + "]"
            lines.append(
                f"- `{item.get('context')}` / `{item.get('name')}`: "
                f"{str(item.get('reason') or '')[:220]}{missing}"
            )
        if len(bad) > 60:
            lines.append(f"- ... and {len(bad) - 60} more")

    md_path = out_dir / f"env-{tier}-report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DOL-X environment matrix sweep (engine A)")
    parser.add_argument("--target", type=Path, required=True, help="built .html or .zip to sweep")
    parser.add_argument("--tier", choices=TIERS, required=True, help="daily = env-sensitive x 8; full = all x 4")
    parser.add_argument("--limit", type=int, default=None, help="random sample of N executions (seed-controlled)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--jobs", type=int, default=1, help="executor count (only 1 is implemented)")
    parser.add_argument("--fixture", type=Path, default=None, help="fixture json (default .local/fixtures/base-1004.json if present)")
    parser.add_argument("--out", type=Path, default=None, help="report dir (default .local/sweep/env-<MMDD>)")
    parser.add_argument("--baseline", type=Path, default=None, help="baseline json to diff")
    parser.add_argument("--save-baseline", action="store_true", help="seal this run as .local/sweep/baselines/env-<tier>.json")
    parser.add_argument("--dry-plan", action="store_true", help="print the expanded matrix and exit (no browser)")
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run headless (default true; use --no-headless to watch)",
    )
    parser.add_argument("--timeout-ms", type=int, default=8000, help="per-passage render timeout")
    parser.add_argument("--bootstrap-settle-ms", type=int, default=1500)
    return parser.parse_args(argv)


def target_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target: Path = args.target
    if not target.exists():
        print(f"[env-matrix] target does not exist: {target}")
        return 2

    passages, _ = ps.extract_passages(target)
    env_passages, env_stats = scan_env_sensitive(passages)
    contexts = contexts_for_tier(args.tier)
    planning_passages = env_passages if args.tier == "daily" else passages
    executions = expand_matrix(planning_passages, contexts, limit=args.limit, seed=args.seed)
    plan = plan_summary(
        tier=args.tier, passages=planning_passages, contexts=contexts, executions=executions
    )
    rule = rule_meta(env_stats)

    print(
        f"[env-matrix] target={target} tier={args.tier} passages={len(passages)} "
        f"env_sensitive={len(env_passages)} contexts={len(contexts)} executions={len(executions)}"
    )
    if rule["drift_note"]:
        print(f"[env-matrix] rule: hit_count={rule['hit_count']} drift={rule['drift']:+d} "
              f"(reference {rule['reference_hit_count']})")

    if args.dry_plan:
        lines = dry_plan_lines(
            tier=args.tier,
            all_passages=passages,
            env_passages=env_passages,
            env_stats=env_stats,
            contexts=contexts,
            executions=executions,
            limit=args.limit,
            seed=args.seed,
        )
        print("\n".join(lines))
        return 0

    jobs_requested = max(1, int(args.jobs))
    if jobs_requested != 1:
        print(
            f"[env-matrix] WARNING: --jobs {jobs_requested} is not implemented yet "
            "(single executor); running sequentially."
        )

    fixture_path: Path | None = args.fixture
    if fixture_path is None and DEFAULT_FIXTURE.exists():
        fixture_path = DEFAULT_FIXTURE
    fixture_vars: dict[str, Any] | None = None
    fixture_meta: dict[str, Any] | None = None
    if fixture_path is not None:
        if not fixture_path.exists():
            print(f"[env-matrix] fixture does not exist: {fixture_path}")
            return 2
        fixture_vars, fixture_meta = ps.load_fixture_file(fixture_path)
        print(f"[env-matrix] fixture={fixture_path} keys={fixture_meta['keys']} "
              f"sha256={fixture_meta['sha256'][:12]}")

    html_path = ps.resolve_html_path(target)
    out_dir: Path = args.out or default_out_dir(args.tier)
    report = sweep(
        html_path,
        executions,
        contexts=contexts,
        tier=args.tier,
        per_passage_timeout_ms=args.timeout_ms,
        headless=args.headless,
        bootstrap_settle_ms=args.bootstrap_settle_ms,
        fixture_vars=fixture_vars,
        fixture_meta=fixture_meta,
    )
    report["meta"] = {
        "tool": TOOL,
        "date": time.strftime("%Y-%m-%d"),
        "tier": args.tier,
        "target": str(target),
        "html_path": str(html_path),
        "sha256": target_sha256(target),
        "fixture": fixture_meta or {"source": "bootstrap-snapshot"},
        "contexts": [
            {"key": ctx.key, "label": ctx.label, "summary": ctx.summary, "tier": list(ctx.tiers)}
            for ctx in contexts
        ],
        "env_sensitive_rule": rule,
        "plan": plan,
        "limit": args.limit,
        "seed": args.seed,
        "jobs_requested": jobs_requested,
        "jobs_used": 1,
    }
    report["fixture"] = fixture_meta or {"source": "bootstrap-snapshot"}
    report["target"] = str(target)
    report["html_path"] = str(html_path)
    report["plan"] = plan

    baseline_file: Path | None = args.baseline
    if baseline_file is None and not args.save_baseline:
        candidate = baseline_path(args.tier)
        if candidate.exists():
            baseline_file = candidate
    diff = None
    if baseline_file is not None and baseline_file.exists():
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        diff = diff_against_baseline(report, baseline)
        report["baseline_diff"] = diff
        report["baseline_source"] = str(baseline_file)

    md = write_report(report, out_dir, diff)
    if args.save_baseline:
        sealed = baseline_path(args.tier)
        sealed.parent.mkdir(parents=True, exist_ok=True)
        sealed.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[env-matrix] baseline sealed -> {sealed}")

    print(f"[env-matrix] verdicts={report['verdict_counts']}")
    print(f"[env-matrix] report -> {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
