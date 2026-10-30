#!/usr/bin/env python3
"""Adversarial tests for the packaged skill self-check (self_check.py)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF_CHECK = ROOT / "skills/diagram-design/scripts/self_check.py"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
TEMPLATE = ASSET_DIR / "template-motion.html"
EXAMPLE = ASSET_DIR / "example-policy-trace-animated.html"
STATIC_EXAMPLE = ASSET_DIR / "example-architecture.html"
MANUAL = ASSET_DIR / "template-manual.html"
SCRIPT_DIR = ROOT / "skills/diagram-design/scripts"
SELECTORS = SCRIPT_DIR / "check_manual_selectors.py"
SYNC = SCRIPT_DIR / "sync_manual_controls.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_self_check():
    return load_module("self_check", SELF_CHECK)


FIGURE_RE = re.compile(r'        <div class="diagram-container" data-motion-root.*?\n        </div>\n\n', re.DOTALL)
BANNER_RE = re.compile(r'          <div class="diagram-annotation-banner".*?</div>\n', re.DOTALL)
BAR_RE = re.compile(r'          <div class="diagram-walkthrough-bar".*?</div>\n', re.DOTALL)
CONTROLLER_RE = re.compile(r"<script data-manual-controls>.*?</script>", re.DOTALL)


def manual_with_figures(manual: str, count: int) -> str:
    """Repeat the template figure `count` times, keeping every SVG id unique."""
    figure = FIGURE_RE.search(manual)
    assert figure is not None, "template-manual.html lost its figure block"
    block = figure.group(0)
    copies = "".join(block.replace("manual-sample", f"manual-sample-{n}") for n in range(1, count + 1))
    return manual[: figure.start()] + copies + manual[figure.end() :]


def nth_figure(manual: str, number: int) -> tuple[int, int]:
    match = list(FIGURE_RE.finditer(manual))[number - 1]
    return match.start(), match.end()


def edit_figure(manual: str, number: int, old: str, new: str) -> str:
    start, end = nth_figure(manual, number)
    block = manual[start:end]
    assert old in block, f"figure {number} has no {old!r}"
    return manual[:start] + block.replace(old, new, 1) + manual[end:]


def map_figure(manual: str, number: int, function) -> str:
    start, end = nth_figure(manual, number)
    return manual[:start] + function(manual[start:end]) + manual[end:]


def main() -> int:
    module = load_self_check()
    failures: list[str] = []

    def check_pass(label: str, path: Path) -> None:
        errors = module.verify(path)
        if errors:
            failures.append(f"{label}: expected pass, got {errors}")
        else:
            print(f"OK: {label} passes")

    def check_fail(label: str, source: str, needle: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            errors = module.verify(candidate)
        if not any(needle in error for error in errors):
            failures.append(f"{label}: expected an error containing {needle!r}, got {errors}")
        else:
            print(f"OK: {label} rejected")

    check_pass("shipped template", TEMPLATE)
    check_pass("shipped animated example", EXAMPLE)
    check_pass("shipped static example", STATIC_EXAMPLE)

    static = STATIC_EXAMPLE.read_text(encoding="utf-8")
    animated = EXAMPLE.read_text(encoding="utf-8")

    check_fail(
        "executable attribute",
        static.replace("<body>", '<body onload="fetch(1)">', 1),
        "executable attribute",
    )
    check_fail(
        "remote image",
        static.replace("<body>", '<body><img src="https://tracker.example/p.gif">', 1),
        "remote reference",
    )
    check_fail(
        "lookalike fonts host",
        static.replace(
            "https://fonts.googleapis.com/css2",
            "https://fonts.googleapis.com.evil.tld/css2",
            1,
        ),
        "approved Google Fonts",
    )
    check_fail(
        "javascript URL",
        static.replace("<body>", '<body><a href="javascript:alert(1)">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "data html URL",
        static.replace("<body>", '<body><a href="data:text/html,x">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "iframe injection",
        static.replace("<body>", "<body><iframe></iframe>", 1),
        "not allowed",
    )
    check_fail(
        "arbitrary script",
        static.replace("</body>", "<script>alert(1)</script></body>", 1),
        "canonical data-diagram-controls attribute",
    )
    check_fail(
        "missing svg role",
        static.replace('role="img"', 'role="presentation"', 1),
        "role=img",
    )
    check_fail(
        "modified controller",
        animated.replace("'motion-ready'", "'motion-ready' /* patched */", 1),
        "exactly match the controller",
    )
    check_fail(
        "second script",
        animated.replace("</body>", "<script data-x></script></body>", 1),
        "at most one script",
    )
    check_fail(
        "hidden motion item",
        animated.replace(
            '<g data-motion-item data-step="1"',
            '<g style="opacity:0" data-motion-item data-step="1"',
            1,
        ),
        "hidden in source",
    )
    check_fail(
        "missing noscript",
        animated.replace("<noscript>", "<div>", 1).replace("</noscript>", "</div>", 1),
        "<noscript>",
    )
    check_fail(
        "non-decimal step count",
        animated.replace('data-step-count="5"', 'data-step-count="٥"', 1),
        "ASCII decimal",
    )


    # ---- Publication Manual: multi-root, document-vs-root scope -------------------
    manual = MANUAL.read_text(encoding="utf-8")
    three = manual_with_figures(manual, 3)

    def errors_for(source: str) -> list[str]:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            return module.verify(candidate)

    def check_pass_source(label: str, source: str) -> None:
        errors = errors_for(source)
        if errors:
            failures.append(f"{label}: expected pass, got {errors}")
        else:
            print(f"OK: {label} passes")

    def check_exact(label: str, source: str, needle: str, expected: int = 1) -> None:
        errors = errors_for(source)
        hits = [error for error in errors if needle in error]
        if len(hits) != expected:
            failures.append(f"{label}: expected {expected} error(s) with {needle!r}, got {errors}")
        else:
            print(f"OK: {label} rejected exactly {expected}x")

    check_pass("shipped manual template", MANUAL)
    check_pass_source("three-root manual, one document-level fallback set", three)

    def make_static(block: str) -> str:
        block = block.replace('data-motion-mode="step" data-step-count="3" data-step-current="3"',
                              'data-motion-mode="none" data-step-count="0" data-step-current="0"')
        block = BAR_RE.sub("", BANNER_RE.sub("", block))
        return re.sub(r' data-motion-item data-step="\d" aria-label="[^"]*"', "", block)

    none_root = map_figure(three, 2, make_static)
    check_pass_source("static zoom-only root (mode none) beside stepped roots", none_root)
    check_exact("static root that keeps its controls",
                map_figure(three, 2, lambda b: b.replace('data-motion-mode="step" data-step-count="3"',
                                                         'data-motion-mode="none" data-step-count="0"')
                           .replace('<g data-motion-item data-step="1"', '<g data-step="1"')
                           .replace('<g data-motion-item data-step="2"', '<g data-step="2"')
                           .replace('<g data-motion-item data-step="3"', '<g data-step="3"')),
                "root 2: none mode must not expose playback controls or live status")

    # Document scope: one error per missing fallback, never one per root.
    check_exact("missing noscript in 3-root manual",
                re.sub(r"<noscript>.*?</noscript>", "", three, flags=re.DOTALL), "<noscript>")
    check_exact("second noscript", three.replace("</article>", "<noscript><p>again</p></noscript></article>", 1),
                "exactly one document-level <noscript>")
    check_exact("missing print fallback in 3-root manual", three.replace("@media print", "@media screen"), "@media print")
    check_exact("missing reduced-motion fallback in 3-root manual",
                three.replace("prefers-reduced-motion: reduce", "prefers-contrast: more"), "prefers-reduced-motion")

    # Per-root scope: errors name the owning root and never leak between roots.
    check_exact("root 2 missing next", edit_figure(three, 2, 'data-motion-action="next"', 'data-x="next"'),
                "root 2: controlled mode is missing actions: next")
    check_exact("other roots' pause does not satisfy root 2",
                edit_figure(three, 2, 'data-motion-action="pause"', 'data-x="pause"'),
                "root 2: controlled mode is missing actions: pause")
    check_exact("root 2 non-contiguous steps", edit_figure(three, 2, 'data-step="2"', 'data-step="3"'),
                "root 2: semantic steps must be contiguous")
    check_exact("root 3 step count above 8",
                edit_figure(three, 3, 'data-step-count="3"', 'data-step-count="9"'), "root 3: semantic step count")
    crowded = edit_figure(three, 2, '<g data-motion-item data-step="3"',
                          "".join(f'<g data-motion-item data-step="3" aria-label="extra {n}"></g>' for n in range(10))
                          + '<g data-motion-item data-step="3"')
    check_exact("root 2 over item budget", crowded, "root 2: motion item budget is 12")
    check_exact("root 2 missing status", map_figure(three, 2, lambda b: BANNER_RE.sub("", b)),
                "root 2: controlled mode needs data-motion-status")

    # Status locality: inside its own root and outside the controls group.
    banner = BANNER_RE.search(three).group(0)
    outside = map_figure(three, 1, lambda b: b.replace(banner, "")).replace(
        "      <!-- Document-level fallback", banner + "      <!-- Document-level fallback", 1)
    check_exact("status outside every root", outside, "data-motion-status outside a data-motion-root")
    check_exact("root left without its status", outside, "root 1: controlled mode needs data-motion-status")

    def banner_into_controls(block: str) -> str:
        block = block.replace(banner, "")
        marker = "          </div>\n          <!-- The status is a sibling"
        assert marker in block
        return block.replace(marker, banner + marker, 1)

    check_exact("status inside the controls group", map_figure(three, 2, banner_into_controls),
                "root 2: motion status must sit outside data-motion-controls")
    check_exact("status without role", edit_figure(three, 3, 'role="status" ', ""),
                "root 3: motion status needs role=status")

    # Script / security contract.
    check_exact("tampered manual controller", manual.replace("const HOLD_MS = 2000;", "const HOLD_MS = 1;", 1),
                "must exactly match the controller in template-manual.html")
    check_exact("second script beside the manual controller",
                manual.replace("</body>", "<script data-x></script></body>", 1), "at most one script")
    check_exact("inline onclick", manual.replace("<h1 ", '<h1 onclick="x()" ', 1), "executable attribute onclick")
    check_exact("wrong script attribute", manual.replace("<script data-manual-controls>", "<script data-manual>", 1),
                "canonical data-diagram-controls attribute")

    # Modal contract.
    dialog = re.search(r"  <dialog class=\"diagram-modal\".*?</dialog>\n", manual, re.DOTALL).group(0)
    check_exact("zero dialogs", manual.replace(dialog, ""), "exactly one <dialog data-diagram-modal>")
    check_exact("two dialogs", manual.replace(dialog, dialog + dialog), "exactly one <dialog data-diagram-modal>")
    check_exact("dialog without body", manual.replace(" data-diagram-modal-body", ""), "data-diagram-modal-body")
    check_exact("dialog without close", manual.replace(" data-diagram-close", ""), "at least one data-diagram-close")
    check_exact("root without opener", manual.replace(" data-diagram-open", "", 1),
                "root 1: needs exactly one data-diagram-open")
    check_exact("root with two openers",
                edit_figure(manual, 1, '<span class="diagram-header-tag">',
                            '<button type="button" data-diagram-open>x</button><span class="diagram-header-tag">'),
                "root 1: needs exactly one data-diagram-open")
    check_exact("orphan opener outside every root",
                manual.replace("</article>", '<button type="button" data-diagram-open>x</button></article>', 1),
                "data-diagram-open outside a data-motion-root")
    opener = '<button type="button" class="diagram-expand-btn" data-diagram-open aria-label="Present diagram in fullscreen">&#10530; Present</button>'
    check_exact("opener outside the root header",
                map_figure(manual, 1, lambda b: b.replace(opener, "").replace(
                    '<div class="diagram-walkthrough-bar"', '<button type="button" data-diagram-open>x</button><div class="diagram-walkthrough-bar"', 1)),
                "must sit inside the root's .diagram-header")

    # Shadows are banned in diagram CSS (regex-matched; the tokens are assembled so this file never spells them).
    for label, css in (
        ("box shadow", "box" + "-shadow: 0 0 4px #000"),
        ("text shadow", "text" + "-shadow: 0 0 4px #000"),
        ("drop shadow filter", "filter: drop" + "-shadow(0 0 4px #000)"),
        ("blur glow filter", "filter: blur(3px)"),
    ):
        check_exact(f"{label} in CSS", manual.replace("  </style>", f"    .is-current {{ {css}; }}\n  </style>", 1),
                    "shadow/glow tokens")
    check_exact("shadow in an inline style", manual.replace("<h1 ", '<h1 style="' + "box" + '-shadow:0 0 2px red" ', 1),
                "shadow/glow tokens")
    check_exact("shadow token inside a CSS comment is ignored",
                manual.replace("  </style>", "    /* never use " + "box" + "-shadow here */\n  </style>", 1),
                "shadow/glow tokens", expected=0)

    # Legacy single-diagram path keeps its one-root rule.
    check_exact("legacy file with two roots",
                animated.replace("</main>", '<div data-motion-root data-motion-mode="none" data-step-count="0"></div></main>', 1),
                "expected exactly one data-motion-root")

    # ---- Publication Manual seams: check_manual_selectors.py and sync_manual_controls.py ----
    selectors = load_module("check_manual_selectors", SELECTORS)
    sync = load_module("sync_manual_controls", SYNC)

    def selector_fail(label: str, source: str, needle: str) -> None:
        problems = selectors.check_page(source)
        if not any(needle in problem for problem in problems):
            failures.append(f"selectors {label}: expected {needle!r}, got {problems}")
        else:
            print(f"OK: selectors {label} rejected")

    for label, source in (("template", manual), ("three roots", three), ("zoom-only root", none_root)):
        problems = selectors.check_page(source)
        if problems:
            failures.append(f"selectors {label}: expected clean, got {problems}")
        else:
            print(f"OK: selectors {label} passes")
    selector_fail("missing toc toggle", manual.replace(" data-toc-toggle", "", 1), "[data-toc-toggle]")
    selector_fail("duplicate theme toggle", manual.replace("</nav>", "<button data-theme-toggle></button></nav>", 1),
                  "[data-theme-toggle]")
    selector_fail("missing dialog", manual.replace(dialog, ""), "<dialog data-diagram-modal>")
    selector_fail("missing opener", manual.replace(" data-diagram-open", "", 1), "[data-diagram-open]")
    selector_fail("status inside controls", map_figure(manual, 1, banner_into_controls), "must sit outside [data-motion-controls]")
    selector_fail("no manual script", CONTROLLER_RE.sub("", manual), "data-manual-controls")
    selector_fail("no noscript", re.sub(r"<noscript>.*?</noscript>", "", manual, flags=re.DOTALL), "<noscript>")
    selector_fail("no print", manual.replace("@media print", "@media screen"), "@media print")
    selector_fail("shadow token", manual.replace("  </style>", "    .x { box" + "-shadow: 0 0 1px red; }\n  </style>", 1), "shadow/glow")
    single_column = re.sub(r'    <aside class="toc-sidebar".*?</aside>\n', "", manual, flags=re.DOTALL)
    selector_fail("toc toggle on a single-column page", single_column, "only allowed on a page with aside.toc-sidebar")
    exempt = selectors.check_page(single_column.replace(" data-toc-toggle", "", 1))
    if exempt:
        failures.append(f"selectors single-column page without a toc toggle: {exempt}")
    else:
        print("OK: selectors single-column page is exempt from the toc toggle")

    def selector_pass(label: str, source: str) -> None:
        problems = selectors.check_page(source)
        if problems:
            failures.append(f"selectors {label}: expected clean, got {problems}")
        else:
            print(f"OK: selectors {label} passes")

    # Dark-theme SVG & .diagram-viewport fail-closed polarity checks.
    selector_fail(
        "viewport hardcoded hex background",
        manual.replace(
            ".diagram-viewport { background: var(--svg-paper);",
            ".diagram-viewport { background: #f5f5f5;",
            1,
        ),
        ".diagram-viewport",
    )
    selector_fail(
        "viewport hardcoded #ffffff background",
        manual.replace(
            ".diagram-viewport { background: var(--svg-paper);",
            ".diagram-viewport { background-color: #ffffff;",
            1,
        ),
        ".diagram-viewport",
    )
    selector_fail(
        "viewport hardcoded rgb background",
        manual.replace(
            ".diagram-viewport { background: var(--svg-paper);",
            ".diagram-viewport { background: rgb(245, 245, 245);",
            1,
        ),
        ".diagram-viewport",
    )
    selector_fail(
        "viewport hardcoded rgba background",
        manual.replace(
            ".diagram-viewport { background: var(--svg-paper);",
            ".diagram-viewport { background: rgba(255, 255, 255, 0.95);",
            1,
        ),
        ".diagram-viewport",
    )
    selector_fail(
        "viewport inline style hex background",
        manual.replace(
            '<div class="diagram-viewport">',
            '<div class="diagram-viewport" style="background: #f5f5f5">',
            1,
        ),
        ".diagram-viewport",
    )
    selector_fail(
        "raw #hex fill on svg rect",
        manual.replace('fill="var(--svg-surface, #ffffff)"', 'fill="#ffffff"', 1),
        "raw #hex",
    )
    selector_fail(
        "raw #hex stroke on svg line",
        manual.replace('stroke="var(--svg-muted, #4f5d75)"', 'stroke="#4f5d75"', 1),
        "raw #hex",
    )
    selector_fail(
        "raw #hex fill inside svg marker",
        manual.replace(
            '<polygon points="0 0, 8 3, 0 6" fill="var(--svg-muted, #4f5d75)"/>',
            '<polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/>',
            1,
        ),
        "raw #hex",
    )
    selector_fail(
        "raw #hex fill on svg text",
        manual.replace(
            '<text x="180" y="104" fill="var(--svg-ink, #2d3142)"',
            '<text x="180" y="104" fill="#2d3142"',
            1,
        ),
        "raw #hex",
    )
    selector_fail(
        "raw #hex in svg inline style",
        manual.replace(
            'fill="var(--svg-paper, #f5f5f5)"',
            'style="background: #f5f5f5; fill: var(--svg-paper, #f5f5f5)"',
            1,
        ),
        "raw #hex",
    )
    selector_fail(
        "raw #hex in svg <style> rule outside custom property definition",
        manual.replace(
            "<defs>",
            "<defs><style>.bad-node { fill: #ffffff; stroke: #2d3142; }</style>",
            1,
        ),
        "raw #hex",
    )
    selector_fail(
        "undefined CSS variable fallback bypass in svg",
        manual.replace('fill="var(--svg-surface, #ffffff)"', 'fill="var(--svg-nonexistent, #ffffff)"', 1),
        "--svg-nonexistent",
    )
    selector_fail(
        "missing html[data-theme=dark] --svg-paper override",
        re.sub(
            r'(html\[data-theme="dark"\]\s*\{.*?)--svg-paper:\s*#[0-9a-fA-F]+;\n',
            r"\1",
            manual,
            count=1,
            flags=re.DOTALL,
        ),
        "--svg-paper",
    )
    selector_fail(
        "unflipped identical light/dark --svg-paper polarity",
        re.sub(
            r'(html\[data-theme="dark"\]\s*\{.*?)--svg-paper:\s*#[0-9a-fA-F]+;',
            r"\1--svg-paper: #f5f5f5;",
            manual,
            count=1,
            flags=re.DOTALL,
        ),
        "--svg-paper",
    )
    # Positive edge cases: CSS custom property definitions (--*:#hex), var(--svg-*, rgba(...)),
    # url(#abcdef) marker/gradient ids, and #hex text in prose/comments must pass cleanly.
    selector_pass(
        "svg custom property definition, hex-like url(#abcdef), and #hex in text/comment",
        manual.replace(
            'id="manual-sample-arrow"',
            'id="abcdef"',
            1,
        )
        .replace(
            "url(#manual-sample-arrow)",
            "url(#abcdef)",
        )
        .replace(
            "<defs>",
            '<defs><!-- legacy fill="#ffffff" --><style>:root { --local-chip: #123456; }</style>',
            1,
        )
        .replace(
            ">Step one</text>",
            ">Step #deadbeef</text>",
            1,
        ),
    )

    canonical = sync.canonical_body()
    with tempfile.TemporaryDirectory() as scratch:
        good = Path(scratch) / "good.html"
        bad = Path(scratch) / "bad.html"
        missing = Path(scratch) / "missing.html"
        good.write_text(manual, encoding="utf-8", newline="")
        bad_source = manual.replace("const HOLD_MS = 2000;", "const HOLD_MS = 5;", 1).replace("Publication Manual", "Edited Manual", 1)
        bad.write_text(bad_source, encoding="utf-8", newline="")
        missing.write_text(CONTROLLER_RE.sub("", manual), encoding="utf-8")

        def run_sync(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(SYNC), *args], capture_output=True, text=True, check=False)

        result = run_sync("--check", str(good))
        if result.returncode != 0:
            failures.append(f"sync --check on identical page: rc={result.returncode} {result.stdout}")
        else:
            print("OK: sync --check accepts a matching page")
        result = run_sync("--check", str(good), str(bad), str(missing))
        if (
            result.returncode != 1
            or f"DIVERGENT: {bad}" not in result.stdout
            or f"DIVERGENT: {missing}" not in result.stdout
            or f"DIVERGENT: {good}" in result.stdout
        ):
            failures.append(f"sync --check divergence report: rc={result.returncode} out={result.stdout!r}")
        else:
            print("OK: sync --check names each divergent page")
        before = bad.read_text(encoding="utf-8")
        result = run_sync("--write", str(bad))
        after = bad.read_text(encoding="utf-8")
        if result.returncode != 0 or run_sync("--check", str(bad)).returncode != 0:
            failures.append(f"sync --write did not converge: {result.stdout} {result.stderr}")
        elif CONTROLLER_RE.sub("", before) != CONTROLLER_RE.sub("", after):
            failures.append("sync --write changed bytes outside the controller body")
        elif sync.normalize(sync.find_controllers(after)[0].group("body")) != canonical:
            failures.append("sync --write left a non-canonical controller")
        else:
            print("OK: sync --write replaces only the controller body")
        crlf = Path(scratch) / "crlf.html"
        crlf.write_bytes(bad_source.replace("\n", "\r\n").encode("utf-8"))
        run_sync("--write", str(crlf))
        raw = crlf.read_bytes()
        if b"\r\n" not in raw or re.search(rb"(?<!\r)\n", raw):
            failures.append("sync --write mixed line endings in a CRLF page")
        elif run_sync("--check", str(crlf)).returncode != 0:
            failures.append("sync --write on a CRLF page did not converge")
        else:
            print("OK: sync --write preserves CRLF line endings")
        result = run_sync("--write", str(missing))
        if result.returncode != 1 or "data-manual-controls" in missing.read_text(encoding="utf-8"):
            failures.append(f"sync --write on a page with no controller must fail untouched: rc={result.returncode}")
        else:
            print("OK: sync --write refuses a page with no controller")

    # Controller contract: separately named single-responsibility functions.
    absent = [name for name in ("readState", "writeState", "initTocState", "initThemeState",
                                "initDiagramModal", "initMotionRoot", "boot")
              if f"function {name}(" not in canonical]
    if absent:
        failures.append(f"canonical controller lacks named functions: {absent}")
    else:
        print("OK: canonical controller defines the seven named functions")

    # C-01 regression gate: verify-motion.py --shipped must pass with template-manual.html present
    # while keeping template-motion.html and animated examples in shipped_motion_files().
    verify_motion_path = ROOT / "scripts/verify-motion.py"
    verify_motion = load_module("verify_motion", verify_motion_path)
    shipped_motion = set(verify_motion.shipped_motion_files())
    if TEMPLATE not in shipped_motion or EXAMPLE not in shipped_motion:
        failures.append(f"shipped_motion_files lost single-diagram assets: {sorted(shipped_motion)}")
    elif MANUAL in shipped_motion:
        failures.append("shipped_motion_files must exclude Publication Manual template (data-manual-controls)")
    else:
        print("OK: shipped_motion_files separates data-diagram-controls from data-manual-controls")
    shipped_cli = subprocess.run(
        [sys.executable, str(verify_motion_path), "--shipped"],
        capture_output=True,
        text=True,
        check=False,
    )
    if shipped_cli.returncode != 0:
        failures.append(f"verify-motion.py --shipped failed (rc={shipped_cli.returncode}): {shipped_cli.stdout}")
    else:
        print("OK: verify-motion.py --shipped exits 0")

    # Adaptive Dark/Light --svg-* token contract in template-manual.html and sample.svg.
    required_svg_tokens = (
        "--svg-paper",
        "--svg-surface",
        "--svg-panel",
        "--svg-ink",
        "--svg-muted",
        "--svg-soft",
        "--svg-rule",
        "--svg-accent",
        "--svg-accent-tint",
        "--svg-green",
        "--svg-green-tint",
        "--svg-blue",
        "--svg-blue-tint",
        "--svg-purple",
        "--svg-purple-tint",
        "--svg-amber",
        "--svg-amber-tint",
        "--svg-red",
        "--svg-red-tint",
    )
    root_match = re.search(r"(?<!\])\s*:root\s*\{([^}]*)\}", manual)
    os_dark_match = re.search(
        r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{\s*:root:not\(\[data-theme=['\"]light['\"]\]\)\s*\{([^}]*)\}",
        manual,
        re.DOTALL,
    )
    html_dark_match = re.search(r"html\[data-theme=['\"]dark['\"]\]\s*\{([^}]*)\}", manual, re.DOTALL)
    if not (root_match and os_dark_match and html_dark_match):
        failures.append("template-manual.html missing :root, prefers-color-scheme: dark :root:not([data-theme=light]), or html[data-theme=dark] block")
    else:
        for block_label, block_body in (
            (":root", root_match.group(1)),
            ("prefers-color-scheme: dark", os_dark_match.group(1)),
            ("html[data-theme=dark]", html_dark_match.group(1)),
        ):
            missing_tokens = [tok for tok in required_svg_tokens if re.search(rf"{re.escape(tok)}\s*:", block_body) is None]
            if missing_tokens:
                failures.append(f"template-manual.html {block_label} missing --svg-* tokens: {missing_tokens}")
        else:
            if not any("missing --svg-* tokens" in f for f in failures):
                print("OK: template-manual.html defines all 19 --svg-* tokens across light and dark blocks")
    if re.search(r"\.diagram-viewport\s*\{[^}]*background\s*:\s*var\(--svg-paper\)", manual) is None:
        failures.append("template-manual.html .diagram-viewport must use background: var(--svg-paper)")
    else:
        print("OK: template-manual.html .diagram-viewport uses background: var(--svg-paper)")
    sample_svg = ASSET_DIR / "diagrams/sample.svg"
    check_pass("shipped manual sample.svg", sample_svg)
    sample_svg_text = sample_svg.read_text(encoding="utf-8")
    if "var(--svg-paper" not in sample_svg_text or "prefers-color-scheme: dark" not in sample_svg_text:
        failures.append("sample.svg must define adaptive --svg-* light/dark tokens")
    else:
        print("OK: sample.svg carries adaptive --svg-* light/dark tokens")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("All self-check tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
