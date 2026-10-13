#!/usr/bin/env python3
"""Build a conservative source index for Twee/SugarCube game sources.

This is intentionally a *source index*, not a JavaScript compiler.  Anything
that cannot be resolved without evaluating code is retained as a dynamic edge
with its source location so the runtime explorer can discover it later.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
SUPPORTED_SUFFIXES = {".twee", ".tw", ".txt", ".js", ".json", ".css", ".html", ".htm"}
PASSAGE_HEADER_RE = re.compile(r"^::\s*(?P<name>[^\[\{\n]+?)\s*(?:\[[^\]]*\])?\s*$", re.MULTILINE)
HTML_PASSAGE_RE = re.compile(
    r'<tw-passagedata\b(?P<attrs>[^>]*)>(?P<body>.*?)</tw-passagedata>',
    re.IGNORECASE | re.DOTALL,
)
# NOTE: the attribute value must be matched with a *matching* quote character.
# A non-greedy `["'].*?["']` stops at the first apostrophe inside a double
# quoted value, truncating names such as ``name="Men's Toilets"`` to ``Men``.
HTML_NAME_RE = re.compile(
    r"""\bname\s*=\s*(?:"(?P<name_dq>[^"]*)"|'(?P<name_sq>[^']*)')""",
    re.I,
)


def _html_name(attrs: str) -> str | None:
    match = HTML_NAME_RE.search(attrs)
    if not match:
        return None
    return match.group("name_dq") if match.group("name_dq") is not None else match.group("name_sq")
MACRO_RE = re.compile(r"<<\s*(?P<name>[A-Za-z_][\w.-]*)\b(?P<args>.*?)>>", re.DOTALL)
LINK_RE = re.compile(r"\[\[(?P<body>[^\]]+)\]\]")
ENGINE_PLAY_RE = re.compile(r"\b(?:SugarCube\.)?Engine\.play\s*\(\s*(?P<arg>[^)]*)\)")
CONFIG_NAV_RE = re.compile(r"Config\.navigation\.override\s*=\s*(?P<expr>[^;]+)")
VAR_RE = re.compile(r"(?:\$|\bV\.)[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*|\[[^\]]+\])*")
SET_RE = re.compile(r"<<\s*set\s+(?P<lhs>(?:\$|V\.)[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\s*(?P<op>to|[+\-*/]?=)", re.I)
STRING_RE = re.compile(r"^[\s]*([\"'])(.*?)\1[\s]*$")
# Matches a double-quoted or single-quoted literal; the two alternatives keep
# the opposite quote character available inside the literal so names such as
# ``"Doctor Harper's Office"`` stay intact.
QUOTED_RE = re.compile(r"\"([^\"]+)\"|'([^']+)'")


def _quoted_values(text: str) -> list[str]:
    return [
        match.group(1) if match.group(1) is not None else match.group(2)
        for match in QUOTED_RE.finditer(text)
    ]


