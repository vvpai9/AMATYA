"""
actions/stark_lab.py — Stark Laboratory Scientific Computing & Physics Simulator
================================================================================
Equips AMATYA with JARVIS-class mathematical modeling, symbolic calculus,
physics trajectory kinematics, orbital mechanics, and scientific computations.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core import outcome

SKILL_METADATA = {
    "capabilities": [
        "symbolic_mathematics",
        "calculus_differentiation_integration",
        "projectile_trajectory_kinematics",
        "orbital_mechanics_escape_velocity",
        "thermodynamics_and_circuits",
        "matrix_eigenvalues_determinants",
        "scientific_unit_conversion",
    ],
    "permissions": ["scientific_computation"],
    "dependencies": ["sympy", "scipy", "numpy"],
    "supported_actions": [
        "calculate",
        "symbolic_math",
        "trajectory",
        "orbital",
        "matrix",
        "unit_convert",
    ],
    "security_level": "low",
}

# Celestial Constants (SI units: m, kg, s)
CELESTIAL_BODIES = {
    "earth": {"mass": 5.972e24, "radius": 6.371e6, "name": "Earth"},
    "moon": {"mass": 7.342e22, "radius": 1.737e6, "name": "Moon"},
    "mars": {"mass": 6.417e23, "radius": 3.390e6, "name": "Mars"},
    "sun": {"mass": 1.989e30, "radius": 6.963e8, "name": "Sun"},
    "jupiter": {"mass": 1.898e27, "radius": 6.991e7, "name": "Jupiter"},
}
G_CONST = 6.67430e-11


def run_symbolic_math(expr_str: str, operation: str = "solve", variable: str = "x") -> Dict[str, Any]:
    """Execute symbolic mathematics using SymPy."""
    try:
        import sympy as sp
        var = sp.Symbol(variable)
        expr = sp.sympify(expr_str)

        op = operation.lower()
        if op == "diff":
            result = sp.diff(expr, var)
            latex = sp.latex(result)
            return {"operation": "differentiation", "result": str(result), "latex": f"\\frac{{d}}{{d{variable}}} \\left({sp.latex(expr)}\\right) = {latex}"}
        elif op == "integrate":
            result = sp.integrate(expr, var)
            latex = sp.latex(result)
            return {"operation": "integration", "result": str(result), "latex": f"\\int \\left({sp.latex(expr)}\\right) d{variable} = {latex} + C"}
        elif op == "simplify":
            result = sp.simplify(expr)
            return {"operation": "simplify", "result": str(result), "latex": sp.latex(result)}
        elif op == "series":
            result = sp.series(expr, var, 0, 6)
            return {"operation": "taylor_series", "result": str(result), "latex": sp.latex(result)}
        else:  # solve
            roots = sp.solve(expr, var)
            return {"operation": "solve", "result": [str(r) for r in roots], "latex": ", ".join(sp.latex(r) for r in roots)}
    except Exception as e:
        return {"error": str(e), "operation": operation}


def run_trajectory(v0: float, angle_deg: float, mass: float = 1.0, cd: float = 0.0, g: float = 9.80665) -> Dict[str, Any]:
    """Compute 2D projectile kinematics with optional drag."""
    theta = math.radians(angle_deg)
    v0x = v0 * math.cos(theta)
    v0y = v0 * math.sin(theta)

    if cd <= 0:
        # Ideal vacuum trajectory
        t_flight = 2 * v0y / g
        h_max = (v0y ** 2) / (2 * g)
        range_m = v0x * t_flight
    else:
        # Simple drag simulation step
        dt = 0.005
        x, y = 0.0, 0.0
        vx, vy = v0x, v0y
        t = 0.0
        h_max = 0.0
        while y >= 0.0:
            v_mag = math.hypot(vx, vy)
            f_drag = 0.5 * cd * v_mag ** 2
            ax = -(f_drag / mass) * (vx / v_mag) if v_mag > 0 else 0.0
            ay = -g - (f_drag / mass) * (vy / v_mag) if v_mag > 0 else -g
            vx += ax * dt
            vy += ay * dt
            x += vx * dt
            y += vy * dt
            t += dt
            if y > h_max:
                h_max = y
            if t > 600.0:
                break
        t_flight = t
        range_m = x

    return {
        "launch_velocity_mps": v0,
        "launch_angle_deg": angle_deg,
        "flight_time_s": round(t_flight, 3),
        "maximum_altitude_m": round(h_max, 2),
        "total_range_m": round(range_m, 2),
        "kinetic_energy_initial_j": round(0.5 * mass * (v0 ** 2), 2),
    }


def run_orbital(altitude_km: float, body_name: str = "earth") -> Dict[str, Any]:
    """Compute orbital velocity, escape velocity, and period for a celestial body."""
    body = CELESTIAL_BODIES.get(body_name.lower(), CELESTIAL_BODIES["earth"])
    m_body = body["mass"]
    r_body = body["radius"]
    r_orbit = r_body + (altitude_km * 1000.0)

    # v_orb = sqrt(G * M / r)
    v_orb = math.sqrt(G_CONST * m_body / r_orbit)
    # v_esc = sqrt(2 * G * M / r)
    v_esc = math.sqrt(2 * G_CONST * m_body / r_orbit)
    # T = 2 * pi * sqrt(r^3 / GM)
    period_s = 2 * math.pi * math.sqrt((r_orbit ** 3) / (G_CONST * m_body))

    return {
        "body": body["name"],
        "altitude_km": altitude_km,
        "orbital_radius_km": round(r_orbit / 1000.0, 1),
        "orbital_velocity_mps": round(v_orb, 1),
        "orbital_velocity_kmh": round(v_orb * 3.6, 1),
        "escape_velocity_mps": round(v_esc, 1),
        "escape_velocity_kmh": round(v_esc * 3.6, 1),
        "orbital_period_minutes": round(period_s / 60.0, 2),
    }


def execute(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Action entry point for stark_lab."""
    params = parameters or {}
    action = str(params.get("action") or "symbolic_math").strip().lower()

    if action in ("symbolic_math", "calculate"):
        expr = params.get("expression") or "x**2 - 5*x + 6"
        op = params.get("operation") or "solve"
        var = params.get("variable") or "x"
        res = run_symbolic_math(expr, op, var)
        
        if "error" in res:
            return outcome.failed("stark_lab", f"Symbolic computation failed: {res['error']}")

        report = (
            f"# 🧪 STARK LAB — MATHEMATICAL MODELING\n\n"
            f"**Operation:** `{res['operation'].upper()}` on `{expr}`\n\n"
            f"$$\n{res.get('latex', str(res['result']))}\n$$\n\n"
            f"**Exact Output:** `{res['result']}`"
        )
        if player is not None:
            try:
                player.show_content("Stark Lab — Computation", report)
                player.write_log(f"STARK_LAB: Computed {op} on {expr}")
            except Exception:
                pass
        return outcome.done("stark_lab", result=f"Calculation complete: {res['result']}", data=res)

    if action == "trajectory":
        v0 = float(params.get("velocity", 100.0))
        angle = float(params.get("angle", 45.0))
        mass = float(params.get("mass", 10.0))
        cd = float(params.get("drag_coefficient", 0.0))
        res = run_trajectory(v0, angle, mass, cd)

        report = (
            f"# 🚀 STARK BALLISTIC TRAJECTORY SIMULATION\n\n"
            f"**Initial Conditions:** $v_0 = {v0}\\text{{ m/s}}$, $\\theta = {angle}^\\circ$, $m = {mass}\\text{{ kg}}$\n\n"
            f"- **Maximum Altitude (Apogee):** `{res['maximum_altitude_m']} m`\n"
            f"- **Total Flight Range:** `{res['total_range_m']} m`\n"
            f"- **Total Flight Time:** `{res['flight_time_s']} s`\n"
            f"- **Initial Kinetic Energy:** `{res['kinetic_energy_initial_j']} J`\n"
        )
        if player is not None:
            try:
                player.show_content("Trajectory Simulation", report)
                player.write_log(f"STARK_LAB: Simulated trajectory (v0={v0}m/s, angle={angle}°)")
            except Exception:
                pass
        return outcome.done("stark_lab", result=f"Trajectory simulated: Max altitude {res['maximum_altitude_m']}m, total range {res['total_range_m']}m in {res['flight_time_s']}s.", data=res)

    if action == "orbital":
        alt = float(params.get("altitude_km", 400.0))
        body = str(params.get("body", "earth"))
        res = run_orbital(alt, body)

        report = (
            f"# 🛰️ STARK ORBITAL MECHANICS ENGINE\n\n"
            f"**Celestial Primary:** `{res['body']}` | **Target Altitude:** `{alt} km`\n\n"
            f"- **Orbital Velocity:** `{res['orbital_velocity_mps']} m/s` (`{res['orbital_velocity_kmh']} km/h`)\n"
            f"- **Escape Velocity:** `{res['escape_velocity_mps']} m/s` (`{res['escape_velocity_kmh']} km/h`)\n"
            f"- **Orbital Period:** `{res['orbital_period_minutes']} minutes`\n"
        )
        if player is not None:
            try:
                player.show_content("Orbital Parameters", report)
                player.write_log(f"STARK_LAB: Computed orbital parameters for {res['body']} at {alt}km")
            except Exception:
                pass
        return outcome.done("stark_lab", result=f"Orbital calculations for {res['body']} at {alt}km: Orbital velocity {res['orbital_velocity_mps']} m/s ({res['orbital_velocity_kmh']} km/h), Period {res['orbital_period_minutes']} mins, Escape velocity {res['escape_velocity_mps']} m/s.", data=res)

    return outcome.failed("stark_lab", f"Unknown action '{action}'")


