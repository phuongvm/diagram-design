#!/usr/bin/env python3
"""Adversarial unit tests for scripts/verify-waterfall.py (Semantic Pattern §9)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-waterfall.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_waterfall", VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {VERIFIER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALID_MEASURED_SVG = """\
<!DOCTYPE html>
<html>
<body>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 220" role="img"
     aria-labelledby="wf-title wf-desc"
     data-waterfall-evidence="measured" data-waterfall-track-x="240" data-waterfall-track-width="640">
  <title id="wf-title">API request execution trace</title>
  <desc id="wf-desc">Measured waterfall trace across gateway, auth, and database spans.</desc>
  <defs>
    <style>
      :root {
        --svg-paper: #f5f5f5; --svg-panel: #eceef2; --svg-ink: #2d3142; --svg-muted: #4f5d75;
        --svg-green: #1f7a4c; --svg-green-tint: rgba(31,122,76,0.12);
        --svg-amber: #b86b11; --svg-amber-tint: rgba(184,107,17,0.12);
        --svg-blue: #2e5aa8; --svg-blue-tint: rgba(46,90,168,0.14);
        --svg-purple: #6b4ca8; --svg-purple-tint: rgba(107,76,168,0.14);
        --svg-red: #c23b2b; --svg-red-tint: rgba(194,59,43,0.14);
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --svg-paper: #161922; --svg-panel: #222736; --svg-ink: #f5f5f5; --svg-muted: #9aa5b8;
        }
      }
    </style>
  </defs>
  <rect x="0" y="0" width="960" height="220" fill="var(--svg-paper, #f5f5f5)"/>
  <g data-waterfall-badge>
    <rect x="24" y="16" width="88" height="20" rx="4" fill="var(--svg-green-tint, rgba(31,122,76,0.12))" stroke="var(--svg-green, #1f7a4c)"/>
    <text x="68" y="28" font-size="8" text-anchor="middle" fill="var(--svg-green, #1f7a4c)">MEASURED</text>
  </g>
  <g data-span-id="root" data-span-start="0" data-span-end="100">
    <text x="24" y="76" font-size="12" fill="var(--svg-ink, #2d3142)">GET /orders</text>
    <rect data-span-bar x="240" y="64" width="640" height="16" rx="4" fill="var(--svg-panel, #eceef2)" stroke="var(--svg-ink, #2d3142)"/>
    <text x="888" y="76" font-size="8" fill="var(--svg-muted, #4f5d75)">100ms</text>
  </g>
  <g data-span-id="auth" data-span-parent="root" data-span-start="0" data-span-end="25">
    <text x="40" y="108" font-size="12" fill="var(--svg-ink, #2d3142)">verify_jwt</text>
    <rect data-span-bar x="240" y="96" width="160" height="16" rx="4" fill="var(--svg-blue-tint, rgba(46,90,168,0.14))" stroke="var(--svg-blue, #2e5aa8)"/>
  </g>
  <g data-span-id="db" data-span-parent="root" data-span-start="25" data-span-end="100" data-span-status="error">
    <text x="40" y="140" font-size="12" fill="var(--svg-red, #c23b2b)">query_orders [ERR]</text>
    <rect data-span-bar x="400" y="128" width="480" height="16" rx="4" fill="var(--svg-red-tint, rgba(194,59,43,0.14))" stroke="var(--svg-red, #c23b2b)"/>
  </g>
