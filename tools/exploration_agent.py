"""Natural-track DOL-X gameplay explorer."""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):  # allow ``python tools/exploration_agent.py``
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.action_model import choose_actions
from tools.checkpoint_store import (
    diagnose_fingerprint_drift,
    load_checkpoint,
    make_checkpoint,
    save_checkpoint,
)
from tools.exploration_archive import plan_failure_archive, write_failure_archive
from tools.exploration_oracle import classify_node
from tools.exploration_replay import replay_reproduces, replay_semantic_trace
from tools.exploration_shrink import shrink_trace
from tools.exploration_runtime import (
    RuntimeSession,
    perform_action,
    reveal_page_actions,
    restore_runtime_state,
    restore_checkpoint_payload,
    snapshot_runtime,
)
from tools.exploration_trace import SemanticTrace
from tools.sweep_ledger import atomic_write_json
from tools.target_manifest import build_manifest, validate_manifest


SCHEMA = "dolx.exploration.v1"
RUNNER_VERSION = "dol-x-exploration-agent-v1"


def _failure_record(
    *,
    step: int,
    verdict: str,
    detail: str,
    before,
    after,
    action: Mapping[str, Any] | None,
    trace: SemanticTrace,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "step": step,
        "verdict": verdict,
        "detail": detail,
        "evidence_track": "natural",
        "action": dict(action) if action else None,
        "fingerprint_before": before.fingerprint,
        "fingerprint_after": after.fingerprint,
        "trace": trace.to_json(),
        "observations": after.observations,
    }


def _archive_failure(
    *,
    out_dir: Path,
    target: Path | None,
    failure: Mapping[str, Any],
    manifest: Mapping[str, Any],
    seed: int,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    shrink_failures: bool = False,
    headless: bool = True,
) -> None:
    minimized_trace: Mapping[str, Any] | None = None
    if shrink_failures and target is not None:
        try:
            def predicate(candidate: Mapping[str, Any]) -> bool:
                replay = replay_semantic_trace(target, candidate, headless=headless)
                return replay_reproduces(replay, failure)

            minimized_trace, _shrink_attempts = shrink_trace(failure.get("trace") or {}, predicate)
        except Exception:
            # Shrink is additional evidence; it must never replace the original
            # failure report when replay/browser access is unavailable.
            minimized_trace = None
    archive = plan_failure_archive(
        failure=failure,
        manifest=manifest,
        seed=seed,
        before=before,
        after=after,
        minimized_trace=minimized_trace,
        observations=(after or before or {}).get("observations") or [],
    )
    try:
        write_failure_archive(out_dir, archive)
    except Exception:
        # Archiving must not prevent the primary report from recording the
        # failure; the report itself already contains the trace and verdict.
        pass


