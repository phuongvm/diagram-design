#!/usr/bin/env python3
"""Keep every Publication Manual page's `<script data-manual-controls>` equal to the canonical one.

The canonical controller is the body of the `<script data-manual-controls>` element in
`assets/template-manual.html`. Edit it there only, then propagate:

    python3 scripts/sync_manual_controls.py --write docs/index.html docs/guide.html
    python3 scripts/sync_manual_controls.py --check <template> docs/index.html docs/guide.html

`--check` prints `DIVERGENT: <path>` per page whose normalized controller body differs (or that has no
controller) and exits 1. `--write` replaces only the controller body (the bytes between the opening
`<script data-manual-controls>` tag and its `</script>`); every other byte is preserved. A bare file
list is treated as `--check`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CANONICAL = SKILL_DIR / "assets" / "template-manual.html"
SCRIPT_RE = re.compile(
    r"(?P<open><script\b(?=[^>]*\bdata-manual-controls\b)[^>]*>)(?P<body>.*?)(?P<close></script\s*>)",
    re.IGNORECASE | re.DOTALL,
)


def normalize(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def find_controllers(source: str) -> list[re.Match[str]]:
    return list(SCRIPT_RE.finditer(source))


def read(path: Path) -> str:
    # newline="" keeps the page's own line endings untouched for --write.
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def canonical_body(template: Path = CANONICAL) -> str:
    matches = find_controllers(read(template))
    if len(matches) != 1:
        raise RuntimeError(f"{template} must contain exactly one <script data-manual-controls>; found {len(matches)}")
    return normalize(matches[0].group("body"))


def divergence(path: Path, canonical: str) -> str | None:
    """Return a reason the page differs from the canonical controller, or None when it matches."""
    matches = find_controllers(read(path))
    if len(matches) != 1:
        return f"{len(matches)} <script data-manual-controls> elements (expected 1)"
    return None if normalize(matches[0].group("body")) == canonical else "controller body differs"


def rewrite(source: str, canonical: str) -> str:
    """Replace only the controller body, keeping the page's own newline style."""
    match = find_controllers(source)[0]
    newline = "\r\n" if "\r\n" in match.group("body") or "\r\n" in source[: match.start()] else "\n"
    body = canonical.replace("\n", newline)
    lead = re.match(r"\s*", match.group("body")).group(0)
    tail = re.search(r"\s*\Z", match.group("body")).group(0)
    return source[: match.start("body")] + lead + body + tail + source[match.end("body") :]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="report divergent pages (default)")
    mode.add_argument("--write", action="store_true", help="replace the controller body in each page")
    parser.add_argument("--canonical", type=Path, default=CANONICAL, help="canonical template (default: shipped)")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        canonical = canonical_body(args.canonical)
    except (OSError, UnicodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    failed = False
    for path in args.files:
        try:
            if args.write:
                source = read(path)
                matches = find_controllers(source)
                if len(matches) != 1:
                    raise RuntimeError(f"{len(matches)} <script data-manual-controls> elements (expected 1)")
                updated = rewrite(source, canonical)
                if updated != source:
                    with path.open("w", encoding="utf-8", newline="") as handle:
                        handle.write(updated)
                    print(f"WROTE: {path}")
                else:
                    print(f"UNCHANGED: {path}")
            else:
                reason = divergence(path, canonical)
                if reason:
                    failed = True
                    print(f"DIVERGENT: {path} ({reason})")
        except (OSError, UnicodeError, RuntimeError) as exc:
            failed = True
            print(f"DIVERGENT: {path} ({exc})")
    if not args.write and not failed:
        print(f"OK: {len(args.files)} file(s) match the canonical controller")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
