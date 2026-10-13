"""Pure tests for the gameplay explorer state/fingerprint layer."""

from __future__ import annotations

from tools.state_fingerprint import (
    build_fingerprint,
    canonical_json,
    canonical_json_exact,
    canonicalize,
    make_checkpoint_metadata,
    validate_checkpoint_metadata,
)


def test_canonical_json_is_order_stable_and_drops_volatile_fields() -> None:
    first = {"b": 2, "a": 1, "timestamp": 10}
    second = {"timestamp": 99, "a": 1, "b": 2}
    assert canonical_json(first) == canonical_json(second)


def test_exact_fingerprint_keeps_stateful_and_volatile_values() -> None:
    first = {
        "a": 1,
        "timestamp": 10,
        "index": 2,
        "random": "sequence",
        "password": "secret",
    }
    second = {
        "a": 1,
        "timestamp": 11,
        "index": 3,
        "random": "different",
        "password": "another",
    }

    assert canonical_json_exact(first) != canonical_json_exact(second)

    before = build_fingerprint({"passage": "Start", "variables": first})
    after = build_fingerprint({"passage": "Start", "variables": second})
    assert before["exact_hash"] != after["exact_hash"]
    assert before["components"]["variables"] != after["components"]["variables"]


def test_canonicalize_redacts_sensitive_values_and_paths() -> None:
    value = {"password": "secret", "path": "C:\\Users\\L\\save", "name": "Avery"}
    result = canonicalize(value)
    assert result["password"] == "<redacted>"
    assert result["path"] == "<redacted-path>"
    assert result["name"] == "Avery"


def test_fingerprint_has_coarse_and_exact_components() -> None:
    snapshot = {
        "passage": "Bedroom",
        "location": "orphanage",
        "day": 3,
        "time_bucket": "morning",
        "variables": {"money": 10, "timestamp": 1},
        "interactive": [{"role": "link", "text": "Sleep", "semantic_id": "sleep"}],
        "mods": ["maplebirch"],
        "prng": {"seed": 4},
    }
    result = build_fingerprint(snapshot)
    assert result["coarse"]["passage"] == "Bedroom"
    assert len(result["coarse_hash"]) == 64
    assert len(result["exact_hash"]) == 64
    assert result["components"]["variables"]


def test_dom_fingerprint_includes_overlay_and_pointer_state() -> None:
    before = build_fingerprint(
        {
            "passage": "Bedroom",
            "interactive": [{"role": "link", "text": "Sleep", "semantic_id": "sleep"}],
        }
    )
    after = build_fingerprint(
        {
            "passage": "Bedroom",
            "interactive": [
                {
                    "role": "link",
                    "text": "Sleep",
                    "semantic_id": "sleep",
                    "scope": "passage",
                    "overlay": True,
                    "pointer_blocked": True,
                    "id": "new-dialogue",
                    "name": "talk",
                    "href": "#new-dialogue",
                }
            ],
        }
    )

    assert before["coarse"]["overlay"] is False
    assert after["coarse"]["overlay"] is True
    assert before["exact_hash"] != after["exact_hash"]


def test_checkpoint_metadata_requires_matching_target_fixture_and_state() -> None:
    fingerprint = {"exact_hash": "e" * 64}
    checkpoint = make_checkpoint_metadata(
        target_sha256="a" * 64,
        fixture_digest="b" * 64,
        fingerprint=fingerprint,
    )
    ok, diagnostics = validate_checkpoint_metadata(
        checkpoint,
        target_sha256="a" * 64,
        fixture_digest="b" * 64,
        fingerprint=fingerprint,
    )
    assert ok is True
    assert diagnostics == []

    ok, diagnostics = validate_checkpoint_metadata(
        checkpoint,
        target_sha256="c" * 64,
        fixture_digest="b" * 64,
        fingerprint=fingerprint,
    )
    assert ok is False
    assert any("target_sha256" in item for item in diagnostics)


def test_checkpoint_track_is_explicit() -> None:
    checkpoint = make_checkpoint_metadata(
        target_sha256="a" * 64,
        fixture_digest=None,
        fingerprint="e" * 64,
        evidence_track="natural_prefix",
    )
    assert checkpoint["continuation"] == "checkpoint_restore"
    assert checkpoint["evidence_track"] == "natural_prefix"
