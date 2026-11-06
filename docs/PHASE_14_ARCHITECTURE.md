# AMATYA Phase 14 Architecture Specification
## Advanced Reasoning, Simulation, Decision Intelligence & Predictive Planning

**Version:** 14.0.0  
**Target Environment:** Linux (KDE Plasma 6 Wayland, PipeWire 1.6, Python 3.12)  
**Host Profile:** Intel Core i5-11300H (8 threads / 4 cores), 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile (4 GB VRAM)  
**Preceding Milestones:** Phase 11 (Security & System Reliability), Phase 12 (Persistent Cognitive Architecture), Phase 13 (Multimodal Knowledge Graph & Universal Ingestion).

---

## 1. Phase 13 Verification Report

A comprehensive audit of the repository establishes that Phase 13 is operational, verified, and committed at `2eabd46`:

- **Universal Ingestion Framework (`core/ingestion.py`):**
  - Universal source abstraction (`FILE`, `DIRECTORY`, `URL`, `TEXT`, `STREAM`, `REPO`).
  - Binary magic byte sniffer + extension detection (`DOCUMENT`, `IMAGE`, `AUDIO`, `VIDEO`, `CODE`, `DATA`, `WEB`).
  - $O(1)$ fast-path incremental sync skipping unchanged sources via `(mtime, size_bytes)` cache.
  - Secret redaction (`redact_secrets`) and SSRF protection.
- **Document Intelligence Engine (`core/document_intelligence.py`):**
  - Structural heading hierarchy ($H_1 \to H_4$) with dynamic breadcrumb tracking.
  - Page-aware paragraph and section tracking.
  - Strict table extraction preserving missing values as `None` or `""` (never coercing to 0).
  - Cross-document comparison detecting parameter discrepancies and agreements.
  - CSV and multi-sheet XLSX table exports.
- **Visual Intelligence Engine (`core/visual_intelligence.py`):**
  - Schematic and block diagram classification with edge density quantification.
  - Uncertainty quantification flagging ambiguous connections without hallucinating components.
  - Pre- and post-action visual change verification with bounding box isolation.
- **Audio & Video Intelligence (`core/media_intelligence.py`):**
  - Timestamped utterance chunking, speaker turn detection, action item extraction.
  - Video scene segmentation and midpoint keyframe extraction.
- **Personal Knowledge Graph (`core/knowledge_graph.py`):**
  - Strongly-typed entity nodes (`PROJECT`, `PERSON`, `DEVICE`, `CONCEPT`, etc.).
  - Directional relationships (`IMPLEMENTS`, `CONNECTED_TO`, `CONTRADICTS`, `SUPERSEDES`).
  - 2-hop BFS multi-hop traversal and cascading deletion.
- **Universal Semantic Search (`core/universal_search.py`):**
  - Tri-modal fusion combining BM25 lexical search, 128-D vector embeddings, and relational graph paths.
- **Source-Grounded Research Engine (`core/research_engine.py`):**
  - 5-step evidence investigation workflow separating primary evidence from model inference with verifiable citations.
- **Project Knowledge Spaces & Live Monitoring (`core/creator_knowledge.py`, `core/live_monitor.py`):**
  - Scoped project knowledge spaces (`mark_lvi`, `research`) and file/device state change tracking.
- **Test Baseline:** Full regression suite of **79 / 79 tests PASS** in under 30 seconds.

---

## 2. Current Reasoning Architecture & Limitations

Prior to Phase 14, AMATYA's reasoning was predominantly LLM-driven:
- Model router (`core/model_router.py`) routed prompts between FAST, SMART, and REASONING tiers.
- Task planning (`core/orchestrator.py`) relied on free-form LLM JSON synthesis of step plans.
- While effective for semantic coordination, this architecture had fundamental limitations:
  1. **Calculation Vulnerability:** LLMs cannot perform reliable complex arithmetic, symbolic calculus, or matrix algebra; they approximate or hallucinate numerical results.
  2. **Lack of Problem Decomposition:** Complex engineering problems were not formalized into structured intermediate objects (given, unknown, constraints, assumptions).
  3. **Absence of Deterministic Simulation:** Problems requiring dynamic modeling (transient circuits, orbital mechanics, queueing theory) had to rely on static textual descriptions rather than executable solvers.
  4. **Uncertainty Conflation:** Correlation was often reported as causation, and probabilistic estimates were not mathematically calibrated.

---

