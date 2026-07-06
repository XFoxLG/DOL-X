#!/usr/bin/env python3
"""Check for mod updates from GitHub releases with enhanced features."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from packaging.version import parse as parse_version, InvalidVersion

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import load_build_config


def load_mods_lock(lock_path: Path) -> dict:
    """Load mods.lock.json for risk assessment."""
    if not lock_path.exists():
        return {}
    try:
        return json.loads(lock_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"Warning: Failed to load mods.lock.json: {e}")
        return {}


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
    
    # Pre-release always medium risk
    if is_prerelease:
        risk_notes.append("Pre-release version (beta/rc)")
        return "medium", risk_notes
    
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
        current_ver = parse_version(current_tag.lstrip('v'))
        latest_ver = parse_version(latest_tag.lstrip('v'))
        
        # Major version change
        if current_ver.major != latest_ver.major:
            risk_notes.append(f"Major version change: {current_ver.major}.x → {latest_ver.major}.x")
            return "high", risk_notes
        
        # Minor version change
        if current_ver.minor != latest_ver.minor:
            risk_notes.append(f"Minor version change: {current_ver.minor} → {latest_ver.minor}")
            if risk_notes:  # Has compatibility warnings
                return "high", risk_notes
            return "medium", risk_notes
        
        # Patch version change
        return "low", risk_notes or ["Patch update"]
        
    except (InvalidVersion, AttributeError):
        # Can't parse version, use heuristic
        if risk_notes:
            return "high", risk_notes
        return "unknown", ["Unable to parse version numbers"]


def check_github_release(
    repo: str,
    current_tag: str,
    mod_key: str,
    include_prerelease: bool,
    lock_data: dict
) -> dict:
    """Check if GitHub repo has a newer release."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    
    # Support GitHub API token to avoid rate limiting
    headers = {}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        latest = response.json()
        
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
        
        has_update = latest["tag_name"] != current_tag
        
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
        
        return {
            "repo": repo,
            "current": current_tag,
            "latest": latest["tag_name"],
            "has_update": has_update,
            "url": latest["html_url"],
            "published_at": latest.get("published_at", ""),
            "is_prerelease": is_prerelease,
            "changelog_summary": changelog,
            "changelog_url": latest["html_url"],
            "risk_level": risk_level,
            "risk_notes": risk_notes,
            "status": "success",
        }
    except requests.RequestException as e:
        error_msg = str(e)
        # Classify error type
        if "403" in error_msg and "rate limit" in error_msg.lower():
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


def check_all_mods(include_prerelease: bool = False) -> dict:
    """Check all enabled mods for updates."""
    config = load_build_config()
    
    # Load mods.lock.json for risk assessment
    lock_path = Path(__file__).parent.parent / "config" / "mods.lock.json"
    lock_data = load_mods_lock(lock_path)
    
    results = []
    skipped_pinned = []
    
    for mod in config.modloader_mods:
        if not mod.enabled or not mod.github_repo:
            continue
        
        # 钉死版本（等 v4.x 兼容 / 自建镜像 / 固定 tag）的 mod 不纳入上游追踪，
        # 避免把"故意不跟的新版"报成待办更新、每周刷无意义 Issue。
        if not mod.track_upstream:
            print(f"Skipping {mod.name or mod.key} (pinned, track_upstream=false)")
            skipped_pinned.append(mod.name or mod.key)
            continue
        
        print(f"Checking {mod.name or mod.key}...")
        result = check_github_release(
            mod.github_repo,
            mod.release_tag,
            mod.key,
            include_prerelease,
            lock_data
        )
        result["mod_key"] = mod.key
        result["mod_name"] = mod.name or mod.key
        results.append(result)
    
    # Build summary report
    updates = [r for r in results if r.get("has_update")]
    errors = [r for r in results if r.get("status") == "error"]
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_checked": len(results),
        "updates_available": len(updates),
        "errors_count": len(errors),
        "has_updates": len(updates) > 0,
        "updates": updates,
        "errors": errors,
        "all_results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check mod updates from GitHub releases"
    )
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument(
        "--summary", action="store_true", help="Print summary only"
    )
    parser.add_argument(
        "--include-prerelease",
        action="store_true",
        help="Include pre-release versions",
    )
    args = parser.parse_args()
    
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
    
    # Exit code: always 0 (success), status conveyed via JSON
    return 0


if __name__ == "__main__":
    sys.exit(main())
