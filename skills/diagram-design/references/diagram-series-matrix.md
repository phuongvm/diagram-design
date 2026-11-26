# Canonical Archetype & Progressive Diagram-Series Matrix

This reference (`references/diagram-series-matrix.md`) is the **authoritative governance specification** for the 5 canonical Publication Manual archetypes, their ordered mandatory progressive diagram lens series, allowed visual types across the **51-type catalog**, non-waivable core lenses, HTML5 `data-*` machine-readable tagging, visible `.lens-waiver` contract, and ratchet fail-closed verification gate.

---

## 1. Reader Mental-Model Progression

Multi-section Publication Manuals (`docs/*.html`, `ai_agents/hermes-agent/docs/*.html`, and `kb.inspire-robotics.com`) guide the reader progressively from external boundaries and human frontstage interaction down to internal mechanisms and concrete deployment/recovery topology:

1. **External Context / Frame** — Who or what sits outside the boundary (upstream sources, callers, downstream consumers, value chain)?
2. **System / Pipeline Overview** — What are the core internal subsystems, layers, or transformation stages?
3. **User Interaction (Line of Visibility)** — What does the human user or operator run, click, or observe on the frontstage above the **Line of Visibility** versus what executes automatically backstage?
4. **Low-Level Internals / Storage** — How do schemas, state guards, wire sequences, or feedback loops behave?
5. **Deployment / Governance / Recovery** — Where does the software physically run (hosts, containers, ports, volumes, trust zones) and how does cutover or rollback execute?

---

## 2. Authoritative 5-Archetype Mandatory Lens Matrix

Every archetype-declared manual MUST set `data-doc-archetype="<archetype>"` on `<article>` and satisfy its ordered mandatory diagram lenses using allowed slugs from the 51-type catalog (`scripts/diagram_registry.py`).

| Archetype (`data-doc-archetype`) | # | Ordered Lens ID (`data-diagram-lens`) | Allowed Visual Types (`data-diagram-type`, from 51-type catalog) | Waivable? | Normative Rules & Reader Question Answered |
| :--- | :-: | :--- | :--- | :---: | :--- |
| **`system-design`** | 1 | `system-context` | `dp-integration`, `high-level`, `architecture` | **Embedded / single-process libs ONLY** (never networked or deployed services) | Who calls this system, what feeds it, and what consumes its outputs across external boundaries? |
| | 2 | `architecture-overview` | `architecture`, `layers`, `nested` | **NO (Non-waivable)** | What are the core internal subsystems, layers, and module seams? |
| | 3 | `user-interaction` | `service-blueprint`, `event-modeling`, `swimlane`, `journey` | **NO (Non-waivable)** | What does the user/operator do and observe above the **Line of Visibility** vs. backstage system work? |
| | 4 | `low-level-design` | `db-schema`, `er`, `state`, `sequence`, `dependency`, `uml-class`, `data-flow` | Conditional (`>= 24`-char reason) | How do internal schemas, state machines, wire protocols, or data flows behave? |
| | 5 | `deployment` | `deployment`, `architecture` | **Embedded / single-process libs ONLY** (never networked or deployed services) | Where does software run (hosts, containers, ports, volumes, trust boundaries)? **Normative**: when `architecture` is chosen for `deployment`, it **MUST** apply the **`Secure paved road`** semantic pattern (`references/semantic-patterns.md` — trust zones, hosts, ports, and permitted/forbidden ingress or deploy paths). |
| **`user-operator-guide`** | 1 | `quickstart-steps` | `steps` | **NO (Non-waivable)** | What exact numbered stage rail gets the operator from zero to working? |
| | 2 | `user-interaction` | `service-blueprint`, `journey`, `swimlane` | **NO (Non-waivable)** | What commands or UI actions does the operator perform vs. automated backstage execution? |
| | 3 | `decision-routing` | `flowchart`, `state`, `org-chart` | Conditional (`>= 24`-char reason) | Which operating mode should the operator select, and how are failures triaged? |
| **`runbook-migration`** | 1 | `change-delta` | `architecture-delta`, `it-state` | **NO (Non-waivable)** | What is removed, moved, modified, and added between Before and After topologies? |
| | 2 | `execution-flow` | `swimlane`, `steps`, `sequence`, `gantt` | **NO (Non-waivable)** | What is the ordered cutover choreography across operators and services? |
| | 3 | `deployment-boundary` | `deployment`, `architecture` | Conditional (`>= 24`-char reason) | Which hosts, zones, and security boundaries govern the cutover? **Normative**: when `architecture` is chosen for `deployment-boundary`, it **MUST** apply the **`Secure paved road`** semantic pattern. |
| | 4 | `rollback-recovery` | `flowchart`, `git-graph`, `state` | **NO (Non-waivable)** | What abort trigger halts cutover, and what is the deterministic rollback topology? |
| **`data-pipeline`** | 1 | `integration-topology` | `dp-integration`, `high-level`, `layers` | **NO (Non-waivable)** | Which upstream producers feed the pipeline and which downstream consumers read from it? |
| | 2 | `pipeline-flow` | `data-flow`, `process`, `event-modeling`, `medallion` | **NO (Non-waivable)** | How do records transform, validate, and route across pipeline stages? |
| | 3 | `storage-or-loop` | `medallion`, `db-schema`, `er`, `loop` | Conditional (`>= 24`-char reason) | How is state persisted across storage tiers or compounded in a feedback loop? |
| | 4 | `governance-access` | `dp-security-matrix`, `layers` | Conditional (`>= 24`-char reason, e.g., single-user local desktop app) | Who holds read/write/admin access per tier and where are controls enforced? **Normative**: when `layers` is chosen for `governance-access`, it **MUST** apply the **`Governance / control catalog`** semantic pattern (`references/semantic-patterns.md`). |
| **`strategy-analysis`** | 1 | `strategic-frame` | `architecture`, `wardley`, `quadrant`, `fishbone`, `requirement-traceability` | **NO (Non-waivable)** | What is the structural problem boundary, value chain, root-cause tree, or compliance frame? |
| | 2 | `quantitative-model` | `waterfall`, `bar`, `sankey`, `unit-grid`, `heatmap`, `line`, `radar` | **NO (Non-waivable)** | What do the numbers prove (cost bridge, quota units, volume flow, risk matrix, or benchmark scores)? |
| | 3 | `decision-roadmap` | `quadrant`, `flowchart`, `timeline`, `gantt`, `story-map` | Conditional (`>= 24`-char reason) | Which option wins by explicit trade-off criteria and in what phased sequence? |

