"""Safe archive extraction tests."""

import io
import tarfile
import zipfile

import pytest

from lyra.utils import ArchiveExtractionError, extract_tar_gz, extract_zip


@pytest.mark.config
def test_extract_zip_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "bad")

    with pytest.raises(ArchiveExtractionError):
        extract_zip(archive, tmp_path / "out")

    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.config
def test_extract_zip_allows_normal_members(tmp_path):
    archive = tmp_path / "good.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("nested/file.txt", "ok")

    out_dir = extract_zip(archive, tmp_path / "out")

    assert (out_dir / "nested" / "file.txt").read_text(encoding="utf-8") == "ok"


@pytest.mark.config
def test_extract_tar_gz_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    data = b"bad"

    with tarfile.open(archive, "w:gz") as tf:
        member = tarfile.TarInfo("../evil.txt")
        member.size = len(data)
        tf.addfile(member, io.BytesIO(data))

    with pytest.raises(ArchiveExtractionError):
        extract_tar_gz(archive, tmp_path / "out")

    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.config
def test_extract_tar_gz_strips_components_safely(tmp_path):
    archive = tmp_path / "good.tar.gz"
    data = b"ok"

    with tarfile.open(archive, "w:gz") as tf:
        member = tarfile.TarInfo("root/nested/file.txt")
        member.size = len(data)
        tf.addfile(member, io.BytesIO(data))

    out_dir = extract_tar_gz(archive, tmp_path / "out", strip_components=1)

    assert (out_dir / "nested" / "file.txt").read_text(encoding="utf-8") == "ok"
