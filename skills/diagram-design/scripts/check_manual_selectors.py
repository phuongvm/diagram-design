#!/usr/bin/env python3
"""Assert the per-page Publication Manual selector and dark-theme polarity checklist.

    python3 scripts/check_manual_selectors.py <page.html> [<page.html> ...]

Prints `OK` when every page satisfies the checklist, otherwise one `<path>: <violation>` line per
problem; exit code 0 / 1. It complements `self_check.py` (contract and safety) and
`sync_manual_controls.py --check` (controller parity) by verifying:

  [data-toc-toggle]          exactly 1 on a page with `aside.toc-sidebar`; 0 on a single-column page
  [data-theme-toggle]        exactly 1
  <dialog data-diagram-modal> exactly 1, holding exactly 1 [data-diagram-modal-body] and >= 1 [data-diagram-close]
  [data-diagram-open]        exactly 1 per [data-motion-root], none outside a root
  step-mode root             exactly 1 [data-motion-controls] and 1 [data-motion-status] (status inside the
                             root, outside the controls); none-mode root: no controls, actions or status
  <script data-manual-controls> exactly 1; <noscript> exactly 1
  @media print, prefers-reduced-motion: reduce   present in the document styles
  shadow / glow tokens in CSS or inline styles   0
  dark-theme SVG & viewport polarity (fail-closed):
    - base :root, explicit html[data-theme=dark|light], and @media (prefers-color-scheme: dark|light)
      define core + referenced --svg-* tokens with distinct light/dark polarity on paper/surface/ink/muted
    - .diagram-viewport sets background via var(--svg-paper) with zero hardcoded #hex/rgb/rgba/named backgrounds
    - inline <svg> elements contain zero raw #hex / rgb() fill, stroke, stop-color, or background literals
      outside CSS custom property definitions (--*: ...) and defined var(--*, fallback) expressions
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

SHADOW_RE = re.compile(
    r"(?<![\w-])(?:box-shadow|text-shadow)\s*:|drop-shadow\s*\(|(?<![\w-])filter\s*:[^;}]*\bblur\s*\(",
    re.IGNORECASE,
)
CORE_SVG_TOKENS = ("--svg-paper", "--svg-surface", "--svg-ink", "--svg-muted")
SVG_PAINT_ATTRS = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color", "background")
SVG_STYLE_PAINT_PROPS = frozenset(
    {
        "fill",
        "stroke",
        "stop-color",
        "flood-color",
        "lighting-color",
        "color",
        "background",
        "background-color",
        "border",
        "border-color",
        "outline",
        "outline-color",
    }
)
URL_REF_RE = re.compile(r"url\(\s*['\"]?#[^)'\"]+['\"]?\s*\)", re.IGNORECASE)
VAR_START_RE = re.compile(r"\bvar\s*\(", re.IGNORECASE)
CUSTOM_PROP_RE = re.compile(r"^--[a-zA-Z0-9_-]+$")
HEX_COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F\w-])"
)
RGB_OPAQUE_RE = re.compile(r"\brgb\s*\(", re.IGNORECASE)
COLOR_FUNC_RE = re.compile(
    r"\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\s*\(",
    re.IGNORECASE,
)
NAMED_BG_COLOR_RE = re.compile(
    r"\b(?:white|whitesmoke|black|snow|ivory|ghostwhite|floralwhite|aliceblue|beige|linen|gainsboro|lightgray|lightgrey)\b",
    re.IGNORECASE,
)
EXPLICIT_DARK_ROOT_RE = re.compile(
    r"^(?:html|:root)?\[\s*data-theme\s*=\s*['\"]?dark['\"]?\s*\]$",
    re.IGNORECASE,
)
EXPLICIT_LIGHT_ROOT_RE = re.compile(
    r"^(?:html|:root)?\[\s*data-theme\s*=\s*['\"]?light['\"]?\s*\]$",
    re.IGNORECASE,
)
MEDIA_ROOT_SELECTOR_RE = re.compile(
    r"^(?:html|:root)(?::not\([^)]*\))?$",
    re.IGNORECASE,
)


def split_css_declarations(body: str) -> list[tuple[str, str]]:
    """Split a CSS declaration block into (property, value) pairs respecting parentheses."""
    declarations: list[tuple[str, str]] = []
    depth = 0
    quote: str | None = None
    start = 0
    for index, char in enumerate(body):
        if quote is not None:
            if char == quote and (index == 0 or body[index - 1] != "\\"):
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif char == ";" and depth == 0:
            chunk = body[start:index].strip()
            if ":" in chunk:
                prop, val = chunk.split(":", 1)
                declarations.append((prop.strip().casefold(), val.strip()))
            start = index + 1
    tail = body[start:].strip()
    if ":" in tail:
        prop, val = tail.split(":", 1)
        declarations.append((prop.strip().casefold(), val.strip()))
    return declarations


def iter_css_rules(css: str, media: str | None = None) -> list[tuple[str | None, str, str]]:
    """Yield (enclosing_media_header, selector_group, declarations_body) across balanced CSS blocks."""
    rules: list[tuple[str | None, str, str]] = []
    index = 0
    length = len(css)
    while index < length:
        brace = css.find("{", index)
        if brace < 0:
            break
        header = " ".join(css[index:brace].split())
        depth = 1
        cursor = brace + 1
        quote: str | None = None
        while cursor < length and depth > 0:
            char = css[cursor]
            if quote is not None:
                if char == quote and css[cursor - 1] != "\\":
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            cursor += 1
        if depth != 0:
            break
        body = css[brace + 1 : cursor - 1]
        if header.startswith("@"):
            lowered = header.casefold()
            if lowered.startswith("@media"):
                nested_media = f"{media} and {header}" if media else header
                rules.extend(iter_css_rules(body, nested_media))
            elif lowered.startswith(("@supports", "@layer", "@container")):
                rules.extend(iter_css_rules(body, media))
        elif header:
            rules.append((media, header, body))
        index = cursor
    return rules


def strip_var_and_url(value: str) -> tuple[str, list[str]]:
    """Remove url(#id) refs and balanced var(--name, fallback) calls, returning (residual, var_names)."""
    cleaned = URL_REF_RE.sub("", value)
    used_vars: list[str] = []
    output: list[str] = []
    index = 0
    length = len(cleaned)
    while index < length:
        match = VAR_START_RE.search(cleaned, index)
        if match is None:
            output.append(cleaned[index:])
            break
        output.append(cleaned[index : match.start()])
        depth = 1
        cursor = match.end()
        quote: str | None = None
        comma_pos: int | None = None
        while cursor < length and depth > 0:
            char = cleaned[cursor]
            if quote is not None:
                if char == quote and cleaned[cursor - 1] != "\\":
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            elif char == "," and depth == 1 and comma_pos is None:
                comma_pos = cursor
            cursor += 1
        if depth != 0:
            # Unbalanced var(: fail closed by keeping the raw text in residual.
            output.append(cleaned[match.start() :])
            break
        inner = cleaned[match.end() : cursor]
        if comma_pos is not None:
            var_name = cleaned[match.end() : comma_pos].strip()
            fallback = cleaned[comma_pos + 1 : cursor]
        else:
            var_name = inner.strip()
            fallback = ""
        if CUSTOM_PROP_RE.fullmatch(var_name):
            used_vars.append(var_name)
            if fallback:
                _nested_residual, nested_vars = strip_var_and_url(fallback)
                used_vars.extend(nested_vars)
        else:
            output.append(cleaned[match.start() : cursor + 1])
        index = cursor + 1
    return "".join(output), used_vars


def normalize_css_value(value: str) -> str:
    return "".join(value.split()).casefold()


def selector_targets_viewport(selector: str) -> bool:
    """True when the compound subject of `selector` is `.diagram-viewport` itself."""
    cleaned = re.sub(r":(?:is|where|not|has)\([^)]*\)", "", selector)
    parts = re.split(r"[\s>+~]+", cleaned.strip())
    if not parts:
        return False
    subject = parts[-1].split(":", 1)[0]
    return ".diagram-viewport" in subject and not subject.endswith("svg")


def selector_targets_svg(selector: str) -> bool:
    cleaned = re.sub(r":(?:is|where|not|has)\([^)]*\)", "", selector)
    parts = re.split(r"[\s>+~]+", cleaned.strip())
    if not parts:
        return False
    subject = parts[-1].split(":", 1)[0]
    return subject == "svg" or subject.startswith("svg.") or subject.startswith("svg[")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.toc_toggles = 0
        self.theme_toggles = 0
        self.toc_sidebars = 0
        self.manual_scripts = 0
        self.noscripts = 0
        self.dialogs: list[dict[str, int]] = []
        self.roots: list[dict[str, object]] = []
        self.stray: set[str] = set()
        self.styles: list[str] = []
        self.inline_styles: list[str] = []
        self.viewport_inline_styles: list[str] = []
        self.svgs: list[dict[str, object]] = []
        self._stack: list[str] = []
        self._root: dict[str, object] | None = None
        self._root_depth = 0
        self._controls_depth: int | None = None
        self._dialog: dict[str, int] | None = None
        self._dialog_depth = 0
        self._in_doc_style = False
        self._in_svg_style = False
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._current_svg_style: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = {key.casefold(): value or "" for key, value in attrs}
        depth = len(self._stack)
        classes = data.get("class", "").split()
        if "style" in data:
            self.inline_styles.append(data["style"])
            if "diagram-viewport" in classes:
                self.viewport_inline_styles.append(data["style"])
        if tag == "svg":
            if self._svg_depth == 0:
                self._current_svg = {
                    "attrs": [],
                    "inline_styles": [],
                    "style_blocks": [],
                }
                self.svgs.append(self._current_svg)
            self._svg_depth += 1
        if self._svg_depth > 0 and self._current_svg is not None:
            if tag == "style":
                self._in_svg_style = True
                self._current_svg_style = []
            else:
                svg_attrs = self._current_svg["attrs"]
                assert isinstance(svg_attrs, list)
                for paint_attr in SVG_PAINT_ATTRS:
                    if paint_attr in data and data[paint_attr].strip():
                        svg_attrs.append((tag, paint_attr, data[paint_attr].strip()))
                if "style" in data and data["style"].strip():
                    svg_inline = self._current_svg["inline_styles"]
                    assert isinstance(svg_inline, list)
                    svg_inline.append((tag, data["style"]))
        elif tag == "style":
            self._in_doc_style = True
        if tag == "noscript":
            self.noscripts += 1
        if tag == "script" and "data-manual-controls" in data:
            self.manual_scripts += 1
        if tag == "aside" and "toc-sidebar" in classes:
            self.toc_sidebars += 1
        self.toc_toggles += "data-toc-toggle" in data
        self.theme_toggles += "data-theme-toggle" in data
        if "data-motion-root" in data and self._root is None:
            self._root = {
                "mode": data.get("data-motion-mode", ""),
                "openers": 0,
                "controls": 0,
                "statuses": 0,
                "actions": 0,
                "status_in_controls": 0,
            }
            self._root_depth = depth
            self.roots.append(self._root)
        if self._root is not None:
            if "data-motion-controls" in data:
                self._root["controls"] += 1
                if self._controls_depth is None:
                    self._controls_depth = depth
            if "data-motion-action" in data:
                self._root["actions"] += 1
            if "data-motion-status" in data:
                self._root["statuses"] += 1
                if self._controls_depth is not None:
                    self._root["status_in_controls"] += 1
        else:
            for key in ("data-motion-controls", "data-motion-action", "data-motion-status", "data-motion-item"):
                if key in data:
                    self.stray.add(key)
        if "data-diagram-open" in data:
            if self._root is None:
                self.stray.add("data-diagram-open")
            else:
                self._root["openers"] += 1
        if tag == "dialog" and "data-diagram-modal" in data:
            new = {"bodies": 0, "closes": 0}
            self.dialogs.append(new)
            if self._dialog is None:
                self._dialog, self._dialog_depth = new, depth
        if self._dialog is not None:
            self._dialog["bodies"] += "data-diagram-modal-body" in data
            self._dialog["closes"] += "data-diagram-close" in data
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "style":
            if self._in_svg_style:
                self._in_svg_style = False
                if self._current_svg is not None and self._current_svg_style is not None:
                    blocks = self._current_svg["style_blocks"]
                    assert isinstance(blocks, list)
                    blocks.append("".join(self._current_svg_style))
                self._current_svg_style = None
            else:
                self._in_doc_style = False
        if tag == "svg" and self._svg_depth > 0:
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index] == tag:
                del self._stack[index:]
                break
        depth = len(self._stack)
        if self._root is not None and depth <= self._root_depth:
            self._root, self._controls_depth = None, None
        if self._controls_depth is not None and depth <= self._controls_depth:
            self._controls_depth = None
        if self._dialog is not None and depth <= self._dialog_depth:
            self._dialog = None

    def handle_data(self, data: str) -> None:
        if self._in_svg_style and self._current_svg_style is not None:
            self._current_svg_style.append(data)
        elif self._in_doc_style:
            self.styles.append(data)