## 3. Existing Computation Capability Assessment

AMATYA's execution environment contains an exceptional scientific Python stack:
- **`numpy` (2.5.4):** High-performance multi-dimensional arrays, vector algebra, matrix operations, FFT, and random number generation (`Generator` with reproducible seeds).
- **`scipy` (1.18.1):**
  - `scipy.integrate.solve_ivp`: Explicit and implicit ODE solvers (RK45, RK23, Radau, BDF, LSODA) for physical dynamics.
  - `scipy.optimize`: Unconstrained and constrained optimization (`minimize`, `linprog`, `curve_fit`, `root_scalar`).
  - `scipy.signal`: LTI system modeling, transfer functions, Bode plots, state-space representations.
  - `scipy.stats`: Probability distributions, hypothesis testing, confidence intervals.
- **`sympy` (1.14.0):** Complete symbolic mathematics engine:
  - Analytical differentiation, definite and indefinite integration, series expansion, limits.
  - Symbolic equation solving (`solve`, `linsolve`, `nonlinsolve`).
  - Symbolic matrix operations, eigenvalues, eigenvectors.
  - Unit-aware expressions with dimensional analysis.
- **`scikit-learn` (1.9.1):** Regression, time-series forecasting, clustering, classification, and cross-validation metrics (MAE, RMSE, MAPE).

---

## 4. Simulation Tool Availability Report

A system probe reveals:
- **Local Native Solvers Available:** Python SciPy ODE solvers, NumPy linear algebra, SymPy symbolic differential equation solvers, Scikit-learn regressors.
- **External Dedicated Simulators:** `ngspice`, `xyce`, `iverilog`, `verilator` are not present on the host system.
- **Strategic Approach:** Build a **Unified Simulation Adapter Architecture** (`core/simulation/`):
  - Primary adapters execute deterministic, high-accuracy native Python models (SciPy IVP for circuits, mechanics, and orbital dynamics).
  - External adapters check CLI tool availability; if an external tool (e.g. `ngspice`) is installed in the future, the adapter routes to it; otherwise it uses the calibrated native solver, reporting the exact solver version and environment.
  - Model outputs are strictly labeled as `simulated`, never masquerading as physical hardware measurements.

---

## 5. Proposed Simulation Adapter Architecture

```
                                  ┌─────────────────────────────┐
                                  │   SimulationManager         │
                                  └──────────────┬──────────────┘
                                                 │
         ┌───────────────────────────────────────┼───────────────────────────────────────┐
         │                                       │                                       │
┌────────▼──────────────┐             ┌──────────▼────────────┐             ┌────────────▼────────────┐
│ CircuitSimulator      │             │ OrbitalSimulator      │             │ MonteCarloSimulator     │
│ (RLC / State-Space /  │             │ (Keplerian / RK45     │             │ (Distribution Sampling, │
│ Thermal RC Networks)  │             │ Orbital Propagation)  │             │ P10, P50, P90, P99)     │
└───────────────────────┘             └───────────────────────┘             └─────────────────────────┘
```

Every simulation run records:
- `simulation_id`: UUID4.
- `model_name` & `model_version`: str.
- `input_parameters`: dictionary with explicit units.
- `initial_conditions`: vector / dict.
- `solver_type`: e.g. `scipy.integrate.solve_ivp(method='RK45')`.
- `execution_time_ms`: float.
- `convergence_status`: `converged` | `diverged` | `timed_out`.
- `validation_metrics`: energy conservation check, dimensional consistency check.
- `time_series`: time vector $t$ and state trajectories $y(t)$.

---

## 6. Proposed Structured Reasoning Architecture

```
                    ┌────────────────────────────┐
                    │      Problem Prompt        │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 1. Problem Classification  │
                    │    (Math, Causal, Dec, ...)│
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 2. Structured Formulation  │
                    │    - Given variables       │
                    │    - Unknown variables     │
                    │    - Assumptions           │
                    │    - Constraints           │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 3. Method Selection        │
                    │    - Symbolic (SymPy)      │
                    │    - Numerical (SciPy)     │
                    │    - Simulation (Adapter)  │
                    │    - Graph / RAG Evidence  │
                    └─────────────┬──────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         │                                                 │
┌────────▼─────────────────┐                    ┌──────────▼────────────────┐
│ 4. Deterministic Solver  │                    │ 5. Independent Verifier   │
│    Execution             │                    │    (Dual Method / Bounds) │
└────────┬─────────────────┘                    └──────────┬────────────────┘
         │                                                 │
         └────────────────────────┬────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │ 6. Evidence-Grounded Trace │
                    │    & Decision Report       │
                    └────────────────────────────┘
```

