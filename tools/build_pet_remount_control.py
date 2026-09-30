#!/usr/bin/env python3
"""Derive a single-variable control APK from a built AU-F artifact.

Only the ``dolxPetRemountAfterPassageDisplay`` IIFE is removed from the embedded
Maplebirch ``dist/inject_early.js``. The AU face-variant patch, the basehead
expression and every other nested/APK member stay byte-identical.

Output is measurement-only and must never be published.

Usage:
    python tools/build_pet_remount_control.py [source.apk]

The default source is the 2026-09-15 AU-F artifact. The rewritten script is run
through ``node --check`` before signing, because the 2026-09-26 incident showed
that dropping the IIFE without its leading comma produces a syntax error which
aborts ModLoader's entire early-load injection.
"""

from __future__ import annotations

import base64
import io
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from lyra.build import (  # noqa: E402
    MAPLEBIRCH_AU_FACE_VARIANT_MARKER,
    MAPLEBIRCH_PET_REMOUNT_MARKER,
    MAPLEBIRCH_PET_REMOUNT_MEMBER,
    MAPLEBIRCH_PET_REMOUNT_NEW,
    MAPLEBIRCH_PET_REMOUNT_OLD,
)

DEFAULT_SOURCE_APK = REPO_ROOT / "output/DoL-0.5.11.9-XFox-1.0.0a-au-f-0915.apk"
SOURCE_APK = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE_APK
OUTPUT_DIRECTORY = REPO_ROOT / "output" / f"pet-remount-control-{SOURCE_APK.stem}"
UNSIGNED_APK = OUTPUT_DIRECTORY / "DoL-au-f-PET-REMOUNT-OFF-0915-unsigned.apk"
HTML_MEMBER = "assets/www/index.html"

KEYSTORE_PATH = REPO_ROOT / "dol.jks"
KEYSTORE_ALIAS = "dol"
KEYSTORE_PASSWORD = "dolchs"
SIGNER_JAR = REPO_ROOT / "uber-apk-signer.jar"


def fail(message: str) -> None:
    raise RuntimeError(message)


def remove_pet_remount(mod_zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(mod_zip_bytes), "r") as source_zip:
        source_infos = source_zip.infolist()
        source_members = {
            member.filename: source_zip.read(member) for member in source_infos
        }

    script = source_members[MAPLEBIRCH_PET_REMOUNT_MEMBER].decode("utf-8")
    if script.count(MAPLEBIRCH_PET_REMOUNT_NEW) != 1:
        fail(
            "expected exactly one pet-remount patched preInit, found "
            f"{script.count(MAPLEBIRCH_PET_REMOUNT_NEW)}"
        )
    # MAPLEBIRCH_PET_REMOUNT_OLD is a prefix of MAPLEBIRCH_PET_REMOUNT_NEW, so its
    # presence is expected in the patched script. What must be true is that the
    # patched form occurs exactly once and no unpatched form exists outside it.
    if script.count(MAPLEBIRCH_PET_REMOUNT_OLD) != 1:
        fail(
            "expected exactly one preInit anchor, found "
            f"{script.count(MAPLEBIRCH_PET_REMOUNT_OLD)}"
        )
    if script.count(MAPLEBIRCH_PET_REMOUNT_MARKER) != 1:
        fail("expected exactly one pet-remount marker")

    control_script = script.replace(
        MAPLEBIRCH_PET_REMOUNT_NEW,
        MAPLEBIRCH_PET_REMOUNT_OLD,
        1,
    )
    if MAPLEBIRCH_PET_REMOUNT_MARKER in control_script:
        fail("pet-remount marker survived removal")
    if control_script.count(MAPLEBIRCH_PET_REMOUNT_OLD) != 1:
        fail("unpatched preInit shape was not restored exactly once")
    if control_script.count(MAPLEBIRCH_PET_REMOUNT_NEW) != 0:
        fail("patched preInit shape survived removal")
    if control_script.count(MAPLEBIRCH_AU_FACE_VARIANT_MARKER) != 1:
        fail("AU face-variant patch changed unexpectedly")
    # The 2026-09-26 incident: the first control package dropped the IIFE text
    # but left its leading comma, producing `t.sync()})}),,this.use(` and a
    # SyntaxError that aborted ModLoader's whole early-load injection. Check the
    # exact failure shape and then syntax-check the result with node.
    if ",,this.use(" in control_script:
        fail("double comma left behind by the removal")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as target_zip:
        for source_info in source_infos:
            member_bytes = source_members[source_info.filename]
            if source_info.filename == MAPLEBIRCH_PET_REMOUNT_MEMBER:
                member_bytes = control_script.encode("utf-8")
            target_info = zipfile.ZipInfo(
                source_info.filename,
                date_time=source_info.date_time,
            )
            target_info.compress_type = source_info.compress_type
            target_info.external_attr = source_info.external_attr
            target_zip.writestr(target_info, member_bytes)

    with zipfile.ZipFile(io.BytesIO(buffer.getvalue()), "r") as check_zip:
        if check_zip.namelist() != [info.filename for info in source_infos]:
            fail("nested member list or order changed")
        for member_name, source_bytes in source_members.items():
            if member_name == MAPLEBIRCH_PET_REMOUNT_MEMBER:
                continue
            if check_zip.read(member_name) != source_bytes:
                fail(f"unexpected nested member change: {member_name}")
    return buffer.getvalue()


