# AMATYA Optimization & Constraint Solving (Phase 14.10)

## 1. Overview
The Optimization Engine (`core/optimization_engine.py`) provides deterministic continuous and combinatorial mathematical optimization using SciPy.

---

## 2. Linear Programming (LP)
Solves standard primal LP problems via the HiGHS dual-simplex and interior-point solver:
$$\min_{\mathbf{x}} \mathbf{c}^T \mathbf{x} \quad \text{subject to} \quad \mathbf{A}_{ub} \mathbf{x} \le \mathbf{b}_{ub}, \quad \mathbf{A}_{eq} \mathbf{x} = \mathbf{b}_{eq}, \quad \mathbf{l} \le \mathbf{x} \le \mathbf{u}$$
- **Slack Evaluation:** Reports slack margins $\mathbf{s} = \mathbf{b}_{ub} - \mathbf{A}_{ub} \mathbf{x}$. Identifies binding/active constraints when $s_k \approx 0$.
- **Maximization:** Automatically handled via negation of the objective vector.

---

## 3. Nonlinear Constrained Optimization (NLP)
Solves general nonlinear optimization problems via Sequential Least Squares Programming (SLSQP):
$$\min_{\mathbf{x}} f(\mathbf{x}) \quad \text{subject to} \quad g_j(\mathbf{x}) \ge 0, \quad h_k(\mathbf{x}) = 0, \quad \mathbf{l} \le \mathbf{x} \le \mathbf{u}$$

---

## 4. Combinatorial & Knapsack Optimization
Solves the 0-1 Knapsack problem:
$$\max_{\mathbf{x} \in \{0, 1\}^N} \sum_{i=1}^N v_i x_i \quad \text{subject to} \quad \sum_{i=1}^N w_i x_i \le W$$
- Exact Dynamic Programming ($O(N \cdot W)$) for integer capacities and weights.
- SciPy mixed-integer linear programming (`scipy.optimize.milp`) for continuous or fractional weights.
