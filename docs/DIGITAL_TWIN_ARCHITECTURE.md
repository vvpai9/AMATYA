# AMATYA Digital Twin Architecture (Phase 14.6)

## 1. Overview
The Digital Twin subsystem (`core/digital_twin.py`) bridges real-time and historical physical sensor telemetry with computational models. It maintains an updated virtual replica of hardware subsystems, monitors discrepancies, detects parameter drift, and estimates degradation.

---

## 2. Component Hierarchy
A Digital Twin is organized as a hierarchical tree of `TwinComponent` objects:
- **Root & Subcomponents:** Subsystems (e.g. `root/battery`, `root/inverter`, `root/motor`).
- **Parameters:** Physical constants and system parameters (e.g. internal resistance $R_i$, heat capacity $C_{th}$, mass $m$).
- **State Variables:** Continuous variables with operating bounds $[min\_limit, max\_limit]$ and units.

---

## 3. Discrepancy & Drift Detection
The twin ingests two independent telemetry streams:
1. **Measured Stream ($y_{meas}(t)$):** Physical sensor readings.
2. **Simulated Stream ($y_{sim}(t)$):** Virtual model output.

For each measured point:
$$\text{Residual } r = y_{meas}(t) - y_{sim}(t), \quad \text{Relative Error } \epsilon_{rel} = \frac{|r|}{|y_{sim}|}$$
An anomaly is flagged whenever $\epsilon_{rel} > \text{tolerance}$ (e.g. 15%).

---

## 4. Parameter Calibration via Optimization
When physical components degrade or environmental conditions shift, the twin automatically recalibrates model parameters using SciPy's non-linear least-squares curve fitting (`scipy.optimize.curve_fit`):
$$\min_{\theta} \sum_{i=1}^N \left(y_{meas}(t_i) - f(t_i, \theta)\right)^2$$
Calibration history, Mean Squared Error (MSE) before/after, and parameter shifts are persisted.

---

## 5. Health Status & Degradation Index
The health index $H \in [0.0, 1.0]$ tracks component wear:
- **Nominal ($H \ge 0.85$):** All state variables within safe margins.
- **Degraded ($0.50 \le H < 0.85$):** State variables operating within 10% of operating boundaries or experiencing persistent drift.
- **Critical ($H < 0.50$):** State variables out of physical limits; immediate throttling or inspection recommended.
