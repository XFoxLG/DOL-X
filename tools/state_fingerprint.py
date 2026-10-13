#!/usr/bin/env python3
"""Deterministic state summaries for the DOL-X gameplay explorer.

The game state is large, cyclic and contains values that are useful for a
runtime but useless for deciding whether two explorer nodes are the same.  This
module deliberately stays independent from Playwright and SugarCube so it can
be unit-tested with small dictionaries and reused by desktop and Android
replay runners.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
DEFAULT_VOLATILE_KEYS = frozenset(
    {
        "timestamp",
        "updated_at",
        "updatedAt",
        "elapsed_ms",
        "elapsedMs",
        "renderSeq",
        "step",
        "index",
        "nonce",
        "random",
    }
)
MAX_EXACT_DEPTH = 10_000
SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|token|secret|cookie|authorization|credential|api[_-]?key|savepayload)",
    re.IGNORECASE,
)
ABSOLUTE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|tmp|var|workspace)(?:[\\/]|$))"
)


def _number(value: float | int) -> int | float | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    rounded = round(float(value), 9)
    return int(rounded) if rounded.is_integer() else rounded


def _redact_string(value: str) -> str:
    if ABSOLUTE_PATH_RE.search(value):
        return "<redacted-path>"
    if len(value) > 10000:
        return value[:10000] + "<truncated>"
    return value


def canonicalize_exact(
    value: Any,
    *,
    max_depth: int = MAX_EXACT_DEPTH,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> Any:
    """Return a lossless, deterministic JSON-safe view of a runtime value.

    This is the fingerprint path.  It never removes volatile keys, redacts
    fields, or truncates strings; report safety is handled separately by
    :func:`redact_for_report`.
    """
    seen = _seen if _seen is not None else set()
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        return _number(value)
    if _depth >= max_depth:
        return "<exact-depth-clipped>"
    identity = id(value)
    if isinstance(value, (Mapping, list, tuple, set)):
        if identity in seen:
            return "<circular>"
        seen.add(identity)
    try:
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                out[str(raw_key)] = canonicalize_exact(
                    raw_value,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen=seen,
                )
            return out
        if isinstance(value, (list, tuple)):
            return [
                canonicalize_exact(item, max_depth=max_depth, _depth=_depth + 1, _seen=seen)
                for item in value
            ]
        if isinstance(value, set):
            items = [
                canonicalize_exact(item, max_depth=max_depth, _depth=_depth + 1, _seen=seen)
                for item in value
            ]
            return sorted(items, key=lambda item: canonical_json_exact(item))
        if hasattr(value, "isoformat"):
            return {"__type__": type(value).__name__, "value": str(value.isoformat())}
        return f"<{type(value).__name__}>"
    finally:
        if isinstance(value, (Mapping, list, tuple, set)):
            seen.discard(identity)


def canonicalize(
    value: Any,
    *,
    volatile_keys: Iterable[str] = DEFAULT_VOLATILE_KEYS,
    redact_sensitive: bool = True,
    max_depth: int = 12,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> Any:
    """Convert arbitrary runtime-like data into stable JSON-safe data.

    Dictionary keys are sorted by :func:`canonical_json`; volatile fields are
    omitted only from mappings.  Cycles and unsupported values are represented
    explicitly so a broken state does not silently become an empty fingerprint.
    """
    seen = _seen if _seen is not None else set()
    volatile = {str(item) for item in volatile_keys}
    if value is None or isinstance(value, (str, bool)):
        return _redact_string(value) if isinstance(value, str) else value
    if isinstance(value, (int, float)):
        return _number(value)
    if _depth >= max_depth:
        return "<depth-clipped>"
    identity = id(value)
    if isinstance(value, (Mapping, list, tuple, set)):
        if identity in seen:
            return "<circular>"
        seen.add(identity)
    try:
        if isinstance(value, Mapping):
            out: dict[str, Any] = {}
            for raw_key, raw_value in value.items():
                key = str(raw_key)
                if key in volatile:
                    continue
                if redact_sensitive and SENSITIVE_KEY_RE.search(key):
                    out[key] = "<redacted>"
                    continue
                out[key] = canonicalize(
                    raw_value,
                    volatile_keys=volatile,
                    redact_sensitive=redact_sensitive,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen=seen,
                )
            return out
        if isinstance(value, (list, tuple)):
            return [
                canonicalize(
                    item,
                    volatile_keys=volatile,
                    redact_sensitive=redact_sensitive,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen=seen,
                )
                for item in value
            ]
        if isinstance(value, set):
            items = [
                canonicalize(
                    item,
                    volatile_keys=volatile,
                    redact_sensitive=redact_sensitive,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                    _seen=seen,
                )
                for item in value
            ]
            return sorted(items, key=lambda item: canonical_json(item))
        if hasattr(value, "isoformat"):
            return {"__type__": type(value).__name__, "value": str(value.isoformat())}
        return f"<{type(value).__name__}>"
    finally:
        if isinstance(value, (Mapping, list, tuple, set)):
            seen.discard(identity)


def canonical_json(value: Any) -> str:
    """Return a deterministic compact JSON representation."""
    return json.dumps(
        canonicalize(value, redact_sensitive=False),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_exact(value: Any) -> str:
    """Return the deterministic JSON representation used for exact hashes."""
    return json.dumps(
        canonicalize_exact(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_json_exact(value: Any) -> str:
    return hashlib.sha256(canonical_json_exact(value).encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_exact(value).encode("utf-8")).hexdigest()


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def semantic_dom(value: Any) -> Any:
    """Normalize a DOM candidate list while ignoring locator noise."""
    if isinstance(value, Mapping):
        fields = {
            key: value[key]
            for key in (
                "id",
                "name",
                "href",
                "role",
                "tag",
                "text",
                "semantic_id",
                "scope",
                "overlay",
                "pointer_blocked",
                "disabled",
                "checked",
                "value",
            )
            if key in value
        }
        return canonicalize_exact(fields)
    if isinstance(value, (list, tuple)):
        normalized = [semantic_dom(item) for item in value]
        return sorted(normalized, key=canonical_json_exact)
    return canonicalize_exact(value)


def redact_for_report(value: Any) -> Any:
    """Return a report-safe copy without changing the local raw evidence."""
    return canonicalize(value, redact_sensitive=True)


def build_fingerprint(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build coarse and exact fingerprints from a runtime snapshot.

    The caller may provide full variables or only a source-driven subset.  The
    exact digest includes all supplied stable fields; the coarse digest uses
    user-facing navigation and interaction fields so it is useful for queue
    de-duplication without storing every variable in the report.
    """
    variables = _pick(snapshot, "variables", "state_variables") or {}
    stable_variables = canonicalize_exact(variables)
    interactive_dom = _pick(snapshot, "dom", "interactive", "interactive_elements") or []
    dom = semantic_dom(interactive_dom)
    passage = _pick(snapshot, "passage", "current_passage")
    overlay = _pick(snapshot, "overlay", "active_overlay")
    if overlay is None:
        overlay = any(
            isinstance(item, Mapping) and bool(item.get("overlay"))
            for item in (interactive_dom if isinstance(interactive_dom, list) else [])
        )
    coarse = {
        "passage": passage,
        "location": _pick(snapshot, "location", "area"),
        "day": _pick(snapshot, "day", "date_day"),
        "time_bucket": _pick(snapshot, "time_bucket", "timeBucket"),
        "weather": _pick(snapshot, "weather", "weather_key"),
        "season": _pick(snapshot, "season"),
        "combat": _pick(snapshot, "combat", "in_combat"),
        "overlay": overlay,
        "active_mods": sorted(str(item) for item in (_pick(snapshot, "active_mods", "mods") or [])),
        "interactive": dom,
    }
    exact = {
        "schema": SCHEMA_VERSION,
        "passage": passage,
        "variables": stable_variables,
        "dom": dom,
        "npc": canonicalize_exact(_pick(snapshot, "npc", "npc_roster") or {}),
        "inventory": canonicalize_exact(_pick(snapshot, "inventory") or {}),
        "combat": canonicalize_exact(_pick(snapshot, "combat_state") or _pick(snapshot, "combat")),
        "storage": canonicalize_exact(_pick(snapshot, "storage", "storage_digest")),
        "mod_registry": canonicalize_exact(_pick(snapshot, "mod_registry", "active_mods", "mods")),
        "prng": canonicalize_exact(_pick(snapshot, "prng", "prng_digest")),
        "history": canonicalize_exact(_pick(snapshot, "history", "history_digest")),
    }
    return {
        "schema": SCHEMA_VERSION,
        "coarse": coarse,
        "coarse_hash": _digest(coarse),
        "exact_hash": _digest(exact),
        "components": {
        "variables": _digest(stable_variables),
            "dom": _digest(dom),
            "npc": _digest(exact["npc"]),
            "inventory": _digest(exact["inventory"]),
            "combat": _digest(exact["combat"]),
            "storage": _digest(exact["storage"]),
            "mod_registry": _digest(exact["mod_registry"]),
            "prng": _digest(exact["prng"]),
            "history": _digest(exact["history"]),
        },
    }


