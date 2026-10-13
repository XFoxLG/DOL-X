"""Fail-closed checkpoint roundtrip tests."""

from __future__ import annotations

import json

from tools.checkpoint_store import (
    diagnose_fingerprint_drift,
    load_checkpoint,
    make_checkpoint,
    save_checkpoint,
)


def test_checkpoint_roundtrip_and_rejects_target_drift(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    checkpoint = make_checkpoint(
        target_sha256="a" * 64,
        fixture_digest=None,
        exact_hash="e" * 64,
        payload={"State.marshalForSave()": {"variables": {"money": 10}}},
    )
    save_checkpoint(path, checkpoint)

    loaded, diagnostics = load_checkpoint(path, target_sha256="a" * 64, exact_hash="e" * 64)
    assert loaded is not None
    assert diagnostics == []
    assert loaded.payload == checkpoint.payload

    loaded, diagnostics = load_checkpoint(path, target_sha256="b" * 64, exact_hash="e" * 64)
    assert loaded is None
    assert any("target_sha256" in item for item in diagnostics)


def test_checkpoint_rejects_state_drift(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    save_checkpoint(
        path,
        make_checkpoint(
            target_sha256="a" * 64,
            fixture_digest=None,
            exact_hash="e" * 64,
            payload={},
        ),
    )
    loaded, diagnostics = load_checkpoint(path, target_sha256="a" * 64, exact_hash="f" * 64)
    assert loaded is None
    assert any("fingerprint" in item for item in diagnostics)


def test_fingerprint_drift_attribution_names_single_surfaces() -> None:
    expected = {"variables": "v1", "combat": "c1", "dom": "d1", "prng": "p1"}
    actual = {"variables": "v1", "combat": "c2", "dom": "d1", "prng": "p1"}
    result = diagnose_fingerprint_drift(expected, actual)
    assert result["classification"] == "combat_side_effect"
    assert result["changed_components"] == ["combat"]
    assert result["component_hypotheses"] == ["combat side effect during rerender or restore"]


def test_fingerprint_drift_attribution_distinguishes_sequences_and_mixed_drift() -> None:
    sequence = diagnose_fingerprint_drift(
        {"history": "h1", "prng": "p1"},
        {"history": "h2", "prng": "p2"},
    )
    assert sequence["classification"] == "history_prng_sequence"

    mixed = diagnose_fingerprint_drift(
        {"variables": "v1", "combat": "c1"},
        {"variables": "v2", "combat": "c1", "mod_registry": "m1"},
    )
    assert mixed["classification"] == "mixed_state_drift"
    assert set(mixed["changed_components"]) == {"mod_registry", "variables"}


def test_fingerprint_drift_attribution_reports_no_component_change() -> None:
    result = diagnose_fingerprint_drift({"variables": "v1"}, {"variables": "v1"})
    assert result["classification"] == "no_component_change"
    assert result["changed_components"] == []
