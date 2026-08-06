"""Registry for fork-scoped compatibility shims.

The entries here are intentionally descriptive: they make local compatibility
work visible, scoped, and testable without changing the stable build matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MORE_LOVE_DRAG_PATCH_KEY = "more_love_drag_event_handlers"
DOLI_FLOAT_ICON_PATCH_KEY = "doli_float_icon_path"
MAPLEBIRCH_BASEHEAD_FALLBACK_PATCH_KEY = "maplebirch_basehead_fallback"
MAPLEBIRCH_PET_PASSAGE_REMOUNT_PATCH_KEY = "maplebirch_pet_passage_remount"
AU_FACE_ALIAS_KEY = "au_face_default_aliases"
APK_CDP_REMOTE_END_RECONNECT_KEY = "apk_cdp_remote_end_reconnect"

PATCH_SUCCESS_STATUSES = frozenset({"patched", "already_patched"})


@dataclass(frozen=True)
class CompatibilitySurface:
    """One fork compatibility shim or hardening surface."""

    key: str
    target: str
    scope: str
    kind: str
    fail_policy: str
    cache_name: str = ""
    github_repo: str = ""
    release_tag: str = ""
    asset_pattern: str = ""
    member: str = ""
    marker: str = ""
    tests: tuple[str, ...] = ()
    removal_condition: str = ""
    stable_matrix_mutation: bool = False
    notes: str = ""


@dataclass(frozen=True)
class GenericRefactorPlan:
    """A future genericity improvement that must preserve stable outputs."""

    key: str
    target: str
    first_safe_step: str
    stable_output_policy: str
    tests: tuple[str, ...] = ()


@dataclass(frozen=True)
class TestPolicyRequirement:
    """Coverage policy for compatibility work."""

    key: str
    requirement: str
    applies_to: tuple[str, ...]


COMPATIBILITY_SURFACES: tuple[CompatibilitySurface, ...] = (
    CompatibilitySurface(
        key=MORE_LOVE_DRAG_PATCH_KEY,
        target="More Love drag handlers",
        scope="default-path",
        kind="payload-patch",
        cache_name="more_love",
        github_repo="Nephthelana/DoL-More-Love-Interests-Mod",
        release_tag="More-Love-Interests-Mod-v0.1.7.0",
        asset_pattern="More.Love.Interests.Mod.mod.zip",
        member="game/More_Love_Interest_Mod_Drag.js",
        marker="function preventDefaultMLIM(ev)",
        fail_policy="fail-closed",
        tests=("tests/test_more_love_drag_patch.py", "tests/test_compatibility_registry.py"),
        removal_condition="Remove after upstream More Love guards non-DOM drag event arguments.",
        notes=(
            "Default stable builds include More Love, so this payload patch must not "
            "silently fall back. Repointed v0.1.6.0 -> v0.1.7.0 on 2026-08-03: that mod "
            "upgrade only fixed food symbols renamed by game 0.5.10.12, and "
            "game/More_Love_Interest_Mod_Drag.js is byte-identical between the two "
            "releases, so the unguarded ev.preventDefault() calls remain and this patch "
            "still applies without code changes."
        ),
    ),
    CompatibilitySurface(
        key=DOLI_FLOAT_ICON_PATCH_KEY,
        target="DOLI floating-button icon path",
        scope="default-path",
        kind="payload-patch",
        cache_name="doli",
        github_repo="ArsNativa/Degrees-of-Lewdity-Intelligence",
        release_tag="v0.2.3",
        asset_pattern="DOLI.mod.zip",
        member="dist/DOLI.js",
        marker="img/ui/sym_awareness.png",
        fail_policy="fail-closed",
        tests=("tests/test_doli_float_icon_patch.py", "tests/test_compatibility_registry.py"),
        removal_condition="Remove after DOLI ships an icon path matching current DoL (sym-*.png) asset naming.",
        notes="DOLI v0.2.3 hardcodes the pre-0.5.9.8 sym_awareness.png; DoL renamed sym_*→sym-*, so the float button 404s without this rewrite.",
    ),
    CompatibilitySurface(
        key=MAPLEBIRCH_BASEHEAD_FALLBACK_PATCH_KEY,
        target="Maplebirch face-style basehead fallback",
        scope="default-path",
        kind="payload-patch",
        cache_name="maplebirch",
        github_repo="MaplebirchLeaf/SCML-DOL-maplebirchFramework",
        release_tag="maplebirch-release-v4.1.13",
        asset_pattern="maplebirch-0.5.10.12-v4.1.13.mod.zip",
        member="dist/inject_early.js",
        marker="aP.has(`img/face/${e.facestyle}/base-head.png`)",
        fail_policy="fail-closed",
        tests=(
            "tests/test_maplebirch_basehead_patch.py",
            "tests/test_compatibility_registry.py",
        ),
        removal_condition=(
            "Remove after upstream Maplebirch resolves basehead candidates from "
            "its completed face-image index instead of treating an asynchronous "
            "image lookup as a synchronous existence result."
        ),
        notes=(
            "Maplebirch v4.1.13 synchronously chooses a face-style base-head path "
            "through loadImage(), which normally returns a Promise for an uncached "
            "path. The Promise is treated as an unknown-but-usable result, so the "
            "first render requests a missing img/face/<style>/base-head.png and can "
            "temporarily remove the head. The patch uses the already-populated "
            "faceImagePaths index and preserves img/body/base-head.png as fallback."
        ),
    ),
    CompatibilitySurface(
        key=MAPLEBIRCH_PET_PASSAGE_REMOUNT_PATCH_KEY,
        target="Maplebirch desktop pet passage remount",
        scope="default-path",
        kind="payload-patch",
        cache_name="maplebirch",
        github_repo="MaplebirchLeaf/SCML-DOL-maplebirchFramework",
        release_tag="maplebirch-release-v4.1.13",
        asset_pattern="maplebirch-0.5.10.12-v4.1.13.mod.zip",
        member="dist/inject_early.js",
        marker="dolxPetRemountAfterPassageDisplay",
        fail_policy="fail-closed",
        tests=(
            "tests/test_maplebirch_pet_remount_patch.py",
            "tests/test_compatibility_registry.py",
        ),
        removal_condition=(
            "Remove after upstream Maplebirch re-mounts the desktop pet when a "
            "passage rebuilds StoryFooter, instead of relying only on its wrapped "
            "<<updatesidebarimg>> macro."
        ),
        notes=(
            "SugarCube rebuilds StoryFooter on every passage render, so the "
            "<div id=\"maplebirch-character-pet\"> that Maplebirch mounted its canvas "
            "into is replaced by a fresh empty node. v4.1.13 only re-syncs the pet "
            "from the <<updatesidebarimg>> wrapper registered in Character.preInit(), "
            "which is not guaranteed to run on a passage change, so an enabled pet "
            "stays invisible while the framework still holds the detached container. "
            "Verified on MuMu 12: after a passage render the live container had 0 "
            "children while pet.container was detached with 1 child, and a single "
            "<<updatesidebarimg>> restored 17588 opaque pixels. The patch subscribes "
            "the framework's own :passagedisplay event to its own wrapped "
            "<<updatesidebarimg>> macro and only acts when the pet is enabled and the "
            "live container is empty, so it is idempotent. The macro path is required "
            "rather than a direct pet.sync(): Pet.draw() reads clothing from "
            "Renderer.CanvasModelCaches.main.sidebar and silently falls back to "
            "model.defaultOptions() (an undressed model) when that cache is not "
            "populated yet. Measured on MuMu 12: direct pet.sync() on a fresh passage "
            "gave 16316 opaque pixels with no sidebar cache, while the macro path gave "
            "17588 with clothing layers present, matching upstream appearance. Upstream "
            "v4.1.14 ships a byte-identical Pet.ts and the same sync wiring, so "
            "upgrading does not remove the need for this patch."
        ),
    ),
    CompatibilitySurface(
        key=AU_FACE_ALIAS_KEY,
        target="AU/default face runtime asset aliases",
        scope="default-path",
        kind="resource-shim",
        cache_name="au_face",
        github_repo="AOKIUTAGE/UTAGEsDOL3.0",
        release_tag="facemod",
        asset_pattern="AUsDoL.facial.expansion.mod.zip",
        member="img/face/default/default/{mouth,blush}*.png",
        fail_policy="create-from-existing-assets",
        tests=("tests/test_au_face_compat.py", "tests/test_compatibility_registry.py"),
        removal_condition="Remove after upstream/runtime no longer requests nested default face aliases.",
        notes="Lower-risk resource aliasing; no third-party JavaScript is modified.",
    ),
    CompatibilitySurface(
        key=APK_CDP_REMOTE_END_RECONNECT_KEY,
        target="APK WebView/CDP remote-end reconnect",
        scope="generic-harness",
        kind="test-harness-resiliency",
        marker="Remote end closed connection without response",
        fail_policy="strict-runtime-gate-after-reconnect",
        tests=("tests/test_apk_emulator_smoke.py", "tests/test_compatibility_registry.py"),
        removal_condition="Keep while Android WebView/CDP transport can surface this remote-close signature.",
        notes="Does not alter mod payloads or loosen expected passage/game-ready criteria.",
    ),
)


GENERIC_REFACTOR_PLAN: tuple[GenericRefactorPlan, ...] = (
    GenericRefactorPlan(
        key="config_driven_feature_suffixes",
        target="artifact suffix generation",
        first_safe_step="Add config-derived suffix snapshots while keeping ModCode.get_suffix as fallback.",
        stable_output_policy="Current stable output suffixes must remain unchanged.",
        tests=("tests/test_build_matrix.py",),
    ),
    GenericRefactorPlan(
        key="config_driven_image_warmup",
        target="image-pack warmup and application order",
        first_safe_step="Read imagepack application metadata from build.toml with current hardcoded order as fallback.",
        stable_output_policy="Current UCB/AU stable artifact contents and aliases must remain unchanged.",
        tests=("tests/test_au_face_compat.py", "tests/test_build_matrix.py"),
    ),
)


TEST_POLICY_REQUIREMENTS: tuple[TestPolicyRequirement, ...] = (
    TestPolicyRequirement(
        key="compatibility_surfaces_are_registered",
        requirement="Every fork compatibility shim must declare scope, fail policy, tests, and removal condition.",
        applies_to=("default-path", "canary-only", "diagnostic-only", "generic-harness"),
    ),
    TestPolicyRequirement(
        key="default_payload_patches_fail_closed",
        requirement="Default-path payload patches must fail closed on source drift or missing patch needles.",
        applies_to=("default-path",),
    ),
    TestPolicyRequirement(
        key="canary_and_diagnostic_do_not_mutate_stable_matrix",
        requirement="Canary-only and diagnostic-only surfaces must report stable_matrix_mutation=false.",
        applies_to=("canary-only", "diagnostic-only"),
    ),
    TestPolicyRequirement(
        key="generic_refactors_preserve_stable_outputs",
        requirement="Generic refactors must start with snapshot/manifest parity tests and preserve stable outputs.",
        applies_to=("planned-refactor",),
    ),
)


def compatibility_surface_by_key(key: str) -> CompatibilitySurface:
    """Return one registered compatibility surface by key."""
    for surface in COMPATIBILITY_SURFACES:
        if surface.key == key:
            return surface
    raise KeyError(f"unknown compatibility surface: {key}")


def compatibility_surfaces_by_scope(scope: str) -> tuple[CompatibilitySurface, ...]:
    """Return registered compatibility surfaces for one scope."""
    return tuple(surface for surface in COMPATIBILITY_SURFACES if surface.scope == scope)


def is_patch_success_status(status: object) -> bool:
    """Return whether a patch status is acceptable for fail-closed patches."""
    return str(status or "") in PATCH_SUCCESS_STATUSES


def compatibility_source_errors(surface: CompatibilitySurface, source: Any) -> list[str]:
    """Compare a source config object against version-scoped registry metadata."""
    errors: list[str] = []
    expected_fields = {
        "cache_name": surface.cache_name,
        "github_repo": surface.github_repo,
        "release_tag": surface.release_tag,
        "asset_pattern": surface.asset_pattern,
    }
    for field_name, expected in expected_fields.items():
        if not expected:
            continue
        actual = str(getattr(source, field_name, "") or "")
        if actual != expected:
            errors.append(f"{field_name} expected {expected!r}, got {actual!r}")
    return errors