---

## 7. Execution Isolation & Security Assessment

1. **Process Sandboxing:**
   - Computational code evaluation runs in an isolated subprocess (`subprocess.Popen`) with dedicated timeout guards (default 10s, hard kill at 30s).
   - Resource limits enforced via `resource.setrlimit` (RLIMIT_CPU, RLIMIT_AS).
2. **Untrusted Code Boundaries:**
   - Generated code or external simulation netlists are inspected for unsafe calls (`os.system`, `subprocess`, socket creation) before execution.
   - Strict separation between reasoning (planning what to compute) and execution (running deterministic solvers).
3. **Audit Logging:**
   - All computational runs log timestamp, parameters, solver status, and resource usage to `memory/simulation_audit.log`.

---

## 8. Hardware Resource Assessment

- **CPU:** 4 physical cores / 8 threads (i5-11300H). Multi-trial Monte Carlo simulations parallelized using worker pools with max concurrency = 4 to keep the voice assistant responsive.
- **RAM:** 16 GB DDR4. Per-simulation memory limit capped at 1.0 GB to prevent system swapping.
- **GPU:** 4 GB VRAM (GTX 1650). Reserved for visual perception and background acceleration; deterministic mathematics runs on CPU.

---

## 9. Phase 14 Implementation Roadmap

- **Phase 14.1 — Architecture Audit & Baseline (Complete):** Established hardware profile, scientific library availability, verification report, and architecture plan.
- **Phase 14.2 — Structured Reasoning Engine (`core/reasoning_engine.py`):** Problem classification, structured intermediate representation, method routing, and independent verification.
- **Phase 14.3 — Scientific Computation & Dimensional Analysis (`core/scientific_computation.py`):** SymPy symbolic algebra/calculus, SciPy numerical solvers, unit-aware computation layer.
- **Phase 14.4 — Causal Reasoning & Counterfactual Engine (`core/causal_engine.py`):** Directed causal graphs, confounding variables, counterfactual queries, and intervention modeling.
- **Phase 14.5 — Universal Simulation Framework (`core/simulation_engine.py`):** Modular simulation adapters (Circuits, Orbital mechanics, Thermal, Queueing) with conservation validation.
- **Phase 14.6 — Digital Twin Architecture (`core/digital_twin.py`):** Component-state models, real-vs-simulated calibration, error metrics, and model versioning.
- **Phase 14.7 — Predictive Intelligence (`core/predictive_intelligence.py`):** Time-series forecasting, confidence intervals, evaluation metrics (MAE, RMSE, MAPE).
- **Phase 14.8 — Scenario Analysis & Monte Carlo Engine (`core/scenario_engine.py`):** Alternative scenario comparison, reproducible Monte Carlo sampling, and sensitivity analysis.
- **Phase 14.9 — Intelligent Decision Support (`core/decision_intelligence.py`):** Multi-Criteria Decision Analysis (MCDA), Pareto analysis, weighted utility, risk assessment.
- **Phase 14.10 — Constraint Solving & Optimization (`core/optimization_engine.py`):** Linear programming, non-linear optimization, constraint satisfaction, and feasibility checking.
- **Phase 14.11 — Strategic Planning & CREATOR Integration (`core/strategic_planner.py`):** Decision-aware task scheduling, critical path analysis, and research/engineering report synthesis.
- **Phase 14.12 — Command Centre & Production Hardening (`actions/reasoning_tools.py`):** Tool integration into actions, regression testing, and acceptance verification.

---

## 10. Acceptance Test Strategy

Every capability will be rigorously verified in `tests/test_phase14_acceptance.py`:
- All tests classified as `PASS`, `FAIL`, `PARTIAL`, `SIMULATED`, `BLOCKED`, or `NOT TESTED`.
- Ground truth comparisons:
  - Mathematical tests compared against exact analytical solutions.
  - ODE simulations compared against known analytical differential equation solutions (e.g. damped harmonic oscillator).
  - Dimensional analysis tested for unit compatibility and rejection of invalid physical combinations (e.g. adding Volts to Amperes).
  - Decision intelligence validated against known Multi-Criteria Decision matrices.
  - Security sandbox tested for timeout enforcement and resource boundaries.
