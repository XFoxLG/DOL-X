"""Documentation boundary tests for DOL-X project identity.

These checks intentionally stay small: they only lock high-risk terminology
that previously blurred DOL-X, DoL-Lyra/Lyra, greenfield work, and local legacy
cheat/CSD entries.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_doc(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_identifies_dolx_as_current_project():
    readme = _read_doc("README.md")

    assert readme.startswith("# DOL-X / XFox")
    assert "DOL-X 是 XFox 自用整合包发布仓库" in readme
    assert "DoL-Lyra/Lyra" in readme
    assert "直接上游构建流程来源" in readme
    assert "不是本仓库的项目身份" in readme
    assert "DoL XFox" in readme
    assert "com.vrelnir.dol.xfox" in readme


def test_upstream_sync_doc_keeps_direction_and_self_use_boundary():
    checklist = _read_doc("UPSTREAM_SYNC_CHECKLIST.md")

    assert "DoL-Lyra/Lyra -> DOL-X" in checklist
    assert "direct upstream for build and packaging flow reuse" in checklist
    assert "DOL-X-specific identity, build matrix, and candidate/rollback mod" in checklist
    assert "do not\n  turn XFox self-use integrations into assumed upstream defaults" in checklist


def test_docs_do_not_call_project_local_mods_upstream_legacy():
    docs = [
        "README.md",
        "TESTING.md",
        "tests/README.md",
        "UPSTREAM_SYNC_CHECKLIST.md",
    ]
    forbidden_terms = [
        "upstream legacy BJX",
        "upstream legacy BCCM",
        "legacy BJX",
        "legacy BCCM",
        "上游 BJX",
        "上游 BCCM",
        "上游旧 BJX",
        "上游旧 BCCM",
        "旧作弊栈",
        "旧作弊/CSD",
    ]

    offenders = []
    for doc in docs:
        text = _read_doc(doc)
        for term in forbidden_terms:
            if term in text:
                offenders.append(f"{doc}: {term}")

    assert offenders == []
