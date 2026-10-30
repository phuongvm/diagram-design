# Multi-Agent System (MAS) & Distributed Mesh Diagrams

**Best for:** visual documentation of multi-agent runtimes, inter-instance A2A networks, relay-mediated swarms, and cross-environment agent choreography.

---

## 1. Core Visual Principle: The Anti-Monolith Rule

Never collapse a distributed multi-agent system into a single "Agents" box backed by dense prose. Readers must visually distinguish:
1. **Intra-Node Co-location (Same Environment):** Multiple distinct agent runtimes (e.g. Hermes, OpenCode, DeepSeek Harness, Codex, Claude Code, Goose) coexisting on a single host, sharing local tools and bus sidecars.
2. **Inter-Node Distribution (Other Environments):** Physical or virtual node boundaries (e.g. Workstation, LAN Micro-Server, Edge Laptop, Pi cluster) connected across network interfaces.
3. **The Dual-Plane Separation:**
   - **Control Plane:** Asynchronous broadcast, gossip, chat rooms (e.g. Nostr relays, Buzz group rooms like `Dream_Team`), and coordination protocols (`(pass)` on idle).
   - **Execution Plane:** Synchronous or task-bound RPC (e.g. A2A Hub Gateway on Port 9900, Git Worktree isolation, Kanban DAG promotion).

---

## 2. Visual Type Selection for Multi-Agent Architectures

| What you are showing | Preferred Visual Type | Reference |
|---|---|---|
| **Inter-Instance Hub & Relay Topology** (Which hosts speak what wire, Control vs Execution planes) | **DP Integration / Integration Topology** | [type-dp-integration.md](type-dp-integration.md) |
| **Multi-Agent Collaborative RACI Flow** (Who does what across lanes: Ingress &rarr; Orchestrator &rarr; Co-located Specialists &rarr; Remote Nodes) | **Swimlane Diagram** | [type-swimlane.md](type-swimlane.md) |
| **Deterministic Worker Handoffs** (Strict step-by-step code delegation, pre-merge reviews, QA verification gates) | **Sequence Diagram** | [type-sequence.md](type-sequence.md) |
| **Cognitive Reflex Decision Loop** (System One fast paths, token trajectory limits, contract specification phases) | **Flowchart &amp; State Machine** | [type-flowchart.md](type-flowchart.md) / [type-state.md](type-state.md) |
| **Continuous Memory Compounding** (Feedback loops accumulating durable state in a central hub across sessions) | **Loop / Flywheel** | [type-loop.md](type-loop.md) |
| **Physical Hardware & Sensor Allocation** (GPU accelerators, ports, PIDs, local daemon bindings) | **Deployment Topology** | [type-deployment.md](type-deployment.md) |

---

## 3. Mandatory Layout Rules for Multi-Agent Diagrams

1. **Explicit Node & Environment Labels:** Every physical host or distinct VM container must be enclosed in an explicit boundary rect (`rx=8`, 2% ink wash) with an uppercase eyebrow badge indicating hostname, operating system, and IP/port.
2. **Channel Wire Legend:** Always provide visual distinction between wire types:
   - Control plane / Gossip relays: Link-blue `#2e5aa8` (e.g. `wss://` Nostr events).
   - Direct execution RPC: Focal coral `#eb6c36` or solid ink `#2d3142` (e.g. `HTTP JSON-RPC :9900`).
   - Async telemetry / Tracing: Dashed muted `#4f5d75` `stroke-dasharray="4,4"`.
3. **Actor Specialization Tags:** Avoid generic "Agent" labels. Always label with specific runtime/role: `Orchestrator`, `Coder (Worktree)`, `Reviewer (AST Audit)`, `QA (E2E Verification)`, `Sidecar ACP`.
4. **Room Coordination Callouts:** When illustrating collaborative chat rooms, explicitly document the idle protocol (`(pass)` to eliminate chatter) and channel root publication directives (`[[BUZZ_FINAL]]` envelopes).
