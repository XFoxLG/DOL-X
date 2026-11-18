#!/usr/bin/env python3
"""Check for mod updates from GitHub releases with enhanced features."""

import argparse
import fnmatch
import json
import os
import re
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import requests
from packaging.version import parse as parse_version, InvalidVersion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import get_config_loader, load_build_config


def github_headers() -> dict[str, str]:
    """Build authenticated GitHub API headers when a token is available."""
    headers = {"Accept": "application/vnd.github+json"}
    github_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def normalize_sha256(digest: str | None) -> str:
    """Return a lowercase SHA-256 value without GitHub's algorithm prefix."""
    if not digest:
        return ""
    return digest.removeprefix("sha256:").lower()


def extract_version_from_tag(tag: str) -> str:
    """Extract the final dotted numeric version from a release tag."""
    version_matches = re.findall(r"\d+(?:\.\d+)+", tag)
    return version_matches[-1] if version_matches else tag.lstrip("vV")


def select_release_asset(release: dict, asset_pattern: str) -> dict | None:
    """Select the first release asset matching an exact or wildcard pattern."""
    for asset in release.get("assets", []):
        asset_name = asset.get("name", "")
        if asset_name == asset_pattern or fnmatch.fnmatch(asset_name, asset_pattern):
            return asset
    return None


def load_mods_lock(lock_path: Path) -> dict:
    """Load mods.lock.json for risk assessment."""
    return json.loads(lock_path.read_text(encoding='utf-8'))


def extract_changelog(release_body: str, max_chars: int = 500) -> str:
    """Extract and summarize changelog from release body."""
    if not release_body:
        return ""
    
    # Remove HTML comments
    body = re.sub(r'<!--.*?-->', '', release_body, flags=re.DOTALL)
    
    # Remove image links
    body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
    
    # Try to find Changes/What's New section
    changes_match = re.search(
        r'##\s*(Changes|What\'s New|更新内容|变更日志).*?\n(.*?)(?=\n##|\Z)',
        body,
        re.IGNORECASE | re.DOTALL
    )
    
    if changes_match:
        content = changes_match.group(2).strip()
    else:
        content = body.strip()
    
    # Truncate to max_chars, keep complete sentences
    if len(content) > max_chars:
        content = content[:max_chars]
        last_newline = content.rfind('\n')
        if last_newline > max_chars * 0.7:
            content = content[:last_newline]
        content += "\n..."
    
    return content.strip()


def assess_risk(
    mod_key: str,
    current_tag: str,
    latest_tag: str,
    lock_data: dict,
    is_prerelease: bool
) -> tuple[str, list[str]]:
    """Assess update risk based on version change and lock file notes."""
    risk_notes = []
    
    # A pre-release must not hide a major-version or known compatibility risk.
    if is_prerelease:
        risk_notes.append("Pre-release version (beta/rc)")
    
    # Check lock file for known issues
    mod_lock = lock_data.get("mods", {}).get(mod_key, {})
    lock_notes = mod_lock.get("notes", [])
    
    # Look for compatibility warnings in notes
    for note in lock_notes:
        note_lower = note.lower()
        if any(kw in note_lower for kw in ["不兼容", "incompatible", "breaking", "等待", "wait"]):
            # Check if the note mentions version constraints
            if latest_tag in note or "v4" in note:
                risk_notes.append(f"Known issue: {note}")
    
    # Version comparison
    try:
        current_ver = parse_version(extract_version_from_tag(current_tag))
        latest_ver = parse_version(extract_version_from_tag(latest_tag))
        
        # Major version change
        if current_ver.major != latest_ver.major:
            risk_notes.append(f"Major version change: {current_ver.major}.x → {latest_ver.major}.x")
            return "high", risk_notes
        
        # Minor version change
        if current_ver.minor != latest_ver.minor:
            has_known_issue = any(note.startswith("Known issue:") for note in risk_notes)
            risk_notes.append(f"Minor version change: {current_ver.minor} → {latest_ver.minor}")
            if has_known_issue:
                return "high", risk_notes
            return "medium", risk_notes
        
        # Patch version change
        if any(note.startswith("Known issue:") for note in risk_notes):
            return "high", risk_notes
        return ("medium" if is_prerelease else "low"), risk_notes or ["Patch update"]
        
    except (InvalidVersion, AttributeError):
        # Can't parse version, use heuristic
        if risk_notes:
            return "high", risk_notes
        return "unknown", ["Unable to parse version numbers"]


