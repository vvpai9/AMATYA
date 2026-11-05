# AMATYA Phase 12 Architecture Specification
## Persistent Intelligence, Autonomous Operations & Adaptive Personal Assistance

**Version:** 12.0.0  
**Target Environment:** Linux (KDE Neon / KDE Plasma 6 Wayland, PipeWire 1.6, Python 3.12)  
**Host Profile:** Intel Core i5-11300H (12 logical threads), 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile (4 GB VRAM)  
**Upstream Lineage:** Built upon [FatihMakes/Mark-LVI](https://github.com/FatihMakes/Mark-LVI) with Wayland automation powered by [kwin-mcp](https://github.com/Aetf/kwin-mcp).

---

## 1. Architectural Philosophy

AMATYA Phase 12 elevates the assistant from a reactive command-dispatch interface into a **persistent, adaptive, context-aware personal operating companion**. Rather than exposing an unconstrained LLM directly to shell commands, Phase 12 establishes a strictly-governed multi-layered cognitive architecture:

```
                                  ┌───────────────────────────┐
                                  │   Continuous Context      │
                                  │ (ContextManager / Turns)  │
                                  └─────────────┬─────────────┘
                                                │
 ┌──────────────────────────┐     ┌─────────────▼─────────────┐     ┌──────────────────────────┐
 │ Layered Memory Engine    │◄───►│    Central Orchestrator   │◄───►│ Proactive Intelligence   │
 │ Working/Episodic/Semantic│     │  Dependency Graph Planner │     │ (5 Tiers / Quiet Hours)  │
 └──────────────────────────┘     └─────────────┬─────────────┘     └──────────────────────────┘
                                                │
                                  ┌─────────────▼─────────────┐
                                  │   Adaptive Workflow Engine│
                                  │  (Routines / Learning)    │
                                  └─────────────┬─────────────┘
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         │                                      │                                      │
┌────────▼────────┐                    ┌────────▼────────┐                    ┌────────▼────────┐
│  Model Router   │                    │ Wayland Desktop │                    │ Connected Device│
│ (Privacy Modes: │                    │  (KWin / AT-SPI │                    │ Manager (UUIDs, │
│ Strict/Hybrid)  │                    │   / EIS Portal) │                    │ Dynamic IP, TV) │
└─────────────────┘                    └─────────────────┘                    └─────────────────┘
```

---

## 2. Core Subsystems Implemented

### 2.1 Layered Persistent Memory (`core/memory_engine.py`)
- **Working Memory (`working_memory.json`):** Active task goal, current step index, active window ID, active file, recent entities.
- **Episodic Memory (`episodic_memory.json`):** Time-ordered event records with success status, parameters, and failure diagnostics.
- **Semantic Memory (`semantic_memory.json`):** Verified user facts, preferences, relationships, and system configuration with confidence (0.0 to 1.0) and provenance tags (`user_stated`, `observed`, `inferred`).
- **Contradiction Detection:** Evaluates incoming facts against existing high-confidence verified facts. Prevents silent overwriting unless explicitly confirmed or corrected.
- **Complete Deletion Purge:** Atomic purge removing items from semantic memory, indices, and legacy `long_term.json`.
- **Privacy Disablement:** Single toggle `set_memory_enabled(False)` halting all retention and extraction.

### 2.2 Continuous Contextual Intelligence (`core/context_manager.py`)
- **Turn & Entity Tracking:** Maintains sliding window of conversational turns, recently focused windows, and recent files.
- **Pronoun & Elliptical Resolution:**
  - *"Send that document to my phone"* -> Resolves to last task artifact or active document.
  - *"Continue what you were doing"* -> Resumes last paused task from orchestrator state.
  - *"Do the same thing for the other project"* -> Resolves secondary project or detects ambiguity.
- **Ambiguity Detection:** Detects missing references and prompts user with targeted clarification questions.

### 2.3 Adaptive Workflow Engine (`core/workflow_engine.py`)
- **Structured Routines:** Multi-step routines with triggers (`manual`, `schedule`, `event`, `sensor`).
- **Approval Gating:** Strict enforcement requiring explicit user authorization before dangerous or automated routines execute.
- **Repetition Learning:** Observes consecutive tool invocations; after 3 observed repetitions of a 2-step sequence, proposes a candidate automated workflow.

### 2.4 Proactive Intelligence Engine (`core/proactive_engine.py`)
- **5 Notification Priority Tiers:**
  1. `INFORMATIONAL`: Background metrics, RAM utilization.
  2. `USEFUL_SUGGESTION`: Paused tasks ready for resumption.
  3. `WARNING`: Low battery on connected devices, task failures.
  4. `URGENT`: Workflow authorization requests, security posture changes.
  5. `CRITICAL`: System-critical hazards, emergency stop alerts.
- **Quiet Hours Policy:** Automatically suppresses tiers 1 through 3 between 23:00 and 07:00.
- **Dignified JARVIS Phrasing:** Explicitly categorizes alerts into Observations, Recommendations, Actions Awaiting Approval, and Completed Routines.

### 2.5 Privacy-Aware Model Routing (`core/model_router.py`)
- **Three Modes:**
  - `strict_local`: Zero external cloud network traffic. If local provider is offline or VRAM exceeds safety ceiling, generation is blocked with an explicit diagnostic message rather than falling back to Gemini.
  - `hybrid` (default): Fast local models for small/sensitive tasks with transparent fallback to Gemini.
  - `cloud_enabled`: Unrestricted routing using Gemini smart/fast tiers.

### 2.6 Memory-Aware CREATOR Mode (`core/creator.py`)
- **Project Profile Management (`memory/project_profiles.json`):** Persistent project metadata containing stack detection, test commands, build scripts, purpose, and known issues.
- **Auto-Profiling:** Automatically detects languages (Python, Node.js, Rust), extracts test runners (`pytest`, `unittest`, `npm test`, `cargo test`), and inspects README files.

### 2.7 Hardware & Device Dynamic Discovery (`core/device_manager.py`)
- **Deterministic Persistent UUIDs:** RFC 4122 v5 UUIDs generated for every connected device.
- **Dynamic IP Resolution:** Socket reachability and ARP neighbor table inspection to accommodate dynamic DHCP lease changes.
- **Real Xiaomi TV (`10.0.0.3`):** Controlled via native `atvremote` binary without simulation fallback when reachable.

### 2.8 Holographic Telemetry HUD & Subsystem Diagnostics (`core/diagnostics.py`)
- **6 Subsystem Health Classifications:**
  - Audio: Healthy (PipeWire 1.6 active)
  - Models: Healthy / Degraded based on provider probe and privacy mode
  - Memory: Healthy (Layered memory active)
  - Desktop: Healthy (Wayland display active)
  - Devices: Healthy (atvremote verified)
  - Security: Autonomy level, voice verification state, PIN configuration.
- **Formatted JARVIS Holographic HUD:** Terminal and dashboard visualization for Command Centre.

