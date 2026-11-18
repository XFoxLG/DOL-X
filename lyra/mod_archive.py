"""Normalize published JeremieModLoader v1 containers for the ZIP build path.

Format source: MaplebirchLeaf/SCML-DOL-maplebirchFramework scripts/modpack.ts.
Only the outer container changes; boot.json, scripts and opaque inner payloads
are copied byte-for-byte. No plugin code is executed during conversion.
"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path, PurePosixPath

from bson import BSON
from bson.errors import InvalidBSON
import xxhash


MODPACK_MAGIC = b"JeremieModLoader"


class ModArchiveError(ValueError):
    """A third-party mod container is corrupt or uses an unsupported format."""


def source_mod_zip_bytes(source_root: Path) -> bytes:
    """Package declared ModLoader files without local paths or file timestamps.

    Source mods use the existing ModInjector ZIP path. Only boot.json and files
    explicitly listed by its file fields enter the archive; editor files, Git
    metadata and unrelated local evidence stay outside the distribution.
    """
    root = source_root.resolve()
    boot_bytes = (root / "boot.json").read_bytes()
    boot = json.loads(boot_bytes)
    if boot.get("additionDir"):
        raise ModArchiveError("source_dir requires explicit additionFile entries, not additionDir")
    names = {"boot.json"}
    for field in ("scriptFileList_inject_early", "scriptFileList_earlyload",
                  "scriptFileList_preload", "scriptFileList", "styleFileList",
                  "tweeFileList", "imgFileList", "replacePatchList", "additionFile", "additionBinaryFile"):
        for name in boot.get(field, []):
            if not isinstance(name, str) or not name:
                raise ModArchiveError(f"source_dir {field} requires a file name")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ModArchiveError(f"Invalid source mod member: {name!r}")
            names.add(name)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(names):
            path = (root / name).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ModArchiveError(f"Source mod member leaves source_dir: {name!r}") from exc
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, boot_bytes if name == "boot.json" else path.read_bytes())
    return output.getvalue()


def zip_without_empty_directories(data: bytes) -> bytes:
    """Repack AU face 1.2.16's invalid empty-directory records only.

    Reading every real member still enforces its CRC and overlap checks. The
    archived original stays untouched; the build injects this derived ZIP.
    """
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w") as target:
        for member in source.infolist():
            if member.is_dir():
                if member.file_size != 0 or member.CRC != 0:
                    raise ModArchiveError(f"Non-empty directory record: {member.filename}")
                continue
            target.writestr(member, source.read(member))
    return output.getvalue()


def mod_zip_bytes(data: bytes) -> bytes:
    """Return unchanged ZIP bytes or a deterministic ZIP of a valid modpack."""
    if not data.startswith(MODPACK_MAGIC):
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ModArchiveError("Expected a ModLoader ZIP or JeremieModLoader modpack")
        return data
    try:
        return _convert_modpack(data)
    except (InvalidBSON, KeyError, TypeError, struct.error) as exc:
        raise ModArchiveError(f"Invalid modpack metadata: {exc}") from exc


def _convert_modpack(data: bytes) -> bytes:
    if len(data) < 200:
        raise ModArchiveError("Truncated modpack header")
    expected_hash = struct.unpack_from("<Q", data, len(data) - 8)[0]
    if xxhash.xxh64(data[:-8]).intdigest() != expected_hash:
        raise ModArchiveError("Modpack xxHash64 mismatch")
    meta_start, meta_end, data_start = struct.unpack_from("<QQQ", data, 64)
    if not (meta_start == 128 < meta_end <= data_start < len(data) - 8) or data_start % 64:
        raise ModArchiveError("Invalid modpack metadata offsets")
    meta = BSON(data[meta_start:meta_end]).decode()
    if meta["protocolVersion"] != 1 or meta["blockSize"] != 64:
        raise ModArchiveError(f"Unsupported modpack protocol/block size: {meta['protocolVersion']}/{meta['blockSize']}")
    if meta["magicNumber"] != "SmVyZW1pZU1vZExvYWRlcg":
        raise ModArchiveError("Invalid modpack metadata magic")

    def member_bytes(location: dict) -> bytes:
        begin, end, length = location["b"], location["e"], location["l"]
        if not all(type(value) is int for value in (begin, end, length)):
            raise ModArchiveError("Non-integer modpack member offsets")
        start = data_start + begin * 64
        if begin < 0 or end < begin or not 0 <= length <= (end - begin + 1) * 64 or data_start + (end + 1) * 64 > len(data) - 8:
            raise ModArchiveError(f"Invalid modpack member range: {location}")
        return data[start:start + length]

    members = {"boot.json": member_bytes(meta["bootJsonFile"])}
    for name, location in meta["fileMeta"].items():
        path = PurePosixPath(name)
        if not name or "\\" in name or path.is_absolute() or ".." in path.parts or ":" in name or name in members:
            raise ModArchiveError(f"Invalid or duplicate modpack member path: {name!r}")
        members[name] = member_bytes(location)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, members[name])
    return output.getvalue()