def explore(
    target: Path,
    out_dir: Path,
    *,
    max_steps: int = 120,
    seed: int = 1719,
    novelty_window: int = 30,
    checkpoint_every: int = 20,
    headless: bool = True,
    expected_version: str | None = None,
    mods_lock: Path | None = None,
    build_toml: Path | None = None,
    source_commit: str | None = None,
    source_index: Path | None = None,
    tag: str | None = None,
    restore_checkpoint: Path | None = None,
    shrink_failures: bool = False,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        target,
        expected_version=expected_version,
        mods_lock=mods_lock,
        build_toml=build_toml,
        source_commit=source_commit,
        source_index=source_index,
        runner_revision=RUNNER_VERSION,
        tag=tag,
    )
    atomic_write_json(out_dir / "target-manifest.json", manifest)
    identity_ok, identity_diagnostics = validate_manifest(manifest)
    if not identity_ok:
        report = {
            "schema": SCHEMA,
            "runner": RUNNER_VERSION,
            "status": "infrastructure_fail",
            "target_manifest": manifest,
            "diagnostics": identity_diagnostics,
            "actions": [],
            "failures": [],
        }
        atomic_write_json(out_dir / "exploration-report.json", report)
        return report

    actions: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    seen_coarse: set[str] = set()
    attempted_action_keys: set[str] = set()
    frontier_digests: list[str] = []
    trace = SemanticTrace.from_actions([])
    stop_reason = "budget_exhausted"
    status = "complete"

    def checkpoint_failure_report(
        detail: str,
        diagnostics: list[str],
        *,
        drift_attribution: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = {
            "schema": SCHEMA,
            "runner": RUNNER_VERSION,
            "status": "infrastructure_fail",
            "stop_reason": "checkpoint_restore_failed",
            "evidence_track": "natural_prefix",
            "continuation": "checkpoint_restore",
            "seed": seed,
            "target_manifest": manifest,
            "restore": {
                "checkpoint": str(restore_checkpoint or ""),
                "diagnostics": diagnostics,
                **({"drift_attribution": drift_attribution} if drift_attribution else {}),
            },
            "bootstrap": {"ok": False, "mode": "checkpoint_restore", "detail": detail},
            "steps": 0,
            "unique_coarse_states": 0,
            "checkpoints": [],
            "actions": [],
            "failures": [
                {
                    "step": 0,
                    "verdict": "infrastructure_fail",
                    "detail": detail,
                }
            ],
            "final": {"passage": None, "exact_hash": None, "coarse_hash": None},
            "rng": {"seed": seed, "serializable_state": None, "probabilistic_replay": True},
        }
        atomic_write_json(out_dir / "exploration-report.json", report)
        return report

    with RuntimeSession(target, headless=headless) as session:
        page = session.page
        if restore_checkpoint is not None:
            try:
                raw_checkpoint = json.loads(Path(restore_checkpoint).read_text(encoding="utf-8"))
                saved_fingerprint = str((raw_checkpoint.get("metadata") or {}).get("fingerprint") or "")
            except Exception as exc:
                return checkpoint_failure_report(
                    f"checkpoint metadata unreadable: {type(exc).__name__}: {exc}",
                    ["checkpoint metadata unreadable"],
                )
            checkpoint, diagnostics = load_checkpoint(
                restore_checkpoint,
                target_sha256=str(manifest["target"]["package_sha256"]),
                fixture_digest=None,
                exact_hash=saved_fingerprint,
            )
            if checkpoint is None:
                return checkpoint_failure_report("checkpoint identity validation failed", diagnostics)
            try:
                overlay_dismissal = session.bootstrap_natural(max_steps=300, deadline_s=240)
                if not overlay_dismissal.get("ok"):
                    return checkpoint_failure_report(
                        "startup overlay dismissal failed before checkpoint restore",
                        [{"overlay_dismissal": overlay_dismissal}],
                    )
                restore_checkpoint_payload(page, checkpoint.payload)
                session.wait_for_mods_stable(timeout_s=30)
                reveal_page_actions(page)
                snapshot = snapshot_runtime(page, session.new_observations())
            except Exception as exc:
                return checkpoint_failure_report(
                    f"checkpoint restore failed: {type(exc).__name__}: {exc}",
                    diagnostics,
                )
            restored_hash = str(snapshot.fingerprint["exact_hash"])
            if restored_hash != saved_fingerprint:
                saved_components = (checkpoint.payload.get("fingerprint") or {}).get("components") or {}
                actual_components = snapshot.fingerprint.get("components") or {}
                drift_attribution = diagnose_fingerprint_drift(saved_components, actual_components)
                component_diagnostics = [
                    f"changed_component={key}: expected={saved_components.get(key)} actual={actual_components.get(key)}"
                    for key in drift_attribution["changed_components"]
                ]
                return checkpoint_failure_report(
                    "checkpoint exact fingerprint mismatch after restore",
                    [
                        f"expected={saved_fingerprint}",
                        f"actual={restored_hash}",
                        *component_diagnostics,
                    ],
                    drift_attribution=drift_attribution,
                )
            boot = {
                "ok": True,
                "mode": "checkpoint_restore",
                "checkpoint": str(restore_checkpoint),
                "passage": snapshot.fingerprint["coarse"]["passage"],
                "fingerprint": restored_hash,
                "overlay_dismissal": overlay_dismissal,
            }
        else:
            boot = session.bootstrap_natural(max_steps=300, deadline_s=240)
            if not boot.get("ok"):
                report = {
                    "schema": SCHEMA,
                    "runner": RUNNER_VERSION,
                    "status": "failed",
                    "stop_reason": "bootstrap_failed",
                    "evidence_track": "natural",
                    "seed": seed,
                    "target_manifest": manifest,
                    "bootstrap": boot,
                    "steps": 0,
                    "unique_coarse_states": 0,
                    "checkpoints": [],
                    "actions": [],
                    "failures": [
                        {
                            "step": 0,
                            "verdict": "infrastructure_fail",
                            "detail": f"natural bootstrap did not reach gameplay: {boot.get('passage')!r}",
                        }
                    ],
                    "final": {
                        "passage": boot.get("passage"),
                        "exact_hash": None,
                        "coarse_hash": None,
                    },
                    "rng": {"seed": seed, "serializable_state": None, "probabilistic_replay": True},
                }
                atomic_write_json(out_dir / "exploration-report.json", report)
                return report

        snapshot = snapshot_runtime(page, session.new_observations())
        seen_coarse.add(str(snapshot.fingerprint["coarse_hash"]))
        frontier_digests.append(str(snapshot.fingerprint["coarse_hash"]))
        last_checkpoint = snapshot.marshal_for_save
        last_checkpoint_hash = str(snapshot.fingerprint["exact_hash"])

        for step in range(1, max_steps + 1):
            reveal_page_actions(page)
            snapshot = snapshot_runtime(page)
            snapshot_with_observations = {
                "finished": True,
                "observations": session.new_observations(),
                **snapshot.fingerprint,
            }
            verdict, detail, diagnostics = classify_node(snapshot_with_observations)
            action_result: dict[str, Any] | None = None
            selected_action: Mapping[str, Any] | None = None
            passage = str(snapshot.fingerprint["coarse"]["passage"])

            def action_key(action: Mapping[str, Any]) -> str:
                return f"{passage}\x1f{action.get('semantic_id') or ''}"
            if verdict != "ok":
                failures.append(
                    _failure_record(
                        step=step,
                        verdict=verdict,
                        detail=detail,
                        before=snapshot,
                        after=snapshot,
                        action=None,
                        trace=trace,
                    )
                )
                _archive_failure(
                    out_dir=out_dir,
                    target=target,
                    failure=failures[-1],
                    manifest=manifest,
                    seed=seed,
                    before=snapshot,
                    after=snapshot,
                    shrink_failures=shrink_failures,
                    headless=headless,
                )
                status = "failed"
                break

            fresh_actions = [
                action
                for action in snapshot.actions
                if action_key(action) not in attempted_action_keys
            ]
            action_pool = fresh_actions or snapshot.actions
            candidates = choose_actions(
                action_pool,
                seed=seed + step,
                uncovered_edges=[
                    action.get("semantic_id")
                    for action in action_pool
                    if action_key(action) not in attempted_action_keys
                ],
            )
            if not candidates:
                stop_reason = "frontier_exhausted"
                break
            selected_action = candidates[0]
            before = snapshot
            try:
                action_result = perform_action(page, selected_action)
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                page.wait_for_timeout(120)
                reveal_page_actions(page)
                after = snapshot_runtime(page)
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    _failure_record(
                        step=step,
                        verdict="hard_fail",
                        detail=f"{type(exc).__name__}: {exc}",
                        before=before,
                        after=before,
                        action=selected_action,
                        trace=trace,
                    )
                )
                _archive_failure(
                    out_dir=out_dir,
                    target=target,
                    failure=failures[-1],
                    manifest=manifest,
                    seed=seed,
                    before=before,
                    after=before,
                    shrink_failures=shrink_failures,
                    headless=headless,
                )
                status = "failed"
                break

            after_snapshot = {
                "finished": True,
                "observations": session.new_observations(),
                **after.fingerprint,
            }
            verdict, detail, diagnostics = classify_node(after_snapshot)
            action_record = {
                "step": step,
                "kind": selected_action.get("kind"),
                "semantic_id": selected_action.get("semantic_id"),
                "role": selected_action.get("role"),
                "id": selected_action.get("id"),
                "name": selected_action.get("name"),
                "href": selected_action.get("href"),
                "value": selected_action.get("value"),
                "text": selected_action.get("text"),
                "text_hash": __import__("hashlib").sha256(
                    str(selected_action.get("text") or "").encode("utf-8")
                ).hexdigest(),
                "passage_before": before.fingerprint["coarse"]["passage"],
                "passage_after": after.fingerprint["coarse"]["passage"],
                "fingerprint_before": before.fingerprint["exact_hash"],
                "fingerprint_after": after.fingerprint["exact_hash"],
                "coarse_before": before.fingerprint["coarse_hash"],
                "coarse_after": after.fingerprint["coarse_hash"],
                "action_result": action_result,
                "verdict": verdict,
                "detail": detail,
                "elapsed_ms": action_result.get("elapsed_ms"),
            }
            actions.append(action_record)
            trace = SemanticTrace.from_actions(actions)
            attempted_action_keys.add(action_key(selected_action))

            if verdict != "ok":
                failures.append(
                    _failure_record(
                        step=step,
                        verdict=verdict,
                        detail=detail,
                        before=before,
                        after=after,
                        action=selected_action,
                        trace=trace,
                    )
                )
                _archive_failure(
                    out_dir=out_dir,
                    target=target,
                    failure=failures[-1],
                    manifest=manifest,
                    seed=seed,
                    before=before,
                    after=after,
                    shrink_failures=shrink_failures,
                    headless=headless,
                )
                status = "failed"
                try:
                    (out_dir / "screenshots").mkdir(exist_ok=True)
                    page.screenshot(path=str(out_dir / "screenshots" / f"step-{step:04d}.png"))
                except Exception:
                    pass
                break

            coarse_hash = str(after.fingerprint["coarse_hash"])
            if coarse_hash not in seen_coarse:
                seen_coarse.add(coarse_hash)
                frontier_digests.append(coarse_hash)
            else:
                frontier_digests.append(coarse_hash)
                if len(frontier_digests) > novelty_window:
                    del frontier_digests[:-novelty_window]
                if len(set(frontier_digests)) <= 2:
                    stop_reason = "no_novelty_window"
                    break

            if step % checkpoint_every == 0:
                checkpoint = make_checkpoint(
                    target_sha256=str(manifest["target"]["package_sha256"]),
                    fixture_digest=None,
                    exact_hash=str(after.fingerprint["exact_hash"]),
                    payload={
                        "marshalForSave": after.marshal_for_save,
                        "storage": after.storage,
                        "registry": after.registry,
                        "fingerprint": after.fingerprint,
                    },
                )
                path = out_dir / "checkpoints" / f"step-{step:04d}.json"
                save_checkpoint(path, checkpoint)
                checkpoints.append(
                    {
                        "path": str(path),
                        "step": step,
                        "exact_hash": after.fingerprint["exact_hash"],
                        "evidence_track": "natural_prefix",
                    }
                )
                last_checkpoint = after.marshal_for_save
                last_checkpoint_hash = str(after.fingerprint["exact_hash"])

        final_snapshot = snapshot_runtime(page, session.new_observations())
        report = {
            "schema": SCHEMA,
            "runner": RUNNER_VERSION,
            "status": status,
            "stop_reason": stop_reason,
            "evidence_track": "natural_prefix" if restore_checkpoint is not None else "natural",
            **({"continuation": "checkpoint_restore"} if restore_checkpoint is not None else {}),
            "seed": seed,
            "target_manifest": manifest,
            "bootstrap": boot,
            "steps": len(actions),
            "unique_coarse_states": len(seen_coarse),
            "checkpoints": checkpoints,
            "actions": actions,
            "failures": failures,
            "final": {
                "passage": final_snapshot.fingerprint["coarse"]["passage"],
                "exact_hash": final_snapshot.fingerprint["exact_hash"],
                "coarse_hash": final_snapshot.fingerprint["coarse_hash"],
            },
            "rng": {"seed": seed, "serializable_state": None, "probabilistic_replay": True},
        }
        atomic_write_json(out_dir / "exploration-report.json", report)
        (out_dir / "trace.jsonl").write_text(
            "\n".join(json.dumps(action, ensure_ascii=False) for action in actions) + ("\n" if actions else ""),
            encoding="utf-8",
        )
        return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--seed", type=int, default=1719)
    parser.add_argument("--novelty-window", type=int, default=30)
    parser.add_argument("--checkpoint-every", type=int, default=20)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--expect-version")
    parser.add_argument("--mods-lock", type=Path)
    parser.add_argument("--build-toml", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--tag")
    parser.add_argument("--restore-checkpoint", type=Path)
    parser.add_argument(
        "--shrink-failures",
        action="store_true",
        help="replay and minimize natural failures from a fresh Start",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = explore(
        args.target,
        args.out,
        max_steps=args.max_steps,
        seed=args.seed,
        novelty_window=args.novelty_window,
        checkpoint_every=args.checkpoint_every,
        headless=not args.headed,
        expected_version=args.expect_version,
        mods_lock=args.mods_lock,
        build_toml=args.build_toml,
        source_commit=args.source_commit,
        source_index=args.source_index,
        tag=args.tag,
        restore_checkpoint=args.restore_checkpoint,
        shrink_failures=args.shrink_failures,
    )
    print(json.dumps({"status": report["status"], "steps": report["steps"], "out": str(args.out)}))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
