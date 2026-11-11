# AMATYA Simulation & Execution Sandbox (Phase 14)

## 1. Overview
The execution sandbox governs all analytical computations, simulation integrations, and dynamic code evaluation to maintain strict process isolation and prevent resource exhaustion.

---

## 2. Resource Envelopes & Limits
- **CPU Timeouts:**
  - Fast algebraic/symbolic operations: $\le 2.0\text{ s}$.
  - Continuous numerical ODE solvers: $\le 10.0\text{ s}$.
  - Multi-variable optimizations and Monte Carlo sampling: $\le 30.0\text{ s}$.
- **Memory Boundaries:**
  - Maximum heap memory allocated per simulation run: $512\text{ MB}$.
  - Grid point limits: Maximum 50,000 steps per trajectory to prevent memory spikes.
- **Subprocess Isolation:**
  - Computational scripts run directly in the isolated `./AMATYA` Python 3.12 virtual environment.
  - Subprocess execution enforces strict environment variable scrubbing and non-interactive limits.

---

## 3. Physical Law & Sanity Enforcement
Every simulation adapter checks physical conservation laws:
1. **Passive Circuits:** Capacitor voltage cannot exceed $2.1 \times V_{in}$ under step excitation.
2. **Thermal Systems:** Junction temperature cannot fall below ambient under positive power dissipation.
3. **Orbital Mechanics:** Mechanical orbital energy drift must remain $< 0.1\%$ over propagation windows.
4. **Units:** Rejection of dimensionally inconsistent equations before computation begins.

