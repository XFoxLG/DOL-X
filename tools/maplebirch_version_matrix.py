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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.utils import download_file
from tools.canary_payload_introspect import PayloadInspection, inspect_payload


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
STATIC_SCAN_KEYWORDS: tuple[str, ...] = (
    "maplebirchFrameworks",
    "CE_options",
    "SCMLSimpleFramework",
    "Simple Frameworks",
    "TimeEvent",
    "addto",
)


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
class CandidateScanResult:
    """Static inspection result for one downloaded candidate."""

    candidate: MaplebirchAssetCandidate
    cache_path: str
    sha256: str
    inspection: PayloadInspection
    likely_old_api_candidate: bool
    scan_notes: list[str] = field(default_factory=list)


@dataclass
class MaplebirchVersionMatrixReport:
    """Full report emitted by the matrix helper."""

    repo: str
    game_version: str
    baseline_tag: str
    max_smoke_candidates: int
    candidates: list[MaplebirchAssetCandidate]
    scans: list[CandidateScanResult] = field(default_factory=list)
    selected_for_smoke: list[MaplebirchAssetCandidate] = field(default_factory=list)
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
) -> MaplebirchVersionMatrixReport:
    candidates = candidates_from_releases(releases, game_version, baseline_tag)
    scans: list[CandidateScanResult] = []
    selected: list[MaplebirchAssetCandidate] = []
    stop_reason: str | None = None
    if scan:
        if cache_dir is None:
            raise ValueError("cache_dir is required when scan=True")
        scans = scan_candidates(candidates, cache_dir)
        selected = select_smoke_candidates(scans, max_smoke_candidates)
        if not selected:
            stop_reason = "no static candidate exposed enough old framework/API evidence; do not build"
    return MaplebirchVersionMatrixReport(
        repo=REPO,
        game_version=game_version,
        baseline_tag=baseline_tag,
        max_smoke_candidates=max_smoke_candidates,
        candidates=candidates,
        scans=scans,
        selected_for_smoke=selected,
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
            lines.append(f"- Keyword hits: `{scan.inspection.keyword_hits}`")
            lines.append(f"- Notes: `{scan.scan_notes}`")
            lines.append("")

    if report.selected_for_smoke:
        lines.extend(["", "## Selected for smoke", ""])
        for candidate in report.selected_for_smoke:
            lines.append(f"- `{candidate.tag}` / `{candidate.asset_name}`")

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
    parser.add_argument("--output", type=Path, default=Path("output/maplebirch-version-candidates.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("output/maplebirch-version-candidates.md"))
    args = parser.parse_args()

    releases = fetch_releases(args.per_page)
    report = build_report(
        releases,
        args.game_version,
        args.baseline_tag,
        args.max_smoke_candidates,
        cache_dir=args.cache_dir,
        scan=args.scan,
    )
    write_json(report, args.output)
    write_markdown(report, args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
