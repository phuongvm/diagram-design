#!/usr/bin/env python3
"""Self-check a generated diagram HTML file, with no third-party deps.

Ships inside the skill so an installed agent can verify its own output:

    python3 <skill-dir>/scripts/self_check.py my-diagram.html

Checks the accessible-SVG contract, the single-file safety rules (no remote
assets beyond the approved Google Fonts stylesheet, no executable attributes,
no scripts other than the one canonical motion or Publication Manual
controller), and — when motion markup is present — the structural motion
contract. Document-scope rules (controller parity, fallbacks, the diagram
modal) are evaluated once per file; per-root rules are evaluated for every
`[data-motion-root]` and reported as `root <n>: ...`. This is a distilled
subset of the repository gates (`lint-skin.py`, `verify-motion.py`), which
remain the authority for contributions to the repository itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
MOTION_TEMPLATE = SKILL_DIR / "assets" / "template-motion.html"
MANUAL_TEMPLATE = SKILL_DIR / "assets" / "template-manual.html"
MODES = {"none", "reveal", "step", "loop"}
ACTIONS = {"play", "pause", "replay", "prev", "next"}
ASCII_DECIMAL_RE = re.compile(r"^[0-9]+$")
REFERENCE_ATTRS = {"src", "href", "xlink:href", "poster", "srcset", "action", "formaction"}
MOTION_PART_ATTRS = ("data-motion-item", "data-motion-action", "data-motion-controls", "data-motion-status")
SHADOW_TOKEN_RE = re.compile(
    r"(?<![\w-])(?:box-shadow|text-shadow)\s*:|drop-shadow\s*\(|(?<![\w-])filter\s*:[^;}]*\bblur\s*\(",
    re.IGNORECASE,
)
FONT_DECL_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
RECT_RE = re.compile(
    r"<rect\b[^>]*?"
    r'\bx="(?P<x>-?[\d.]+)"\s+'
    r'y="(?P<y>-?[\d.]+)"\s+'
    r'width="(?P<w>[\d.]+)"\s+'
    r'height="(?P<h>[\d.]+)"',
    re.IGNORECASE,
)
NODE_MIN_W = 60.0
NODE_MIN_H = 40.0
MASK_MIN_W = 20.0
MASK_MAX_W = 200.0
MASK_MIN_H = 8.0
MASK_MAX_H = 14.0
EPSILON = 0.5
ARCH_DELTA_PHASES: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "Removals", ("removal", "[− del]", "[- del]")),
    (2, "Moves", ("move", "[↔ move]")),
    (3, "Modifications", ("modification", "[~ mod]")),
    (4, "Additions", ("addition", "[+ add]")),
)


def new_root_bucket(attrs: dict[str, str]) -> dict[str, object]:
    return {
        "attrs": attrs,
        "items": [],
        "actions": set(),
        "controls": 0,
        "statuses": [],
        "statuses_in_controls": 0,
        "openers": 0,
        "openers_in_header": 0,
        "ghost_refs": [],
    }


class DiagramParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roots: list[dict[str, str]] = []
        self.root_buckets: list[dict[str, object]] = []
        self.document_errors: list[str] = []
        self.dialogs: list[dict[str, int]] = []
        self.openers_outside_root = 0
        self.noscripts = 0
        self.scripts: list[dict[str, object]] = []
        self.styles: list[str] = []
        self.inline_styles: list[str] = []
        self.svgs: list[dict[str, object]] = []
        self.unsafe: list[str] = []
        self.references: list[tuple[str, str, str]] = []
        self.all_ids: list[str] = []
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._capture: str | None = None
        self._current_script: dict[str, object] | None = None
        self._in_style = False
        self._element_stack: list[str] = []
        self._root: dict[str, object] | None = None
        self._root_depth: int | None = None
        self._controls_depth: int | None = None
        self._header_depth: int | None = None
        self._dialog: dict[str, int] | None = None
        self._dialog_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        normalized_attrs = [(key.casefold(), value or "") for key, value in attrs]
        data = {key: value for key, value in normalized_attrs}
        if data.get("id"):
            self.all_ids.append(data["id"])
        if tag in {"base", "embed", "object", "iframe"}:
            self.unsafe.append(f"<{tag}> is not allowed in a diagram file")
        if tag == "meta" and data.get("name", "").strip().casefold() == "generator" and "archify" in data.get("content", "").casefold():
            self.unsafe.append("generator=archify bundle is not allowed in an editorial/Portal diagram")
        for key, value in normalized_attrs:
            if key.startswith("on"):
                self.unsafe.append(f"executable attribute {key} on <{tag}>")
            if key == "srcdoc":
                self.unsafe.append(f"srcdoc attribute on <{tag}>")
            if key == "font-family" and "jetbrains mono" in value.casefold():
                self.unsafe.append("JetBrains Mono font-family is forbidden in diagram markup")
            if key in REFERENCE_ATTRS:
                self.references.append((tag, data.get("rel", ""), value))
        if "style" in data:
            self.inline_styles.append(data["style"])
        if tag == "noscript":
            self.noscripts += 1
        if "data-motion-root" in data:
            self.roots.append(data)
            if self._root is not None:
                self.document_errors.append("nested data-motion-root is not allowed")
            else:
                self._root = new_root_bucket(data)
                self._root_depth = len(self._element_stack)
                self.root_buckets.append(self._root)
        if self._root is not None:
            if "data-motion-item" in data:
                self._root["items"].append(data)  # type: ignore[union-attr]
            if "data-delta-ghost-of" in data:
                self._root["ghost_refs"].append(data["data-delta-ghost-of"])  # type: ignore[union-attr]
            if "data-motion-action" in data:
                self._root["actions"].add(data["data-motion-action"])  # type: ignore[union-attr]
            if "data-motion-controls" in data:
                self._root["controls"] = int(self._root["controls"]) + 1  # type: ignore[arg-type]
                if self._controls_depth is None:
                    self._controls_depth = len(self._element_stack)
            if "data-motion-status" in data:
                self._root["statuses"].append(data)  # type: ignore[union-attr]
                if self._controls_depth is not None:
                    self._root["statuses_in_controls"] = int(self._root["statuses_in_controls"]) + 1  # type: ignore[arg-type]
            if "diagram-header" in data.get("class", "").split() and self._header_depth is None:
                self._header_depth = len(self._element_stack)
        else:
            for key in MOTION_PART_ATTRS:
                message = f"{key} outside a data-motion-root"
                if key in data and message not in self.document_errors:
                    self.document_errors.append(message)
        if "data-diagram-open" in data:
            if self._root is None:
                self.openers_outside_root += 1
            else:
                self._root["openers"] += 1
                if self._header_depth is not None:
                    self._root["openers_in_header"] += 1
        if tag == "dialog" and "data-diagram-modal" in data and self._dialog is None:
            self._dialog = {"bodies": 0, "closes": 0}
            self._dialog_depth = len(self._element_stack)
            self.dialogs.append(self._dialog)
        elif tag == "dialog" and "data-diagram-modal" in data:
            self.dialogs.append({"bodies": 0, "closes": 0})
        if self._dialog is not None:
            if "data-diagram-modal-body" in data:
                self._dialog["bodies"] += 1
            if "data-diagram-close" in data:
                self._dialog["closes"] += 1
        if tag == "script":
            self._current_script = {
                "attrs": data,
                "attr_names": [name for name, _value in normalized_attrs],
                "body": [],
                "closed": False,
            }
            self.scripts.append(self._current_script)
        if tag == "style":
            self._in_style = True
        self._element_stack.append(tag)
        if tag == "svg" and self._svg_depth == 0:
            self._svg_depth = 1
            self._current_svg = {"attrs": data, "first": None, "title": {}, "desc": {}}
            self.svgs.append(self._current_svg)
            return
        if self._svg_depth:
            self._svg_depth += 1
            assert self._current_svg is not None
            if self._svg_depth == 2 and self._current_svg["first"] is None:
                self._current_svg["first"] = tag
            if self._svg_depth == 2 and tag in {"title", "desc"}:
                self._current_svg[tag] = {"attrs": data, "text": ""}
                self._capture = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "script" and self._current_script is not None:
            self._current_script["closed"] = True
            self._current_script = None
        if tag == "style":
            self._in_style = False
        if self._svg_depth:
            if tag in {"title", "desc"}:
                self._capture = None
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index] == tag:
                del self._element_stack[index:]
                break
        depth = len(self._element_stack)
        if self._root_depth is not None and depth <= self._root_depth:
            self._root = None
            self._root_depth = None
        if self._controls_depth is not None and depth <= self._controls_depth:
            self._controls_depth = None
        if self._header_depth is not None and depth <= self._header_depth:
            self._header_depth = None
        if self._dialog_depth is not None and depth <= self._dialog_depth:
            self._dialog = None
            self._dialog_depth = None

    def handle_data(self, data: str) -> None:
        if self._current_script is not None:
            body = self._current_script["body"]
            assert isinstance(body, list)
            body.append(data)
        if self._in_style:
            self.styles.append(data)
        if self._capture and self._current_svg:
            node = self._current_svg[self._capture]
            assert isinstance(node, dict)
            node["text"] = str(node.get("text", "")) + data


def normalized_controller(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def parsed_document(source: str) -> DiagramParser:
    parser = DiagramParser()
    parser.feed(source)
    parser.close()
    return parser


def is_approved_google_fonts_stylesheet(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == "fonts.googleapis.com"
        and parsed.port is None
        and parsed.path == "/css2"
        and not parsed.fragment
    )


def reference_error(tag: str, rel: str, value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.casefold()
    if not stripped or stripped.startswith("#"):
        return None
    if lowered.startswith("javascript:") or lowered.startswith("data:text/html"):
        return f"executable URL on <{tag}>: {stripped[:80]}"
    remote = lowered.startswith(("http://", "https://", "//")) or (
        ":" in stripped.split("/", 1)[0] and not lowered.startswith("data:")
    )
    if not remote:
        if lowered.startswith("data:") and not lowered.startswith("data:image/"):
            return f"non-image data URL on <{tag}>: {stripped[:80]}"
        return None
    if tag == "link" and "stylesheet" in rel.casefold().split():
        if is_approved_google_fonts_stylesheet(stripped):
            return None
        return f"remote stylesheet is not the approved Google Fonts /css2 URL: {stripped[:80]}"
    return f"remote reference on <{tag}>: {stripped[:80]}"


def load_canonical(template: Path, attribute: str) -> str:
    if not template.is_file():
        raise RuntimeError(
            f"cannot find the canonical controller at {template}; "
            "run self_check.py from its shipped location inside the skill"
        )
    parser = parsed_document(template.read_text(encoding="utf-8"))
    matching = [
        script
        for script in parser.scripts
        if script["attr_names"] == [attribute] and script["closed"]
    ]
    if len(matching) != 1 or len(parser.scripts) != 1:
        raise RuntimeError(f"{template.name} must contain exactly one closed {attribute} controller")
    body = matching[0]["body"]
    assert isinstance(body, list)
    return normalized_controller("".join(body))


def canonical_controller() -> str:
    return load_canonical(MOTION_TEMPLATE, "data-diagram-controls")


def canonical_manual_controller() -> str:
    return load_canonical(MANUAL_TEMPLATE, "data-manual-controls")


def check_svgs(parser: DiagramParser, errors: list[str]) -> None:
    checkable = [
        svg
        for svg in parser.svgs
        if isinstance(svg["attrs"], dict)
        and str(svg["attrs"].get("aria-hidden", "")).casefold() != "true"
    ]
    if not checkable:
        errors.append("diagram file needs at least one accessible (non-aria-hidden) SVG")
    for number, svg in enumerate(checkable, 1):
        attrs = svg["attrs"]
        assert isinstance(attrs, dict)
        if attrs.get("role") != "img":
            errors.append(f"svg {number} needs role=img")
        labelled = attrs.get("aria-labelledby", "").split()
        title = svg["title"]
        desc = svg["desc"]
        assert isinstance(title, dict) and isinstance(desc, dict)
        title_attrs = title.get("attrs", {})
        desc_attrs = desc.get("attrs", {})
        assert isinstance(title_attrs, dict) and isinstance(desc_attrs, dict)
        if svg["first"] != "title":
            errors.append(f"svg {number} title must be its first child")
        if not str(title.get("text", "")).strip() or not str(desc.get("text", "")).strip():
            errors.append(f"svg {number} needs non-empty title and desc")
        title_id = title_attrs.get("id", "")
        desc_id = desc_attrs.get("id", "")
        if title_id in {"", "title"} or desc_id in {"", "desc"}:
            errors.append(f"svg {number} title/desc IDs must be diagram-prefixed, never bare")
        if labelled != [title_id, desc_id]:
            errors.append(f"svg {number} aria-labelledby must name title then desc")


def check_scripts(parser: DiagramParser, errors: list[str]) -> None:
    if not parser.scripts:
        return
    if len(parser.scripts) > 1:
        errors.append(f"at most one script is allowed; found {len(parser.scripts)}")
    for number, script in enumerate(parser.scripts, 1):
        attrs = script["attrs"]
        attr_names = script["attr_names"]
        body = script["body"]
        assert isinstance(attrs, dict) and isinstance(attr_names, list) and isinstance(body, list)
        if not script["closed"]:
            errors.append(f"script {number} must have a closing script tag")
        if attr_names == ["data-manual-controls"] and attrs.get("data-manual-controls") == "":
            loader, template_name = canonical_manual_controller, "template-manual.html"
        elif attr_names == ["data-diagram-controls"] and attrs.get("data-diagram-controls") == "":
            loader, template_name = canonical_controller, "template-motion.html"
        else:
            errors.append(
                f"script {number} must carry only the canonical data-diagram-controls attribute "
                "(or data-manual-controls for a Publication Manual)"
            )
            continue
        try:
            if normalized_controller("".join(body)) != loader():
                errors.append(f"script {number} must exactly match the controller in {template_name}")
        except RuntimeError as exc:
            errors.append(str(exc))


def check_root(
    bucket: dict[str, object],
    errors: list[str],
    prefix: str,
    *,
    manual: bool,
    has_script: bool,
) -> None:
    """Per-root rules; every error carries `prefix` so it names the owning root."""
    root = bucket["attrs"]
    items = bucket["items"]
    actions = bucket["actions"]
    statuses = bucket["statuses"]
    assert isinstance(root, dict) and isinstance(items, list)
    assert isinstance(actions, set) and isinstance(statuses, list)
    controls = int(bucket["controls"])  # type: ignore[arg-type]
    mode = root.get("data-motion-mode", "")
    if mode not in MODES:
        errors.append(f"{prefix}data-motion-mode must be one of {sorted(MODES)}; got {mode!r}")
    raw_count = root.get("data-step-count", "")
    if not ASCII_DECIMAL_RE.fullmatch(raw_count):
        count = -1
        errors.append(f"{prefix}data-step-count must be an ASCII decimal integer")
    else:
        count = int(raw_count)
    minimum_count = 0 if mode == "none" else 1
    if count < minimum_count or count > 8:
        errors.append(f"{prefix}semantic step count must be {minimum_count}..8; got {count}")

    if len(items) > 12:
        errors.append(f"{prefix}motion item budget is 12; found {len(items)}")
    semantic_steps: list[int] = []
    for index, item in enumerate(items, 1):
        raw_step = item.get("data-step", "")
        if not ASCII_DECIMAL_RE.fullmatch(raw_step):
            errors.append(f"{prefix}motion item {index} has a non-ASCII-decimal data-step")
            continue
        step = int(raw_step)
        decorative = "data-motion-decorative" in item
        if not decorative:
            semantic_steps.append(step)
            if not item.get("aria-label", "").strip():
                errors.append(f"{prefix}semantic motion item {index} needs a non-color aria-label")
        elif item.get("aria-hidden") != "true" or item.get("focusable") != "false":
            errors.append(f"{prefix}decorative motion item {index} needs aria-hidden=true and focusable=false")
        inline = item.get("style", "").replace(" ", "").lower()
        if any(token in inline for token in ("display:none", "visibility:hidden", "opacity:0")):
            errors.append(f"{prefix}motion item {index} is hidden in source; the fallback must be visible")

    expected = set(range(1, count + 1)) if count > 0 else set()
    if set(semantic_steps) != expected:
        errors.append(f"{prefix}semantic steps must be contiguous 1..{count}; found {sorted(set(semantic_steps))}")
    crowded = {step: n for step, n in Counter(semantic_steps).items() if n > 2}
    if crowded:
        errors.append(f"{prefix}no more than two semantic items may share a step; found {crowded}")

    if not manual and mode in {"none", "loop"} and has_script:
        errors.append(f"{prefix}{mode} mode must be script-free")
    if mode in {"none", "loop"} and (controls or actions or statuses):
        errors.append(f"{prefix}{mode} mode must not expose playback controls or live status")
    controlled = mode == "step" or (mode == "reveal" and has_script)
    if controlled:
        if controls != 1:
            errors.append(f"{prefix}controlled mode needs one in-root control group; found {controls}")
        missing = ACTIONS - actions
        if missing:
            errors.append(f"{prefix}controlled mode is missing actions: {', '.join(sorted(missing))}")
        if not statuses:
            errors.append(f"{prefix}controlled mode needs data-motion-status inside the root")
        else:
            if manual and len(statuses) != 1:
                errors.append(f"{prefix}controlled mode needs exactly one data-motion-status; found {len(statuses)}")
            status = statuses[0]
            if (
                status.get("role") != "status"
                or status.get("aria-live") != "polite"
                or status.get("aria-atomic") != "true"
            ):
                errors.append(f"{prefix}motion status needs role=status, aria-live=polite, aria-atomic=true")
            if bucket["statuses_in_controls"]:
                errors.append(f"{prefix}motion status must sit outside data-motion-controls")
        if not has_script:
            errors.append(f"{prefix}controlled mode needs the scoped control script")

    if manual:
        openers = bucket["openers"]
        in_header = bucket["openers_in_header"]
        if openers != 1:
            errors.append(f"{prefix}needs exactly one data-diagram-open; found {openers}")
        elif in_header != 1:
            errors.append(f"{prefix}data-diagram-open must sit inside the root's .diagram-header")


def check_architecture_delta(
    bucket: dict[str, object],
    id_counts: Counter[str],
    errors: list[str],
    prefix: str,
) -> None:
    root = bucket["attrs"]
    items = bucket["items"]
    ghost_refs = bucket["ghost_refs"]
    assert isinstance(root, dict) and isinstance(items, list) and isinstance(ghost_refs, list)
    if root.get("data-semantic-pattern", "").strip().casefold() != "architecture-delta":
        return
    mode = root.get("data-motion-mode", "")
    raw_count = root.get("data-step-count", "")
    if mode != "step" or raw_count != "4":
        errors.append(
            f"{prefix}architecture-delta requires data-motion-mode='step' and data-step-count='4' "
            f"(got mode={mode!r}, count={raw_count!r})"
        )
    if root.get("data-frame") != "end":
        errors.append(f"{prefix}architecture-delta requires data-frame='end' on normal load")
    by_step: dict[int, list[str]] = {}
    for item in items:
        if "data-motion-decorative" in item:
            continue
        raw_step = item.get("data-step", "")
        if ASCII_DECIMAL_RE.fullmatch(raw_step):
            text = f"{item.get('data-delta-phase', '')} {item.get('aria-label', '')}".casefold()
            by_step.setdefault(int(raw_step), []).append(text)
    for step_num, phase_title, tokens in ARCH_DELTA_PHASES:
        labels = by_step.get(step_num, [])
        if not labels or not any(tok in lbl for lbl in labels for tok in tokens):
            errors.append(
                f"{prefix}architecture-delta step {step_num} must represent {phase_title} "
                "(order: 1 Removals -> 2 Moves -> 3 Modifications -> 4 Additions)"
            )
    for ghost_target in ghost_refs:
        target = str(ghost_target).strip()
        if not target or id_counts.get(target, 0) != 1:
            errors.append(
                f"{prefix}data-delta-ghost-of={ghost_target!r} must resolve to a unique element id in the document"
            )


def check_diagram_modal(parser: DiagramParser, errors: list[str]) -> None:
    if len(parser.dialogs) != 1:
        errors.append(f"expected exactly one <dialog data-diagram-modal>; found {len(parser.dialogs)}")
    else:
        dialog = parser.dialogs[0]
        if dialog["bodies"] != 1:
            errors.append(f"diagram modal needs exactly one data-diagram-modal-body; found {dialog['bodies']}")
        if dialog["closes"] < 1:
            errors.append("diagram modal needs at least one data-diagram-close")
    if parser.openers_outside_root:
        errors.append(f"data-diagram-open outside a data-motion-root header ({parser.openers_outside_root})")


def check_shadows(parser: DiagramParser, errors: list[str]) -> None:
    css = re.sub(r"/\*.*?\*/", "", "".join(parser.styles) + "\n" + "\n".join(parser.inline_styles), flags=re.DOTALL)
    found = sorted({match.group(0).strip().lower() for match in SHADOW_TOKEN_RE.finditer(css)})
    if found:
        errors.append(f"shadow/glow tokens are banned in diagram CSS (borders, not shadows): {', '.join(found)}")


def check_fonts(parser: DiagramParser, errors: list[str]) -> None:
    css = re.sub(r"/\*.*?\*/", "", "".join(parser.styles) + "\n" + "\n".join(parser.inline_styles), flags=re.DOTALL)
    for match in FONT_DECL_RE.finditer(css):
        if "jetbrains mono" in match.group(1).casefold():
            errors.append("JetBrains Mono font-family is forbidden in diagram CSS")
            break


def check_portal_sidecars(path: Path, errors: list[str]) -> None:
    try:
        resolved = path.resolve()
    except OSError:
        return
    if "docs" not in {part.casefold() for part in resolved.parts}:
        return
    parent = resolved.parent
    stem = resolved.stem
    forbidden_candidates = (
        parent / ".archify-delivery-lock.json",
        parent / f"{stem}.delivery.json",
        parent / f"{stem}.finalize.json",
        parent / f"{stem}.finalize-summary.json",
        parent / f"{stem}.browser-check.json",
    )
    for candidate in forbidden_candidates:
        if candidate.exists():
            errors.append(f"Portal docs/ directory contains forbidden Archify sidecar: {candidate.name}")


def check_geometry(path: Path, source: str, errors: list[str]) -> None:
    rects: list[tuple[float, float, float, float, int, int]] = []
    for match in RECT_RE.finditer(source):
        rects.append(
            (
                float(match.group("x")),
                float(match.group("y")),
                float(match.group("w")),
                float(match.group("h")),
                source.count("\n", 0, match.start()) + 1,
                match.start(),
            )
        )
    nodes = [r for r in rects if r[2] >= NODE_MIN_W and r[3] >= NODE_MIN_H]
    masks = [r for r in rects if MASK_MIN_W <= r[2] <= MASK_MAX_W and MASK_MIN_H <= r[3] <= MASK_MAX_H]
    for mx, my, mw, mh, mline, moff in masks:
        for nx, ny, nw, nh, nline, noff in nodes:
            if noff <= moff:
                continue
            dx = min(mx + mw, nx + nw) - max(mx, nx)
            dy = min(my + mh, ny + nh) - max(my, ny)
            inside = (
                mx >= nx - EPSILON
                and my >= ny - EPSILON
                and mx + mw <= nx + nw + EPSILON
                and my + mh <= ny + nh + EPSILON
            )
            if dx <= 1.0 or dy <= 1.0 or inside:
                continue
            errors.append(
                f"{path.name}:{mline}: label mask ({mx:g},{my:g} {mw:g}x{mh:g}) is clipped by node "
                f"({nx:g},{ny:g} {nw:g}x{nh:g}) declared later at line {nline} (overlap {dx:g}x{dy:g}px)"
            )
            break


def check_document_fallbacks(parser: DiagramParser, source: str, errors: list[str], *, manual: bool) -> None:
    style_source = "".join(parser.styles)
    if re.search(r"prefers-reduced-motion\s*:\s*reduce", style_source, re.IGNORECASE) is None:
        errors.append("missing reduced-motion CSS fallback (prefers-reduced-motion)")
    if re.search(r"@media\s+print\b", style_source, re.IGNORECASE) is None:
        errors.append("missing print CSS fallback (@media print)")
    if manual:
        if parser.noscripts != 1:
            errors.append(
                "motion file needs exactly one document-level <noscript> explanation of the complete static frame; "
                f"found {parser.noscripts}"
            )
    elif "<noscript" not in source.casefold():
        errors.append("motion file needs a <noscript> explanation of the complete static frame")


def check_motion(parser: DiagramParser, source: str, errors: list[str]) -> None:
    manual = any(script["attr_names"] == ["data-manual-controls"] for script in parser.scripts)
    has_motion_markup = bool(parser.roots or parser.scripts or parser.document_errors)
    if not has_motion_markup:
        return
    errors.extend(parser.document_errors)
    id_counts = Counter(parser.all_ids)
    if manual:
        if not parser.root_buckets:
            errors.append("a Publication Manual needs at least one data-motion-root")
        for number, bucket in enumerate(parser.root_buckets, 1):
            check_root(bucket, errors, f"root {number}: ", manual=True, has_script=True)
            check_architecture_delta(bucket, id_counts, errors, f"root {number}: ")
        check_diagram_modal(parser, errors)
        check_shadows(parser, errors)
    else:
        if len(parser.roots) != 1:
            errors.append(f"expected exactly one data-motion-root; found {len(parser.roots)}")
            return
        check_root(parser.root_buckets[0], errors, "", manual=False, has_script=bool(parser.scripts))
        check_architecture_delta(parser.root_buckets[0], id_counts, errors, "")
    if parser.scripts:
        check_document_fallbacks(parser, source, errors, manual=manual)


def error_to_diagnostic(path: Path, error: str) -> dict[str, object]:
    lowered = error.casefold()
    if "label mask" in lowered:
        code = "geometry/label-mask-clipped"
        fixes = ["move the label mask onto an open connector segment clear of later-painted nodes"]
    elif "architecture-delta" in lowered or "data-delta-ghost-of" in lowered:
        code = "pattern/architecture-delta-invalid"
        fixes = ["use step mode with data-step-count='4', data-frame='end', and 1 Removals -> 2 Moves -> 3 Modifications -> 4 Additions"]
    elif "archify" in lowered or "jetbrains mono" in lowered:
        code = "portal/tier3-bundle-forbidden"
        fixes = ["author Portal HTML/SVG with diagram-design and stage Archify bundles outside docs/"]
    elif "script" in lowered or "controller" in lowered:
        code = "controller/non-canonical"
        fixes = ["copy the canonical controller verbatim or run sync_manual_controls.py --write"]
    elif "svg" in lowered:
        code = "a11y/svg-contract"
        fixes = ["ensure <svg role='img'> has first-child <title> and <desc> referenced by aria-labelledby"]
    else:
        code = "contract/self-check-violation"
        fixes = ["resolve the reported diagram contract finding and re-run self_check.py"]
    return {
        "code": code,
        "severity": "error",
        "subject": {"file": str(path)},
        "evidence": {"message": error},
        "supportedFixes": fixes,
    }


def verify(path: Path, *, verify_geometry: bool = False) -> list[str]:
    source = path.read_text(encoding="utf-8")
    parser = parsed_document(source)
    errors: list[str] = []
    errors.extend(parser.unsafe)
    for tag, rel, value in parser.references:
        finding = reference_error(tag, rel, value)
        if finding:
            errors.append(finding)
    check_fonts(parser, errors)
    check_portal_sidecars(path, errors)
    check_svgs(parser, errors)
    check_scripts(parser, errors)
    check_motion(parser, source, errors)
    if verify_geometry:
        check_geometry(path, source, errors)
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("files", nargs="+", type=Path)
    argument_parser.add_argument("--verify-geometry", action="store_true", help="check z-order label-mask clipping")
    argument_parser.add_argument("--json", action="store_true", help="emit machine-readable JSON diagnostics")
    args = argument_parser.parse_args()
    failed = False
    results: list[dict[str, object]] = []
    all_diagnostics: list[dict[str, object]] = []
    for path in args.files:
        try:
            errors = verify(path, verify_geometry=args.verify_geometry)
        except (OSError, UnicodeError) as exc:
            errors = [str(exc)]
        diags = [error_to_diagnostic(path, err) for err in errors]
        all_diagnostics.extend(diags)
        results.append({"ok": not errors, "file": str(path), "diagnostics": diags})
        if errors:
            failed = True
            if not args.json:
                print(f"FAIL {path}")
                for error in errors:
                    print(f"  - {error}")
        elif not args.json:
            print(f"OK {path}")
    if args.json:
        if len(results) == 1:
            print(json.dumps(results[0], ensure_ascii=False))
        else:
            print(json.dumps({"ok": not failed, "file": str(args.files[0]), "diagnostics": all_diagnostics, "results": results}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