def check_github_release(
    repo: str,
    current_tag: str,
    mod_key: str,
    asset_pattern: str,
    include_prerelease: bool,
    lock_data: dict
) -> dict:
    """Check if GitHub repo has a newer release."""
    if include_prerelease:
        api_url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
    else:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    
    try:
        response = requests.get(api_url, headers=github_headers(), timeout=10)
        response.raise_for_status()
        response_data = response.json()

        if include_prerelease:
            if not isinstance(response_data, list) or any(not isinstance(item, dict) for item in response_data):
                raise ValueError(f"Expected a release list from {repo}")
            releases = [release for release in response_data if not release.get("draft")]
            if not releases:
                raise RuntimeError(f"No published releases found for {repo}")
            latest = max(releases, key=lambda release: release.get("published_at") or "")
        else:
            latest = response_data
        if not isinstance(latest, dict) or not latest.get("tag_name"):
            raise ValueError(f"Expected release metadata with tag_name from {repo}")
        
        # Check if it's a pre-release
        is_prerelease = latest.get("prerelease", False)
        
        # Skip pre-releases unless explicitly requested
        if is_prerelease and not include_prerelease:
            return {
                "repo": repo,
                "current": current_tag,
                "latest": current_tag,
                "has_update": False,
                "status": "success",
                "skipped_prerelease": latest["tag_name"],
            }
        
        latest_asset = select_release_asset(latest, asset_pattern)
        latest_asset_digest = normalize_sha256(
            latest_asset.get("digest") if latest_asset else ""
        )
        locked_asset_digest = normalize_sha256(
            lock_data.get("mods", {}).get(mod_key, {}).get("last_tested_sha256")
        )
        release_tag_changed = latest["tag_name"] != current_tag
        if asset_pattern and not latest_asset and not release_tag_changed:
            raise ValueError(f"Release {current_tag} has no asset matching {asset_pattern!r}")
        release_asset_changed = bool(
            not release_tag_changed
            and latest_asset_digest
            and locked_asset_digest
            and latest_asset_digest != locked_asset_digest
        )
        has_update = release_tag_changed or release_asset_changed
        
        # Extract changelog
        changelog = extract_changelog(latest.get("body", "")) if has_update else ""
        
        # Assess risk
        risk_level, risk_notes = assess_risk(
            mod_key,
            current_tag,
            latest["tag_name"],
            lock_data,
            is_prerelease
        ) if has_update else ("low", [])
        if release_asset_changed:
            risk_level = "medium"
            risk_notes = [
                "Release asset digest changed under the same tag; re-validation required"
            ]
        
        return {
            "repo": repo,
            "current": current_tag,
            "latest": latest["tag_name"],
            "has_update": has_update,
            "url": latest["html_url"],
            "published_at": latest.get("published_at", ""),
            "is_prerelease": is_prerelease,
            "asset_name": latest_asset.get("name", "") if latest_asset else "",
            "asset_digest": latest_asset_digest,
            "locked_asset_digest": locked_asset_digest,
            "asset_verification": (
                "digest_compared" if latest_asset_digest and locked_asset_digest and not release_tag_changed
                else "not_matched" if asset_pattern and not latest_asset
                else "tag_only"
            ),
            "release_tag_changed": release_tag_changed,
            "release_asset_changed": release_asset_changed,
            "changelog_summary": changelog,
            "changelog_url": latest["html_url"],
            "risk_level": risk_level,
            "risk_notes": risk_notes,
            "status": "success",
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as e:
        error_msg = str(e)
        # Classify error type
        if not isinstance(e, requests.RequestException):
            error_kind = "invalid_release"
        elif "403" in error_msg and "rate limit" in error_msg.lower():
            error_kind = "rate_limit"
        elif "404" in error_msg:
            error_kind = "not_found"
        else:
            error_kind = "network_error"
        
        return {
            "repo": repo,
            "current": current_tag,
            "status": "error",
            "error": error_msg,
            "error_kind": error_kind,
        }


def check_all_mods(include_prerelease: bool = False, *, watch_path: Path | None = None) -> dict:
    """Check all enabled mods for updates."""
    config = load_build_config()
    
    # Load mods.lock.json for risk assessment
    lock_path = get_config_loader().config_dir / "mods.lock.json"
    lock_data = load_mods_lock(lock_path)
    
    results = []
    skipped = []
    
    for mod in config.modloader_mods:
        reason = (
            "disabled" if not mod.enabled else "no_repository" if not mod.github_repo
            else "pinned" if not mod.track_upstream else None
        )
        if reason:
            skipped.append({"mod_key": mod.key, "mod_name": mod.name or mod.key, "reason": reason})
            continue
        
        print(f"Checking {mod.name or mod.key}...")
        result = check_github_release(
            mod.github_repo,
            mod.release_tag,
            mod.key,
            mod.asset_pattern,
            include_prerelease or mod.include_prerelease_updates,
            lock_data
        )
        result["mod_key"] = mod.key
        result["mod_name"] = mod.name or mod.key
        results.append(result)
    
    # Observation sources never change the installed build inputs.
    references = []
    watch_path = watch_path or Path(__file__).resolve().parents[1] / "config" / "upstream-watch.toml"
    with watch_path.open("rb") as handle:
        watch_config = tomllib.load(handle)
    for source in watch_config.get("sources", []):
        result = check_github_release(
            source["repo"], source["observed_tag"], source["key"],
            source.get("asset_pattern", ""), source.get("include_prerelease", False),
            {"mods": {source["key"]: {"last_tested_sha256": source.get("sha256", "")}}},
        )
        result.update(mod_key=source["key"], mod_name=source["name"], scope="reference")
        references.append(result)

    updates = [r for r in results if r.get("has_update")]
    errors = [r for r in [*results, *references] if r.get("status") == "error"]
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_checked": len(results),
        "updates_available": len(updates),
        "errors_count": len(errors),
        "has_updates": len(updates) > 0,
        "updates": updates,
        "errors": errors,
        "all_results": results,
        "skipped": skipped,
        "references": references,
        "reference_updates": [r for r in references if r.get("has_update")],
        "check_complete": not errors,
    }


