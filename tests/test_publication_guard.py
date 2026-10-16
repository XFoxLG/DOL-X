import subprocess
from pathlib import Path

from tools.publication_guard import check_text, outgoing, scan_index, scan_tree


def init(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True).stdout.decode().strip()
    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (tmp_path / "notes.md").write_text("public details\n", encoding="utf-8")
    git("add", "notes.md")
    git("commit", "-qm", "docs: clarify release notes")
    return git


def test_private_key_and_message_do_not_echo_values():
    value = "gh" + "p_" + "x" * 36
    findings = check_text(value, path="notes.md")
    assert findings and value not in str(findings)
    header = "-----BEGIN " + "PRIVATE KEY-----"
    assert check_text(header, path="notes.md")[0]["rule"] == "private-key"
    message = "docs: " + "解" + "密研究记录"
    assert check_text(message, path="commit", message=True)[0]["rule"] == "private-research-message"


def test_secret_literals_and_placeholders():
    secret = "not-a-real-" + "credential-123"
    text = 'password = "' + secret + '"'
    assert check_text(text, path="config.py")[0]["rule"] == "credential-literal"
    assert not check_text('password = "<private-value>"', path="example.py")
    assert not check_text('version = "4.1.14"', path="config.toml")
    assert check_text("details " + secret, path="notes.md", literals=[secret])[0]["rule"] == "private-literal"


def test_scans_index_not_unstaged_clean_replacement(tmp_path):
    git = init(tmp_path)
    value = "gh" + "p_" + "q" * 36
    file = tmp_path / "notes.md"
    file.write_text(value, encoding="utf-8")
    git("add", "notes.md")
    file.write_text("now clean in working tree", encoding="utf-8")
    assert any(x["rule"] == "access-token" for x in scan_index(tmp_path, []))


def test_pre_push_checks_deleted_history_and_private_refs(tmp_path):
    git = init(tmp_path)
    base = git("rev-parse", "HEAD")
    value = "gh" + "p_" + "z" * 36
    (tmp_path / "notes.md").write_text(value, encoding="utf-8")
    git("add", "notes.md"); git("commit", "-qm", "docs: test change")
    (tmp_path / "notes.md").write_text("clean again", encoding="utf-8")
    git("add", "notes.md"); git("commit", "-qm", "docs: cleanup")
    tip = git("rev-parse", "HEAD")
    assert not scan_tree(tmp_path, tip, [])
    line = f"refs/heads/vega {tip} refs/heads/vega {base}\n"
    assert any(x["rule"] == "access-token" for x in outgoing(tmp_path, line, []))
    line = f"refs/heads/backup/private {tip} refs/heads/archive {base}\n"
    assert any(x["rule"] == "private-ref" for x in outgoing(tmp_path, line, []))


def test_private_files_and_unreadable_ref_fail_closed(tmp_path):
    git = init(tmp_path)
    (tmp_path / "signing.jks").write_bytes(b"private binary")
    git("add", "signing.jks")
    assert scan_index(tmp_path, [])[0]["rule"] == "private-file"


def test_repository_public_tree_is_clean():
    root = Path(__file__).resolve().parents[1]
    assert scan_tree(root, "HEAD", []) == []


def test_annotated_tag_message_is_checked(tmp_path):
    git = init(tmp_path)
    message = 'research ' + 'decrypt' + ' notes'
    git('tag', '-a', 'v1', '-m', message)
    oid = git('rev-parse', 'v1')
    line = f'refs/tags/v1 {oid} refs/tags/v1 ' + '0' * 40 + '\n'
    assert any(x['rule'] == 'private-research-message' for x in outgoing(tmp_path, line, []))
