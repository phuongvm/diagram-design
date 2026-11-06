# Publication Manual Layout & Interactive Controls (`assets/template-manual.html`)

Start from `assets/template-manual.html` for any multi-section guide, runbook, or documentation portal index that embeds more than one section or more than one diagram. Single-column `assets/template-full.html` is reserved for single-hero diagrams only.

## 1. Required Document Structure (In Order)

1. `nav.top-nav` — brand link to `index.html` plus sibling-document navigation buttons; the active page carries `class="current"`.
2. `div.layout-frame` — CSS grid `260px 1fr`; collapses to one column under 900px.
3. `aside.toc-sidebar` — sticky, lists every `section[id]` of the article; use `.toc-group` labels for grouped portals.
4. `article` — `div.report-meta-badge` (doc ID, edition), `h1.report-title`, `div.metadata-grid` (`.meta-item` label/value pairs), `div.callout-box` with the one-paragraph summary.
5. Sections — `h2.section-heading`, then figures packaged as `div.diagram-container` > `div.diagram-header` (figure number and `VISUAL PATTERN` tag) + `div.diagram-viewport` (inline `<svg>`) + `div.diagram-caption` (takeaway and link to the standalone `diagrams/<slug>.svg`). Tables go in `div.table-container`; commands in dark `pre > code`.
6. `footer` — document reference line.

## 2. Customization & Migration Rules

- Keep every inline SVG unchanged when migrating an older page; preserve existing section and row anchor IDs (`#skill-*`, `#os-*`, `#fig-*`) and cross-links.
- Vary only `--doc-accent` and `--doc-accent-tint` per document; add no external CSS/JS framework.
- Do not include `<link rel="preconnect">` tags for font domains; use only the single authorized Google Fonts stylesheet `<link>` to satisfy single-file and remote-reference safety in `scripts/self_check.py`.
- The one permitted script is the canonical `<script data-manual-controls>` copied verbatim from `assets/template-manual.html`.

## 3. Interactive Controls & Adaptive `--svg-*` Polarity

All interactive controls are inert without JavaScript so the page reads complete as static HTML:

- **Collapsible TOC & Theme Toggle**: `[data-toc-toggle]` in `.top-nav` collapses the sidebar to a full-width article (also via the `[` key outside text inputs); omit it on single-column pages. `[data-theme-toggle]` pins `html[data-theme="light"|"dark"]`; both persist in `localStorage`.
- **Adaptive Dark/Light `--svg-*` Diagram Tokens**: Every Publication Manual declares the 19 semantic `--svg-*` tokens (`--svg-paper`, `--svg-surface`, `--svg-panel`, `--svg-ink`, `--svg-muted`, `--svg-soft`, `--svg-rule`, `--svg-accent`, `--svg-accent-tint`, `--svg-green`, `--svg-green-tint`, `--svg-blue`, `--svg-blue-tint`, `--svg-purple`, `--svg-purple-tint`, `--svg-amber`, `--svg-amber-tint`, `--svg-red`, `--svg-red-tint`) in `:root`, `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`, and `html[data-theme="dark"]`. `.diagram-viewport` uses `background: var(--svg-paper)` (never hardcoded `#f5f5f5`/`#ffffff`), and inline `<svg>` elements use `var(--svg-*, <fallback>)` for fills, strokes, text, and markers so dark theme flips diagrams seamlessly.
- **Fullscreen Modal (`<dialog data-diagram-modal>`)**: Include exactly one document-level `<dialog data-diagram-modal>` (holding one `[data-diagram-modal-body]` and a `[data-diagram-close]`) per page. Each figure root carries `[data-diagram-open]` in its `.diagram-header`; the controller reparents the live root into the dialog and back so SVG IDs stay unique.
- **Ordered-Narrative Walkthroughs**: Ordered-narrative figures use `data-motion-mode="step"` (`3..7` steps, or `4` fixed phases `1: Removals`, `2: Moves`, `3: Modifications`, `4: Additions` when `data-semantic-pattern="architecture-delta"`, at most 2 items per step, loading complete at `step = count` / `data-frame="end"`) with one `[data-motion-controls]` bar and one `.diagram-annotation-banner[data-motion-status]` inside the root but outside the controls. Matrices, legends, and inventories use `data-motion-mode="none" data-step-count="0"` with the opener only.
- **Emphasis & Fallbacks**: `.is-current` emphasis uses an accent stroke plus contrast, never a shadow or glow. Include one `<noscript>`, one `@media print`, and one `prefers-reduced-motion: reduce` block per document.

## 4. Multi-Document Portal & Verification Workflow

- **Multi-Diagram Deliverable**: Embed each `<svg>` inline directly into the document; never use `<object>`, `<img>`, or `<iframe>` tags. Provide external links to standalone `.svg` copies saved under `docs/diagrams/<slug>.svg`.
- **Multi-Document Architecture Portals**: Separate distinct domains or pillars into dedicated standalone HTML guides anchored by a master Portal index (`index.html`) whose sticky `toc-sidebar` groups documents and standalone SVG assets by domain. Assign stable row anchors (`id="<prefix>-<slug>"`) so counterpart tables cross-link directly (`<sibling>-guide.html#<id>`), and pair top-level topology diagrams with component deep-dive diagrams selected from the 39 visual types.
- **Controller Update & Verification Procedure**: Edit the controller only in `assets/template-manual.html`, then run:
  ```bash
  python3 scripts/sync_manual_controls.py --write <pages>
  python3 scripts/sync_manual_controls.py --check --canonical assets/template-manual.html <pages>
  python3 scripts/check_manual_selectors.py <pages>
  python3 scripts/self_check.py <pages>
  ```
  Alongside these scripts, verify that every local `href` and `#anchor` target resolves.
