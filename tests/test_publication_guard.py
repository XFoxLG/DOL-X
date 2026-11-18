import subprocess
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.publication_guard import (MAX_BYTES, check_text, identity_findings,
    load_private_policy, main, outgoing, scan_archive, scan_index, scan_tree)


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


def test_archive_large_members_block_and_explicit_full_audit_scans_them():
    raw = io.BytesIO()
    large = b"public text\n" + b"x" * MAX_BYTES + b"private-fixture-literal"
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.txt", large)
        archive.writestr("notes.md", "safe")
    findings = scan_archive(raw.getvalue(), "historical.zip", ["private-fixture-literal"])
    assert findings == [{"path": "historical.zip!large.txt", "rule": "oversized-review-required"}]
    audited = scan_archive(raw.getvalue(), "historical.zip", ["private-fixture-literal"], max_bytes=len(large))
    assert audited[0]["rule"] == "private-literal"
    assert "private-fixture-literal" not in str(audited)


def test_tar_large_members_and_nested_private_archives_are_not_skipped():
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        data = b"x" * (MAX_BYTES + 1)
        member = tarfile.TarInfo("large.log")
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    assert scan_archive(raw.getvalue(), "old.tgz", [])[0]["rule"] == "oversized-review-required"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr(".local/private.txt", b"\0private binary")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("nested.zip", inner.getvalue())
    assert scan_archive(outer.getvalue(), "old.zip", []) == [
        {"path": "old.zip!nested.zip!.local/private.txt", "rule": "private-file"}
    ]


def test_binary_members_are_checked_against_private_literals():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("opaque.bin", b"\0safe header\0private-fixture-literal")
    findings = scan_archive(raw.getvalue(), "old.zip", ["private-fixture-literal"])
    assert findings == [{"path": "old.zip!opaque.bin", "rule": "private-literal"}]


def test_mixed_creator_and_submitter_identity_is_checked_per_field():
    owned = [{"name": "PrivateFixture", "email": "private-fixture@example.invalid"}]
    assert not identity_findings("a", "OriginalAuthor", "author@example.invalid", "OriginalAuthor", "author@example.invalid", owned)
    findings = identity_findings("b", "OriginalAuthor", "author@example.invalid", "PrivateFixture", "private-fixture@example.invalid", owned)
    assert findings == [{"path": "commit:b", "rule": "private-committer-identity"}]
    findings = identity_findings("c", "PrivateFixture", "private-fixture@example.invalid", "XFoxLG", "noreply@example.invalid", owned)
    assert findings == [{"path": "commit:c", "rule": "private-author-identity"}]


def test_external_policy_missing_explicit_file_fails_and_original_details_stay(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    private = tmp_path / "policy.json"
    private.write_text(json.dumps({"literals": ["fixture-private-path"], "identities": [{"name": "PrivateFixture", "email": "fixture@example.invalid"}]}))
    monkeypatch.setenv("DOLX_PUBLICATION_DENYLIST", str(private))
    assert load_private_policy(root)["identities"][0]["name"] == "PrivateFixture"
    assert load_private_policy(root, private)["literals"] == ["fixture-private-path"]
    with pytest.raises(FileNotFoundError):
        load_private_policy(root, tmp_path / "missing.json")
    assert check_text("Original author <original@example.invalid>", path="LICENSE", literals=["fixture-private-path"]) == []


def test_pre_push_and_ref_gate_check_owned_tagger(tmp_path):
    git = init(tmp_path)
    git("config", "user.name", "PrivateFixture")
    git("config", "user.email", "private-fixture@example.invalid")
    git("tag", "-a", "v1", "-m", "public release")
    tag = git("rev-parse", "v1")
    owned = [{"name": "PrivateFixture", "email": "private-fixture@example.invalid"}]
    lines = f"refs/tags/v1 {tag} refs/tags/v1 " + "0" * 40 + "\n"
    assert any(row["rule"] == "private-tagger-identity" for row in outgoing(tmp_path, lines, [], identities=owned))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"identities": owned}))
    assert main(["--root", str(tmp_path), "--ref", "v1", "--denylist", str(policy)]) == 1


def test_attachment_gate_output_omits_absolute_paths_and_matched_values(tmp_path, capsys):
    target = tmp_path / "historical.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("note.txt", b"private-fixture-literal")
    policy = tmp_path / "private-policy.json"
    policy.write_text(json.dumps({"literals": ["private-fixture-literal"]}))
    assert main(["--artifact", str(target), "--denylist", str(policy)]) == 1
    output = capsys.readouterr().out
    assert str(tmp_path) not in output
    assert "private-fixture-literal" not in output
    assert "artifact:1/historical.zip!note.txt" in output


def test_userinfo_urls_with_short_or_username_only_credentials_are_detected():
    assert check_text("https://fixture-user:short@host.invalid/file", path="config")[0]["rule"] == "credential-url"
    assert check_text("https://fixture-user@host.invalid/file", path="config")[0]["rule"] == "credential-url"


def test_released_computed_header_selection_is_not_a_credential_assignment():
    text = 'headers[provider ? "x-api-key" : "Authorization"] = token;'
    assert check_text(text, path="framework.js") == []
    actual = '{"x-api-key": "fixture-secret-123"}'
    assert check_text(actual, path="config.json")[0]["rule"] == "credential-literal"
    assert check_text(actual, path="tests/fixtures/config.json") == []
    assert check_text("https://fixture-user:short@host.invalid/file", path="tests/test_download_privacy.py") == []
    live = "https://" + "realuser" + ":" + "realpass" + "@host.invalid/file"
    assert check_text(live, path="tests/probe.py")[0]["rule"] == "credential-url"
    assert check_text(live, path="config/settings.toml")[0]["rule"] == "credential-url"
    secret = '{"api_key": "' + "realvalue" + "123456" + '"}'
    assert check_text(secret, path="tests/probe.py")[0]["rule"] == "credential-literal"
    assert check_text(secret, path="config/settings.json")[0]["rule"] == "credential-literal"