def main() -> int:
    if not SOURCE_APK.exists():
        fail(f"source APK missing: {SOURCE_APK}")
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(SOURCE_APK, "r") as source_apk:
        apk_infos = source_apk.infolist()
        source_html = source_apk.read(HTML_MEMBER).decode("utf-8")

    target_blob: str | None = None
    for blob_match in re.finditer(r"UEsDB[A-Za-z0-9+/=]{2000,}", source_html):
        candidate_blob = blob_match.group(0)
        try:
            candidate_bytes = base64.b64decode(candidate_blob, validate=False)
            with zipfile.ZipFile(io.BytesIO(candidate_bytes), "r") as candidate_zip:
                if MAPLEBIRCH_PET_REMOUNT_MEMBER not in candidate_zip.namelist():
                    continue
                candidate_script = candidate_zip.read(
                    MAPLEBIRCH_PET_REMOUNT_MEMBER
                ).decode("utf-8", errors="replace")
        except (ValueError, zipfile.BadZipFile, KeyError):
            continue
        if MAPLEBIRCH_PET_REMOUNT_MARKER not in candidate_script:
            continue
        if target_blob is not None:
            fail("more than one embedded payload carries the pet-remount marker")
        target_blob = candidate_blob

    if target_blob is None:
        fail("embedded Maplebirch payload with the pet-remount patch was not found")

    control_mod_bytes = remove_pet_remount(
        base64.b64decode(target_blob, validate=False)
    )

    # Syntax-check the rewritten script, not just the needle counts.
    with zipfile.ZipFile(io.BytesIO(control_mod_bytes), "r") as syntax_zip:
        syntax_source = syntax_zip.read(MAPLEBIRCH_PET_REMOUNT_MEMBER).decode("utf-8")
    syntax_path = OUTPUT_DIRECTORY / "control-inject_early.syntax-check.js"
    syntax_path.write_text(syntax_source, encoding="utf-8")
    syntax_result = subprocess.run(
        ["node", "--check", str(syntax_path)],
        capture_output=True,
        text=True,
    )
    if syntax_result.returncode != 0:
        print((syntax_result.stdout or "")[-2000:])
        print((syntax_result.stderr or "")[-2000:])
        fail("node --check rejected the rewritten inject_early.js")
    syntax_path.unlink()
    print("node --check: control inject_early.js parses cleanly")

    control_blob = base64.b64encode(control_mod_bytes).decode("ascii")
    if source_html.count(target_blob) != 1:
        fail("target base64 payload is not unique in index.html")
    control_html = source_html.replace(target_blob, control_blob, 1)
    if control_html.replace(control_blob, target_blob, 1) != source_html:
        fail("index.html changed outside the one embedded payload")

    if UNSIGNED_APK.exists():
        UNSIGNED_APK.unlink()
    with zipfile.ZipFile(SOURCE_APK, "r") as source_apk:
        with zipfile.ZipFile(UNSIGNED_APK, "w") as target_apk:
            for source_info in apk_infos:
                member_bytes = source_apk.read(source_info.filename)
                if source_info.filename == HTML_MEMBER:
                    member_bytes = control_html.encode("utf-8")
                target_info = zipfile.ZipInfo(
                    source_info.filename,
                    date_time=source_info.date_time,
                )
                target_info.compress_type = source_info.compress_type
                target_info.external_attr = source_info.external_attr
                if source_info.filename == "resources.arsc":
                    target_info.compress_type = zipfile.ZIP_STORED
                target_apk.writestr(target_info, member_bytes)

    signed_directory = OUTPUT_DIRECTORY / "signed"
    if signed_directory.exists():
        shutil.rmtree(signed_directory)
    signed_directory.mkdir(parents=True)
    completed = subprocess.run(
        [
            "java",
            "-jar",
            str(SIGNER_JAR),
            "-a",
            str(UNSIGNED_APK),
            "--ks",
            str(KEYSTORE_PATH),
            "--ksAlias",
            KEYSTORE_ALIAS,
            "--ksKeyPass",
            KEYSTORE_PASSWORD,
            "--ksPass",
            KEYSTORE_PASSWORD,
            "-o",
            str(signed_directory),
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print((completed.stdout or "")[-3000:])
        print((completed.stderr or "")[-3000:])
        fail("APK signing failed")
    signed_apks = sorted(signed_directory.glob("*.apk"))
    if len(signed_apks) != 1:
        fail(f"expected one signed APK, found {len(signed_apks)}")
    signed_apk = signed_apks[0]

    # Final assertion on the signed artifact.
    with zipfile.ZipFile(signed_apk, "r") as verify_apk:
        verify_html = verify_apk.read(HTML_MEMBER).decode("utf-8")
    found = False
    for blob_match in re.finditer(r"UEsDB[A-Za-z0-9+/=]{2000,}", verify_html):
        try:
            raw = base64.b64decode(blob_match.group(0), validate=False)
            with zipfile.ZipFile(io.BytesIO(raw), "r") as nested:
                if MAPLEBIRCH_PET_REMOUNT_MEMBER not in nested.namelist():
                    continue
                script = nested.read(MAPLEBIRCH_PET_REMOUNT_MEMBER).decode(
                    "utf-8", errors="replace"
                )
        except (ValueError, zipfile.BadZipFile, KeyError):
            continue
        if MAPLEBIRCH_PET_REMOUNT_OLD in script:
            if MAPLEBIRCH_PET_REMOUNT_MARKER in script:
                fail("signed control still carries the pet-remount patch")
            if MAPLEBIRCH_AU_FACE_VARIANT_MARKER not in script:
                fail("signed control lost the AU face-variant patch")
            found = True
    if not found:
        fail("could not re-locate the control payload in the signed APK")

    print(f"source: {SOURCE_APK} ({SOURCE_APK.stat().st_size} bytes)")
    print(f"control: {signed_apk} ({signed_apk.stat().st_size} bytes)")
    print("PASS: only the pet-remount IIFE removed; AU variant patch retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
