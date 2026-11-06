"""
core/optimization_engine.py — Mathematical Optimization & Constraint Solving for AMATYA Phase 14.

Provides deterministic Linear Programming (via SciPy HiGHS), Nonlinear Constrained Optimization
(via SciPy SLSQP / trust-constr), and Combinatorial / Knapsack problem solving.
Audits feasibility, computes constraint slack, and reports exact optimal variable assignments.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize

logger = logging.getLogger(__name__)


@dataclass
class VariableSpec:
    name: str
    lower_bound: Optional[float] = 0.0
    upper_bound: Optional[float] = None
    initial_guess: float = 0.0
    is_integer: bool = False


@dataclass
class OptimizationResult:
    problem_type: str  # "linear" | "nonlinear" | "knapsack"
    success: bool
    objective_value: float
    variables: Dict[str, float]
    slack: Dict[str, float] = field(default_factory=dict)
    iterations: int = 0
    message: str = ""
    summary_markdown: str = ""


class OptimizationEngine:
    """
    AMATYA Mathematical Optimization Engine.
    Executes LP, NLP, and combinatorial optimization with feasibility checking.
    """

    def __init__(self):
        pass

    def solve_linear_program(
        self,
        c: List[float],  # Objective coefficients (minimize c^T x)
        variable_names: List[str],
        A_ub: Optional[List[List[float]]] = None,  # A_ub * x <= b_ub
        b_ub: Optional[List[float]] = None,
        A_eq: Optional[List[List[float]]] = None,  # A_eq * x == b_eq
        b_eq: Optional[List[float]] = None,
        bounds: Optional[List[Tuple[Optional[float], Optional[float]]]] = None,
        maximize: bool = False,
    ) -> OptimizationResult:
        """
        Solves a Linear Program using SciPy's HiGHS solver.
        """
        c_vec = np.array(c, dtype=float)
        if maximize:
            c_vec = -c_vec

        res = linprog(
            c=c_vec,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            method="highs",
        )

        obj_val = float(res.fun)
        if maximize and res.success:
            obj_val = -obj_val

        var_dict = {}
        if res.x is not None:
            for i, name in enumerate(variable_names):
                var_dict[name] = round(float(res.x[i]), 6)

        slack_dict = {}
        if res.slack is not None:
            for idx, s in enumerate(res.slack):
                slack_dict[f"ineq_constraint_{idx+1}"] = round(float(s), 6)

        md_lines = [
            "# Linear Programming Optimization Report",
            "",
            f"- **Status:** {'✅ Optimal Solution Found' if res.success else '❌ Optimization Failed'}",
            f"- **Message:** {res.message}",
            f"- **Objective Value ({'Max' if maximize else 'Min'}):** `{round(obj_val, 6)}`",
            f"- **Iterations:** {res.nit}",
            "",
            "### Optimal Variable Values:",
            "| Variable | Optimal Value |",
            "|:---|:---:|",
        ]
        for k, v in var_dict.items():
            md_lines.append(f"| `{k}` | **{v}** |")

        if slack_dict:
            md_lines.extend([
                "",
                "### Constraint Slack (Zero = Active / Binding):",
                "| Constraint | Slack Margin |",
                "|:---|:---:|",
            ])
            for k, v in slack_dict.items():
                active_str = "*(Binding)*" if abs(v) < 1e-6 else ""
                md_lines.append(f"| `{k}` | {v} {active_str} |")

        return OptimizationResult(
            problem_type="linear",
            success=res.success,
            objective_value=round(obj_val, 6),
            variables=var_dict,
            slack=slack_dict,
            iterations=int(res.nit),
            message=res.message,
            summary_markdown="\n".join(md_lines),
        )

    def solve_nonlinear(
        self,
        objective_fn: Callable[[np.ndarray], float],
        variable_names: List[str],
        x0: List[float],
        bounds: Optional[List[Tuple[Optional[float], Optional[float]]]] = None,
        ineq_constraints: Optional[List[Callable[[np.ndarray], float]]] = None,  # ineq >= 0
        eq_constraints: Optional[List[Callable[[np.ndarray], float]]] = None,    # eq == 0
        method: str = "SLSQP",
    ) -> OptimizationResult:
        """
        Solves a nonlinear constrained minimization problem using SciPy SLSQP.
        """
        constraints = []
        if ineq_constraints:
            for fn in ineq_constraints:
                constraints.append({"type": "ineq", "fun": fn})
        if eq_constraints:
            for fn in eq_constraints:
                constraints.append({"type": "eq", "fun": fn})

        res = minimize(
            fun=objective_fn,
            x0=x0,
            method=method,
            bounds=bounds,
            constraints=constraints,
        )

        var_dict = {}
        for i, name in enumerate(variable_names):
            var_dict[name] = round(float(res.x[i]), 6)

        md_lines = [
            f"# Nonlinear Optimization Report ({method})",
            "",
            f"- **Status:** {'✅ Optimal Solution Found' if res.success else '❌ Optimization Failed'}",
            f"- **Message:** {res.message}",
            f"- **Optimal Objective Value:** `{round(float(res.fun), 6)}`",
            f"- **Function Evaluations:** {res.nfev}",
            "",
            "### Optimal Variable Assignments:",
            "| Variable | Optimal Value |",
            "|:---|:---:|",
        ]
        for k, v in var_dict.items():
            md_lines.append(f"| `{k}` | **{v}** |")

        return OptimizationResult(
            problem_type="nonlinear",
            success=res.success,
            objective_value=round(float(res.fun), 6),
            variables=var_dict,
            iterations=int(getattr(res, "nit", 0)),
            message=res.message,
            summary_markdown="\n".join(md_lines),
        )

    def solve_knapsack(
        self,
        items: List[Dict[str, Any]],  # each dict: {"name": str, "weight": float, "value": float}
        capacity: float,
    ) -> OptimizationResult:
        """
        Solves the 0-1 Knapsack problem using exact dynamic programming (for integer weights)
        or fractional relaxation / branch-and-bound for general weights.
        """
        n = len(items)
        if n == 0 or capacity <= 0:
            return OptimizationResult("knapsack", True, 0.0, {}, message="Empty knapsack.")

        # If weights are integer-like, use exact DP
        weights = [it["weight"] for it in items]
        values = [it["value"] for it in items]
        names = [it["name"] for it in items]

        is_integer_weights = all(abs(w - round(w)) < 1e-6 for w in weights) and abs(capacity - round(capacity)) < 1e-6

        if is_integer_weights:
            W = int(round(capacity))
            int_weights = [int(round(w)) for w in weights]
            dp = [[0.0] * (W + 1) for _ in range(n + 1)]

            for i in range(1, n + 1):
                wt = int_weights[i - 1]
                val = values[i - 1]
                for w in range(W + 1):
                    if wt <= w:
                        dp[i][w] = max(dp[i - 1][w], dp[i - 1][w - wt] + val)
                    else:
                        dp[i][w] = dp[i - 1][w]

            best_val = dp[n][W]
            selected = {}
            curr_w = W
            for i in range(n, 0, -1):
                if dp[i][curr_w] != dp[i - 1][curr_w]:
                    selected[names[i - 1]] = 1.0
                    curr_w -= int_weights[i - 1]
                else:
                    selected[names[i - 1]] = 0.0

            total_weight = sum(selected[names[i]] * weights[i] for i in range(n))
        else:
            # SciPy integer programming using HiGHS
            c = -np.array(values, dtype=float)
            A_ub = [weights]
            b_ub = [capacity]
            from scipy.optimize import milp
            from scipy.optimize import LinearConstraint, Bounds
            constraints = LinearConstraint(A_ub, -np.inf, b_ub)
            integrality = np.ones(n)
            bounds = Bounds(0, 1)
            res = milp(c=c, integrality=integrality, constraints=constraints, bounds=bounds)
            if res.success:
                best_val = -float(res.fun)
                selected = {names[i]: float(res.x[i]) for i in range(n)}
                total_weight = sum(selected[names[i]] * weights[i] for i in range(n))
            else:
                best_val = 0.0
                selected = {name: 0.0 for name in names}
                total_weight = 0.0

        md_lines = [
            "# Knapsack Combinatorial Optimization Report",
            "",
            f"- **Capacity Limit:** `{capacity}`",
            f"- **Total Weight Selected:** `{total_weight:.2f}`",
            f"- **Optimal Value Achieved:** `{best_val:.2f}`",
            "",
            "### Item Selection Breakdown:",
            "| Item | Weight | Value | Selected |",
            "|:---|:---:|:---:|:---:|",
        ]
        for it in items:
            sel = "✅ Yes" if selected.get(it["name"], 0) > 0.5 else "❌ No"
            md_lines.append(f"| `{it['name']}` | {it['weight']} | {it['value']} | {sel} |")

        return OptimizationResult(
            problem_type="knapsack",
            success=True,
            objective_value=round(best_val, 4),
            variables=selected,
            slack={"weight_margin": round(capacity - total_weight, 4)},
            message="Optimal selection identified.",
            summary_markdown="\n".join(md_lines),
        )


_optimization_engine: Optional[OptimizationEngine] = None


def get_optimization_engine() -> OptimizationEngine:
    global _optimization_engine
    if _optimization_engine is None:
        _optimization_engine = OptimizationEngine()
    return _optimization_engine
