"""Tests for the manual test-checklist generator."""

from pathlib import Path

from tools.download_latest_build import BuildDownloader, DEFAULT_BUILD_CODE


def test_default_manual_test_build_is_au_f():
    assert DEFAULT_BUILD_CODE == 15705344


def test_generated_checklist_tracks_current_four_x_stack(tmp_path: Path):
    downloader = BuildDownloader(tmp_path)

    checklist = downloader._build_checklist_content(DEFAULT_BUILD_CODE, {"mods": {}})

    assert "AU-F" in checklist
    assert "maplebirch v4.1.13" in checklist
    assert "Cheat Extended v1.20(dev260719)" in checklist
    assert "LongerCombat v1.0.1" in checklist
    assert "YanlingCheatCollection v1.0.1" in checklist
    assert "More Love Interests Mod v0.1.7.0" in checklist
    assert "AU Female v0.9.3 + AU Face v1.1.0" in checklist


def test_generated_checklist_marks_retired_stack_as_absent(tmp_path: Path):
    downloader = BuildDownloader(tmp_path)

    checklist = downloader._build_checklist_content(DEFAULT_BUILD_CODE, {"mods": {}})

    assert "maplebirch v3.1.14" not in checklist
    assert "cheat extended v1.18" not in checklist
    assert "maplebirchEx v1.2.4 不应出现" in checklist