</svg>
</body>
</html>
"""


def main() -> int:
    module = load_verifier()
    failures: list[str] = []

    def expect_pass(label: str, source: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "trace.html"
            p.write_text(source, encoding="utf-8")
            findings = module.check(p)
        if findings:
            failures.append(f"{label}: expected 0 findings, got {findings}")
        else:
            print(f"OK: {label}")

    def expect_fail(label: str, source: str, needle: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "trace.html"
            p.write_text(source, encoding="utf-8")
            findings = module.check(p)
        if not any(needle.casefold() in f.casefold() for f in findings):
            failures.append(f"{label}: expected finding with {needle!r}, got {findings}")
        else:
            print(f"OK: {label} rejected")

    expect_pass("valid measured waterfall trace", VALID_MEASURED_SVG)

    illustrative = (
        VALID_MEASURED_SVG.replace('data-waterfall-evidence="measured"', 'data-waterfall-evidence="illustrative"')
        .replace("MEASURED", "ILLUSTRATIVE")
        .replace("--svg-green-tint", "--svg-amber-tint")
        .replace("--svg-green, #1f7a4c", "--svg-amber, #b86b11")
    )
    expect_pass("valid illustrative waterfall trace", illustrative)

    expect_fail(
        "badge text mismatch (measured attribute with ILLUSTRATIVE badge)",
        VALID_MEASURED_SVG.replace("MEASURED", "ILLUSTRATIVE"),
        "badge",
    )
    expect_fail(
        "duplicate data-span-id",
        VALID_MEASURED_SVG.replace('data-span-id="db"', 'data-span-id="auth"'),
        "duplicate",
    )
    expect_fail(
        "cyclic data-span-parent chain",
        VALID_MEASURED_SVG.replace('data-span-id="root"', 'data-span-id="root" data-span-parent="db"'),
        "cycle",
    )
    expect_fail(
        "end < start timing violation",
        VALID_MEASURED_SVG.replace('data-span-start="0" data-span-end="25"', 'data-span-start="30" data-span-end="25"'),
        "end >= start",
    )
    expect_fail(
        "child span escaping parent envelope",
        VALID_MEASURED_SVG.replace('data-span-end="100" data-span-status="error"', 'data-span-end="120" data-span-status="error"'),
        "parent",
    )
    expect_fail(
        "off-grid bar height (14px instead of 16px)",
        VALID_MEASURED_SVG.replace('height="16"', 'height="14"', 1),
        "bar_h=16",
    )
    expect_fail(
        "off-grid row spacing (row_h=25 instead of 32)",
        VALID_MEASURED_SVG.replace('y="96"', 'y="89"'),
        "row_h=32",
    )
    expect_fail(
        "wrong depth indentation (indent != 16 * depth)",
        VALID_MEASURED_SVG.replace('<text x="40" y="108"', '<text x="46" y="108"'),
        "indent",
    )
    expect_fail(
        "disallowed font-size (10 instead of 12/8)",
        VALID_MEASURED_SVG.replace('font-size="12"', 'font-size="10"', 1),
        "font-size",
    )
    expect_fail(
        "parent bar missing --svg-panel / --svg-ink tokens",
        VALID_MEASURED_SVG.replace('fill="var(--svg-panel, #eceef2)"', 'fill="var(--svg-blue-tint, rgba(46,90,168,0.14))"'),
        "parent",
    )
    expect_fail(
        "error span missing [ERR] label",
        VALID_MEASURED_SVG.replace("query_orders [ERR]", "query_orders"),
        "[ERR]",
    )
    expect_fail(
        "raw #hex paint literal outside var(--svg-*, fallback)",
        VALID_MEASURED_SVG.replace('fill="var(--svg-paper, #f5f5f5)"', 'fill="#f5f5f5"'),
        "raw",
    )
    expect_fail(
        "disproportionate bar width (>2px error)",
        VALID_MEASURED_SVG.replace('width="160"', 'width="240"'),
        "proportional",
    )

    with tempfile.TemporaryDirectory() as cli_tmp:
        ok_file = Path(cli_tmp) / "ok.html"
        bad_file = Path(cli_tmp) / "bad.html"
        ok_file.write_text(VALID_MEASURED_SVG, encoding="utf-8")
        bad_file.write_text(VALID_MEASURED_SVG.replace('width="160"', 'width="240"'), encoding="utf-8")
        r_ok = subprocess.run([sys.executable, str(VERIFIER), str(ok_file)], capture_output=True, text=True)
        r_bad = subprocess.run([sys.executable, str(VERIFIER), str(bad_file)], capture_output=True, text=True)
        if r_ok.returncode != 0 or r_bad.returncode != 1:
            failures.append(f"CLI exit codes expected (0, 1), got ({r_ok.returncode}, {r_bad.returncode})")
        else:
            print("OK: CLI exit codes 0 on valid and 1 on invalid trace")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("All waterfall verifier tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