### 2.1 Non-Waivable Core Lenses Summary

Ten lenses across the 5 archetypes are **strictly non-waivable** and reject `.lens-waiver` declarations unconditionally:

- **`system-design`**: `architecture-overview`, `user-interaction`
- **`user-operator-guide`**: `quickstart-steps`, `user-interaction`
- **`runbook-migration`**: `change-delta`, `execution-flow`, `rollback-recovery`
- **`data-pipeline`**: `integration-topology`, `pipeline-flow`
- **`strategy-analysis`**: `strategic-frame`, `quantitative-model`

In addition, for **`system-design`**, `system-context` and `deployment` are waivable **ONLY** when the subject is an embedded or single-process library with zero external network boundaries — never for networked services, daemons, web portals, or multi-host deployments.

### 2.2 Supplemental Figures (`data-diagram-lens="supplemental"`)

Any additional supporting figure beyond the mandatory series (for example, secondary subsystem deep dives or auxiliary reference topologies) MUST declare:

- Unique non-empty `id="fig-<slug>"`
- `data-diagram-lens="supplemental"`
- `data-diagram-type="<slug-from-51>"` (any valid slug in the 51-type catalog)

---

## 3. HTML5 Machine-Readable Archetype, Figure & Visible Waiver Contract

All metadata lives on semantic body elements inside `<article>` so it survives `CanonicalManualExtractor` (`container.decode_contents()`) and `kb/sanitize.py`, works with JavaScript disabled, and remains visible in `@media print`:

### 3.1 Document Root Declaration

```html
<article data-doc-archetype="system-design">
  <!-- manual header, .quick-start-strip, auto-hydrated .diagram-lens-jump-strip, sections -->
</article>
```

When compiled into the Enterprise Knowledge Base (`ai_agents/knowledge-base`), `CanonicalManualExtractor` extracts `archetype`, `diagram_lenses`, `diagram_types`, and `waived_lenses` before stripping `<article>`, and `compiler.py:render_page()` re-emits `data-doc-archetype="<archetype>"` on `<main id="content" class="kb-doc">`.

### 3.2 Figure Container Tagging

Every `.diagram-container` (or `figure.diagram-figure`) inside `<article>` MUST declare a unique `id`, `data-diagram-type`, and `data-diagram-lens`:

```html
<div class="diagram-container"
     id="fig-kb-user-interaction"
     data-diagram-type="service-blueprint"
     data-diagram-lens="user-interaction">
  <div class="diagram-header">
    <span class="diagram-title">FIG 2.1 — USER FRONTSTAGE VS. TRI-STORE BACKSTAGE</span>
    <span class="diagram-tag">VISUAL PATTERN: SERVICE BLUEPRINT</span>
    <button type="button" class="diagram-expand" data-diagram-open>Expand</button>
  </div>
  <div class="diagram-viewport">
    <svg role="img" aria-labelledby="kb-ui-title kb-ui-desc" viewBox="0 0 960 520">
      <!-- accessible inline SVG using var(--svg-*) tokens -->
    </svg>
  </div>
  <div class="diagram-caption">...</div>
</div>
```

### 3.3 Explicit Visible Lens Waiver Block (`.lens-waiver`)

When an eligible conditional lens is legitimately omitted, place a visible `.lens-waiver` block inside `<article>` (never inside `<head><meta>`):

