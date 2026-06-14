#!/usr/bin/env python3
"""Check for mod updates from GitHub releases."""

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import load_build_config


def check_github_release(repo: str, current_tag: str) -> dict:
    """Check if GitHub repo has a newer release."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        latest = response.json()
        
        return {
            "repo": repo,
            "current": current_tag,
            "latest": latest["tag_name"],
            "has_update": latest["tag_name"] != current_tag,
            "url": latest["html_url"],
            "published_at": latest["published_at"],
            "status": "success",
        }
    except requests.RequestException as e:
        return {
            "repo": repo,
            "current": current_tag,
            "status": "error",
            "error": str(e),
        }


def check_all_mods() -> list[dict]:
    """Check all enabled mods for updates."""
    config = load_build_config()
    results = []
    
    for mod in config.modloader_mods:
        if not mod.enabled or not mod.github_repo:
            continue
        
        print(f"Checking {mod.name or mod.key}...")
        result = check_github_release(mod.github_repo, mod.release_tag)
        result["mod_key"] = mod.key
        result["mod_name"] = mod.name or mod.key
        results.append(result)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Check mod updates")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    args = parser.parse_args()
    
    results = check_all_mods()
    
    # Count updates
    updates = [r for r in results if r.get("has_update")]
    errors = [r for r in results if r.get("status") == "error"]
    
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"\n✓ Saved to {args.output}")
    
    if args.summary or not args.output:
        print("\n=== Summary ===")
        print(f"Total mods checked: {len(results)}")
        print(f"Updates available: {len(updates)}")
        print(f"Errors: {len(errors)}")
        
        if updates:
            print("\nMods with updates:")
            for r in updates:
                print(f"  - {r['mod_name']}: {r['current']} → {r['latest']}")
                print(f"    {r['url']}")
        
        if errors:
            print("\nErrors:")
            for r in errors:
                print(f"  - {r['mod_name']}: {r['error']}")
    
    # Exit code: 0 if no updates, 1 if updates available
    return 1 if updates else 0


if __name__ == "__main__":
    sys.exit(main())
