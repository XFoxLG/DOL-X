#!/usr/bin/env python3
"""Helper to add new mods to DOL-X configuration.

Automates the process of:
1. Assigning a unique feature ID and bit
2. Adding mod entry to config/build.toml
3. Adding feature definition to config/features.toml
"""

import argparse
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_existing_features() -> dict:
    """Load existing features from config/features.toml."""
    config_path = Path("config/features.toml")
    if not config_path.exists():
        return {"features": []}
    
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def suggest_feature_bit() -> int:
    """Suggest next available feature bit."""
    features = load_existing_features()
    used_bits = {f["bit"] for f in features.get("features", [])}
    
    bit = 1
    while bit in used_bits:
        bit *= 2
    
    return bit


def check_conflicts(feature_id: str, key: str) -> None:
    """Check for naming conflicts."""
    features = load_existing_features()
    
    existing_ids = {f["id"] for f in features.get("features", [])}
    if feature_id in existing_ids:
        raise ValueError(f"Feature ID '{feature_id}' already exists")
    
    build_config = Path("config/build.toml")
    if build_config.exists():
        with open(build_config, "rb") as f:
            build_data = tomllib.load(f)
            existing_keys = {m.get("key") for m in build_data.get("modloader_mods", [])}
            if key in existing_keys:
                raise ValueError(f"Mod key '{key}' already exists")


def generate_mod_entry(
    key: str,
    name: str,
    github_repo: str,
    asset_pattern: str,
    release_tag: str,
    feature_id: str,
) -> str:
    """Generate TOML entry for build.toml."""
    return f"""
[[modloader_mods]]
key = "{key}"
name = "{name}"
enabled = true
feature_id = "{feature_id}"
github_repo = "{github_repo}"
asset_pattern = "{asset_pattern}"
release_tag = "{release_tag}"
"""


def generate_feature_entry(
    feature_id: str,
    name: str,
    bit: int,
    required: bool = False,
) -> str:
    """Generate TOML entry for features.toml."""
    return f"""
[[features]]
id = "{feature_id}"
name = "{name}"
bit = {bit}
required = {str(required).lower()}
"""


def main():
    parser = argparse.ArgumentParser(description="Add new mod to configuration")
    parser.add_argument("key", help="Mod key (unique identifier)")
    parser.add_argument("name", help="Mod display name")
    parser.add_argument("github_repo", help="GitHub repo (owner/repo)")
    parser.add_argument("asset_pattern", help="Asset filename pattern")
    parser.add_argument("--release-tag", default="latest", help="Release tag")
    parser.add_argument("--feature-id", help="Feature ID (auto-generated if not provided)")
    parser.add_argument("--required", action="store_true", help="Mark as required feature")
    parser.add_argument("--dry-run", action="store_true", help="Print entries without modifying files")
    args = parser.parse_args()
    
    feature_id = args.feature_id or args.key
    
    try:
        check_conflicts(feature_id, args.key)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    feature_bit = suggest_feature_bit()
    
    mod_entry = generate_mod_entry(
        args.key,
        args.name,
        args.github_repo,
        args.asset_pattern,
        args.release_tag,
        feature_id,
    )
    
    feature_entry = generate_feature_entry(
        feature_id,
        args.name,
        feature_bit,
        args.required,
    )
    
    if args.dry_run:
        print("=== build.toml entry ===")
        print(mod_entry)
        print("\n=== features.toml entry ===")
        print(feature_entry)
        print(f"\nAssigned feature bit: {feature_bit}")
        return 0
    
    with open("config/build.toml", "a", encoding="utf-8") as f:
        f.write(mod_entry)
    
    with open("config/features.toml", "a", encoding="utf-8") as f:
        f.write(feature_entry)
    
    print(f"✓ Added mod '{args.name}' to configuration")
    print(f"  Feature ID: {feature_id}")
    print(f"  Feature bit: {feature_bit}")
    print(f"  Key: {args.key}")
    print("\nNext steps:")
    print(f"  1. Run: python tools/validate_mod_addition.py {args.key} {feature_bit + 256}")
    print("  2. Test manually")
    print("  3. Update documentation")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
