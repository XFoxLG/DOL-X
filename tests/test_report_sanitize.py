"""tools/report_sanitize.py 的单元测试（CI 上传前脱敏）。"""

from __future__ import annotations

import json
from pathlib import Path

from tools.report_sanitize import (
    _path_pairs,
    _repo_root,
    iter_report_files,
    main,
    sanitize_dir,
    sanitize_file,
    sanitize_obj,
    sanitize_text,
)


def test_sanitize_text_replaces_repo_root_both_slashes() -> None:
    repo = str(_repo_root())

    assert sanitize_text(repo + r"\tools\passage_sweep.py") == "<repo>\\tools\\passage_sweep.py"
    assert sanitize_text(repo.replace("\\", "/") + "/tools/x.py") == "<repo>/tools/x.py"


def test_sanitize_text_replaces_home_root() -> None:
    home = str(Path.home())

    cleaned = sanitize_text(f"cookie jar at {home}\\AppData\\x")

    assert "<home>" in cleaned
    assert home not in cleaned


def test_sanitize_text_replaces_foreign_absolute_paths() -> None:
    assert sanitize_text(r"open D:\elsewhere\private\thing.txt") == "open <abs-path>"
    assert sanitize_text("read /tmp/pytest-of-x/secret") == "read <abs-path>"


def test_sanitize_text_redacts_lzstring_saves() -> None:
    blob = "N4Ig" + "A" * 120

    cleaned = sanitize_text(blob)

    assert cleaned == "<redacted-save>"
    assert "N4Ig" not in cleaned


def test_sanitize_obj_redacts_large_fixture_dumps_only() -> None:
    big = {"variables": {f"k{i}": i for i in range(300)}}

    cleaned = sanitize_obj(big, pairs=[])

    assert cleaned["variables"] == {"__redacted__": True, "keys": 300}

    small = {"variables": {"a": 1}}
    assert sanitize_obj(small, pairs=[]) == small


def test_sanitize_obj_sanitizes_nested_strings() -> None:
    repo = str(_repo_root())
    obj = {"results": [{"detail": f"loaded from {repo}\\fixtures\\base.json"}]}

    cleaned = sanitize_obj(obj, pairs=_path_pairs())

    assert cleaned["results"][0]["detail"] == "loaded from <repo>\\fixtures\\base.json"


def test_sanitize_file_json_is_idempotent(tmp_path: Path) -> None:
    repo = str(_repo_root())
    path = tmp_path / "report.json"
    payload = {"target": f"{repo}\\workspace\\Degrees of Lewdity.html", "ok": True}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    changed, _ = sanitize_file(path)
    assert changed is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["target"] == "<repo>\\workspace\\Degrees of Lewdity.html"

    again, _ = sanitize_file(path)
    assert again is False


def test_sanitize_file_markdown_text(tmp_path: Path) -> None:
    repo = str(_repo_root())
    path = tmp_path / "report.md"
    path.write_text(f"- target: `{repo}\\out\\x`\n", encoding="utf-8")

    changed, _ = sanitize_file(path)

    assert changed is True
    assert "<repo>" in path.read_text(encoding="utf-8")


def test_sanitize_dir_walks_reports_and_skips_binaries(tmp_path: Path) -> None:
    repo = str(_repo_root())
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.json").write_text(json.dumps({"p": repo + "\\x"}), encoding="utf-8")
    (tmp_path / "sub" / "b.md").write_text(f"path {repo}\\y", encoding="utf-8")
    (tmp_path / "c.bin").write_bytes(b"\x00\x01")

    summary = sanitize_dir(tmp_path)

    assert summary == {"files": 2, "changed": 2}
    # binary untouched
    assert (tmp_path / "c.bin").read_bytes() == b"\x00\x01"
    # second pass is a no-op
    assert sanitize_dir(tmp_path) == {"files": 2, "changed": 0}


def test_iter_report_files_accepts_single_file(tmp_path: Path) -> None:
    path = tmp_path / "one.md"
    path.write_text("x", encoding="utf-8")

    assert iter_report_files(path) == [path]
    assert iter_report_files(tmp_path / "missing.md") == [tmp_path / "missing.md"]


def test_main_check_mode_exit_codes(tmp_path: Path) -> None:
    repo = str(_repo_root())
    (tmp_path / "r.json").write_text(json.dumps({"p": repo + "\\x"}), encoding="utf-8")

    assert main(["--check", str(tmp_path)]) == 1
    assert main([str(tmp_path)]) == 0
    assert main(["--check", str(tmp_path)]) == 0
