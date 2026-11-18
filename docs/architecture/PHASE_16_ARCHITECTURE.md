# AMATYA (अमात्य) — Phase 16 Architecture
## JARVIS Cognitive Core & Autonomous Orchestration

**Codename:** JARVIS  
**Primary Objective:** Transform AMATYA from a collection of isolated capabilities into a unified, context-aware, autonomous personal AI operating system following the continuous 8-stage operational cycle:  
`PERCEIVE → UNDERSTAND → REASON → PLAN → AUTHORIZE → EXECUTE → VERIFY → LEARN`

---

## 1. Architectural Overview

```
                      ┌──────────────────────────────────────────────┐
                      │             Perception Hub (A.1)             │
                      │  Voice • Text • Screen • Telemetry • Devices │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          Intent Understanding (A.2)          │
                      │ Goal • Instructions • Constraints • Ambiguity │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │             Unified Context Broker           │
                      │ Working • Episodic • Semantic • KG • Telemetry│
                      │     [Prompt Injection Boundary Isolation]    │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          Reasoning & Planner (A.3)           │
                      │ Multi-Step Decomposition • Capability Binding│
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │             Task Graph (DAG) (B.1)           │
                      │ Topological Scheduling • Parameter Bridging  │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │     Central Security Gateway (Fail-Closed)   │
                      │ Autonomy Gates • Interactive Confirmation    │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │       Task Orchestrator & Workers (B.2)      │
                      │  State Checkpointing • Crash/Restart Recovery│
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │         Verification & Recovery (B.3)        │
                      │  TaskVerifier • FailureRecoveryEngine        │
                      │  (Transient Retry vs. Destructive Safe Guard)│
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │               Learning Engine                │
                      │ Episodic Recording • Working Context Update  │
                      └──────────────────────────────────────────────┘
```

---

## 2. Core Subsystems

### 2.1 Unified Capability Registry (`core/capability_registry.py`)
Unifies discovery and execution across all 74 AMATYA capabilities (43 actions, 8 plugins, 23 skills):
- **Contract:** Standardized metadata with parameters schema, output schema, permission tier, risk level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), reversibility flag, and execution callable.
- **Fail-Closed Security:** Every capability execution routes through `core.security.authorize_tool_execution`.
- **Plugin Trust Gates:** AST pre-import security checks and approval gating are preserved.

### 2.2 Dependency-Aware Task Graph Engine (`core/task_graph.py`)
Deterministic Directed Acyclic Graph (DAG) representing multi-step execution workflows:
- **States:** `PENDING`, `PLANNED`, `WAITING_FOR_APPROVAL`, `READY`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED`, `VERIFYING`.
- **Validation:** Strict state machine transitions preventing invalid or illegal state jumps.
- **Algorithms:** In-degree topological sorting and cycle detection via DFS recursion stack.
- **Bridging:** Dynamic parameter resolution from upstream task results (`$parent_task.field` or `{parent_task.field}`).

### 2.3 Persistent Task Orchestrator (`core/task_orchestrator.py`)
Stateful execution manager supporting sequential, parallel, and resumable execution:
- **Persistence:** Atomic checkpointing to `memory/orchestrator_tasks.json` on every state transition.
- **Crash Recovery:** `recover_interrupted_tasks()` executed on startup; in-flight tasks (`RUNNING`/`VERIFYING`) are safely transitioned to `PAUSED` without duplicate execution.
- **Runtime Controls:** Thread-safe `pause_graph()`, `resume_graph()`, `cancel_graph()`, `approve_task()`, `deny_task()`, and `emergency_stop()`.

### 2.4 Multimodal Perception Hub (`core/perception.py`)
Central event bus capturing sensory signals from:
- `TEXT_CHAT`, `VOICE`, `DESKTOP_SCREEN`, `SYSTEM_EVENT`, `DEVICE_TRIGGER`, `FILESYSTEM`, `NOTIFICATION`, `BACKGROUND_TASK`, `SCHEDULED_EVENT`.
- Structure: `PerceptionEvent` with event ID, source, payload, timestamp, trust level, and priority.

### 2.5 Intent Understanding Engine (`core/intent_engine.py`)
Decodes natural language instructions:
- Classifies: `CONVERSATIONAL`, `INFORMATIONAL`, `OPERATIONAL_DIRECT`, `COMPLEX_GOAL`, and `UNCERTAIN`.
- Ambiguity & High-Impact Detection: Underspecified broad commands ("clean everything", "delete all") trigger explicit clarification questions rather than guessing or performing destructive actions.

### 2.6 Context Broker & Environmental Awareness (`core/context_broker.py`, `core/environmental_awareness.py`)
- **Telemetry:** Real-time CPU, RAM, disk, thermal, battery, and active window state debounced to prevent CPU-spinning loops.
- **Security Isolation:** Untrusted inputs (files, web snippets) are enclosed in `<UNTRUSTED_CONTENT source="..." label="...">` tags with internal closing-tag sanitization to block prompt injection attacks.

### 2.7 Verification & Adaptive Recovery (`core/task_verifier.py`, `core/failure_recovery.py`)
- **TaskVerifier:** Validates post-conditions (`file_exists`, `contains`, `regex`, output schema) before marking nodes `COMPLETED`.
- **FailureRecoveryEngine:** Classifies faults as `TRANSIENT`, `PERMANENT`, `AUTHORIZATION_DENIED`, or `UNSUPPORTED`.
- **Destructive Operation Safety Guard:** Reversible operations with transient faults retry with exponential backoff; destructive/irreversible operations (`delete`, `rm`, `kill`) are strictly forbidden from automatic retrying.

### 2.8 Cognitive Core Integration (`core/cognitive_core.py`)
Integrates the complete cycle into `process(text, source, user, player, speak)`:
- Powers `actions/orchestrator.py` via `action="cognitive_process"`.
- Exposes RESTful endpoints in `dashboard/server.py` (`/api/orchestrator/tasks`, `/api/orchestrator/capabilities`, `/api/orchestrator/approve`, `/api/orchestrator/deny`, `/api/orchestrator/pause`, `/api/orchestrator/resume`, `/api/orchestrator/environment`).