def check_polarity(page: PageParser, css: str, problems: list[str]) -> None:
    """Enforce fail-closed dark/light polarity on CSS --svg-* tokens, .diagram-viewport, and inline <svg>."""
    base_vars: dict[str, str] = {}
    explicit_dark_vars: dict[str, str] = {}
    explicit_light_vars: dict[str, str] = {}
    media_dark_vars: dict[str, str] = {}
    media_light_vars: dict[str, str] = {}
    defined_vars: set[str] = set()
    referenced_svg_vars: set[str] = set()
    viewport_uses_svg_paper = False
    viewport_hardcoded: list[str] = []

    for media, selector_group, decl_body in iter_css_rules(css):
        declarations = split_css_declarations(decl_body)
        custom_props = {prop: val for prop, val in declarations if prop.startswith("--")}
        defined_vars.update(custom_props)
        for _prop, val in declarations:
            _res, used = strip_var_and_url(val)
            referenced_svg_vars.update(v for v in used if v.startswith("--svg-"))

        selectors = [" ".join(sel.split()) for sel in selector_group.split(",") if sel.strip()]
        for sel in selectors:
            if media is None:
                if sel.casefold() in {":root", "html"}:
                    base_vars.update(custom_props)
                elif EXPLICIT_DARK_ROOT_RE.fullmatch(sel):
                    explicit_dark_vars.update(custom_props)
                elif EXPLICIT_LIGHT_ROOT_RE.fullmatch(sel):
                    explicit_light_vars.update(custom_props)
            elif re.search(r"prefers-color-scheme\s*:\s*dark\b", media, re.IGNORECASE):
                if MEDIA_ROOT_SELECTOR_RE.fullmatch(sel):
                    media_dark_vars.update(custom_props)
            elif re.search(r"prefers-color-scheme\s*:\s*light\b", media, re.IGNORECASE):
                if MEDIA_ROOT_SELECTOR_RE.fullmatch(sel):
                    media_light_vars.update(custom_props)

            if selector_targets_viewport(sel):
                for prop, val in declarations:
                    if prop not in {"background", "background-color"}:
                        continue
                    residual, used = strip_var_and_url(val)
                    if "--svg-paper" in used:
                        viewport_uses_svg_paper = True
                    if (
                        HEX_COLOR_RE.search(residual)
                        or COLOR_FUNC_RE.search(residual)
                        or NAMED_BG_COLOR_RE.search(residual)
                    ):
                        viewport_hardcoded.append(f"{prop}: {val}")
            elif selector_targets_svg(sel):
                for prop, val in declarations:
                    if prop not in {"background", "background-color"}:
                        continue
                    residual, _used = strip_var_and_url(val)
                    if (
                        HEX_COLOR_RE.search(residual)
                        or COLOR_FUNC_RE.search(residual)
                        or NAMED_BG_COLOR_RE.search(residual)
                    ):
                        viewport_hardcoded.append(f"{sel} {{ {prop}: {val} }}")

    for inline_style in page.viewport_inline_styles:
        for prop, val in split_css_declarations(inline_style):
            if prop not in {"background", "background-color"}:
                continue
            residual, used = strip_var_and_url(val)
            if (
                "--svg-paper" not in used
                or HEX_COLOR_RE.search(residual)
                or COLOR_FUNC_RE.search(residual)
                or NAMED_BG_COLOR_RE.search(residual)
            ):
                viewport_hardcoded.append(f'inline style="{prop}: {val}"')

    if viewport_hardcoded:
        problems.append(
            ".diagram-viewport has hardcoded background color literal "
            f"({', '.join(viewport_hardcoded[:3])}); use background: var(--svg-paper)"
        )
    elif page.roots and not viewport_uses_svg_paper:
        problems.append(".diagram-viewport must set background: var(--svg-paper)")

    for svg_number, svg in enumerate(page.svgs, 1):
        svg_attrs = svg["attrs"]
        svg_inline = svg["inline_styles"]
        svg_style_blocks = svg["style_blocks"]
        assert isinstance(svg_attrs, list) and isinstance(svg_inline, list) and isinstance(svg_style_blocks, list)

        local_vars: set[str] = set()
        cleaned_svg_styles: list[str] = []
        for raw_block in svg_style_blocks:
            cleaned_block = re.sub(r"/\*.*?\*/", "", raw_block, flags=re.DOTALL)
            cleaned_svg_styles.append(cleaned_block)
            for _m, _sel, decl_body in iter_css_rules(cleaned_block):
                for prop, _val in split_css_declarations(decl_body):
                    if prop.startswith("--"):
                        local_vars.add(prop)
        for _tag, style_text in svg_inline:
            for prop, _val in split_css_declarations(style_text):
                if prop.startswith("--"):
                    local_vars.add(prop)

        allowed_vars = defined_vars | local_vars
        raw_hits: list[str] = []
        undef_hits: list[str] = []

        for tag, attr, val in svg_attrs:
            residual, used = strip_var_and_url(val)
            referenced_svg_vars.update(v for v in used if v.startswith("--svg-"))
            for var_name in used:
                if var_name not in allowed_vars:
                    undef_hits.append(f'{var_name} in <{tag} {attr}="{val}">')
            if (
                HEX_COLOR_RE.search(residual)
                or RGB_OPAQUE_RE.search(residual)
                or (attr in {"background", "background-color"} and COLOR_FUNC_RE.search(residual))
            ):
                raw_hits.append(f'<{tag} {attr}="{val}">')

        for tag, style_text in svg_inline:
            for prop, val in split_css_declarations(style_text):
                if prop.startswith("--") or prop not in SVG_STYLE_PAINT_PROPS:
                    continue
                residual, used = strip_var_and_url(val)
                referenced_svg_vars.update(v for v in used if v.startswith("--svg-"))
                for var_name in used:
                    if var_name not in allowed_vars:
                        undef_hits.append(f'{var_name} in <{tag} style="{prop}: {val}">')
                if (
                    HEX_COLOR_RE.search(residual)
                    or RGB_OPAQUE_RE.search(residual)
                    or (prop in {"background", "background-color"} and COLOR_FUNC_RE.search(residual))
                ):
                    raw_hits.append(f'<{tag} style="{prop}: {val}">')

        for cleaned_block in cleaned_svg_styles:
            for _m, _sel, decl_body in iter_css_rules(cleaned_block):
                for prop, val in split_css_declarations(decl_body):
                    if prop.startswith("--") or prop not in SVG_STYLE_PAINT_PROPS:
                        continue
                    residual, used = strip_var_and_url(val)
                    referenced_svg_vars.update(v for v in used if v.startswith("--svg-"))
                    for var_name in used:
                        if var_name not in allowed_vars:
                            undef_hits.append(f"{var_name} in <style {prop}: {val}>")
                    if (
                        HEX_COLOR_RE.search(residual)
                        or RGB_OPAQUE_RE.search(residual)
                        or (prop in {"background", "background-color"} and COLOR_FUNC_RE.search(residual))
                    ):
                        raw_hits.append(f"<style {prop}: {val}>")

        if raw_hits:
            preview = ", ".join(raw_hits[:3])
            if len(raw_hits) > 3:
                preview += f" (+{len(raw_hits) - 3} more)"
            problems.append(
                f"svg {svg_number}: raw #hex color literal outside CSS variable definition/fallback "
                f"({preview}); use var(--svg-*)"
            )
        if undef_hits:
            problems.append(f"svg {svg_number}: undefined CSS variable {', '.join(undef_hits[:3])}")

    if not page.svgs and not page.roots:
        return

    dark_first = bool(explicit_light_vars or media_light_vars) and not bool(explicit_dark_vars or media_dark_vars)
    opp_name = "light" if dark_first else "dark"
    opp_explicit = explicit_light_vars if dark_first else explicit_dark_vars
    opp_media = media_light_vars if dark_first else media_dark_vars

    required_tokens = sorted(set(CORE_SVG_TOKENS) | referenced_svg_vars)
    missing_base = [tok for tok in required_tokens if tok not in base_vars]
    missing_explicit = [tok for tok in required_tokens if tok not in opp_explicit]
    missing_media = [tok for tok in required_tokens if tok not in opp_media]
    if missing_base:
        problems.append(f"missing base :root --svg-* tokens: {', '.join(missing_base)}")
    if missing_explicit:
        problems.append(f'missing html[data-theme="{opp_name}"] --svg-* tokens: {', '.join(missing_explicit)}')
    if missing_media:
        problems.append(
            f"missing @media (prefers-color-scheme: {opp_name}) --svg-* tokens: {', '.join(missing_media)}"
        )

    for tok in CORE_SVG_TOKENS:
        if tok in base_vars and tok in opp_explicit:
            if normalize_css_value(base_vars[tok]) == normalize_css_value(opp_explicit[tok]):
                problems.append(
                    f'{tok} has identical base and html[data-theme="{opp_name}"] value '
                    f"({base_vars[tok]}); theme polarity must flip"
                )
        if tok in base_vars and tok in opp_media:
            if normalize_css_value(base_vars[tok]) == normalize_css_value(opp_media[tok]):
                problems.append(
                    f"{tok} has identical base and prefers-color-scheme:{opp_name} value "
                    f"({base_vars[tok]}); theme polarity must flip"
                )


