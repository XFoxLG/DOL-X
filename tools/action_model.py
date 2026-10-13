"""Semantic UI action discovery and selection for DOL-X exploration."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DiscoveredAction:
    kind: str
    semantic_id: str
    text: str
    role: str
    disabled: bool = False
    checked: bool | None = None
    value: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "kind": self.kind,
            "semantic_id": self.semantic_id,
            "text": self.text,
            "text_hash": text_hash(self.text),
            "role": self.role,
            "disabled": self.disabled,
            "checked": self.checked,
            "value": self.value,
        }


def score_action(action: Mapping[str, Any], *, uncovered_edge: bool = False) -> int:
    if action.get("disabled"):
        return -100
    if action.get("pointer_blocked"):
        # A Playwright click here would normally hit the overlay/modal covering
        # the control instead of the underlying game control.
        return -1000
    score = 0
    if uncovered_edge:
        score += 10
    if action.get("overlay"):
        # Modal controls are often the only useful way to dismiss or configure
        # an overlay; rank them ahead of ordinary passage links.
        score += 120
    if action.get("scope") == "passage":
        score += 100
    if action.get("semantic_id"):
        score += 8
    if action.get("text"):
        score += 2
    return score


def choose_actions(
    actions: Iterable[Mapping[str, Any]], *, seed: int, uncovered_edges: Iterable[str] = ()
) -> list[Mapping[str, Any]]:
    rng = random.Random(seed)
    actions = [
        dict(action)
        for action in actions
        if not action.get("disabled") and not action.get("pointer_blocked")
    ]
    uncovered = set(uncovered_edges)
    return sorted(
        actions,
        key=lambda action: (
            -score_action(action, uncovered_edge=action.get("semantic_id") in uncovered),
            str(action.get("semantic_id") or ""),
            rng.random(),
        ),
    )
