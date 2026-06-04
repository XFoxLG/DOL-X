"""Build-code validation helpers shared by CLI, matrix, and gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .config_loader import Feature, get_config_loader


LEGACY_BUILD_CODE_MIGRATIONS: dict[int, int] = {
    24834: 57602,
    25858: 58626,
    26882: 59650,
    28930: 61698,
}


@dataclass(frozen=True)
class ParsedBuildCode:
    """One normalized build-code token."""

    raw: str
    code: int | None
    is_polyfill: bool = False
    error: str | None = None

    @property
    def code_str(self) -> str:
        if self.code is None:
            return self.raw
        prefix = "polyfill-" if self.is_polyfill else ""
        return f"{prefix}{self.code}"


@dataclass(frozen=True)
class BuildCodeFinding:
    """One validation finding for a build code."""

    kind: str
    message: str
    severity: str = "error"
    feature: str | None = None
    dependency: str | None = None
    conflict: str | None = None
    unknown_bits: int | None = None
    suggested_code: int | None = None


@dataclass
class BuildCodeValidationResult:
    """Validation result for one build-code token."""

    raw: str
    code: int | None
    code_str: str
    is_polyfill: bool
    valid: bool
    findings: list[BuildCodeFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw,
            "code": self.code,
            "code_str": self.code_str,
            "is_polyfill": self.is_polyfill,
            "valid": self.valid,
            "findings": [asdict(finding) for finding in self.findings],
        }


def parse_build_code(raw_code: object) -> ParsedBuildCode:
    """Parse ``N`` or ``polyfill-N`` into a normalized build code."""
    raw = str(raw_code).strip()
    if not raw:
        return ParsedBuildCode(raw=raw, code=None, error="empty build code")

    is_polyfill = raw.startswith("polyfill-")
    numeric = raw[len("polyfill-") :] if is_polyfill else raw
    if not numeric:
        return ParsedBuildCode(raw=raw, code=None, is_polyfill=is_polyfill, error="missing numeric build code")

    try:
        code = int(numeric)
    except ValueError:
        return ParsedBuildCode(raw=raw, code=None, is_polyfill=is_polyfill, error="build code is not an integer")

    if code < 0:
        return ParsedBuildCode(raw=raw, code=code, is_polyfill=is_polyfill, error="build code must be non-negative")
    return ParsedBuildCode(raw=raw, code=code, is_polyfill=is_polyfill)


def normalize_build_codes(raw_codes: Iterable[object]) -> list[str]:
    """Normalize build codes while preserving order and removing duplicates."""
    normalized: list[str] = []
    seen: set[tuple[int, bool]] = set()
    for raw_code in raw_codes:
        parsed = parse_build_code(raw_code)
        if parsed.error or parsed.code is None:
            normalized.append(parsed.raw)
            continue
        key = (parsed.code, parsed.is_polyfill)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(parsed.code_str)
    return normalized


def _enabled_features(code: int, features: list[Feature]) -> list[Feature]:
    return [feature for feature in features if code & feature.bit]


def validate_build_code(
    raw_code: object,
    *,
    config_dir: Optional[Path] = None,
    include_legacy_hints: bool = True,
) -> BuildCodeValidationResult:
    """Validate one explicit build code against the feature graph."""
    parsed = parse_build_code(raw_code)
    findings: list[BuildCodeFinding] = []

    if parsed.error:
        findings.append(BuildCodeFinding(kind="invalid_code", message=parsed.error))
        return BuildCodeValidationResult(
            raw=parsed.raw,
            code=parsed.code,
            code_str=parsed.code_str,
            is_polyfill=parsed.is_polyfill,
            valid=False,
            findings=findings,
        )

    assert parsed.code is not None
    loader = get_config_loader(config_dir)
    features = loader.features
    feature_by_id = {feature.id: feature for feature in features}
    enabled_features = _enabled_features(parsed.code, features)
    enabled_ids = {feature.id for feature in enabled_features}
    known_bits = 0
    for feature in features:
        known_bits |= feature.bit

    unknown_bits = parsed.code & ~known_bits
    if unknown_bits:
        findings.append(
            BuildCodeFinding(
                kind="unknown_bits",
                message=f"build code contains unknown bits: {unknown_bits}",
                unknown_bits=unknown_bits,
            )
        )

    if parsed.code == 0:
        findings.append(BuildCodeFinding(kind="empty_code", message="build code 0 does not enable any features"))

    if parsed.code in loader.combinations.blacklist:
        findings.append(BuildCodeFinding(kind="blacklisted", message=f"build code is blacklisted: {parsed.code}"))

    for feature in features:
        if feature.required and feature.id not in enabled_ids:
            findings.append(
                BuildCodeFinding(
                    kind="missing_required",
                    message=f"missing required feature: {feature.id}",
                    feature=feature.id,
                )
            )
        if feature.skip and feature.id in enabled_ids:
            findings.append(
                BuildCodeFinding(
                    kind="skipped_feature",
                    message=f"code enables skipped feature: {feature.id}",
                    feature=feature.id,
                )
            )

    for feature in enabled_features:
        for dep_id in feature.depends_on:
            dep_feature = feature_by_id.get(dep_id)
            if dep_feature is None:
                findings.append(
                    BuildCodeFinding(
                        kind="unknown_dependency",
                        message=f"feature {feature.id} depends on unknown feature {dep_id}",
                        feature=feature.id,
                        dependency=dep_id,
                    )
                )
            elif dep_feature.id not in enabled_ids:
                findings.append(
                    BuildCodeFinding(
                        kind="missing_dependency",
                        message=f"feature {feature.id} requires {dep_id}",
                        feature=feature.id,
                        dependency=dep_id,
                    )
                )

        for conflict_id in feature.conflicts_with:
            conflict_feature = feature_by_id.get(conflict_id)
            if conflict_feature is None:
                findings.append(
                    BuildCodeFinding(
                        kind="unknown_conflict",
                        message=f"feature {feature.id} conflicts with unknown feature {conflict_id}",
                        feature=feature.id,
                        conflict=conflict_id,
                    )
                )
            elif conflict_feature.id in enabled_ids:
                findings.append(
                    BuildCodeFinding(
                        kind="conflict_present",
                        message=f"feature {feature.id} conflicts with enabled feature {conflict_id}",
                        feature=feature.id,
                        conflict=conflict_id,
                    )
                )

    if include_legacy_hints and parsed.code in LEGACY_BUILD_CODE_MIGRATIONS:
        suggestion = LEGACY_BUILD_CODE_MIGRATIONS[parsed.code]
        findings.append(
            BuildCodeFinding(
                kind="legacy_migration_hint",
                severity="hint",
                message=f"legacy stable code {parsed.code} can migrate to candidate code {suggestion} after gate promotion",
                suggested_code=suggestion,
            )
        )

    valid = not any(finding.severity == "error" for finding in findings)
    return BuildCodeValidationResult(
        raw=parsed.raw,
        code=parsed.code,
        code_str=parsed.code_str,
        is_polyfill=parsed.is_polyfill,
        valid=valid,
        findings=findings,
    )


def validate_build_codes(
    raw_codes: Iterable[object],
    *,
    config_dir: Optional[Path] = None,
    include_legacy_hints: bool = True,
) -> list[BuildCodeValidationResult]:
    """Validate multiple build-code tokens."""
    return [
        validate_build_code(
            raw_code,
            config_dir=config_dir,
            include_legacy_hints=include_legacy_hints,
        )
        for raw_code in raw_codes
    ]