```html
<div class="lens-waiver"
     data-waive-lens="governance-access"
     data-waive-reason="Local single-user desktop application with zero multi-tenant RBAC or network-exposed data access matrix; all state remains inside the local OS user profile.">
  <strong>Lens Waiver (`governance-access`):</strong> Local single-user desktop application with zero multi-tenant RBAC or network-exposed data access matrix; all state remains inside the local OS user profile.
</div>
```

**Hard Waiver Validation Rules (`scripts/diagram_registry.py` & `scripts/check_manual_selectors.py`)**:

1. `[data-waive-lens]` MUST appear inside `<article>` (or `<main class="kb-doc">`), never outside it.
2. Target lens MUST belong to the declared archetype and MUST have `waivable=True` (waiving a non-waivable lens fails closed).
3. `data-waive-reason` MUST contain **`>= 24` non-whitespace characters** (`len("".join(reason.split())) >= 24`) and MUST NOT match generic placeholders (`n/a`, `na`, `tbd`, `todo`, `none`, `skipped`, `not needed`, `not applicable`).
4. The element MUST contain visible inner text so static/no-JS and print readers see the rationale, and `.lens-waiver` stays visible in `@media print`.
5. Duplicate waivers for the same `data-waive-lens` OR waiving a lens that already has a figure in the same document fail closed.

---

## 4. Progressive `.diagram-lens-jump-strip` & Ratchet Verification Gate

### 4.1 Auto-Hydrated Jump Strip UX (`assets/manual-shared.{css,js}`)

- `initDiagramLensJumpStrip()` in `assets/manual-shared.js` inspects `<article>` / `<main class="kb-doc">` and auto-renders `<nav class="diagram-lens-jump-strip" data-lens-jump-strip aria-label="Diagram lens navigation">` immediately after `.quick-start-strip` using DOM-safe `createElement` calls (`innerHTML` is forbidden).
- Displays the document's archetype badge followed by ordered `[data-lens-jump="<lens>"]` anchor chips (with compact `.lens-type-badge` tags) and `[data-lens-waived="<lens>"]` chips (`title` bound to `data-waive-reason`), wired to `IntersectionObserver` scrollspy (`.is-active` + `aria-current="location"`).
- Injects `style[data-manual-lens-fallback]` automatically on standalone `docs/*.html` pages when `--manual-lens-strip` is unset, hides `.diagram-lens-jump-strip` in `@media print`, and exits as a clean no-op on untagged legacy manuals.

### 4.2 Ratchet Fail-Closed Verification Pipeline

| Validator / Command | Default Behavior | `--require-archetype` Strict Mode |
| :--- | :--- | :--- |
| `scripts/visual_audit.py` | **Fail-closed (`exit 1`)** on any contract violation inside manuals declaring `data-doc-archetype`; emits non-blocking `WARN [ARCHETYPE-LEGACY]` (`severity="warning"`, `exit 0`) on untouched legacy manuals omitting `data-doc-archetype`. | **Fail-closed (`exit 1`)** if `data-doc-archetype` is missing (`stage2/missing-archetype`) or invalid. Mandatory for all newly authored and retrofitted manuals. |
| `scripts/check_manual_selectors.py` | Accepts `.diagram-lens-jump-strip` / `[data-lens-jump]`; fails closed if `[data-waive-lens]` appears outside `<article>` or lacks a non-empty `data-waive-reason`. | Enforced unconditionally on all checked HTML files. |
| `docs/scripts/docs_engine.py verify` | Prints `OK [ARCHETYPE]`, `FAIL [ARCHETYPE]` (`exit 1`), and `WARN [ARCHETYPE-LEGACY]` with summary `Archetype Coverage: X/Y converted, Z legacy`. | Fails closed (`exit 1`) if any catalogued manual omits `data-doc-archetype`. |

---

## 5. Complete 51-Type Canonical Slug Catalog (`CATALOG_51_TYPES`)

Every `data-diagram-type` value MUST match one of these **51 canonical visual-type slugs** (`references/type-<slug>.md`):

| Domain Group | Canonical `data-diagram-type` Slugs (`references/type-<slug>.md`) |
| :--- | :--- |
| **System, Topology & Infrastructure (10)** | `architecture`, `architecture-delta`, `it-state`, `high-level`, `layers`, `nested`, `deployment`, `dependency`, `exploded`, `axonometric-plan` |
| **User, Process & Operational Flow (10)** | `service-blueprint`, `steps`, `event-modeling`, `journey`, `swimlane`, `flowchart`, `process`, `sequence`, `state`, `loop` |
| **Data, Schema & Security Governance (7)** | `dp-integration`, `data-flow`, `medallion`, `db-schema`, `er`, `uml-class`, `dp-security-matrix` |
| **Planning, Delivery & Version Control (8)** | `git-graph`, `gantt`, `schedule-network`, `timeline`, `kanban`, `story-map`, `requirement-traceability`, `org-chart` |
| **Quantitative, Analytical & Strategy (16)** | `waterfall`, `heatmap`, `unit-grid`, `bar`, `line`, `scatter`, `sankey`, `treemap`, `quadrant`, `radar`, `polar`, `wardley`, `fishbone`, `tree`, `pyramid`, `venn` |
