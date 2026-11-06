#!/usr/bin/env python3
"""Adversarial tests for the block registry verifier (verify-block-registry.py)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-block-registry.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_block_registry", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass's deferred-annotation resolution looks the module up by name
    # in sys.modules, so it must be registered before exec_module runs it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SVG_HEAD = (
    '<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="t-title t-desc">'
    "<title id=\"t-title\">T</title><desc id=\"t-desc\">T.</desc>"
)


def document(body: str) -> str:
    return f"<!DOCTYPE html><html><body>{SVG_HEAD}{body}</svg></body></html>"


def block(block_id: str, parent: str | None = None, name: str | None = "Name", extra: str = "") -> str:
    parent_attr = f' data-block-parent="{parent}"' if parent is not None else ""
    name_attr = f' data-block-name="{name}"' if name is not None else ""
    return (
        f'<rect x="0" y="0" width="160" height="48" rx="6" data-block-id="{block_id}"'
        f"{parent_attr}{name_attr}{extra}/>"
    )


def main() -> int:
    module = load_verifier()
    failures: list[str] = []

    def check(label: str, source: str, expect_findings: int) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if len(findings) != expect_findings:
            failures.append(
                f"{label}: expected {expect_findings} finding(s), got "
                f"{len(findings)}: {findings}"
            )
        else:
            print(f"OK: {label}")

    # A single root block, no parent attribute at all, is legal.
    check("single root block", document(block("BLK-001")), 0)

    # A valid parent-child pair, parent resolves to a real sibling id.
    check(
        "valid parent-child pair",
        document(block("BLK-001") + block("BLK-001-01", parent="BLK-001")),
        0,
    )

    # A valid three-level chain, root -> child -> grandchild.
    check(
        "valid three-level chain",
        document(
            block("BLK-001")
            + block("BLK-001-01", parent="BLK-001")
            + block("BLK-001-01-01", parent="BLK-001-01")
        ),
        0,
    )

    # Two children sharing one valid parent is ordinary breadth, not a defect.
    check(
        "shared parent, two children",
        document(
            block("BLK-001")
            + block("BLK-001-01", parent="BLK-001")
            + block("BLK-001-02", parent="BLK-001")
        ),
        0,
    )

    # Two blocks copy-pasted with the same id is the defect this exists to catch.
    check(
        "duplicate id",
        document(block("BLK-001") + block("BLK-001", name="Renamed")),
        1,
    )

    # A parent attribute pointing at an id absent from the file — a renamed or
    # deleted parent left a dangling reference behind.
    check(
        "orphan parent reference",
        document(block("BLK-001-01", parent="BLK-999")),
        1,
    )

    # A block whose own id is its parent — the smallest possible cycle.
    check(
        "self-parent cycle",
        document(block("BLK-001", parent="BLK-001")),
        1,
    )

    # Two blocks whose parents point at each other — no root either could reach.
    check(
        "two-node cycle",
        document(
            block("BLK-001", parent="BLK-002") + block("BLK-002", parent="BLK-001")
        ),
        1,
    )

    # An id with no data-block-name attribute at all.
    check(
        "missing name attribute",
        document(block("BLK-001", name=None)),
        1,
    )

    # data-block-name present but empty is the same defect as absent.
    check(
        "empty name attribute",
        document(block("BLK-001", name="")),
        1,
    )

    # data-block-name present but whitespace-only is the same defect as empty.
    check(
        "whitespace-only name attribute",
        document(block("BLK-001", name="   ")),
        1,
    )

    # data-block-id present but empty must not silently satisfy itself as a
    # valid, resolvable identifier.
    check(
        "empty id attribute",
        document(block("")),
        1,
    )

    # data-block-id present but whitespace-only is the same defect as empty.
    check(
        "whitespace-only id attribute",
        document(block("   ")),
        1,
    )

    # A blank id must never act as a resolvable identifier. Two otherwise-valid
    # blocks joined only by "" used to report 0 findings — a coherent tree
    # built from an empty string. Now both broken attributes are reported: the
    # blank id itself, and the child's blank data-block-parent as unresolved.
    check(
        "blank id never satisfies a blank parent",
        document(block("") + block("BLK-001", parent="")),
        2,
    )

    # data-block-parent present but empty is a dangling reference, not root;
    # absent-means-root is the only root convention (export-registry.md).
    check(
        "blank parent attribute is unresolved",
        document(block("BLK-001") + block("BLK-001-01", parent="")),
        1,
    )

    # A diagram that doesn't use the pattern at all has no data-block-id
    # anywhere — legal; most Tree diagrams will look like this.
    check(
        "no blocks in file",
        document('<rect x="0" y="0" width="160" height="48" rx="6"/>'),
        0,
    )

    # A node carrying an unrelated data-* attribute, but no data-block-id, is
    # not a block and must not be collected as one.
    check(
        "unrelated data attribute is not a block",
        document('<rect x="0" y="0" width="160" height="48" rx="6" data-foo="bar"/>'),
        0,
    )

    # The full optional metadata set (input/output/constraint/assumption/impl)
    # must parse cleanly without tripping any check.
    check(
        "full optional metadata set present",
        document(
            block(
                "BLK-001",
                extra=(
                    ' data-block-input="card details" data-block-output="auth token"'
                    ' data-block-constraint="single writer" data-block-assumption="PCI boundary"'
                    ' data-block-impl="src/payments/authorization/"'
                ),
            )
        ),
        0,
    )

    # Two unrelated root blocks (no shared ancestor) in one file — a diagram
    # can legally show more than one top-level block.
    check(
        "multiple independent trees",
        document(block("BLK-001") + block("BLK-002")),
        0,
    )

    # A literal '>' inside a quoted attribute value, positioned BEFORE
    # data-block-id in the tag, is valid HTML and must not truncate the tag
    # match — a naive [^>]* match would lose data-block-id entirely and the
    # block would silently vanish (0 findings AND 0 blocks, a false-clean
    # pass on a file that has a real, valid block).
    check(
        "literal greater-than before id does not truncate the tag",
        document(
            '<rect data-block-constraint="output > input" data-block-id="BLK-001" '
            'data-block-name="X" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # Same hazard with the '>' positioned after id/name — must also survive;
    # this ordering happened to work even before the fix, so it guards
    # against a regression that only re-breaks the before-id ordering above.
    check(
        "literal greater-than after id does not truncate the tag",
        document(
            '<rect data-block-id="BLK-001" data-block-name="X" '
            'data-block-constraint="output > input" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # Single-quoted attribute values are valid HTML; the parser must not
    # silently see zero blocks on a file that uses them.
    check(
        "single-quoted attribute values are recognized",
        document(
            "<rect data-block-id='BLK-001' data-block-name='X' "
            "x='0' y='0' width='160' height='48' rx='6'/>"
        ),
        0,
    )

    # Mixed quoting within one tag -- an adversarial author (or a hand-edit)
    # might quote some attributes one way and others another; both must be
    # read, not just whichever style the parser happens to expect.
    check(
        "mixed quoting styles in one tag",
        document(
            '<rect data-block-id="BLK-001" data-block-name=\'X\' '
            'data-block-parent="BLK-000" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        1,  # data-block-parent references BLK-000, which this document never defines
    )

    # Unquoted attribute values are valid HTML; a browser reads them the same
    # as quoted ones, and so must this parser.
    check(
        "unquoted attribute values are recognized",
        document('<rect data-block-id=BLK-001 data-block-name=X x="0" y="0" width="160" height="48" rx="6"/>'),
        0,
    )

    # Whitespace around the '=' is valid HTML; a naive attribute regex
    # anchored on `name="value"` misses it entirely.
    check(
        "whitespace around the attribute equals sign is recognized",
        document(
            '<rect data-block-id = "BLK-001" data-block-name\t=\t"X" '
            'x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # data-block-* attribute names are case-insensitive in HTML, same as any
    # other attribute name; a browser (and this parser) lowercases them.
    check(
        "case-insensitive data-block-* attribute names are recognized",
        document(
            '<rect DATA-BLOCK-ID="BLK-001" Data-Block-Name="X" '
            'x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # A boolean/valueless data-block-id (present, no '=' at all) is a real,
    # present attribute with a blank value -- it must surface as a blank-id
    # finding, not vanish the whole element from the scan the way "id" not
    # in attrs used to when the attribute carried no value.
    check(
        "a boolean data-block-id attribute is a blank id, not an invisible block",
        document('<rect data-block-id data-block-name="X" x="0" y="0" width="160" height="48" rx="6"/>'),
        1,
    )

    # A commented-out block must never be scanned as live: pairing it with a
    # real block sharing the same id proves it, since a parser that (wrongly)
    # read tag-like text inside a comment would report a duplicate id here.
    check(
        "a commented-out block is not scanned as live",
        document(
            block("BLK-001")
            + '<!-- <rect data-block-id="BLK-001" data-block-name="Ghost"/> -->'
        ),
        0,
    )

    # HTML gives precedence to an attribute's first occurrence within one
    # tag; a duplicated data-block-id must resolve the same way a browser's
    # DOM would, not to whichever value a scanner happened to see last.
    # Proven the same way "mixed quoting" is: the resulting id collides with
    # a real block's id only if the *first* value ("BLK-001") won.
    check(
        "a duplicated attribute name keeps its first value, matching a browser",
        document(
            block("BLK-001")
            + '<rect data-block-id="BLK-001" data-block-id="BLK-002" data-block-name="X"/>'
        ),
        1,  # duplicate data-block-id "BLK-001", only if the first value was kept
    )

    # ---- Repo-backed --repo-root and root-inheritable data-block-rev tests ----
    import subprocess as sp

    with tempfile.TemporaryDirectory() as repo_tmp:
        repo = Path(repo_tmp) / "repo"
        (repo / "src/pkg").mkdir(parents=True)
        sp.run(["git", "init", str(repo)], check=True, capture_output=True)
        sp.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
        sp.run(["git", "-C", str(repo), "config", "user.name", "Tester"], check=True)
        (repo / "src/pkg/mod.py").write_text("line1\nline2\n", encoding="utf-8")
        sp.run(["git", "-C", str(repo), "add", "."], check=True)
        sp.run(["git", "-C", str(repo), "commit", "-m", "c1"], check=True, capture_output=True)
        rev1 = sp.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

        (repo / "src/pkg/mod.py").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
        sp.run(["git", "-C", str(repo), "add", "."], check=True)
        sp.run(["git", "-C", str(repo), "commit", "-m", "c2"], check=True, capture_output=True)
        rev2 = sp.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

        def check_repo(label: str, source: str, target_root: Path | None, expect_findings: int, needle: str = "") -> None:
            with tempfile.TemporaryDirectory() as scratch:
                candidate = Path(scratch) / "candidate.html"
                candidate.write_text(source, encoding="utf-8")
                findings = module.check(candidate, repo_root=target_root)
            if len(findings) != expect_findings or (needle and not any(needle in f for f in findings)):
                failures.append(
                    f"{label}: expected {expect_findings} finding(s) ({needle!r}), got {len(findings)}: {findings}"
                )
            else:
                print(f"OK: {label}")

        # 1. Root/ancestor inheritance: <html data-block-rev=rev1> inherited by directory + file blocks
        inherited_doc = (
            f'<!DOCTYPE html><html data-block-rev="{rev1}"><body>{SVG_HEAD}'
            + block("BLK-DIR", extra=' data-block-impl="src/pkg/"')
            + block("BLK-FILE", parent="BLK-DIR", extra=' data-block-impl="src/pkg/mod.py#L1-L2"')
            + "</svg></body></html>"
        )
        check_repo("inherited root data-block-rev passes tree and blob line bounds", inherited_doc, repo, 0)

        # 2. Override precedence: ancestor has rev1 (2 lines), block overrides with rev2 (4 lines) -> #L1-L4 passes!
        override_doc = (
            f'<!DOCTYPE html><html data-block-rev="{rev1}"><body>{SVG_HEAD}'
            + block("BLK-OVR", extra=f' data-block-rev="{rev2}" data-block-impl="src/pkg/mod.py#L1-L4"')
            + "</svg></body></html>"
        )
        check_repo("block data-block-rev overrides ancestor data-block-rev", override_doc, repo, 0)

        # 3. Same #L1-L4 without override inherits rev1 (only 2 lines) -> fails closed naming candidate.html:<line>
        stale_inherited_doc = (
            f'<!DOCTYPE html><html data-block-rev="{rev1}"><body>{SVG_HEAD}\n'
            + block("BLK-STALE", extra=' data-block-impl="src/pkg/mod.py#L1-L4"')
            + "\n</svg></body></html>"
        )
        check_repo("inherited rev1 catches out-of-range line bound", stale_inherited_doc, repo, 1, "candidate.html:2:")

        # 4. Absent revision: passes structural-only mode without --repo-root, fails closed WITH --repo-root
        no_rev_doc = document("\n" + block("BLK-NOREV", extra=' data-block-impl="src/pkg/mod.py#L1-L2"'))
        check_repo("absent rev without --repo-root stays backward-compatible", no_rev_doc, None, 0)
        check_repo("absent rev with --repo-root fails closed on data-block-impl", no_rev_doc, repo, 1, "candidate.html:2:")

        # 5. Malformed data-block-rev (non-40-hex or blank) fails closed with exact line number
        bad_anc_rev = f'<!DOCTYPE html>\n<html data-block-rev="not-a-sha"><body>{SVG_HEAD}{block("BLK-1")}</svg></body></html>'
        check_repo("malformed ancestor data-block-rev reports offending line", bad_anc_rev, None, 1, "candidate.html:2:")
        bad_blk_rev = document("\n" + block("BLK-1", extra=' data-block-rev=""'))
        check_repo("blank block data-block-rev reports offending line", bad_blk_rev, None, 1, "candidate.html:2:")

        # 6. Malformed data-block-impl syntax fails closed
        check_repo("traversal data-block-impl rejected", document("\n" + block("BLK-1", extra=' data-block-impl="../secret.py"')), None, 1, "candidate.html:2:")
        check_repo("inverted line range rejected", document("\n" + block("BLK-1", extra=' data-block-impl="src/pkg/mod.py#L4-L2"')), None, 1, "candidate.html:2:")

        # 7. Unknown commit SHA, missing path, tree/blob mismatch, and non-toplevel --repo-root
        dead_sha = "deadbeef" * 5
        check_repo(
            "missing commit SHA rejected offline",
            document("\n" + block("BLK-1", extra=f' data-block-rev="{dead_sha}" data-block-impl="src/pkg/mod.py"')),
            repo,
            1,
            "candidate.html:2:",
        )
        check_repo(
            "directory cited without trailing slash or file cited with trailing slash fails",
            f'<!DOCTYPE html><html data-block-rev="{rev2}"><body>{SVG_HEAD}\n'
            + block("BLK-1", extra=' data-block-impl="src/pkg/mod.py/"')
            + "</svg></body></html>",
            repo,
            1,
            "candidate.html:2:",
        )
        check_repo("non-toplevel --repo-root subdirectory fails closed", inherited_doc, repo / "src", 1, "--repo-root")

        # 8. CLI exit codes
        with tempfile.TemporaryDirectory() as cli_tmp:
            good_html = Path(cli_tmp) / "good.html"
            bad_html = Path(cli_tmp) / "bad.html"
            good_html.write_text(inherited_doc, encoding="utf-8")
            bad_html.write_text(stale_inherited_doc, encoding="utf-8")
            rc_ok = sp.run([sys.executable, str(VERIFIER), "--repo-root", str(repo), str(good_html)], capture_output=True, text=True)
            rc_bad = sp.run([sys.executable, str(VERIFIER), "--repo-root", str(repo), str(bad_html)], capture_output=True, text=True)
            if rc_ok.returncode != 0:
                failures.append(f"CLI --repo-root good.html expected 0, got {rc_ok.returncode}: {rc_ok.stdout}{rc_ok.stderr}")
            else:
                print("OK: CLI --repo-root exits 0 on valid citations")
            if rc_bad.returncode != 1 or "bad.html:2:" not in rc_bad.stdout:
                failures.append(f"CLI --repo-root bad.html expected 1 with bad.html:2:, got {rc_bad.returncode}: {rc_bad.stdout}")
            else:
                print("OK: CLI --repo-root exits 1 naming file:line on invalid citation")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All block registry tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
