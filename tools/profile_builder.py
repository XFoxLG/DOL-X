#!/usr/bin/env python3
"""Build by profile name instead of raw build code."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lyra.config_loader import load_profiles_config
from lyra.build import BuildTask, build_single


def main():
    parser = argparse.ArgumentParser(description="Build by profile")
    parser.add_argument("profile", nargs="?", help="Profile ID (e.g., 'standard', 'au-f-standard')")
    parser.add_argument("--pack-type", choices=["zip", "apk"], default="zip")
    parser.add_argument("--list", action="store_true", help="List available profiles")
    args = parser.parse_args()
    
    profiles = load_profiles_config()
    
    if args.list or not args.profile:
        print("Available profiles:")
        for p in profiles:
            marker = " [recommended]" if p.recommended else ""
            marker += " [experimental]" if p.experimental else ""
            print(f"  {p.id:20} - {p.name}{marker}")
            if p.description:
                print(f"    {p.description}")
        if not args.list and not args.profile:
            print("\nUsage: python tools/profile_builder.py <profile_id>")
        sys.exit(0)
    
    profile = next((p for p in profiles if p.id == args.profile), None)
    
    if not profile:
        print(f"Error: Profile '{args.profile}' not found")
        print(f"Available profiles: {', '.join(p.id for p in profiles)}")
        sys.exit(1)
    
    if profile.experimental:
        print(f"Warning: Building experimental profile '{profile.name}'")
    
    task = BuildTask(code=profile.build_code, pack_type=args.pack_type)
    result = build_single(task)
    
    if result.success:
        print(f"Built {profile.name}: {result.output_name}")
    else:
        print(f"Build failed: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
