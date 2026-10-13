"""Deterministic semantic traces for the DOL-X gameplay explorer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Keep semantic fields and drop desktop-only locator noise."""
    fields = (
        "step",
        "kind",
        "semantic_id",
        "role",
        "text",
        "text_hash",
        "passage_before",
        "passage_after",
        "fingerprint_before",
        "fingerprint_after",
    )
    result: dict[str, Any] = {"schema": SCHEMA_VERSION}
    for field in fields:
        if field in action:
            result[field] = action[field]
    return result


@dataclass(frozen=True)
class SemanticTrace:
    actions: tuple[dict[str, Any], ...]

    @classmethod
    def from_actions(cls, actions: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> "SemanticTrace":
        return cls(tuple(normalize_action(action) for action in actions))

    def to_json(self) -> dict[str, Any]:
        actions = list(self.actions)
        return {
            "schema": SCHEMA_VERSION,
            "trace_digest": digest(actions),
            "actions": actions,
        }

    def subsequence(self, indices: list[int]) -> "SemanticTrace":
        return SemanticTrace(tuple(self.actions[index] for index in indices))


def traces_match(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical_json(left) == canonical_json(right)
