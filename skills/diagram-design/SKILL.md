---
name: diagram-design
description: "Create branded HTML, SVG, and architecture charts."
license: MIT
metadata:
  version: "2.6"
---

# Diagram Design

Create self-contained HTML diagrams with inline SVG and CSS (`paper` `#f5f5f5`, `ink` `#2d3142`, `accent` `#eb6c36`, `muted` `#4f5d75`, `link` `#2e5aa8`). Full 39-type guide and checklists: [`references/diagram-design-full.md`](references/diagram-design-full.md).

## 0. Style-Guide Gate

Check `.diagram-design` per [`references/profiles.md`](references/profiles.md) and tokens in [`references/style-guide.md`](references/style-guide.md); if still default in a new project, offer onboarding per [`references/onboarding.md`](references/onboarding.md).

## 1. When to Use

Use for any of the 39 visual types when a schematic clarifies structure, state, flow, or topology better than prose. Route behavioral triggers via [`references/semantic-patterns.md`](references/semantic-patterns.md) first, then load the matching type guide in `references/`. Multi-section guides (`docs/*.html`, `docs/index.html`) use [`references/publication-manual.md`](references/publication-manual.md).

## 2. Core Rules

1. **4px grid & budget**: all coords/sizes/gaps divisible by 4; max 9 nodes, 12 arrows, 2 coral focal elements (`accent` on 1–2 focal nodes only).
2. **6 connector rules**: orthogonal rounded elbows (`r=8`, never diagonal), 6–10px gap between opaque label mask (`#f5f5f5`) and stroke, bridge/hop crossings, fan shared-edge attach points >=12px apart, no solid lines behind non-endpoint boxes, no label masks clipped by later nodes.
3. **Accessible SVG & checks**: `<svg role="img" aria-labelledby="<slug>-title <slug>-desc">` with `<title>` first child; no `box-shadow`, no `<link rel="preconnect">`, no JetBrains Mono. Verify with `scripts/self_check.py`, `scripts/check_manual_selectors.py`, and `scripts/sync_manual_controls.py --check`.
