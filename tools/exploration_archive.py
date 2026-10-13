"""Local failure evidence archives for the DOL-X gameplay explorer."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA = "dolx.exploration-failure.v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exception_parts(failure: Mapping[str, Any]) -> tuple[str, str]:
    detail = str(failure.get("detail") or "")
    action = failure.get("action") if isinstance(failure.get("action"), Mapping) else {}
    result = action.get("action_result") if isinstance(action.get("action_result"), Mapping) else {}
    error = str(result.get("error") or detail)
    if ":" in error:
        name, message = error.split(":", 1)
        return name.strip(), message.strip()
    return str(failure.get("verdict") or ""), error


def _state_summary(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """Public-safe fingerprint summary; never embeds the full game state."""
    if not isinstance(snapshot, Mapping):
        return {"present": False}
    variables = snapshot.get("variables")
    fingerprint = snapshot.get("fingerprint") or {}
    return {
        "present": True,
        "passage": snapshot.get("passage"),
        "variable_keys": len(variables) if isinstance(variables, Mapping) else 0,
        "exact_hash": fingerprint.get("exact_hash"),
        "coarse_hash": fingerprint.get("coarse_hash"),
        "sha256": digest(snapshot),
    }


def state_diff_digest(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> str:
    return digest({"before": _state_summary(before), "after": _state_summary(after)})


def failure_signature(
    *,
    failure: Mapping[str, Any],
    manifest: Mapping[str, Any],
    evidence_track: str | None = None,
    seed: int | str | None = None,
    source_refs: Iterable[Mapping[str, Any]] | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> str:
    target = (manifest.get("target") or {}) if isinstance(manifest, Mapping) else {}
    action = failure.get("action") if isinstance(failure.get("action"), Mapping) else {}
    exception_name, exception_message = _exception_parts(failure)
    payload = {
        "target_sha256": target.get("package_sha256"),
        "game_version": target.get("game_version"),
        "target_tag": target.get("target_tag"),
        "source_commit": target.get("source_commit"),
        "mods_lock_sha256": manifest.get("mods_lock_sha256"),
        "source_index_sha256": manifest.get("source_index_sha256"),
        "runner_revision": manifest.get("runner_revision"),
        "evidence_track": evidence_track or failure.get("evidence_track") or "unknown",
        "seed": seed,
        "failure_kind": failure.get("verdict") or "unknown",
        "passage": before.get("passage") if isinstance(before, Mapping) else None,
        "action_id": action.get("semantic_id"),
        "exception_name": exception_name,
        "exception_message": exception_message,
        "source_refs": [dict(item) for item in (source_refs or [])],
        "state_diff_digest": state_diff_digest(before, after),
    }
    return digest(payload)


def plan_failure_archive(
    *,
    failure: Mapping[str, Any],
    manifest: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]] | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    minimized_trace: Mapping[str, Any] | None = None,
    screenshots: Iterable[str | Path] | None = None,
    source_refs: Iterable[Mapping[str, Any]] | None = None,
    evidence_track: str | None = None,
    seed: int | str | None = None,
) -> dict[str, Any]:
    observations = [dict(item) for item in (observations or [])]
    page_errors = [
        item for item in observations if str(item.get("kind") or "").startswith("pageerror")
    ]
    network_failures = [
        item for item in observations if str(item.get("kind") or "").startswith("requestfailed")
    ]
    console_lines = [
        f"{item.get('kind')}:{item.get('message')}"
        for item in observations
        if str(item.get("kind") or "").startswith("console")
    ]
    original_trace = list((failure.get("trace") or {}).get("actions") or [])
    minimized_actions = list((minimized_trace or {}).get("actions") or [])
    signature = failure_signature(
        failure=failure,
        manifest=manifest,
        evidence_track=evidence_track,
        seed=seed,
        source_refs=source_refs,
        before=before,
        after=after,
    )
    screenshot_rows = [
        {"path": Path(item).name, "sha256": digest(Path(item).name)}
        for item in (screenshots or [])
    ]
    return {
        "schema": SCHEMA,
        "directory": f"failure-{signature[:12]}",
        "signature": signature,
        "files": {
            "failure.json": {"schema": SCHEMA, "failure": dict(failure), "signature": signature},
            "original-trace.jsonl": original_trace,
            "minimized-trace.jsonl": minimized_actions,
            "state-before.json": dict(before or {}),
            "state-after.json": dict(after or {}),
            "console.log": console_lines,
            "page-errors.json": page_errors,
            "network-failures.json": network_failures,
            "screenshots.json": screenshot_rows,
        },
        "private_files": sorted(
            name
            for name, value in (("state-before.json", before), ("state-after.json", after))
            if value
        ),
    }


def _atomic_write(path: Path, raw: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_failure_archive(
    out_dir: Path,
    archive: Mapping[str, Any],
    *,
    overwrite: bool = False,
) -> Path:
    root = Path(out_dir) / str(archive["directory"])
    if root.exists() and not overwrite:
        return root
    for name, value in archive["files"].items():
        path = root / name
        if name.endswith(".jsonl"):
            raw = "".join(canonical_json(item) + "\n" for item in value)
        elif name.endswith(".json"):
            raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        else:
            raw = "".join(f"{item}\n" for item in value)
        _atomic_write(path, raw)
    return root


def public_failure_summary(archive: Mapping[str, Any]) -> dict[str, Any]:
    files = archive.get("files") or {}
    failure = files.get("failure.json") or {}
    inner = failure.get("failure") or {}
    action = inner.get("action") if isinstance(inner.get("action"), Mapping) else {}
    return {
        "schema": "dolx.exploration-failure-summary.v1",
        "directory": archive.get("directory"),
        "signature": archive.get("signature"),
        "failure_kind": inner.get("verdict"),
        "detail": inner.get("detail"),
        "evidence_track": inner.get("evidence_track"),
        "action": {"semantic_id": action.get("semantic_id"), "kind": action.get("kind")},
        "trace": {
            "original_actions": len(files.get("original-trace.jsonl") or []),
            "minimized_actions": len(files.get("minimized-trace.jsonl") or []),
            "minimized_available": bool(files.get("minimized-trace.jsonl")),
        },
        "state": {
            "before": _state_summary(files.get("state-before.json") or None),
            "after": _state_summary(files.get("state-after.json") or None),
        },
        "observations": {
            "console": len(files.get("console.log") or []),
            "page_errors": len(files.get("page-errors.json") or []),
            "network_failures": len(files.get("network-failures.json") or []),
            "screenshots": len(files.get("screenshots.json") or []),
        },
        "completion_claim": "none",
    }