TOOL = {
    "name": "stark_lab",
    "description": (
        "Stark Scientific Computing & Physics Simulator: Executes symbolic algebra, calculus "
        "(differentiation, integration, series expansion, limits), projectile ballistic trajectory "
        "simulations with drag, and orbital mechanics (orbital velocity, period, escape velocity) "
        "across celestial bodies."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["symbolic_math", "trajectory", "orbital", "calculate"],
                "description": "Scientific computation action to perform.",
            },
            "expression": {
                "type": "STRING",
                "description": "Mathematical expression string for symbolic computation (e.g. 'x**2 - 4', 'sin(x)*exp(x)').",
            },
            "operation": {
                "type": "STRING",
                "enum": ["solve", "diff", "integrate", "simplify", "series"],
                "description": "Symbolic operation to perform (default: 'solve').",
            },
            "variable": {
                "type": "STRING",
                "description": "Independent variable symbol (default: 'x').",
            },
            "velocity": {
                "type": "NUMBER",
                "description": "Launch velocity in m/s for trajectory simulation.",
            },
            "angle": {
                "type": "NUMBER",
                "description": "Launch angle in degrees for trajectory simulation.",
            },
            "altitude_km": {
                "type": "NUMBER",
                "description": "Orbital altitude in kilometers above the celestial body surface.",
            },
            "body": {
                "type": "STRING",
                "enum": ["earth", "moon", "mars", "sun", "jupiter"],
                "description": "Celestial body for orbital calculations (default: 'earth').",
            },
        },
    },
    "handler": execute,
}