def render_summary(report: dict) -> str:
    """One truthful summary shared by local output and Actions, including failures."""
    lines = ["## Mod 与上游观察报告", "", f"检查时间：{report['timestamp']}", ""]
    if not report["check_complete"]:
        lines.append(f"检查未完成：{report['errors_count']} 项失败，不能据此判断这些来源是否有更新。")
    elif not report["total_checked"]:
        lines.append("没有检查启用的安装项；请查看下方跳过原因与候选观察结果。")
    elif report["has_updates"]:
        lines.append(f"已检查 {report['total_checked']} 个安装项，发现 {report['updates_available']} 项变化。")
    else:
        lines.append(f"已检查的 {report['total_checked']} 个安装项未发现版本变化。")
    lines.extend(["", "锁定、禁用和候选观察项不等于已安装或已验证兼容；本检查不会修改配置。", ""])
    for title, rows in (("安装项检查", report["all_results"]), ("上游与 Fork 候选观察", report["references"])):
        details = []
        lines.extend([f"### {title}", "", "| 项目 | 当前／上次观察 | 上游 | 结果 |", "|---|---|---|---|"])
        for row in rows:
            if row["status"] == "error":
                state = f"检查失败：{row['error_kind']}"
            else:
                state = "发现变化" if row["has_update"] else "未发现版本变化"
                if row.get("is_prerelease"):
                    state += "；预发布"
                verification = row.get("asset_verification")
                if verification == "tag_only":
                    state += "；仅标签比较"
                elif verification == "not_matched":
                    state += "；新版本需重新选择资产"
                if row.get("release_asset_changed"):
                    state += "；同标签资产已变化"
            lines.append(f"| {row['mod_name']} | `{row['current']}` | `{row.get('latest', '未知')}` | {state} |")
            if row["status"] == "success" and row["has_update"]:
                details.extend(["", f"[{row['mod_name']} 发布说明]({row['url']})", "", *row["risk_notes"], ""])
        lines.append("")
        lines.extend(details)
    if report["skipped"]:
        reasons = {"pinned": "主动锁定", "disabled": "已禁用", "no_repository": "未配置仓库"}
        lines.extend(["### 跳过项", ""])
        lines.extend(f"- {row['mod_name']}：{reasons[row['reason']]}" for row in report["skipped"])
    if report["errors"]:
        lines.extend(["", "### 检查失败", ""])
        lines.extend(f"- {row['mod_name']}（{row['repo']}）：{row['error']}" for row in report["errors"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Check mod updates from GitHub releases"
    )
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--markdown", type=Path, help="Write a Markdown report for Actions or local review")
    parser.add_argument(
        "--summary", action="store_true", help="Print summary only"
    )
    parser.add_argument(
        "--include-prerelease",
        action="store_true",
        help="Include pre-release versions",
    )
    args = parser.parse_args(argv)
    
    report = check_all_mods(include_prerelease=args.include_prerelease)
    
    # Save to file
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        print(f"\nSaved to {args.output}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_summary(report), encoding="utf-8")
    
    # Print summary
    if args.summary or not args.output:
        print("\n=== Summary ===")
        print(f"Total mods checked: {report['total_checked']}")
        print(f"Updates available: {report['updates_available']}")
        print(f"Errors: {report['errors_count']}")
        
        if report["updates"]:
            print("\nMods with updates:")
            for r in report["updates"]:
                # Use ASCII indicators for Windows console compatibility
                risk_indicator = {
                    "low": "[LOW]",
                    "medium": "[MEDIUM]",
                    "high": "[HIGH]",
                    "unknown": "[UNKNOWN]"
                }.get(r.get("risk_level", "unknown"), "[?]")
                
                print(f"  {risk_indicator} {r['mod_name']}: {r['current']} -> {r['latest']}")
                print(f"    {r['url']}")
                
                if r.get("risk_notes"):
                    for note in r["risk_notes"]:
                        print(f"    [!] {note}")
        
        if report["errors"]:
            print("\nErrors:")
            for r in report["errors"]:
                print(f"  - {r['mod_name']}: {r['error']}")
    
    # Keep the report even when upstream checks fail; CI must expose that failure.
    return 0 if report["check_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
