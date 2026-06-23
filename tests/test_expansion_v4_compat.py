"""Tests for expansion v4.x compatibility patch."""

from pathlib import Path


def test_expansion_patch_file_exists():
    """Verify patch file exists in expected location."""
    patch_file = Path("patches/expansion_v4_compat.js")
    assert patch_file.exists(), f"Patch file not found: {patch_file}"


def test_expansion_patch_detects_v4():
    """Verify patch only applies to v4.x (checks for missing maplebirch.use)."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should detect v4.x by checking if use() doesn't exist
    assert "typeof maplebirch.use !== 'function'" in content, \
        "Patch must detect v4.x by checking for missing maplebirch.use()"


def test_expansion_patch_sets_exposed_flag():
    """Verify patch wraps Expansion constructor to set exposed=true."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should wrap Expansion and set exposed flag
    assert "instance.exposed = true" in content, \
        "Patch must set exposed=true on Expansion instance"


def test_expansion_patch_preserves_constructor():
    """Verify patch preserves original Expansion constructor behavior."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should wrap original constructor
    assert "var OrigExpansion = window.Expansion" in content, \
        "Patch must preserve original Expansion constructor"
    assert "new OrigExpansion(maplebirch)" in content, \
        "Patch must call original constructor with maplebirch"


def test_expansion_patch_prevents_duplicate_application():
    """Verify patch prevents duplicate application."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should check if already applied
    assert "__expansionPatched" in content, \
        "Patch must prevent duplicate application using flag"


def test_expansion_patch_is_iife():
    """Verify patch is wrapped in IIFE for scope isolation."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should contain IIFE (may have comment headers before it)
    assert "(function()" in content or "(function ()" in content, \
        "Patch must be wrapped in IIFE for scope isolation"
    assert "'use strict';" in content, \
        "Patch should use strict mode"


def test_expansion_patch_has_eol_documentation():
    """Verify patch has End-of-Life conditions documented."""
    patch_file = Path("patches/expansion_v4_compat.js")
    content = patch_file.read_text(encoding="utf-8")
    
    # Patch should document removal conditions
    assert "END OF LIFE CONDITIONS" in content or "remove this patch" in content.lower(), \
        "Patch must document when it should be removed"
