"""Reliable ledger helpers for long-running DOL-X sweep jobs.

The ledger is deliberately independent from Playwright and the individual
sweep tools.  It only deals with identities, planned keys, atomic checkpoint
writes, and completeness checks so combat/env/passage shards can share the same
fail-closed contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

TOOL = "dol-x-sweep-ledger"
SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    """Return a deterministic JSON representation for hashing and comparison."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def plan_digest(keys: Sequence[str], strategy: dict[str, Any] | None = None) -> str:
    """Hash the ordered execution plan and its configuration."""
    return sha256_text(canonical_json({"keys": [str(key) for key in keys], "strategy": strategy or {}}))


def run_identity(
    kind: str,
    *,
    html_sha256: str,
    fixture_digest: str,
    tool_version: str,
    plan_digest: str,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the identity shared by every shard of one logical sweep."""
    return {
        "tool": TOOL,
        "schema_version": SCHEMA_VERSION,
        "kind": str(kind),
        "html_sha256": str(html_sha256),
        "fixture_digest": str(fixture_digest),
        "tool_version": str(tool_version),
        "plan_digest": str(plan_digest),
        "strategy": strategy or {},
    }


def _identity_field_diagnostics(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    diagnostics: list[str] = []
    for field in (
        "tool",
        "schema_version",
        "kind",
        "html_sha256",
        "fixture_digest",
        "tool_version",
        "plan_digest",
    ):
        if expected.get(field) != actual.get(field):
            diagnostics.append(
                f"{field}: expected {expected.get(field)!r}, got {actual.get(field)!r}"
            )
    if canonical_json(expected.get("strategy")) != canonical_json(actual.get("strategy")):
        diagnostics.append("strategy: does not match")
    return diagnostics


def identity_matches(
    expected: dict[str, Any], actual: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Fail-closed identity comparison with human-readable diagnostics."""
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False, ["identity: expected and actual must both be JSON objects"]
    diagnostics = _identity_field_diagnostics(expected, actual)
    return not diagnostics, diagnostics


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON through a same-directory temp file and ``os.replace``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    temp_path: Path | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(temp_path, path)
        temp_path = None
        # Read back before returning so callers never trust a partial rename.
        json.loads(path.read_text(encoding="utf-8"))
    finally:
        if handle is not None:
            handle.close()
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _empty_ledger(status: str = "missing") -> dict[str, Any]:
    return {
        "status": status,
        "identity": None,
        "plan_digest": None,
        "planned_keys": [],
        "results": [],
        "completed": [],
        "diagnostics": [],
        "updated_at": None,
    }


def load_ledger(path: Path) -> dict[str, Any]:
    """Load a checkpoint.  A missing or damaged file never raises."""
    path = Path(path)
    if not path.exists():
        return _empty_ledger("missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("ledger root is not an object")
        ledger = _empty_ledger("loaded")
        ledger.update(payload)
        if not isinstance(ledger.get("results"), list):
            raise ValueError("ledger.results is not a list")
        if not isinstance(ledger.get("planned_keys"), list):
            raise ValueError("ledger.planned_keys is not a list")
        return ledger
    except Exception as exc:  # noqa: BLE001 - damaged resume data must not kill a run
        ledger = _empty_ledger("corrupt")
        ledger["diagnostics"] = [f"checkpoint unreadable: {type(exc).__name__}: {exc}"]
        return ledger


def _result_key(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    value = result.get("key")
    if value is not None and str(value):
        return str(value)
    name = result.get("name")
    if name is None or not str(name):
        section = result.get("section")
        index = result.get("index")
        if section is not None and index is not None:
            return f"{section}#{index}"
        return None
    context = result.get("context")
    if context is not None and str(context):
        return f"{context}#{name}"
    return str(name)


def validate_resume(
    expected_identity: dict[str, Any],
    expected_plan_digest: str,
    expected_keys: Sequence[str],
    ledger: dict[str, Any],
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Return resumable results, refusing mismatched or incomplete checkpoints.

    A legacy checkpoint containing only ``completed`` keys is treated as
    unusable because those keys have no result payload that can be audited.
    """
    diagnostics: list[str] = []
    if not isinstance(ledger, dict):
        return False, ["checkpoint: root is not an object"], []
    status = str(ledger.get("status") or "")
    if status in {"missing", "corrupt"}:
        diagnostics.extend(str(item) for item in ledger.get("diagnostics") or [])
        if not diagnostics:
            diagnostics.append(f"checkpoint: {status}")
        return False, diagnostics, []

    identity = ledger.get("identity")
    if not isinstance(identity, dict):
        return False, ["checkpoint: identity is missing"], []
    identity_ok, identity_diagnostics = identity_matches(expected_identity, identity)
    diagnostics.extend(identity_diagnostics)
    if ledger.get("plan_digest") != expected_plan_digest:
        diagnostics.append(
            f"plan_digest: expected {expected_plan_digest!r}, got {ledger.get('plan_digest')!r}"
        )
    if diagnostics:
        return False, diagnostics, []

    expected = {str(key) for key in expected_keys}
    seen: dict[str, str] = {}
    results: list[dict[str, Any]] = []
    for raw in ledger.get("results") or []:
        key = _result_key(raw)
        if key is None:
            diagnostics.append("result without key")
            continue
        if key not in expected:
            diagnostics.append(f"result key not in plan: {key}")
            continue
        digest = sha256_text(canonical_json(raw))
        if key in seen:
            if seen[key] != digest:
                diagnostics.append(f"duplicate result differs: {key}")
            continue
        seen[key] = digest
        results.append(raw)

    if diagnostics:
        return False, diagnostics, []
    if not results:
        completed = ledger.get("completed") or []
        if completed:
            return False, ["legacy checkpoint has completed keys but no result payloads"], []
        return False, ["checkpoint has no usable results"], []
    return True, [], results


def merge_result(
    ledger: dict[str, Any],
    expected_keys: Sequence[str],
    result: dict[str, Any],
    *,
    key_field: str = "key",
) -> bool:
    """Merge one result by key and recompute ``completed`` from actual results."""
    key = result.get(key_field) if isinstance(result, dict) else None
    key_text = str(key) if key is not None and str(key) else None
    expected = [str(item) for item in expected_keys]
    if key_text is None or key_text not in set(expected):
        ledger["ignored_results"] = int(ledger.get("ignored_results") or 0) + 1
        return False

    by_key: dict[str, dict[str, Any]] = {}
    for raw in ledger.get("results") or []:
        raw_key = _result_key(raw)
        if raw_key is not None:
            by_key[raw_key] = raw
    by_key[key_text] = result
    ledger["results"] = [by_key[k] for k in expected if k in by_key]
    ledger["completed"] = list(ledger["results"][i].get("key") for i in range(len(ledger["results"])))
    ledger["status"] = "running"
    return True


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    payload = dict(ledger)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    atomic_write_json(Path(path), payload)


def validate_complete(
    expected_keys: Iterable[str],
    results: Sequence[dict[str, Any]],
    *,
    allow_missing: bool = False,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate the exact key set and duplicate-free claim of a finished run."""
    expected = [str(key) for key in expected_keys]
    expected_set = set(expected)
    seen: set[str] = set()
    duplicates: list[str] = []
    extra: list[str] = []
    for raw in results:
        key = _result_key(raw)
        if key is None:
            extra.append("<missing-key>")
            continue
        if key not in expected_set:
            extra.append(key)
            continue
        if key in seen:
            duplicates.append(key)
            continue
        seen.add(key)
    missing = [key for key in expected if key not in seen]
    diagnostics: list[str] = []
    if missing and not allow_missing:
        diagnostics.append(f"missing results: {len(missing)}")
    if duplicates:
        diagnostics.append(f"duplicate results: {len(duplicates)}")
    if extra:
        diagnostics.append(f"results outside plan: {len(extra)}")
    if diagnostics:
        summary_status = "incomplete"
    elif missing:
        summary_status = "incomplete_allowed"
    else:
        summary_status = "complete"
    summary = {
        "expected": len(expected),
        "completed": len(seen),
        "missing": len(missing),
        "duplicates": len(duplicates),
        "extra": len(extra),
        "status": summary_status,
    }
    return not diagnostics, diagnostics, summary


__all__ = [
    "SCHEMA_VERSION",
    "TOOL",
    "atomic_write_json",
    "canonical_json",
    "identity_matches",
    "load_ledger",
    "merge_result",
    "plan_digest",
    "run_identity",
    "save_ledger",
    "sha256_text",
    "validate_complete",
    "validate_resume",
]
