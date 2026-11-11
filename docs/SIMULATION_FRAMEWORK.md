# AMATYA Universal Simulation Framework (Phase 14.5)

## 1. Overview
The Universal Simulation Engine (`core/simulation_engine.py`) provides physical state-space modeling, numerical ODE integration, and stochastic Monte Carlo analysis.

### Physical Isolation Rule
All outputs from this engine are explicitly labeled `simulated`. Simulated values are never reported as measured physical values.

---

## 2. Domain Simulation Adapters

### A. Circuit Transient Simulation (`CircuitSimulationAdapter`)
- **System:** Second-order Series RLC Circuit.
- **Differential Equations:**
  $$\frac{dI}{dt} = \frac{V_{in} - V_C - R \cdot I}{L}, \quad \frac{dV_C}{dt} = \frac{I}{C}$$
- **Metrics Calculated:** Natural frequency $\omega_0 = \frac{1}{\sqrt{LC}}$, damping ratio $\zeta = \frac{R}{2}\sqrt{\frac{C}{L}}$, peak voltage, percentage overshoot.
- **Physical Validation:** Checks passive energy conservation (capacitor voltage cannot exceed $2 \times V_{in}$).

### B. Thermal Dynamics Simulation (`ThermalSimulationAdapter`)
- **System:** Lumped RC semiconductor junction thermal model.
- **Differential Equation:**
  $$\frac{dT_j}{dt} = \frac{P_{diss} - \frac{T_j - T_{amb}}{R_{th}}}{C_{th}}$$
- **Metrics Calculated:** Steady-state temperature $T_{ss} = T_{amb} + P_{diss} R_{th}$, thermal time constant $\tau = R_{th} C_{th}$, peak temperature reached.
- **Physical Validation:** First-order linear time-invariant asymptotic convergence.

### C. Orbital Mechanics (`OrbitalSimulationAdapter`)
- **System:** Two-body celestial Keplerian orbital propagation around Earth.
- **Differential Equations:**
  $$\frac{d^2 \mathbf{r}}{dt^2} = -\frac{\mu \mathbf{r}}{\|\mathbf{r}\|^3}$$
- **Metrics Calculated:** Circular orbital velocity $v_{circ} = \sqrt{\frac{\mu}{r}}$, orbital period $T = 2\pi\sqrt{\frac{r^3}{\mu}}$, total specific mechanical energy drift.
- **Physical Validation:** Specific mechanical energy conservation drift $\Delta E / E < 0.1\%$.

### D. Monte Carlo Uncertainty Propagation (`MonteCarloSimulationAdapter`)
- **Stochastic Sampling:** Reproducible pseudo-random number generator (`numpy.random.default_rng`) with deterministic seed control.
- **Statistical Analytics:** Sample mean, sample standard deviation, and percentiles ($P_{10}, P_{50}, P_{90}, P_{99}$).

