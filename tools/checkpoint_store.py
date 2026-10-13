"""Fail-closed checkpoint storage for gameplay exploration."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tools.state_fingerprint import (
    make_checkpoint_metadata,
    validate_checkpoint_metadata,
)


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Checkpoint:
    metadata: dict[str, Any]
    payload: dict[str, Any]


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def encode_checkpoint(checkpoint: Checkpoint) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "metadata": checkpoint.metadata,
            "payload": checkpoint.payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def save_checkpoint(path: Path, checkpoint: Checkpoint) -> None:
    atomic_write(path, encode_checkpoint(checkpoint))


def load_checkpoint(
    path: Path,
    *,
    target_sha256: str,
    fixture_digest: str | None = None,
    exact_hash: str | None = None,
) -> tuple[Checkpoint | None, list[str]]:
    diagnostics: list[str] = []
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        return None, [f"checkpoint unreadable: {exc}"]
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return None, [f"checkpoint invalid JSON: {exc}"]
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        return None, ["checkpoint schema mismatch"]
    metadata = data.get("metadata")
    payload = data.get("payload")
    if not isinstance(metadata, dict) or not isinstance(payload, dict):
        return None, ["checkpoint metadata/payload missing"]
    fingerprint = exact_hash
    ok, metadata_diagnostics = validate_checkpoint_metadata(
        metadata,
        target_sha256=target_sha256,
        fixture_digest=fixture_digest,
        fingerprint=fingerprint,
    )
    diagnostics.extend(metadata_diagnostics)
    if not ok:
        return None, diagnostics
    return Checkpoint(metadata=metadata, payload=payload), diagnostics


def make_checkpoint(
    *,
    target_sha256: str,
    fixture_digest: str | None,
    exact_hash: str,
    payload: Mapping[str, Any],
    evidence_track: str = "natural_prefix",
) -> Checkpoint:
    metadata = make_checkpoint_metadata(
        target_sha256=target_sha256,
        fixture_digest=fixture_digest,
        fingerprint=exact_hash,
        evidence_track=evidence_track,
    )
    return Checkpoint(metadata=metadata, payload=dict(payload))


def diagnose_fingerprint_drift(
    saved_components: Mapping[str, Any] | None,
    actual_components: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Classify the visible component deltas behind an exact fingerprint mismatch.

    The result is evidence for triage, not proof that a product passage is bad:
    SugarCube side effects, Mod bootstrap work and missing payload fields can all
    produce the same hashes.  It deliberately names changed surfaces first and
    then gives a conservative classification.
    """
    saved = dict(saved_components or {})
    actual = dict(actual_components or {})
    changed = sorted(key for key in saved.keys() | actual.keys() if saved.get(key) != actual.get(key))

    component_hypotheses = {
        "combat": "combat side effect during rerender or restore",
        "dom": "interactive DOM changed during rerender or bootstrap",
        "history": "history sequence changed during restore/rerender",
        "mod_registry": "mod registry changed during bootstrap/rerender",
        "prng": "PRNG sequence advanced or cannot roundtrip",
        "storage": "localStorage/sessionStorage changed after restore",
        "variables": "game variables changed during rerender/restore",
    }
    hypotheses = [component_hypotheses[key] for key in changed if key in component_hypotheses]

    if not changed:
        classification = "no_component_change"
    elif changed == ["combat"]:
        classification = "combat_side_effect"
    elif changed == ["prng"]:
        classification = "prng_sequence"
    elif changed == ["history"]:
        classification = "history_sequence"
    elif changed == ["dom"]:
        classification = "render_side_effect"
    elif changed == ["mod_registry"]:
        classification = "mod_registry_bootstrap"
    elif changed == ["storage"]:
        classification = "storage_side_effect"
    elif changed == ["variables"]:
        classification = "state_side_effect"
    elif changed == ["history", "prng"]:
        classification = "history_prng_sequence"
    elif changed == ["combat", "history", "prng"]:
        classification = "combat_sequence_side_effect"
    elif changed == ["dom", "history", "prng"]:
        classification = "render_sequence_side_effect"
    else:
        classification = "mixed_state_drift"

    return {
        "changed_components": changed,
        "component_hypotheses": hypotheses,
        "classification": classification,
        "expected": {key: saved.get(key) for key in changed},
        "actual": {key: actual.get(key) for key in changed},
    }
