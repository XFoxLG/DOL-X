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
    assert "DOL-X 是由 XFoxLG 维护的游戏整合包" in readme
    assert "https://github.com/DoL-Lyra/Lyra" in readme
    assert "构建系统" in readme
    assert "当前稳定版" in readme
    assert "十一月候选仍在测试" in readme
    assert "DoL XFox" in readme
    assert "com.vrelnir.dol.xfox" in readme


def test_upstream_sync_doc_preserves_upstream_layout_and_project_config():
    checklist = _read_doc("UPSTREAM_SYNC_CHECKLIST.md")

    assert "DoL-Lyra/Lyra -> DOL-X" in checklist
    assert "https://github.com/DoL-Lyra/Lyra" in checklist
    assert "保留上游根目录、`lyra/`、`config/`、`scripts/`" in checklist
    assert "APK 名称、包名、版本组合及下载源通过配置维护" in checklist
    assert "保留当前稳定组合" in checklist
    assert "候选配置验证" in checklist


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