def check_page(source: str) -> list[str]:
    page = PageParser()
    page.feed(source)
    page.close()
    problems: list[str] = []
    if page.toc_sidebars and page.toc_toggles != 1:
        problems.append(f"[data-toc-toggle] must appear exactly once on a 2-column page; found {page.toc_toggles}")
    if not page.toc_sidebars and page.toc_toggles:
        problems.append("[data-toc-toggle] is only allowed on a page with aside.toc-sidebar")
    if page.theme_toggles != 1:
        problems.append(f"[data-theme-toggle] must appear exactly once; found {page.theme_toggles}")
    if len(page.dialogs) != 1:
        problems.append(f"<dialog data-diagram-modal> must appear exactly once; found {len(page.dialogs)}")
    else:
        dialog = page.dialogs[0]
        if dialog["bodies"] != 1:
            problems.append(f"dialog needs exactly one [data-diagram-modal-body]; found {dialog['bodies']}")
        if dialog["closes"] < 1:
            problems.append("dialog needs at least one [data-diagram-close]")
    for number, root in enumerate(page.roots, 1):
        label = f"root {number}"
        if root["openers"] != 1:
            problems.append(f"{label}: needs exactly one [data-diagram-open]; found {root['openers']}")
        if root["mode"] == "step":
            if root["controls"] != 1:
                problems.append(f"{label}: step mode needs exactly one [data-motion-controls]; found {root['controls']}")
            if root["statuses"] != 1:
                problems.append(f"{label}: step mode needs exactly one [data-motion-status]; found {root['statuses']}")
            if root["status_in_controls"]:
                problems.append(f"{label}: [data-motion-status] must sit outside [data-motion-controls]")
        elif root["controls"] or root["statuses"] or root["actions"]:
            problems.append(f"{label}: {root['mode'] or 'unmoded'} root must not carry controls, actions or status")
    for key in sorted(page.stray):
        problems.append(f"{key} found outside a [data-motion-root]")
    if page.manual_scripts != 1:
        problems.append(f"<script data-manual-controls> must appear exactly once; found {page.manual_scripts}")
    if page.noscripts != 1:
        problems.append(f"document-level <noscript> must appear exactly once; found {page.noscripts}")
    doc_css = re.sub(r"/\*.*?\*/", "", "".join(page.styles), flags=re.DOTALL)
    if re.search(r"@media\s+print\b", doc_css, re.IGNORECASE) is None:
        problems.append("missing @media print rule set")
    if re.search(r"prefers-reduced-motion\s*:\s*reduce", doc_css, re.IGNORECASE) is None:
        problems.append("missing prefers-reduced-motion: reduce rule set")
    svg_css = "\n".join(
        block
        for svg in page.svgs
        if isinstance(svg["style_blocks"], list)
        for block in svg["style_blocks"]
    )
    all_css_for_shadows = re.sub(
        r"/\*.*?\*/",
        "",
        "".join(page.styles) + "\n" + svg_css + "\n" + "\n".join(page.inline_styles),
        flags=re.DOTALL,
    )
    shadows = sorted({m.group(0).strip().lower() for m in SHADOW_RE.finditer(all_css_for_shadows)})
    if shadows:
        problems.append(f"shadow/glow tokens in CSS: {', '.join(shadows)}")
    check_polarity(page, doc_css, problems)
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check_manual_selectors.py <page.html> [...]")
        return 2
    failed = False
    for name in argv:
        try:
            problems = check_page(Path(name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            problems = [str(exc)]
        for problem in problems:
            failed = True
            print(f"{name}: {problem}")
    if not failed:
        print("OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
