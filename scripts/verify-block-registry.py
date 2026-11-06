#!/usr/bin/env python3
"""Verify a Traceable block decomposition diagram's data-block-* metadata.

semantic-patterns.md § 8 requires every block to carry a stable, unique,
non-blank data-block-id, a non-blank data-block-name, and (when present) a
data-block-parent that resolves to another block's id in the same file, with
no cycles in the parent chain -- the same "no orphan blocks, no cycles" shape
Tree's own layout already assumes. Nothing in the SVG grammar enforces that
on its own: a copy-pasted node keeps its sibling's id, a renamed block leaves
its children pointing at an id that no longer exists, an empty id="" passes
as a real identifier, and all of them render as an ordinary,
unremarkable-looking diagram.

This does not correlate a block's metadata against its drawn position or
connector geometry -- see export-registry.md "What this never does". It is a
metadata-only structural check, not a visual layout check, and it is
independent of verify-geometry.py: that script catches a label mask clipped
by a node painted after it, this one catches a block registry that does not
cohere as a tree.

Parsing goes through the stdlib html.parser.HTMLParser rather than a regex,
so a block is recognized exactly when a browser would recognize its
data-block-* attributes: unquoted values, whitespace around `=`, and
case-insensitive attribute names all parse the same as their canonical form,
a comment's contents are never scanned as live markup (HTMLParser routes
`<!-- ... -->` to handle_comment, never to handle_starttag), and a repeated
attribute name keeps its first value, matching how a browser resolves a
duplicate attribute in one tag. A blank or boolean attribute (data-block-id
present with no value at all) still counts as the attribute being present --
with an empty string -- so it is reported as a blank id or blank name
finding rather than silently making the whole block invisible to the scan.
The prior regex scanner's quoted-`>` fix is superseded by this: a real regex
tag matcher cannot separate "not yet closed" from "attribute value contains
a literal `>`" for every valid quoting and spacing HTML allows, and each
such gap was the same failure shape -- a real block silently vanishing from
the scan, CI green as if the file had none.

Usage:
    python3 scripts/verify-block-registry.py --all
    python3 scripts/verify-block-registry.py skills/diagram-design/assets/example-x.html
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

DATA_BLOCK_PREFIX = "data-block-"
HEX_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
LINE_FRAGMENT_RE = re.compile(r"^L([1-9]\d*)(?:-L([1-9]\d*))?$")
VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


@dataclass
class Block:
    id: str
    parent: str | None
    name: str | None
    line: int
    rev: str | None = None
    rev_line: int | None = None
    impl: str | None = None
    has_own_rev: bool = False


class _BlockScanner(HTMLParser):
    """Collect one Block per start tag carrying a data-block-id attribute.

    Tracks enclosing ancestor elements that declare data-block-rev so blocks
    without their own data-block-rev inherit the nearest ancestor revision.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.rev_declarations: list[tuple[int, str]] = []
        self._stack: list[tuple[str, str | None, int | None]] = []

    def _inherited_rev(self) -> tuple[str | None, int | None]:
        for _tag, rev, rev_line in reversed(self._stack):
            if rev is not None:
                return rev, rev_line
        return None, None

    def _process_tag(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        tag_lower = tag.casefold()
        line = self.getpos()[0]
        seen: dict[str, str | None] = {}
        for name, value in attrs:
            seen.setdefault(name, value)

        block_attrs: dict[str, str] = {}
        for name, value in seen.items():
            if name.startswith(DATA_BLOCK_PREFIX):
                block_attrs[name[len(DATA_BLOCK_PREFIX) :]] = value if value is not None else ""

        own_rev = block_attrs.get("rev")
        if own_rev is not None:
            self.rev_declarations.append((line, own_rev))

        inherited_rev, inherited_line = self._inherited_rev()
        effective_rev = own_rev if own_rev is not None else inherited_rev
        effective_rev_line = line if own_rev is not None else inherited_line

        if "id" in block_attrs:
            self.blocks.append(
                Block(
                    id=block_attrs["id"],
                    parent=block_attrs.get("parent"),
                    name=block_attrs.get("name"),
                    line=line,
                    rev=effective_rev,
                    rev_line=effective_rev_line,
                    impl=block_attrs.get("impl"),
                    has_own_rev=own_rev is not None,
                )
            )

        if not self_closing and tag_lower not in VOID_ELEMENTS:
            self._stack.append((tag_lower, own_rev, line if own_rev is not None else None))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_tag(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.casefold()
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx][0] == tag_lower:
                del self._stack[idx:]
                break


def parse_document(source: str) -> tuple[list[Block], list[tuple[int, str]]]:
    scanner = _BlockScanner()
    scanner.feed(source)
    scanner.close()
    return scanner.blocks, scanner.rev_declarations


def parse_blocks(source: str) -> list[Block]:
    blocks, _revs = parse_document(source)
    return blocks


def find_blank_ids(path: Path, blocks: list[Block]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if not block.id.strip():
            findings.append(
                f"{path.name}:{block.line}: block has a blank data-block-id"
            )
    return findings


def find_duplicates(path: Path, blocks: list[Block]) -> list[str]:
    by_id: dict[str, list[Block]] = {}
    for block in blocks:
        by_id.setdefault(block.id, []).append(block)

    findings: list[str] = []
    for block_id, group in by_id.items():
        if len(group) > 1:
            lines = ", ".join(str(b.line) for b in group)
            findings.append(
                f'{path.name}: duplicate data-block-id "{block_id}" at lines {lines}'
            )
    return findings


def find_orphan_parents(path: Path, blocks: list[Block], known_ids: set[str]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if block.parent is not None and block.parent not in known_ids:
            findings.append(
                f'{path.name}:{block.line}: data-block-parent "{block.parent}" on block '
                f'"{block.id}" does not match any data-block-id in this file'
            )
    return findings


def find_missing_names(path: Path, blocks: list[Block]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if not block.name or not block.name.strip():
            findings.append(
                f'{path.name}:{block.line}: block "{block.id}" has a missing or blank data-block-name'
            )
    return findings


def find_cycles(path: Path, blocks: list[Block], known_ids: set[str]) -> list[str]:
    parent_of = {block.id: block.parent for block in blocks}
    findings: list[str] = []
    reported: set[str] = set()

    for block in blocks:
        if block.id in reported:
            continue
        chain: list[str] = []
        current: str | None = block.id
        while current is not None:
            if current in chain:
                cycle = chain[chain.index(current) :] + [current]
                reported.update(cycle)
                findings.append(f'{path.name}: parent cycle: {" -> ".join(cycle)}')
                break
            chain.append(current)
            if current not in known_ids:
                break  # broken parent reference; already reported by find_orphan_parents
            current = parent_of.get(current)
    return findings


def parse_impl(raw_impl: str) -> tuple[str, bool, int | None, int | None] | None:
    """Parse data-block-impl="<repo-rel-posix-path>[#L<start>[-L<end>]]"."""
    val = raw_impl.strip()
    if not val or "\\" in val or val.startswith("/"):
        return None
    if "#" in val:
        rel_path, fragment = val.split("#", 1)
        m = LINE_FRAGMENT_RE.fullmatch(fragment)
        if m is None or rel_path.endswith("/"):
            return None
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) is not None else start
        if start > end:
            return None
    else:
        rel_path = val
        start = end = None
    is_dir = rel_path.endswith("/")
    cleaned = rel_path.rstrip("/")
    if not cleaned:
        return None
    parts = PurePosixPath(cleaned).parts
    if not parts or any(p in ("", ".", "..") or ":" in p for p in parts):
        return None
    return cleaned, is_dir, start, end


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_ALLOW_PROTOCOL"] = ""
    return env


def _batch_cat_objects(real_root: Path, specs: list[str]) -> dict[str, tuple[str, bytes]]:
    if not specs:
        return {}
    proc = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(real_root), "cat-file", "--batch"],
        input="".join(f"{s}\n" for s in specs).encode("utf-8"),
        capture_output=True,
        env=_git_env(),
        check=False,
    )
    out = proc.stdout
    pos = 0
    results: dict[str, tuple[str, bytes]] = {}
    for spec in specs:
        nl = out.find(b"\n", pos)
        if nl < 0:
            results[spec] = ("missing", b"")
            break
        header = out[pos:nl].decode("utf-8", errors="replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) < 2 or parts[-1] == "missing":
            results[spec] = ("missing", b"")
            continue
        obj_type = parts[1]
        size = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        payload = out[pos : pos + size]
        pos += size
        if pos < len(out) and out[pos : pos + 1] == b"\n":
            pos += 1
        results[spec] = (obj_type, payload)
    return results


def verify_citations(
    path: Path,
    blocks: list[Block],
    rev_declarations: list[tuple[int, str]],
    repo_root: Path | None,
) -> list[str]:
    findings: list[str] = []
    bad_rev_lines: set[int] = set()
    for line, rev_val in rev_declarations:
        if not HEX_SHA40_RE.fullmatch(rev_val):
            findings.append(
                f'{path.name}:{line}: malformed data-block-rev "{rev_val}" (expected 40 lowercase hex characters)'
            )
            bad_rev_lines.add(line)

    parsed_impls: list[tuple[Block, str, bool, int | None, int | None]] = []
    for block in blocks:
        if block.impl is None:
            continue
        parsed = parse_impl(block.impl)
        if parsed is None:
            findings.append(
                f'{path.name}:{block.line}: block "{block.id}" has malformed data-block-impl "{block.impl}"'
            )
            continue
        rel_path, is_dir, start, end = parsed
        parsed_impls.append((block, rel_path, is_dir, start, end))

    if repo_root is None:
        return findings

    candidate_root: Path | None = None
    try:
        candidate_root = Path(repo_root).resolve()
        top_proc = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(candidate_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            env=_git_env(),
            check=False,
        )
        toplevel = Path(top_proc.stdout.strip()).resolve() if top_proc.returncode == 0 and top_proc.stdout.strip() else None
    except OSError:
        toplevel = None

    if candidate_root is None or toplevel is None or toplevel != candidate_root:
        findings.append(
            f'{path.name}:1: --repo-root "{repo_root}" does not match git rev-parse --show-toplevel'
        )
        return findings

    valid_revs: dict[str, int] = {}
    for line, rev_val in rev_declarations:
        if line not in bad_rev_lines and rev_val not in valid_revs:
            valid_revs[rev_val] = line

    commit_specs = [f"{rev}^{{commit}}" for rev in valid_revs]
    commit_objs = _batch_cat_objects(candidate_root, commit_specs)
    missing_revs: set[str] = set()
    for rev, line in valid_revs.items():
        obj_type, _ = commit_objs.get(f"{rev}^{{commit}}", ("missing", b""))
        if obj_type != "commit":
            findings.append(
                f'{path.name}:{line}: data-block-rev "{rev}" does not resolve to a local commit'
            )
            missing_revs.add(rev)

    obj_specs: list[str] = []
    pending_checks: list[tuple[Block, str, str, bool, int | None, int | None]] = []
    for block, rel_path, is_dir, start, end in parsed_impls:
        if block.rev is None:
            findings.append(
                f'{path.name}:{block.line}: block "{block.id}" has data-block-impl "{block.impl}" without an effective data-block-rev'
            )
            continue
        if not HEX_SHA40_RE.fullmatch(block.rev) or block.rev in missing_revs:
            continue
        spec = f"{block.rev}:{rel_path}"
        if spec not in obj_specs:
            obj_specs.append(spec)
        pending_checks.append((block, spec, rel_path, is_dir, start, end))

    repo_objs = _batch_cat_objects(candidate_root, obj_specs)
    for block, spec, _rel_path, is_dir, start, end in pending_checks:
        obj_type, payload = repo_objs.get(spec, ("missing", b""))
        expected_type = "tree" if is_dir else "blob"
        if obj_type != expected_type:
            findings.append(
                f'{path.name}:{block.line}: data-block-impl "{block.impl}" on block "{block.id}" resolved to {obj_type} (expected {expected_type} at {block.rev})'
            )
            continue
        if not is_dir and start is not None and end is not None:
            line_count = len(payload.splitlines())
            if start < 1 or end > line_count:
                findings.append(
                    f'{path.name}:{block.line}: data-block-impl "{block.impl}" on block "{block.id}" exceeds blob line count ({line_count}) at {block.rev}'
                )
    return findings


def check(path: Path, repo_root: Path | None = None) -> list[str]:
    source = path.read_text(encoding="utf-8")
    blocks, rev_declarations = parse_document(source)
    if not blocks:
        return []  # not every diagram uses the pattern; that's legal

    # A blank id is never a resolvable target: a blank data-block-parent must
    # report as unresolved, not quietly match a block whose id is also blank.
    known_ids = {block.id for block in blocks if block.id.strip()}
    findings: list[str] = []
    findings.extend(find_blank_ids(path, blocks))
    findings.extend(find_duplicates(path, blocks))
    findings.extend(find_orphan_parents(path, blocks, known_ids))
    findings.extend(find_missing_names(path, blocks))
    findings.extend(find_cycles(path, blocks, known_ids))
    findings.extend(verify_citations(path, blocks, rev_declarations, repo_root))
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset")
    parser.add_argument("--repo-root", type=Path, default=None, help="verify data-block-rev and data-block-impl against local git objects")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    for path in paths:
        if not path.exists():
            findings.append(f"{path}: file not found")
            continue
        findings.extend(check(path, repo_root=args.repo_root))

    for finding in findings:
        print(finding)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
