"""
AMATYA Scientific Computation & Dimensional Analysis Engine (core/scientific_computation.py)
=============================================================================================
Phase 14.3 Core Implementation:
  - Deterministic Symbolic Computation (Algebra, Calculus, Differential Equations, Limits).
  - High-Precision Numerical Computation (Roots, ODE Solvers, Eigenvalues, Optimization).
  - Physical Unit-Aware Computation Layer with Strict Dimensional Analysis.
  - Rejection of Dimensionally Incompatible Operations (Never combines incompatible units).
  - Independent Dual-Method Verification (Symbolic analytical vs. Numerical finite-difference).
"""
from __future__ import annotations

import ast
import math
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import scipy.integrate
import scipy.optimize
import sympy as sp

_LOCK = threading.RLock()


# ============================================================================
# Safe AST Symbolic Parser (Phase 15.4)
# ============================================================================

ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Pow,
    ast.Mod,
    ast.UAdd,
    ast.USub,
    ast.Load,
)

ALLOWED_MATH_FUNCS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "exp", "log", "ln", "sqrt", "cbrt", "abs", "sign",
    "factorial", "gamma", "pi", "E", "oo", "zoo", "nan",
}


def _validate_ast_node(node: ast.AST) -> None:
    """Validate that AST node contains only strictly safe mathematical operations."""
    if not isinstance(node, ALLOWED_AST_NODES):
        raise ValueError(
            f"Disallowed AST node type '{type(node).__name__}'. Only mathematical expressions are allowed."
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError(
                f"Disallowed function call syntax. Function must be a simple name, not '{type(node.func).__name__}'."
            )
        func_name = node.func.id
        if func_name not in ALLOWED_MATH_FUNCS:
            raise ValueError(
                f"Disallowed function '{func_name}'. Only mathematical functions ({', '.join(sorted(ALLOWED_MATH_FUNCS))}) are permitted."
            )
        if node.keywords:
            raise ValueError("Keyword arguments are disallowed in mathematical expressions.")

    for child in ast.iter_child_nodes(node):
        _validate_ast_node(child)


def safe_sympify(expr_str: str, allowed_symbols: set[str] | None = None) -> sp.Expr:
    """Restricted AST symbolic parser replacing direct sympy.sympify on untrusted input.

    Validates AST structure to guarantee:
    - No attribute lookups (e.g. os.system, __class__)
    - No imports or exec
    - No subscripts or lambdas
    - Only registered mathematical functions and allowed symbols.
    """
    clean_str = str(expr_str or "").strip()
    if not clean_str:
        raise ValueError("Cannot parse empty symbolic expression.")

    try:
        tree = ast.parse(clean_str, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid mathematical syntax: {exc}")

    _validate_ast_node(tree)

    if allowed_symbols is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in ALLOWED_MATH_FUNCS:
                if node.id not in allowed_symbols:
                    raise ValueError(f"Symbol '{node.id}' is not in allowed symbols: {allowed_symbols}")

    try:
        parsed = sp.sympify(clean_str)
    except Exception as exc:
        raise ValueError(f"SymPy evaluation error: {exc}")

    return parsed


# ============================================================================
# Dimensional Analysis & Unit-Aware Computation
# ============================================================================

class DimensionalInconsistencyError(ValueError):
    """Raised when dimensionally incompatible physical quantities are combined."""
    pass


# Base Dimensions: [Mass, Length, Time, ElectricCurrent, Temperature, Amount, LuminousIntensity]
# Vector: (M, L, T, I, Theta, N, J)
DIMENSIONS = {
    # Base
    "dimensionless": (0, 0, 0, 0, 0, 0, 0),
    "length": (0, 1, 0, 0, 0, 0, 0),
    "time": (0, 0, 1, 0, 0, 0, 0),
    "mass": (1, 0, 0, 0, 0, 0, 0),
    "current": (0, 0, 0, 1, 0, 0, 0),
    "temperature": (0, 0, 0, 0, 1, 0, 0),
    # Derived
    "velocity": (0, 1, -1, 0, 0, 0, 0),
    "acceleration": (0, 1, -2, 0, 0, 0, 0),
    "force": (1, 1, -2, 0, 0, 0, 0),
    "energy": (1, 2, -2, 0, 0, 0, 0),
    "power": (1, 2, -3, 0, 0, 0, 0),
    "voltage": (1, 2, -3, -1, 0, 0, 0),
    "resistance": (1, 2, -3, -2, 0, 0, 0),
    "capacitance": (-1, -2, 4, 2, 0, 0, 0),
    "inductance": (1, 2, -2, -2, 0, 0, 0),
    "frequency": (0, 0, -1, 0, 0, 0, 0),
}

# Unit multipliers to SI base
UNIT_REGISTRY: dict[str, tuple[tuple[int, ...], float]] = {
    # Dimensionless
    "": (DIMENSIONS["dimensionless"], 1.0),
    "%": (DIMENSIONS["dimensionless"], 0.01),
    "ratio": (DIMENSIONS["dimensionless"], 1.0),

    # Length (base: meter)
    "m": (DIMENSIONS["length"], 1.0),
    "km": (DIMENSIONS["length"], 1000.0),
    "cm": (DIMENSIONS["length"], 0.01),
    "mm": (DIMENSIONS["length"], 0.001),
    "um": (DIMENSIONS["length"], 1e-6),
    "nm": (DIMENSIONS["length"], 1e-9),

    # Time (base: second)
    "s": (DIMENSIONS["time"], 1.0),
    "ms": (DIMENSIONS["time"], 0.001),
    "us": (DIMENSIONS["time"], 1e-6),
    "ns": (DIMENSIONS["time"], 1e-9),
    "min": (DIMENSIONS["time"], 60.0),
    "hour": (DIMENSIONS["time"], 3600.0),
    "day": (DIMENSIONS["time"], 86400.0),

    # Mass (base: kg)
    "kg": (DIMENSIONS["mass"], 1.0),
    "g": (DIMENSIONS["mass"], 0.001),
    "mg": (DIMENSIONS["mass"], 1e-6),

    # Electric Current (base: Ampere)
    "A": (DIMENSIONS["current"], 1.0),
    "mA": (DIMENSIONS["current"], 0.001),
    "uA": (DIMENSIONS["current"], 1e-6),
    "nA": (DIMENSIONS["current"], 1e-9),

    # Temperature (base: Kelvin)
    "K": (DIMENSIONS["temperature"], 1.0),

    # Voltage (base: Volt)
    "V": (DIMENSIONS["voltage"], 1.0),
    "mV": (DIMENSIONS["voltage"], 0.001),
    "kV": (DIMENSIONS["voltage"], 1000.0),

    # Resistance (base: Ohm)
    "Ohm": (DIMENSIONS["resistance"], 1.0),
    "ohm": (DIMENSIONS["resistance"], 1.0),
    "kOhm": (DIMENSIONS["resistance"], 1000.0),
    "MOhm": (DIMENSIONS["resistance"], 1e6),

    # Capacitance (base: Farad)
    "F": (DIMENSIONS["capacitance"], 1.0),
    "mF": (DIMENSIONS["capacitance"], 0.001),
    "uF": (DIMENSIONS["capacitance"], 1e-6),
    "nF": (DIMENSIONS["capacitance"], 1e-9),
    "pF": (DIMENSIONS["capacitance"], 1e-12),

    # Inductance (base: Henry)
    "H": (DIMENSIONS["inductance"], 1.0),
    "mH": (DIMENSIONS["inductance"], 0.001),
    "uH": (DIMENSIONS["inductance"], 1e-6),

    # Power (base: Watt)
    "W": (DIMENSIONS["power"], 1.0),
    "mW": (DIMENSIONS["power"], 0.001),
    "kW": (DIMENSIONS["power"], 1000.0),
    "MW": (DIMENSIONS["power"], 1e6),

    # Energy (base: Joule)
    "J": (DIMENSIONS["energy"], 1.0),
    "mJ": (DIMENSIONS["energy"], 0.001),
    "kJ": (DIMENSIONS["energy"], 1000.0),
    "Wh": (DIMENSIONS["energy"], 3600.0),
    "kWh": (DIMENSIONS["energy"], 3.6e6),

    # Frequency (base: Hertz)
    "Hz": (DIMENSIONS["frequency"], 1.0),
    "kHz": (DIMENSIONS["frequency"], 1000.0),
    "MHz": (DIMENSIONS["frequency"], 1e6),
    "GHz": (DIMENSIONS["frequency"], 1e9),

    # Velocity (base: m/s)
    "m/s": (DIMENSIONS["velocity"], 1.0),
    "km/h": (DIMENSIONS["velocity"], 1.0 / 3.6),
}


@dataclass
class UnitQuantity:
    """Represents a physical quantity with magnitude, unit, and dimensional vector."""
    value: float
    unit: str
    dimensions: tuple[int, ...] | None = None

    def __post_init__(self):
        norm_unit = self.unit.strip()
        if self.dimensions is None:
            if norm_unit not in UNIT_REGISTRY:
                raise DimensionalInconsistencyError(
                    f"Unrecognized or unsupported physical unit '{norm_unit}'. Refusing silent dimensionless fallback."
                )
            self.dimensions, self.si_multiplier = UNIT_REGISTRY[norm_unit]
        else:
            if norm_unit in UNIT_REGISTRY:
                _, self.si_multiplier = UNIT_REGISTRY[norm_unit]
            elif norm_unit == "":
                self.si_multiplier = 1.0
            else:
                raise DimensionalInconsistencyError(
                    f"Unrecognized or unsupported physical unit '{norm_unit}'."
                )

    @classmethod
    def parse(cls, text: str) -> UnitQuantity:
        """Parses a string representation like '10 m', '25 V', '100.5 ohm'."""
        text = text.strip()
        m = re.match(r"^([+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*([A-Za-zµ%°/Ω^0-9\-_]*)$", text)
        if not m:
            raise ValueError(f"Cannot parse '{text}' as a valid UnitQuantity.")
        val = float(m.group(1))
        unit = m.group(2).strip()
        return cls(value=val, unit=unit)

    @property
    def magnitude(self) -> float:
        return self.value

    @property
    def unit_str(self) -> str:
        return self.unit

    @property
    def si_value(self) -> float:
        """Returns the value converted to standard SI base unit."""
        return self.value * self.si_multiplier

    def to(self, target_unit: str) -> UnitQuantity:
        """Converts quantity to target unit if dimensionally compatible."""
        if target_unit not in UNIT_REGISTRY:
            raise DimensionalInconsistencyError(f"Target unit '{target_unit}' is not registered.")
        target_dim, target_mult = UNIT_REGISTRY[target_unit]
        if self.dimensions != target_dim:
            raise DimensionalInconsistencyError(
                f"Cannot convert '{self.unit}' (dim={self.dimensions}) to '{target_unit}' (dim={target_dim})."
            )
        new_val = self.si_value / target_mult
        return UnitQuantity(value=new_val, unit=target_unit)

    def __add__(self, other: UnitQuantity) -> UnitQuantity:
        if not isinstance(other, UnitQuantity):
            raise TypeError("Can only add UnitQuantity to UnitQuantity.")
        if self.dimensions != other.dimensions:
            raise DimensionalInconsistencyError(
                f"Dimensional mismatch: Cannot add {self.unit} to {other.unit}."
            )
        # Convert other to self's unit
        other_in_self = other.to(self.unit)
        return UnitQuantity(value=self.value + other_in_self.value, unit=self.unit)

    def __sub__(self, other: UnitQuantity) -> UnitQuantity:
        if not isinstance(other, UnitQuantity):
            raise TypeError("Can only subtract UnitQuantity from UnitQuantity.")
        if self.dimensions != other.dimensions:
            raise DimensionalInconsistencyError(
                f"Dimensional mismatch: Cannot subtract {other.unit} from {self.unit}."
            )
        other_in_self = other.to(self.unit)
        return UnitQuantity(value=self.value - other_in_self.value, unit=self.unit)

    def __mul__(self, other: UnitQuantity | float | int) -> UnitQuantity:
        if isinstance(other, (int, float)):
            return UnitQuantity(value=self.value * float(other), unit=self.unit)
        if isinstance(other, UnitQuantity):
            # Compute product dimensions
            prod_si = self.si_value * other.si_value
            prod_dim = tuple(a + b for a, b in zip(self.dimensions, other.dimensions))
            # Match registered SI unit
            matched_unit = self._find_unit_by_dim(prod_dim)
            return UnitQuantity(value=prod_si, unit=matched_unit)
        raise TypeError("Multiplication only supported with scalar or UnitQuantity.")

    def __truediv__(self, other: UnitQuantity | float | int) -> UnitQuantity:
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("Division by zero in physical quantity.")
            return UnitQuantity(value=self.value / float(other), unit=self.unit)
        if isinstance(other, UnitQuantity):
            if other.si_value == 0:
                raise ZeroDivisionError("Division by zero in physical quantity.")
            quot_si = self.si_value / other.si_value
            quot_dim = tuple(a - b for a, b in zip(self.dimensions, other.dimensions))
            matched_unit = self._find_unit_by_dim(quot_dim)
            return UnitQuantity(value=quot_si, unit=matched_unit)
        raise TypeError("Division only supported with scalar or UnitQuantity.")

    @staticmethod
    def _find_unit_by_dim(dim: tuple[int, ...]) -> str:
        for name, d_tuple in DIMENSIONS.items():
            if d_tuple == dim:
                # Return standard base unit for this dimension
                mapping = {
                    "voltage": "V",
                    "current": "A",
                    "resistance": "Ohm",
                    "power": "W",
                    "energy": "J",
                    "frequency": "Hz",
                    "capacitance": "F",
                    "inductance": "H",
                    "length": "m",
                    "time": "s",
                    "velocity": "m/s",
                    "acceleration": "m/s^2",
                    "dimensionless": "",
                }
                return mapping.get(name, "")
        return ""

    def __repr__(self) -> str:
        return f"{self.value:.4g} {self.unit}".strip()


# ============================================================================
# Deterministic Symbolic Mathematics
# ============================================================================

class SymbolicSolver:
    """Symbolic algebra, calculus, and equation solving via SymPy."""

    @classmethod
    def solve_equation(cls, equation_str: str, var: str = "x") -> list[str]:
        """Solves an equation for a variable symbolically. Example: 'x**2 - 4 = 0'."""
        eq_clean = equation_str.strip()
        if "=" in eq_clean:
            lhs_s, rhs_s = eq_clean.split("=", 1)
            expr = safe_sympify(lhs_s) - safe_sympify(rhs_s)
        else:
            expr = safe_sympify(eq_clean)

        v = sp.Symbol(var)
        solutions = sp.solve(expr, v)
        return [str(s) for s in solutions]

    @classmethod
    def differentiate(cls, expr_str: str, var: str = "x", order: int = 1) -> str:
        """Computes analytical derivative of expression."""
        v = sp.Symbol(var)
        expr = safe_sympify(expr_str)
        deriv = sp.diff(expr, v, order)
        return str(deriv)

    @classmethod
    def integrate(cls, expr_str: str, var: str = "x", lower: float | None = None, upper: float | None = None) -> str:
        """Computes analytical definite or indefinite integral."""
        v = sp.Symbol(var)
        expr = safe_sympify(expr_str)
        if lower is not None and upper is not None:
            res = sp.integrate(expr, (v, lower, upper))
        else:
            res = sp.integrate(expr, v)
        return str(res)

    @classmethod
    def limit(cls, expr_str: str, var: str = "x", target: str = "0") -> str:
        """Computes analytical limit as var -> target."""
        v = sp.Symbol(var)
        expr = safe_sympify(expr_str)
        t = safe_sympify(target)
        lim = sp.limit(expr, v, t)
        return str(lim)

    @classmethod
    def simplify(cls, expr_str: str) -> str:
        """Symbolically simplifies an algebraic expression."""
        expr = safe_sympify(expr_str)
        return str(sp.simplify(expr))


# ============================================================================
# High-Precision Numerical Solvers
# ============================================================================

class RootResult(float):
    """Float subclass storing root metadata while behaving like a float."""
    converged: bool
    iterations: int
    root: float

    def __new__(cls, val: float, converged: bool = True, iterations: int = 0):
        obj = super().__new__(cls, float(val))
        obj.converged = converged
        obj.iterations = iterations
        obj.root = float(val)
        return obj

    def __getitem__(self, item: str) -> Any:
        if item == "root":
            return self.root
        elif item == "converged":
            return self.converged
        elif item == "iterations":
            return self.iterations
        raise KeyError(item)


@dataclass
class ODEResult:
    success: bool
    t: np.ndarray
    y: np.ndarray


class NumericalSolver:
    """High-precision root finding, numerical ODE solving, and optimization via SciPy."""

    @classmethod
    def find_root(cls, func: Any, x0: float, var: str = "x") -> RootResult:
        """Finds root of f(x) = 0 starting from x0."""
        if callable(func):
            f_lam = func
        else:
            v = sp.Symbol(var)
            expr = safe_sympify(str(func))
            f_lam = sp.lambdify(v, expr, "numpy")

        res = scipy.optimize.root_scalar(f_lam, x0=x0, method="newton")
        return RootResult(float(res.root), converged=bool(res.converged), iterations=int(getattr(res, "iterations", 0)))

    @classmethod
    def minimize(
        cls,
        func_str: str,
        x0: list[float],
        bounds: list[tuple[float, float]] | None = None,
    ) -> dict[str, Any]:
        """Numerical optimization: finds minimum of objective function."""
        # Parse scalar or multi-variable function
        if len(x0) == 1:
            x = sp.Symbol("x")
            expr = safe_sympify(func_str)
            f_lam = sp.lambdify(x, expr, "numpy")
            cost_fn = lambda v: float(f_lam(v[0]))
        else:
            symbols = [sp.Symbol(f"x{i}") for i in range(len(x0))]
            expr = safe_sympify(func_str)
            f_lam = sp.lambdify(symbols, expr, "numpy")
            cost_fn = lambda v: float(f_lam(*v))

        res = scipy.optimize.minimize(cost_fn, x0, bounds=bounds, method="L-BFGS-B")
        return {
            "success": bool(res.success),
            "optimal_x": [float(x) for x in res.x],
            "optimal_value": float(res.fun),
            "message": str(res.message),
        }

    @classmethod
    def solve_ode(
        cls,
        ode_func: Callable[[float, np.ndarray], np.ndarray],
        t_span: tuple[float, float],
        y0: list[float],
        num_points: int = 100,
        method: str = "RK45",
    ) -> dict[str, Any]:
        """Solves system of ordinary differential equations dy/dt = f(t, y)."""
        t_eval = np.linspace(t_span[0], t_span[1], num_points)
        sol = scipy.integrate.solve_ivp(ode_func, t_span, y0, t_eval=t_eval, method=method)

        return {
            "success": bool(sol.success),
            "t": sol.t.tolist(),
            "y": sol.y.tolist(),
            "status": sol.status,
            "message": sol.message,
        }

    @classmethod
    def solve_ode_ivp(
        cls,
        dydt_fn: Callable[[float, list[float]], list[float]],
        y0: list[float],
        t_span: tuple[float, float],
        num_points: int = 100,
        method: str = "RK45",
    ) -> ODEResult:
        """Solves ODE IVP returning ODEResult with success, t, y numpy arrays."""
        t_eval = np.linspace(t_span[0], t_span[1], num_points)
        sol = scipy.integrate.solve_ivp(dydt_fn, t_span, y0, t_eval=t_eval, method=method)
        return ODEResult(success=bool(sol.success), t=sol.t, y=sol.y)


# ============================================================================
# Dual-Method Independent Verification
# ============================================================================

class VerificationAuditor:
    """Validates mathematical and physical results with independent verification methods."""

    @classmethod
    def verify_derivative(
        cls,
        expr_str: str,
        f: Any = None,
        at_x: float | None = None,
        x_eval: float | None = None,
        h: float = 1e-6,
    ) -> dict[str, Any]:
        """Compares symbolic analytical derivative with independent central finite-difference."""
        target_x = at_x if at_x is not None else (x_eval if x_eval is not None else 0.0)
        x = sp.Symbol("x")
        expr = safe_sympify(expr_str)
        analytical_deriv_expr = sp.diff(expr, x)
        analytical_val = float(analytical_deriv_expr.subs(x, target_x))

        if callable(f):
            f_lam = f
        else:
            f_lam = sp.lambdify(x, expr, "numpy")

        # Central difference: (f(x+h) - f(x-h)) / (2h)
        numerical_val = float((f_lam(target_x + h) - f_lam(target_x - h)) / (2.0 * h))

        error = abs(analytical_val - numerical_val)
        rel_error = error / (abs(analytical_val) + 1e-12)
        verified = rel_error < 1e-4

        return {
            "verified": verified,
            "matches": verified,
            "analytical_value": round(analytical_val, 6),
            "symbolic_val": analytical_val,
            "numerical_approximation": round(numerical_val, 6),
            "absolute_error": error,
            "relative_error": rel_error,
            "method": "Central Difference O(h^2)",
        }
        verified = rel_error < 1e-4

        return {
            "verified": verified,
            "analytical_value": round(analytical_val, 6),
            "numerical_approximation": round(numerical_val, 6),
            "absolute_error": error,
            "relative_error": rel_error,
            "method": "Central Difference O(h^2)",
        }
