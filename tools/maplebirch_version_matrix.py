#!/usr/bin/env python3
"""Enumerate and statically rank maplebirch framework release assets.

This helper is intentionally canary-only. It downloads candidate maplebirch
assets into an isolated cache and inspects them offline before any browser
smoke or GitHub Actions build is considered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.utils import download_file
from tools.canary_payload_introspect import PayloadInspection, inspect_payload
from tools.cheat_extended_canary import (
    MAPLEBIRCH_IDB_PATCH_MEMBER,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL,
    MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED,
)


REPO = "MaplebirchLeaf/SCML-DOL-maplebirchFramework"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases"
DEFAULT_GAME_VERSION = "0.5.8.10"
BASELINE_TAG = "maplebirch-release-v3.2.5"
PRIORITY_RELEASES: tuple[str, ...] = (
    "maplebirch-release-v3.2.3",
    "maplebirch-release-v3.1.14",
    "maplebirch-release-v3.1.13",
    "maplebirch-release-v3.1.11",
    "maplebirch-release-v3.1.10",
)
HYBRID_TRIAGE_TAGS: tuple[str, ...] = (
    "maplebirch-release-v3.1.13",
    "maplebirch-release-v3.1.14",
    "maplebirch-release-v3.2.3",
)
STATIC_SCAN_KEYWORDS: tuple[str, ...] = (
    "maplebirchFrameworks",
    "CE_options",
    "SCMLSimpleFramework",
    "Simple Frameworks",
    "TimeEvent",
    "addto",
)
CANARY_BRANCH = "experiment/cheat-extended-maplebirch"
BUILD_WORKFLOW = "build.yaml"
COMPATIBILITY_WORKFLOW = "compatibility.yaml"
CANARY_BUILD_REPORT_ARTIFACT = "cheat-canary-build-reports"
CANARY_ZIP_ARTIFACT = "dol-builds-cheat-canary-zip"
CANARY_SMOKE_REPORT_ARTIFACT = "cheat-canary-browser-smoke-report"


@dataclass
class MaplebirchAssetCandidate:
    """One maplebirch release asset candidate."""

    tag: str
    release_name: str
    asset_name: str
    download_url: str
    size_bytes: int = 0
    digest: str | None = None
    game_version: str | None = None
    framework_version: str | None = None
    is_baseline: bool = False
    exact_game_match: bool = False
    compatibility_risk: str = "unknown"
    priority: int = 999
    notes: list[str] = field(default_factory=list)


@dataclass
class IDBPatchAssessment:
    """Static patchability summary for the maplebirch IndexedDB runtime."""

    member: str
    status: str = "not_scanned"
    has_original_needle: bool = False
    has_patched_needle: bool = False
    has_with_transaction: bool = False
    has_reset_database: bool = False
    has_check_store: bool = False
    has_settings_store: bool = False
    error: str | None = None


@dataclass
class CandidateScanResult:
    """Static inspection result for one downloaded candidate."""

    candidate: MaplebirchAssetCandidate
    cache_path: str
    sha256: str
    inspection: PayloadInspection
    likely_old_api_candidate: bool
    idb_patch: IDBPatchAssessment = field(
        default_factory=lambda: IDBPatchAssessment(member=MAPLEBIRCH_IDB_PATCH_MEMBER)
    )
    scan_notes: list[str] = field(default_factory=list)


@dataclass
class CandidateAssessment:
    """Ranked automated-triage decision for one static candidate."""

    tag: str
    asset_name: str
    score: int
    rank: int = 0
    recommendation: str = "do_not_smoke"
    patch_status: str = "not_scanned"
    idb_schema_status: str = "unknown"
    maplebirch_framework_status: str = "unknown"
    simple_framework_status: str = "unknown"
    ce_contract_status: str = "unknown"
    exact_game_match: bool = False
    stable_isolation: bool = True
    reasons: list[str] = field(default_factory=list)


@dataclass
class MaplebirchVersionMatrixReport:
    """Full report emitted by the matrix helper."""

    repo: str
    game_version: str
    baseline_tag: str
    max_smoke_candidates: int
    candidates: list[MaplebirchAssetCandidate]
    scans: list[CandidateScanResult] = field(default_factory=list)
    assessments: list[CandidateAssessment] = field(default_factory=list)
    selected_for_smoke: list[MaplebirchAssetCandidate] = field(default_factory=list)
    top_candidate: MaplebirchAssetCandidate | None = None
    fallback_candidate: MaplebirchAssetCandidate | None = None
    ci_handoff: list[str] = field(default_factory=list)
    manual_gates: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_releases(per_page: int = 30) -> list[dict[str, Any]]:
    """Fetch maplebirch releases from GitHub."""
    response = requests.get(
        RELEASES_API,
        headers=github_headers(),
        params={"per_page": per_page},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("GitHub releases response was not a list")
    return payload


def _parse_asset_versions(asset_name: str) -> tuple[str | None, str | None]:
    match = re.search(r"maplebirch-(?P<game>\d+\.\d+\.\d+\.\d+)-v(?P<framework>\d+\.\d+\.\d+)", asset_name)
    if not match:
        return None, None
    return match.group("game"), match.group("framework")


def _candidate_priority(tag: str, asset_name: str, game_version: str, is_baseline: bool) -> tuple[int, list[str]]:
    notes: list[str] = []
    asset_game, _ = _parse_asset_versions(asset_name)
    exact_game_match = asset_game == game_version
    suffix_rank = 0 if asset_name.endswith(".mod.zip") else 1 if asset_name.endswith(".modpack") else 2

    if is_baseline:
        notes.append("current baseline; keep for comparison only")
        return 900 + suffix_rank, notes

    if exact_game_match and tag == "maplebirch-release-v3.2.3":
        notes.append("highest-priority rollback before v3.2.5 simplification")
        return 0 + suffix_rank, notes

    if exact_game_match and tag in PRIORITY_RELEASES:
        notes.append("exact game-version rollback candidate")
        return 10 + PRIORITY_RELEASES.index(tag) * 5 + suffix_rank, notes

    if exact_game_match:
        notes.append("exact game-version candidate")
        return 100 + suffix_rank, notes

    if tag in PRIORITY_RELEASES:
        notes.append("older API candidate, but game-version mismatch")
        return 200 + PRIORITY_RELEASES.index(tag) * 5 + suffix_rank, notes

    notes.append("low-priority candidate")
    return 500 + suffix_rank, notes


def candidates_from_releases(
    releases: list[dict[str, Any]],
    game_version: str = DEFAULT_GAME_VERSION,
    baseline_tag: str = BASELINE_TAG,
) -> list[MaplebirchAssetCandidate]:
    """Extract and rank maplebirch release assets."""
    candidates: list[MaplebirchAssetCandidate] = []
    seen_urls: set[str] = set()

    for release in releases:
        tag = str(release.get("tag_name") or "")
        release_name = str(release.get("name") or tag)
        for asset in release.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            asset_name = str(asset.get("name") or "")
            if not asset_name.startswith("maplebirch-"):
                continue
            if not (asset_name.endswith(".mod.zip") or asset_name.endswith(".modpack")):
                continue
            download_url = str(asset.get("browser_download_url") or "")
            if not download_url or download_url in seen_urls:
                continue
            seen_urls.add(download_url)

            asset_game, framework_version = _parse_asset_versions(asset_name)
            is_baseline = tag == baseline_tag
            priority, notes = _candidate_priority(tag, asset_name, game_version, is_baseline)
            exact_game_match = asset_game == game_version
            compatibility_risk = "low" if exact_game_match else "high"
            if is_baseline:
                compatibility_risk = "baseline"

            candidates.append(
                MaplebirchAssetCandidate(
                    tag=tag,
                    release_name=release_name,
                    asset_name=asset_name,
                    download_url=download_url,
                    size_bytes=int(asset.get("size") or 0),
                    digest=asset.get("digest") if isinstance(asset.get("digest"), str) else None,
                    game_version=asset_game,
                    framework_version=framework_version,
                    is_baseline=is_baseline,
                    exact_game_match=exact_game_match,
                    compatibility_risk=compatibility_risk,
                    priority=priority,
                    notes=notes,
                )
            )

    return sorted(candidates, key=lambda item: (item.priority, item.tag, item.asset_name))


def _candidate_cache_path(cache_dir: Path, candidate: MaplebirchAssetCandidate) -> Path:
    safe_tag = re.sub(r"[^A-Za-z0-9_.-]+", "-", candidate.tag)
    return cache_dir / safe_tag / candidate.asset_name


def _download_candidate(candidate: MaplebirchAssetCandidate, cache_dir: Path) -> Path:
    dest_path = _candidate_cache_path(cache_dir, candidate)
    if not dest_path.exists() or dest_path.stat().st_size == 0:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        download_file(candidate.download_url, dest_path, quiet=True)
    return dest_path


def _has_static_framework_evidence(keyword_hits: dict[str, int]) -> bool:
    return any(keyword_hits.get(keyword, 0) > 0 for keyword in STATIC_SCAN_KEYWORDS)


def filter_candidates_by_tags(
    candidates: list[MaplebirchAssetCandidate], tags: Iterable[str] | None
) -> list[MaplebirchAssetCandidate]:
    """Keep the release matrix focused on an explicit candidate tag set."""
    if not tags:
        return candidates
    allowed = set(tags)
    return [candidate for candidate in candidates if candidate.tag in allowed]


def assess_idb_patch(payload_path: Path) -> IDBPatchAssessment:
    """Determine whether the existing canary IndexedDB patch can apply to a payload."""
    assessment = IDBPatchAssessment(member=MAPLEBIRCH_IDB_PATCH_MEMBER)
    try:
        with zipfile.ZipFile(payload_path) as payload_zip:
            try:
                raw_member = payload_zip.read(MAPLEBIRCH_IDB_PATCH_MEMBER)
            except KeyError:
                assessment.status = "missing_member"
                assessment.error = f"{MAPLEBIRCH_IDB_PATCH_MEMBER} not found"
                return assessment
    except zipfile.BadZipFile as exc:
        assessment.status = "not_zip"
        assessment.error = str(exc)
        return assessment
    except OSError as exc:
        assessment.status = "read_error"
        assessment.error = str(exc)
        return assessment

    runtime = raw_member.decode("utf-8", errors="replace")
    assessment.has_original_needle = MAPLEBIRCH_IDB_WITH_TRANSACTION_ORIGINAL in runtime
    assessment.has_patched_needle = MAPLEBIRCH_IDB_WITH_TRANSACTION_PATCHED in runtime
    assessment.has_with_transaction = "withTransaction" in runtime
    assessment.has_reset_database = "resetDatabase" in runtime
    assessment.has_check_store = "checkStore" in runtime or "objectStoreNames.contains" in runtime
    assessment.has_settings_store = any(marker in runtime for marker in ('"settings"', "'settings'", "`settings`"))

    if assessment.has_patched_needle:
        assessment.status = "already_patched"
    elif assessment.has_original_needle:
        assessment.status = "patchable"
    elif assessment.has_with_transaction:
        assessment.status = "needle_not_found"
        assessment.error = "withTransaction exists, but the known canary patch needle did not match"
    else:
        assessment.status = "runtime_not_found"
        assessment.error = "withTransaction runtime was not found in the expected member"
    return assessment


def _candidate_key(candidate: MaplebirchAssetCandidate) -> tuple[str, str]:
    return candidate.tag, candidate.asset_name


def _candidate_lookup(scans: list[CandidateScanResult]) -> dict[tuple[str, str], MaplebirchAssetCandidate]:
    return {_candidate_key(scan.candidate): scan.candidate for scan in scans}


def assess_candidate(scan: CandidateScanResult) -> CandidateAssessment:
    """Score one static scan for the automation-first canary triage gate."""
    candidate = scan.candidate
    keyword_hits = scan.inspection.keyword_hits
    reasons: list[str] = []
    score = 0

    if candidate.is_baseline:
        score -= 100
        reasons.append("current baseline is comparison-only and must not be canary-smoked")
    if candidate.exact_game_match:
        score += 35
        reasons.append("asset game version exactly matches target")
    else:
        score -= 25
        reasons.append("asset game version differs from target")

    if candidate.tag in HYBRID_TRIAGE_TAGS:
        score += 10
        reasons.append("tag is in the hybrid canary triage set")
    if candidate.tag in PRIORITY_RELEASES:
        score += 10
        reasons.append("tag is a prioritized rollback candidate")

    if scan.likely_old_api_candidate:
        score += 25
        reasons.append("static scan exposed old framework/API evidence")
    else:
        score -= 35
        reasons.append("static scan did not expose enough old framework/API evidence")

    if scan.inspection.defines_maplebirch_frameworks:
        maplebirch_framework_status = "defines"
        score += 20
        reasons.append("payload defines maplebirchFrameworks")
    elif keyword_hits.get("maplebirchFrameworks", 0) > 0 or scan.inspection.references_maplebirch_frameworks:
        maplebirch_framework_status = "mentions"
        score += 15
        reasons.append("payload mentions maplebirchFrameworks")
    else:
        maplebirch_framework_status = "missing"
        score -= 20
        reasons.append("payload lacks maplebirchFrameworks evidence")

    if keyword_hits.get("SCMLSimpleFramework", 0) > 0 or keyword_hits.get("Simple Frameworks", 0) > 0:
        simple_framework_status = "present"
        score += 10
        reasons.append("payload mentions Simple Framework APIs")
    else:
        simple_framework_status = "missing"

    if keyword_hits.get("CE_options", 0) > 0 or scan.inspection.references_ce_options:
        ce_contract_status = "present"
        score += 5
        reasons.append("payload references the CE_options contract")
    else:
        ce_contract_status = "missing"

    patch_status = scan.idb_patch.status
    if patch_status == "patchable":
        idb_schema_status = "can_apply_existing_patch"
        score += 12
        reasons.append("known maplebirch IDB patch needle matches")
    elif patch_status == "already_patched":
        idb_schema_status = "already_patched"
        score += 8
        reasons.append("payload already contains the known maplebirch IDB patch")
    elif patch_status == "needle_not_found":
        idb_schema_status = "requires_manual_patch_review"
        score -= 15
        reasons.append("withTransaction exists but known IDB patch needle did not match")
    elif patch_status in {"missing_member", "runtime_not_found"}:
        idb_schema_status = "missing_runtime_evidence"
        score -= 20
        reasons.append("expected maplebirch IDB runtime evidence is missing")
    elif patch_status in {"not_zip", "read_error"}:
        idb_schema_status = "unreadable"
        score -= 15
        reasons.append("payload could not be read as a maplebirch zip for IDB assessment")
    else:
        idb_schema_status = "unknown"

    if scan.idb_patch.has_reset_database:
        score += 5
        reasons.append("runtime exposes resetDatabase for one-shot recovery")
    if scan.idb_patch.has_settings_store:
        score += 5
        reasons.append("runtime references the settings object store")
    if candidate.compatibility_risk == "high":
        score -= 20
        reasons.append("candidate is high compatibility risk")

    recommendation = "static_candidate" if score > 0 and scan.likely_old_api_candidate and not candidate.is_baseline else "do_not_smoke"
    return CandidateAssessment(
        tag=candidate.tag,
        asset_name=candidate.asset_name,
        score=score,
        recommendation=recommendation,
        patch_status=patch_status,
        idb_schema_status=idb_schema_status,
        maplebirch_framework_status=maplebirch_framework_status,
        simple_framework_status=simple_framework_status,
        ce_contract_status=ce_contract_status,
        exact_game_match=candidate.exact_game_match,
        stable_isolation=True,
        reasons=reasons,
    )


def assess_candidates(scans: list[CandidateScanResult]) -> list[CandidateAssessment]:
    """Rank static candidates and label top/fallback recommendations."""
    scan_order = {_candidate_key(scan.candidate): scan.candidate.priority for scan in scans}
    assessments = [assess_candidate(scan) for scan in scans]
    assessments.sort(key=lambda item: (-item.score, scan_order.get((item.tag, item.asset_name), 999), item.tag, item.asset_name))
    positive_rank = 0
    for index, assessment in enumerate(assessments, start=1):
        assessment.rank = index
        if assessment.recommendation == "do_not_smoke":
            continue
        positive_rank += 1
        if positive_rank == 1:
            assessment.recommendation = "top_candidate"
        elif positive_rank == 2:
            assessment.recommendation = "fallback_candidate"
        else:
            assessment.recommendation = "ranked_candidate"
    return assessments


def select_assessed_smoke_candidates(
    scans: list[CandidateScanResult], assessments: list[CandidateAssessment], max_count: int
) -> list[MaplebirchAssetCandidate]:
    """Select smoke candidates from ranked assessments while preserving the explicit budget."""
    if max_count <= 0:
        return []
    candidates_by_key = _candidate_lookup(scans)
    selected: list[MaplebirchAssetCandidate] = []
    for assessment in assessments:
        if assessment.recommendation == "do_not_smoke":
            continue
        candidate = candidates_by_key.get((assessment.tag, assessment.asset_name))
        if candidate is not None:
            selected.append(candidate)
        if len(selected) >= max_count:
            break
    return selected


def build_ci_handoff(
    top_candidate: MaplebirchAssetCandidate | None, fallback_candidate: MaplebirchAssetCandidate | None
) -> list[str]:
    """Describe the one-build/one-smoke handoff without triggering CI."""
    handoff = [
        f"Keep this canary isolated on `{CANARY_BRANCH}`; do not mutate stable/default combinations.",
        "Do not trigger Build or browser smoke until the static matrix report is reviewed.",
    ]
    if top_candidate is None:
        handoff.append("No top candidate selected; stop and return to runtime patching instead of switching versions.")
        return handoff

    handoff.extend(
        [
            f"Top candidate for the single Build/browser-smoke attempt: `{top_candidate.tag}` / `{top_candidate.asset_name}`.",
            "Before Build, ensure the canary-only maplebirch release tag, asset pattern, and cache label match the top candidate.",
            f"Run exactly one `{BUILD_WORKFLOW}` Build on `{CANARY_BRANCH}`, then download `{CANARY_BUILD_REPORT_ARTIFACT}` and `{CANARY_ZIP_ARTIFACT}`.",
            "Parse the build report and record commit SHA, run ID, artifact names, candidate tag, and patch status before smoke.",
            f"If Build succeeds, run exactly one `{COMPATIBILITY_WORKFLOW}` canary browser smoke for that Build run and download `{CANARY_SMOKE_REPORT_ARTIFACT}`.",
            "Parse browser smoke pageerrors, runtime globals, and passage readiness; do not rerun the same workflow/artifact as new evidence.",
        ]
    )
    if fallback_candidate is None:
        handoff.append("No fallback candidate selected; a runtime blocker should return to patching, not version roulette.")
    else:
        handoff.append(
            f"Fallback candidate `{fallback_candidate.tag}` / `{fallback_candidate.asset_name}` is only for CI/download/artifact failure, not runtime blocker failure."
        )
    return handoff


def build_manual_gates() -> list[str]:
    """List human-only gates that static automation must not cross."""
    return [
        "Manual canary play test of the downloaded ZIP is required before treating the candidate as playable.",
        "Merging canary work into stable/default requires human confirmation.",
        "Replacing stable build combinations or release artifacts requires human confirmation.",
        "Publishing or announcing a playable release requires human confirmation.",
    ]


def scan_candidates(candidates: list[MaplebirchAssetCandidate], cache_dir: Path) -> list[CandidateScanResult]:
    """Download and statically inspect candidate assets once."""
    scans: list[CandidateScanResult] = []
    for candidate in candidates:
        path = _download_candidate(candidate, cache_dir)
        data = path.read_bytes()
        inspection = inspect_payload(path)
        notes: list[str] = []
        keyword_hits = inspection.keyword_hits

        if inspection.defines_maplebirch_frameworks:
            notes.append("static scan found a maplebirchFrameworks assignment")
        if keyword_hits.get("maplebirchFrameworks", 0) > 0:
            notes.append("payload mentions maplebirchFrameworks")
        if keyword_hits.get("SCMLSimpleFramework", 0) or keyword_hits.get("Simple Frameworks", 0):
            notes.append("payload mentions Simple Framework APIs")
        if keyword_hits.get("TimeEvent", 0) or keyword_hits.get("addto", 0):
            notes.append("payload mentions old framework extension points")
        if candidate.compatibility_risk == "high":
            notes.append("asset game version does not match 0.5.8.10; do not smoke unless no safer candidate exists")

        likely_old_api_candidate = bool(
            not candidate.is_baseline
            and (candidate.exact_game_match or candidate.tag in PRIORITY_RELEASES)
            and (inspection.defines_maplebirch_frameworks or _has_static_framework_evidence(keyword_hits))
        )

        scans.append(
            CandidateScanResult(
                candidate=candidate,
                cache_path=str(path),
                sha256=hashlib.sha256(data).hexdigest(),
                inspection=inspection,
                likely_old_api_candidate=likely_old_api_candidate,
                idb_patch=assess_idb_patch(path),
                scan_notes=notes,
            )
        )
    return scans


def select_smoke_candidates(scans: list[CandidateScanResult], max_count: int = 2) -> list[MaplebirchAssetCandidate]:
    """Select at most max_count candidates for expensive runtime smoke."""
    likely = [scan for scan in scans if scan.likely_old_api_candidate]
    exact = [scan for scan in likely if scan.candidate.exact_game_match]
    fallback = [scan for scan in likely if not scan.candidate.exact_game_match]
    ordered = sorted(exact, key=lambda scan: scan.candidate.priority) + sorted(
        fallback, key=lambda scan: scan.candidate.priority
    )
    return [scan.candidate for scan in ordered[:max_count]]


def build_report(
    releases: list[dict[str, Any]],
    game_version: str,
    baseline_tag: str,
    max_smoke_candidates: int,
    cache_dir: Path | None = None,
    scan: bool = False,
    candidate_tags: Iterable[str] | None = None,
) -> MaplebirchVersionMatrixReport:
    candidates = filter_candidates_by_tags(candidates_from_releases(releases, game_version, baseline_tag), candidate_tags)
    scans: list[CandidateScanResult] = []
    assessments: list[CandidateAssessment] = []
    selected: list[MaplebirchAssetCandidate] = []
    top_candidate: MaplebirchAssetCandidate | None = None
    fallback_candidate: MaplebirchAssetCandidate | None = None
    stop_reason: str | None = None
    if scan:
        if cache_dir is None:
            raise ValueError("cache_dir is required when scan=True")
        scans = scan_candidates(candidates, cache_dir)
        assessments = assess_candidates(scans)
        selected = select_assessed_smoke_candidates(scans, assessments, max_smoke_candidates)
        if not selected:
            stop_reason = "no static candidate exposed enough old framework/API evidence; do not build"
        else:
            top_candidate = selected[0]
            fallback_candidate = selected[1] if len(selected) > 1 else None
    return MaplebirchVersionMatrixReport(
        repo=REPO,
        game_version=game_version,
        baseline_tag=baseline_tag,
        max_smoke_candidates=max_smoke_candidates,
        candidates=candidates,
        scans=scans,
        assessments=assessments,
        selected_for_smoke=selected,
        top_candidate=top_candidate,
        fallback_candidate=fallback_candidate,
        ci_handoff=build_ci_handoff(top_candidate, fallback_candidate),
        manual_gates=build_manual_gates(),
        stop_reason=stop_reason,
    )


def write_markdown(report: MaplebirchVersionMatrixReport, output_path: Path) -> None:
    lines = [
        "# Maplebirch version candidate matrix",
        "",
        f"- Repo: `{report.repo}`",
        f"- Target game version: `{report.game_version}`",
        f"- Baseline tag: `{report.baseline_tag}`",
        f"- Max smoke candidates: `{report.max_smoke_candidates}`",
        f"- Stop reason: `{report.stop_reason}`",
        "",
        "## Candidates",
        "",
        "| Priority | Tag | Asset | Game | Framework | Risk | Notes |",
        "|---:|---|---|---|---|---|---|",
    ]
    for candidate in report.candidates:
        notes = "; ".join(candidate.notes)
        lines.append(
            "| "
            f"{candidate.priority} | `{candidate.tag}` | `{candidate.asset_name}` | "
            f"`{candidate.game_version}` | `{candidate.framework_version}` | "
            f"`{candidate.compatibility_risk}` | {notes} |"
        )

    if report.scans:
        lines.extend(["", "## Static scan", ""])
        for scan in report.scans:
            lines.append(f"### {scan.candidate.tag} / {scan.candidate.asset_name}")
            lines.append("")
            lines.append(f"- Cache path: `{scan.cache_path}`")
            lines.append(f"- Kind: `{scan.inspection.kind}`")
            lines.append(f"- Defines maplebirchFrameworks: `{scan.inspection.defines_maplebirch_frameworks}`")
            lines.append(f"- Likely old API candidate: `{scan.likely_old_api_candidate}`")
            lines.append(f"- IDB patch status: `{scan.idb_patch.status}`")
            lines.append(f"- IDB patch member: `{scan.idb_patch.member}`")
            lines.append(f"- Keyword hits: `{scan.inspection.keyword_hits}`")
            lines.append(f"- Notes: `{scan.scan_notes}`")
            lines.append("")

    if report.assessments:
        lines.extend(
            [
                "",
                "## Candidate assessments",
                "",
                "| Rank | Recommendation | Score | Tag | Asset | Patch | IDB schema | maplebirchFrameworks | Simple Frameworks | CE contract | Reasons |",
                "|---:|---|---:|---|---|---|---|---|---|---|---|",
            ]
        )
        for assessment in report.assessments:
            reasons = "; ".join(assessment.reasons)
            lines.append(
                "| "
                f"{assessment.rank} | `{assessment.recommendation}` | {assessment.score} | "
                f"`{assessment.tag}` | `{assessment.asset_name}` | `{assessment.patch_status}` | "
                f"`{assessment.idb_schema_status}` | `{assessment.maplebirch_framework_status}` | "
                f"`{assessment.simple_framework_status}` | `{assessment.ce_contract_status}` | {reasons} |"
            )

    if report.selected_for_smoke:
        lines.extend(["", "## Selected for smoke", ""])
        for candidate in report.selected_for_smoke:
            lines.append(f"- `{candidate.tag}` / `{candidate.asset_name}`")

    lines.extend(["", "## Top and fallback", ""])
    if report.top_candidate is None:
        lines.append("- Top candidate: none")
    else:
        lines.append(f"- Top candidate: `{report.top_candidate.tag}` / `{report.top_candidate.asset_name}`")
    if report.fallback_candidate is None:
        lines.append("- Fallback candidate: none")
    else:
        lines.append(f"- Fallback candidate: `{report.fallback_candidate.tag}` / `{report.fallback_candidate.asset_name}`")

    if report.ci_handoff:
        lines.extend(["", "## CI handoff", ""])
        for step in report.ci_handoff:
            lines.append(f"- {step}")

    if report.manual_gates:
        lines.extend(["", "## Manual gates", ""])
        for gate in report.manual_gates:
            lines.append(f"- {gate}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(report: MaplebirchVersionMatrixReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enumerate and rank maplebirch framework release assets")
    parser.add_argument("--game-version", default=DEFAULT_GAME_VERSION)
    parser.add_argument("--baseline-tag", default=BASELINE_TAG)
    parser.add_argument("--per-page", type=int, default=30)
    parser.add_argument("--scan", action="store_true", help="Download and statically scan candidates")
    parser.add_argument("--cache-dir", type=Path, default=Path("workspace/temp/maplebirch-candidates"))
    parser.add_argument("--max-smoke-candidates", type=int, default=2)
    parser.add_argument(
        "--candidate-tag",
        action="append",
        dest="candidate_tags",
        help="Restrict the matrix to a release tag. Repeat for multiple tags.",
    )
    parser.add_argument(
        "--hybrid-triage",
        action="store_true",
        help="Restrict the matrix to the agreed v3.1.13/v3.1.14/v3.2.3 canary triage set.",
    )
    parser.add_argument("--output", type=Path, default=Path("output/maplebirch-version-candidates.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("output/maplebirch-version-candidates.md"))
    args = parser.parse_args()

    candidate_tags = HYBRID_TRIAGE_TAGS if args.hybrid_triage else args.candidate_tags
    releases = fetch_releases(args.per_page)
    report = build_report(
        releases,
        args.game_version,
        args.baseline_tag,
        args.max_smoke_candidates,
        cache_dir=args.cache_dir,
        scan=args.scan,
        candidate_tags=candidate_tags,
    )
    write_json(report, args.output)
    write_markdown(report, args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
