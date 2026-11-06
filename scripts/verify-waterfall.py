#!/usr/bin/env python3
"""Verify Execution trace waterfall diagrams (Semantic Pattern §9 -> Gantt).

Enforces:
1. data-waterfall-evidence="measured|illustrative" paired with matching MEASURED
   (--svg-green / --svg-green-tint) or ILLUSTRATIVE (--svg-amber / --svg-amber-tint) badge pill.
2. Unique non-blank data-span-id attributes and acyclic data-span-parent references.
3. Numeric data-span-start / data-span-end with end >= start and parent [start, end]
   enveloping child spans.
4. 4px-grid trace geometry (row_h=32, bar_h=16, indent=16 * depth) and typography
   font-size in {12, 8}.
5. Parent bracket bars in --svg-panel fill / --svg-ink stroke, leaf cohorts in
   --svg-blue / --svg-purple / --svg-muted, and data-span-status="error" spans in
   --svg-red with [ERR] label text (zero raw #hex / rgb() outside var(--svg-*, fallback)).
6. Linear horizontal bar x and width proportionality within 2px 4px-grid rounding
   tolerance (min_bar_w=4).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

PAINT_ATTRS = ("fill", "stroke", "stop-color", "color", "background")
VAR_WRAP_RE = re.compile(r"^\s*var\(\s*--svg-[a-zA-Z0-9_-]+(?:\s*,\s*.+)?\)\s*$", re.IGNORECASE)
RAW_PAINT_RE = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b|\brgba?\s*\(", re.IGNORECASE)


@dataclass
class SpanRecord:
    span_id: str
    parent: str | None
    start_raw: str | None
    end_raw: str | None
    status: str | None
    kind: str | None
    line: int
    label_x: float | None = None
    label_texts: list[str] = field(default_factory=list)
    bar_x: float | None = None
    bar_y: float | None = None
    bar_w: float | None = None
    bar_h: float | None = None
    bar_fill: str = ""
    bar_stroke: str = ""


@dataclass
class WaterfallSVG:
    evidence: str
    track_x: float | None
    track_w: float | None
    line: int
    badge_texts: list[str] = field(default_factory=list)
    badge_paints: list[str] = field(default_factory=list)
    spans: list[SpanRecord] = field(default_factory=list)
    font_sizes: list[tuple[int, str]] = field(default_factory=list)
    raw_paint_findings: list[str] = field(default_factory=list)


class _WaterfallScanner(HTMLParser):
    def __init__(self, filename: str) -> None:
        super().__init__(convert_charrefs=True)
        self.filename = filename
        self.waterfalls: list[WaterfallSVG] = []
        self._wf: WaterfallSVG | None = None
        self._wf_depth = 0
        self._span: SpanRecord | None = None
        self._span_depth: int | None = None
        self._in_badge_depth: int | None = None
        self._in_text = False
        self._text_buf: list[str] = []
        self._text_x: float | None = None

    def _check_paint_attrs(self, attrs: dict[str, str], line: int) -> None:
        if self._wf is None:
            return
        for key in PAINT_ATTRS:
            val = attrs.get(key, "").strip()
            if not val or val.casefold() in ("none", "transparent", "currentcolor") or val.startswith("url("):
                continue
            if not VAR_WRAP_RE.fullmatch(val) and RAW_PAINT_RE.search(val):
                self._wf.raw_paint_findings.append(
                    f'{self.filename}:{line}: raw #hex or rgb() literal in {key}="{val}" (use var(--svg-*, fallback))'
                )

    def _process_start(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        tag_l = tag.casefold()
        line = self.getpos()[0]
        data = {k.casefold(): (v if v is not None else "") for k, v in attrs}

        if tag_l == "svg" and "data-waterfall-evidence" in data and self._wf is None:
            tx = float(data["data-waterfall-track-x"]) if "data-waterfall-track-x" in data else None
            tw = float(data["data-waterfall-track-width"]) if "data-waterfall-track-width" in data else None
            self._wf = WaterfallSVG(
                evidence=data["data-waterfall-evidence"].strip(),
                track_x=tx,
                track_w=tw,
                line=line,
            )
            self.waterfalls.append(self._wf)
            self._wf_depth = 1
            return

        if self._wf is None:
            return

        if not self_closing:
            self._wf_depth += 1

        self._check_paint_attrs(data, line)

        if "font-size" in data:
            self._wf.font_sizes.append((line, data["font-size"].strip()))

        if "data-waterfall-badge" in data and self._in_badge_depth is None:
            self._in_badge_depth = self._wf_depth

        if self._in_badge_depth is not None:
            for k in ("fill", "stroke"):
                if data.get(k):
                    self._wf.badge_paints.append(data[k])

        if "data-span-id" in data:
            self._span = SpanRecord(
                span_id=data["data-span-id"],
                parent=data.get("data-span-parent"),
                start_raw=data.get("data-span-start"),
                end_raw=data.get("data-span-end"),
                status=data.get("data-span-status"),
                kind=data.get("data-span-kind"),
                line=line,
            )
            self._wf.spans.append(self._span)
            if not self_closing:
                self._span_depth = self._wf_depth

        if self._span is not None and tag_l == "rect" and ("data-span-bar" in data or self._span.bar_w is None):
            try:
                self._span.bar_x = float(data.get("x", "nan"))
                self._span.bar_y = float(data.get("y", "nan"))
                self._span.bar_w = float(data.get("width", "nan"))
                self._span.bar_h = float(data.get("height", "nan"))
            except ValueError:
                pass
            self._span.bar_fill = data.get("fill", "")
            self._span.bar_stroke = data.get("stroke", "")

        if tag_l == "text" and not self_closing:
            self._in_text = True
            self._text_buf = []
            try:
                self._text_x = float(data["x"]) if "x" in data else None
            except ValueError:
                self._text_x = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._process_start(tag, attrs, self_closing=True)

    def handle_data(self, data: str) -> None:
        if self._in_text:
            self._text_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._wf is None:
            return
        tag_l = tag.casefold()
        if tag_l == "text" and self._in_text:
            txt = "".join(self._text_buf).strip()
            if self._in_badge_depth is not None and txt:
                self._wf.badge_texts.append(txt)
            if self._span is not None:
                if txt:
                    self._span.label_texts.append(txt)
                if self._span.label_x is None and self._text_x is not None:
                    self._span.label_x = self._text_x
            self._in_text = False
            self._text_buf = []
            self._text_x = None

        self._wf_depth -= 1
        if self._in_badge_depth is not None and self._wf_depth < self._in_badge_depth:
            self._in_badge_depth = None
        if self._span_depth is not None and self._wf_depth < self._span_depth:
            self._span = None
            self._span_depth = None
        if self._wf_depth <= 0:
            self._wf = None
            self._wf_depth = 0


def _verify_single_waterfall(path: Path, wf: WaterfallSVG) -> list[str]:
    findings: list[str] = list(wf.raw_paint_findings)
    ev = wf.evidence.casefold()
    if ev not in ("measured", "illustrative"):
        findings.append(
            f'{path.name}:{wf.line}: data-waterfall-evidence must be "measured" or "illustrative"; got "{wf.evidence}"'
        )
    else:
        expected_badge = "MEASURED" if ev == "measured" else "ILLUSTRATIVE"
        expected_tok = "--svg-green" if ev == "measured" else "--svg-amber"
        badge_joined = " ".join(wf.badge_texts).upper()
        paint_joined = " ".join(wf.badge_paints).casefold()
        if expected_badge not in badge_joined or expected_tok not in paint_joined:
            findings.append(
                f"{path.name}:{wf.line}: waterfall evidence badge must display {expected_badge!r} with {expected_tok} tokens"
            )

    for line, fs in wf.font_sizes:
        cleaned = fs.removesuffix("px").strip()
        if cleaned not in ("12", "8"):
            findings.append(
                f'{path.name}:{line}: waterfall typography font-size must be in {{12, 8}}; got "{fs}"'
            )

    if not wf.spans:
        findings.append(f"{path.name}:{wf.line}: waterfall SVG contains zero data-span-id spans")
        return findings

    by_id: dict[str, SpanRecord] = {}
    for sp in wf.spans:
        sid = sp.span_id.strip()
        if not sid:
            findings.append(f"{path.name}:{sp.line}: blank data-span-id")
        elif sid in by_id:
            findings.append(f'{path.name}:{sp.line}: duplicate data-span-id "{sid}"')
        else:
            by_id[sid] = sp

    # Acyclic parent check & depth computation
    depths: dict[str, int] = {}
    parent_ids: set[str] = set()
    for sp in wf.spans:
        sid = sp.span_id.strip()
        if not sid:
            continue
        if sp.parent is not None:
            parent_ids.add(sp.parent)
            if sp.parent not in by_id:
                findings.append(
                    f'{path.name}:{sp.line}: data-span-parent "{sp.parent}" on "{sid}" does not resolve'
                )
        chain: list[str] = []
        curr: str | None = sid
        while curr is not None:
            if curr in chain:
                findings.append(f'{path.name}:{sp.line}: parent cycle detected: {" -> ".join(chain + [curr])}')
                break
            chain.append(curr)
            rec = by_id.get(curr)
            curr = rec.parent if rec is not None and rec.parent in by_id else None
        depths[sid] = len(chain) - 1

    # Timing & parent envelope
    times: dict[str, tuple[float, float]] = {}
    for sp in wf.spans:
        sid = sp.span_id.strip()
        try:
            st = float(sp.start_raw if sp.start_raw is not None else "nan")
            en = float(sp.end_raw if sp.end_raw is not None else "nan")
            if st != st or en != en:
                raise ValueError
        except ValueError:
            findings.append(f'{path.name}:{sp.line}: span "{sid}" needs numeric data-span-start and data-span-end')
            continue
        if en < st:
            findings.append(f'{path.name}:{sp.line}: span "{sid}" violates end >= start ({st:g}..{en:g})')
        times[sid] = (st, en)

    for sp in wf.spans:
        sid = sp.span_id.strip()
        if sp.parent and sp.parent in times and sid in times:
            pst, pen = times[sp.parent]
            cst, cen = times[sid]
            if cst < pst - 1e-6 or cen > pen + 1e-6:
                findings.append(
                    f'{path.name}:{sp.line}: child span "{sid}" [{cst:g}, {cen:g}] escapes parent "{sp.parent}" envelope [{pst:g}, {pen:g}]'
                )

    # 4px-grid trace geometry: bar_h=16, row_h=32, indent=16*depth
    root_label_xs = [
        sp.label_x for sp in wf.spans if depths.get(sp.span_id.strip(), 0) == 0 and sp.label_x is not None
    ]
    base_label_x = min(root_label_xs) if root_label_xs else None
    prev_bar_y: float | None = None
    for sp in wf.spans:
        sid = sp.span_id.strip()
        if sp.bar_h is None or abs(sp.bar_h - 16.0) > 1e-6:
            findings.append(f'{path.name}:{sp.line}: span "{sid}" bar height must be bar_h=16; got {sp.bar_h}')
        if sp.bar_y is not None:
            if prev_bar_y is not None and abs((sp.bar_y - prev_bar_y) - 32.0) > 1e-6:
                findings.append(
                    f'{path.name}:{sp.line}: span "{sid}" row spacing must be row_h=32; got {sp.bar_y - prev_bar_y:g}'
                )
            prev_bar_y = sp.bar_y
        depth = depths.get(sid, 0)
        if base_label_x is not None and sp.label_x is not None:
            expected_lx = base_label_x + 16.0 * depth
            if abs(sp.label_x - expected_lx) > 1e-6:
                findings.append(
                    f'{path.name}:{sp.line}: span "{sid}" label x={sp.label_x:g} violates indent=16 * depth (expected {expected_lx:g})'
                )

        # Token & error semantics
        fill_l = sp.bar_fill.casefold()
        stroke_l = sp.bar_stroke.casefold()
        is_parent = sid in parent_ids or (sp.kind or "").casefold() == "parent"
        is_err = (sp.status or "").casefold() == "error"
        if is_parent:
            if "--svg-panel" not in fill_l or "--svg-ink" not in stroke_l:
                findings.append(
                    f'{path.name}:{sp.line}: parent bracket span "{sid}" must use --svg-panel fill and --svg-ink stroke'
                )
        elif is_err:
            if "--svg-red" not in stroke_l or "[err]" not in " ".join(sp.label_texts).casefold():
                findings.append(
                    f'{path.name}:{sp.line}: error span "{sid}" requires --svg-red stroke and "[ERR]" in its label'
                )
        else:
            if not any(tok in fill_l or tok in stroke_l for tok in ("--svg-blue", "--svg-purple", "--svg-muted")):
                findings.append(
                    f'{path.name}:{sp.line}: leaf span "{sid}" must use --svg-blue, --svg-purple, or --svg-muted tokens'
                )

    # Proportionality check within 2px tolerance (min_bar_w=4)
    if len(times) == len(wf.spans) and times:
        dom_start = min(v[0] for v in times.values())
        dom_end = max(v[1] for v in times.values())
        total_dur = dom_end - dom_start
        valid_bars = [sp for sp in wf.spans if sp.bar_x is not None and sp.bar_w is not None]
        if total_dur > 0 and valid_bars:
            track_x = wf.track_x if wf.track_x is not None else min(sp.bar_x for sp in valid_bars if sp.bar_x is not None)
            track_right = max((sp.bar_x or 0.0) + (sp.bar_w or 0.0) for sp in valid_bars)
            track_w = wf.track_w if wf.track_w is not None else (track_right - track_x)
            for sp in valid_bars:
                sid = sp.span_id.strip()
                st, en = times[sid]
                exp_x = track_x + ((st - dom_start) / total_dur) * track_w
                exp_w = max(4.0, ((en - st) / total_dur) * track_w)
                assert sp.bar_x is not None and sp.bar_w is not None
                if abs(sp.bar_x - exp_x) > 2.0 or abs(sp.bar_w - exp_w) > 2.0:
                    findings.append(
                        f'{path.name}:{sp.line}: span "{sid}" bar (x={sp.bar_x:g}, width={sp.bar_w:g}) is not proportional '
                        f"to [{st:g}, {en:g}] (expected x={exp_x:.1f}, width={exp_w:.1f} +/-2px)"
                    )

    return findings


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    scanner = _WaterfallScanner(path.name)
    scanner.feed(source)
    scanner.close()
    findings: list[str] = []
    for wf in scanner.waterfalls:
        findings.extend(_verify_single_waterfall(path, wf))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="HTML/SVG waterfall files to check")
    parser.add_argument("--all", action="store_true", help="check all shipped assets")
    args = parser.parse_args()
    paths = sorted(ASSET_DIR.glob("*.html")) if args.all else list(args.files)
    if not paths:
        parser.error("pass one or more files, or --all")
    findings: list[str] = []
    for path in paths:
        if not path.exists():
            findings.append(f"{path}: file not found")
            continue
        findings.extend(check(path))
    for f in findings:
        print(f)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