@dataclass(frozen=True)
class CheckpointIdentity:
    target_sha256: str
    fixture_digest: str | None
    fingerprint: str
    evidence_track: str
    continuation: str
    schema: int = SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_sha256": self.target_sha256,
            "fixture_digest": self.fixture_digest,
            "fingerprint": self.fingerprint,
            "evidence_track": self.evidence_track,
            "continuation": self.continuation,
        }


def make_checkpoint_metadata(
    *,
    target_sha256: str,
    fixture_digest: str | None,
    fingerprint: Mapping[str, Any] | str,
    evidence_track: str = "natural_prefix",
    continuation: str = "checkpoint_restore",
) -> dict[str, Any]:
    exact_hash = fingerprint if isinstance(fingerprint, str) else str(fingerprint.get("exact_hash") or "")
    if not exact_hash:
        raise ValueError("checkpoint requires an exact fingerprint hash")
    return CheckpointIdentity(
        target_sha256=str(target_sha256),
        fixture_digest=str(fixture_digest) if fixture_digest is not None else None,
        fingerprint=exact_hash,
        evidence_track=str(evidence_track),
        continuation=str(continuation),
    ).to_json()


def validate_checkpoint_metadata(
    checkpoint: Mapping[str, Any],
    *,
    target_sha256: str,
    fixture_digest: str | None = None,
    fingerprint: Mapping[str, Any] | str | None = None,
) -> tuple[bool, list[str]]:
    diagnostics: list[str] = []
    if checkpoint.get("schema") != SCHEMA_VERSION:
        diagnostics.append(f"schema: expected {SCHEMA_VERSION}, got {checkpoint.get('schema')!r}")
    if checkpoint.get("target_sha256") != target_sha256:
        diagnostics.append("target_sha256: checkpoint belongs to another artifact")
    if checkpoint.get("fixture_digest") != fixture_digest:
        diagnostics.append("fixture_digest: checkpoint belongs to another fixture")
    if fingerprint is not None:
        actual = fingerprint if isinstance(fingerprint, str) else str(fingerprint.get("exact_hash") or "")
        if checkpoint.get("fingerprint") != actual:
            diagnostics.append("fingerprint: restored state differs from checkpoint")
    if checkpoint.get("evidence_track") not in {"natural_prefix", "assisted"}:
        diagnostics.append("evidence_track: unsupported checkpoint track")
    return not diagnostics, diagnostics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=PurePath, help="JSON snapshot file")
    parser.add_argument("--out", type=PurePath, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = open(str(args.input), encoding="utf-8")
    try:
        snapshot = json.load(source)
    finally:
        source.close()
    result = build_fingerprint(snapshot)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(str(args.out), "w", encoding="utf-8") as handle:
            handle.write(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