@dataclass
class SourceFile:
    path: str
    sha256: str
    bytes: int
    kind: str
    owner: str | None = None
    passages: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "kind": self.kind,
            "owner": self.owner,
            "passages": self.passages,
            "symbols": self.symbols,
            "edges": self.edges,
            "variables": self.variables,
        }


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _new_line_positions(text: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = text.find("\n", start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + 1


def _line_number_fast(positions: list[int], offset: int) -> int:
    return bisect.bisect_right(positions, max(0, offset)) + 1


def _clean_target(raw: str) -> str | None:
    value = html.unescape(str(raw or "").strip())
    if not value:
        return None
    # SugarCube links may be ``target``, ``label|target``, ``label->target``
    # or ``target<-label``.
    if "|" in value:
        value = value.rsplit("|", 1)[1].strip()
    elif "->" in value:
        value = value.split("->", 1)[1].strip()
    elif "<-" in value:
        value = value.split("<-", 1)[0].strip()
    value = value.strip("[] ")
    match = STRING_RE.match(value)
    if match:
        value = match.group(2)
    return value or None


def _target_kind(target: str | None) -> str:
    if target is None:
        return "dynamic"
    if re.search(r"(?:^|[\s([{}])[$`]", target):
        return "dynamic"
    # Temporary variables (``_name``, including property chains and indexing)
    # are per-passage state, not passage names.
    if target.startswith("_"):
        return "dynamic"
    # Expressions with string concatenation or operators cannot be a literal
    # passage name.  Apostrophes are allowed because real passage names use
    # them (e.g. ``Men's Toilets``).
    if re.search(r"[\"+*/%]", target):
        return "dynamic"
    return "static"


def _target_from_macro(name: str, args: str) -> tuple[str | None, str]:
    lower = name.lower()
    if lower not in {"link", "button", "goto", "include", "run"}:
        return None, "macro"
    link = LINK_RE.search(args)
    if link:
        target = _clean_target(link.group("body"))
        return target, _target_kind(target)
    quoted_values = _quoted_values(args)
    if lower in {"goto", "include"} and quoted_values:
        # ``<<include "Asylum Hypnosis " + $phase>>`` concatenates a literal
        # with runtime state: the literal prefix is not a passage name.  Only a
        # lone quoted literal (nothing but whitespace around it) is static.
        if len(quoted_values) == 1 and not QUOTED_RE.sub("", args).strip():
            target = _clean_target(quoted_values[0])
            return target, _target_kind(target)
        return None, "dynamic"
    if lower in {"link", "button"} and quoted_values and "[[" not in args:
        # Only interpret adjacent literals as ``label target``.  Backtick
        # templates, ternaries and concatenations leave non-literal text
        # behind after removing the literals, so they stay dynamic.
        if len(quoted_values) >= 2 and not QUOTED_RE.sub("", args).strip():
            target = _clean_target(quoted_values[-1])
            return target, _target_kind(target)
    return None, "dynamic"


def _append_variable_rows(
    rows: list[dict[str, Any]],
    text: str,
    *,
    path: str,
    passage: str | None,
    owner: str | None,
    line_positions: list[int] | None = None,
) -> None:
    writes: set[tuple[str, int]] = set()
    for match in SET_RE.finditer(text):
        name = match.group("lhs")
        row = {
            "name": name,
            "kind": "write",
            "operator": match.group("op"),
            "path": path,
            "line": _line_number_fast(line_positions or [], match.start()) if line_positions is not None else _line_number(text, match.start()),
            "passage": passage,
            "owner": owner,
        }
        rows.append(row)
        writes.add((name, row["line"]))
    for match in VAR_RE.finditer(text):
        name = match.group(0)
        line = _line_number_fast(line_positions or [], match.start()) if line_positions is not None else _line_number(text, match.start())
        rows.append(
            {
                "name": name,
                "kind": "write" if (name, line) in writes else "read",
                "path": path,
                "line": line,
                "passage": passage,
                "owner": owner,
            }
        )


def _scan_block(
    *,
    path: str,
    body: str,
    start_line: int,
    passage: str | None,
    owner: str | None,
    symbols: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    variables: list[dict[str, Any]],
) -> None:
    body_lines = _new_line_positions(body)
    for match in MACRO_RE.finditer(body):
        name = match.group("name")
        args = match.group("args")
        line = start_line + _line_number_fast(body_lines, match.start()) - 1
        lower = name.lower()
        if lower == "widget":
            widget_match = re.search(r"(?:[\"'])([^\"']+)(?:[\"'])", args)
            widget = widget_match.group(1) if widget_match else args.strip().split()[0] if args.strip() else ""
            symbols.append(
                {"kind": "widget", "name": widget, "path": path, "line": line, "passage": passage, "owner": owner}
            )
        elif lower in {"if", "elseif", "else"}:
            symbols.append(
                {"kind": "condition", "name": lower, "expression": args.strip(), "path": path, "line": line, "passage": passage, "owner": owner}
            )
        target, target_kind = _target_from_macro(name, args)
        if lower in {"link", "button", "goto", "include", "run"}:
            edges.append(
                {
                    "kind": "macro",
                    "macro": name,
                    "source": passage,
                    "target": target,
                    "target_kind": target_kind,
                    "expression": args.strip(),
                    "path": path,
                    "line": line,
                    "owner": owner,
                }
            )
    for link in LINK_RE.finditer(body):
        target = _clean_target(link.group("body"))
        edges.append(
            {
                "kind": "wiki_link",
                "source": passage,
                "target": target,
                "target_kind": _target_kind(target),
                "expression": link.group("body"),
                "path": path,
                "line": start_line + _line_number_fast(body_lines, link.start()) - 1,
                "owner": owner,
            }
        )
    _append_variable_rows(
        variables,
        body,
        path=path,
        passage=passage,
        owner=owner,
        line_positions=body_lines,
    )


def scan_text(path: str, text: str, *, owner: str | None = None) -> SourceFile:
    """Scan one source file and return a deterministic structured record."""
    raw = text.encode("utf-8", errors="replace")
    suffix = Path(path).suffix.lower()
    record = SourceFile(path=path, sha256=_sha256(raw), bytes=len(raw), kind=suffix.lstrip("."), owner=owner)
    blocks: list[tuple[str | None, str, int]] = []
    if suffix in {".twee", ".tw", ".txt"}:
        matches = list(PASSAGE_HEADER_RE.finditer(text))
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            name = match.group("name").strip()
            blocks.append((name, text[match.end():end], _line_number(text, match.end())))
    elif suffix in {".html", ".htm"}:
        text_lines = _new_line_positions(text)
        for match in HTML_PASSAGE_RE.finditer(text):
            name = _html_name(match.group("attrs"))
            if name is not None:
                blocks.append(
                    (
                        html.unescape(name),
                        html.unescape(match.group("body")),
                        _line_number_fast(text_lines, match.start("body")),
                    )
                )
    else:
        blocks.append((None, text, 1))

    for name, body, line in blocks:
        if name is not None:
            record.passages.append({"name": name, "path": path, "line": line, "owner": owner})
            record.symbols.append({"kind": "passage", "name": name, "path": path, "line": line, "owner": owner})
        _scan_block(
            path=path,
            body=body,
            start_line=line,
            passage=name,
            owner=owner,
            symbols=record.symbols,
            edges=record.edges,
            variables=record.variables,
        )

    for match in ENGINE_PLAY_RE.finditer(text):
        argument = match.group("arg").strip()
        literal = STRING_RE.match(argument)
        target = literal.group(2) if literal else None
        record.edges.append(
            {
                "kind": "engine_play",
                "source": None,
                "target": target,
                "target_kind": _target_kind(target),
                "expression": argument,
                "path": path,
                "line": _line_number(text, match.start()),
                "owner": owner,
            }
        )
    for match in CONFIG_NAV_RE.finditer(text):
        record.edges.append(
            {
                "kind": "navigation_override",
                "source": None,
                "target": None,
                "target_kind": "dynamic",
                "expression": match.group("expr").strip(),
                "path": path,
                "line": _line_number(text, match.start()),
                "owner": owner,
            }
        )
    return record


def _iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def build_index(root: Path, *, owner: str | None = None, source_commit: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    files: list[dict[str, Any]] = []
    for path in _iter_files(root):
        raw = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(root.parent if root.is_file() else root)).replace("\\", "/")
        files.append(scan_text(relative, raw, owner=owner).to_json())
    passages = [item for file in files for item in file["passages"]]
    symbols = [item for file in files for item in file["symbols"]]
    edges = [item for file in files for item in file["edges"]]
    variables = [item for file in files for item in file["variables"]]
    return {
        "schema": "dolx.source-index.v1",
        "source_commit": source_commit,
        "root": str(root),
        "files": files,
        "passages": passages,
        "symbols": symbols,
        "edges": edges,
        "variables": variables,
        "stats": {
            "files": len(files),
            "passages": len(passages),
            "symbols": len(symbols),
            "edges": len(edges),
            "static_edges": sum(1 for edge in edges if edge.get("target_kind") == "static"),
            "dynamic_edges": sum(1 for edge in edges if edge.get("target_kind") == "dynamic"),
            "variable_reads": sum(1 for row in variables if row.get("kind") == "read"),
            "variable_writes": sum(1 for row in variables if row.get("kind") == "write"),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="source directory or HTML/Twee file")
    parser.add_argument("--owner")
    parser.add_argument("--source-commit")
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_index(args.root, owner=args.owner, source_commit=args.source_commit)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
