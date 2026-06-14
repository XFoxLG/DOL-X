#!/usr/bin/env python3
"""Validate a newly added mod through automated testing pipeline."""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> dict:
    """Run a command and return result."""
    print(f"→ {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ {description} passed")
        return {"success": True, "stdout": result.stdout}
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed")
        print(f"  Error: {e.stderr}")
        return {"success": False, "error": e.stderr}


def validate_new_mod(mod_key: str, test_code: int) -> dict:
    """Run full validation pipeline for a new mod."""
    results = {}
    
    # Step 1: Build test artifact
    results["build"] = run_command(
        ["python", "tools/build.py", "--codes", str(test_code)],
        f"Building test artifact (code {test_code})"
    )
    if not results["build"]["success"]:
        return {"success": False, "failed_at": "build", "results": results}
    
    # Step 2: HTML smoke test
    results["html_smoke"] = run_command(
        ["python", "tools/html_smoke_test.py", f"output/DoL-*-{test_code}-*.zip"],
        "Running HTML smoke test"
    )
    if not results["html_smoke"]["success"]:
        return {"success": False, "failed_at": "html_smoke", "results": results}
    
    # Step 3: Browser smoke test
    results["browser_smoke"] = run_command(
        ["python", "tools/browser_smoke_test.py", f"output/DoL-*-{test_code}-*.zip"],
        "Running browser smoke test"
    )
    if not results["browser_smoke"]["success"]:
        return {"success": False, "failed_at": "browser_smoke", "results": results}
    
    # Step 4: Functional tests
    results["functional"] = run_command(
        ["python", "tools/functional_smoke_test.py", f"output/DoL-*-{test_code}-*.zip"],
        "Running functional tests"
    )
    if not results["functional"]["success"]:
        return {"success": False, "failed_at": "functional", "results": results}
    
    return {"success": True, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Validate new mod addition")
    parser.add_argument("mod_key", help="Mod key to validate")
    parser.add_argument("test_code", type=int, help="Test build code")
    args = parser.parse_args()
    
    print(f"\n=== Validating mod: {args.mod_key} ===\n")
    
    result = validate_new_mod(args.mod_key, args.test_code)
    
    print("\n=== Validation Summary ===")
    if result["success"]:
        print("✓ All tests passed!")
        print("\nNext steps:")
        print("  1. Manually test mod functionality")
        print("  2. Update documentation")
        print("  3. Create PR for review")
        return 0
    else:
        print(f"✗ Validation failed at: {result['failed_at']}")
        print("\nPlease fix the issues and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
