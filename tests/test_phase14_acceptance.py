"""
tests/test_phase14_acceptance.py — Comprehensive Acceptance Test Suite for AMATYA Phase 14.

Covers:
  - Phase 14.1: Architecture & Baseline verification.
  - Phase 14.2: Structured Reasoning Engine.
  - Phase 14.3: Scientific Computation & Dimensional Analysis.
  - Phase 14.4: Causal & Counterfactual Engine.
  - Phase 14.5: Universal Simulation Engine (Circuit, Thermal, Orbit, Monte Carlo).
  - Phase 14.6: Digital Twin Architecture & Parameter Calibration.
  - Phase 14.7: Predictive Intelligence & Time-Series Forecasting.
  - Phase 14.8: Scenario Analysis & Tornado Sensitivity.
  - Phase 14.9: Decision Intelligence (WSM, TOPSIS, Pareto Dominance).
  - Phase 14.10: Constraint Solving & Optimization (LP, NLP, Knapsack).
  - Phase 14.11: Strategic Planning & Critical Path Method (CPM).
  - Phase 14.12: Action Registry & Tool Execution Integration.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from actions import reasoning_tools
from core.action_loader import discover_actions
from core.causal_engine import CausalGraph, CausalVariable, get_causal_engine
from core.decision_intelligence import (
    AlternativeOption,
    Criterion,
    get_decision_engine,
)
from core.digital_twin import DigitalTwin, TwinComponent, get_digital_twin_registry
from core.optimization_engine import get_optimization_engine
from core.predictive_intelligence import get_predictive_engine
from core.reasoning_engine import (
    ProblemCategory,
    ProblemDefinition,
    get_reasoning_engine,
)
from core.scenario_engine import ScenarioDefinition, get_scenario_engine
from core.scientific_computation import (
    DimensionalInconsistencyError,
    NumericalSolver,
    SymbolicSolver,
    UnitQuantity,
    VerificationAuditor,
)
from core.simulation_engine import get_simulation_engine
from core.strategic_planner import PlannedTask, get_strategic_planner


# ============================================================================
# Category A: Scientific Computation & Dimensional Analysis (Phase 14.3)
# ============================================================================

def test_01_unit_quantity_and_dimensional_analysis():
    # Length addition
    d1 = UnitQuantity.parse("10 m")
    d2 = UnitQuantity.parse("25 m")
    d_total = d1 + d2
    assert d_total.magnitude == 35.0
    assert d_total.unit_str == "m"

    # Multiplication: V = I * R
    current = UnitQuantity(2.5, "A", (0, 0, 0, 1, 0))
    resistance = UnitQuantity(10.0, "ohm", (2, 1, -3, -2, 0))
    voltage = current * resistance
    assert voltage.magnitude == 25.0

    # Incompatible addition must raise DimensionalInconsistencyError
    with pytest.raises(DimensionalInconsistencyError):
        _ = current + resistance


def test_02_symbolic_solver_and_verification():
    # Analytical derivative: d/dx(x^3 - 5x + 7) = 3x^2 - 5
    deriv = SymbolicSolver.differentiate("x**3 - 5*x + 7", "x")
    assert "3*x**2 - 5" in deriv or "3*x**2" in deriv

    # Analytical integral: int(2*x, x) = x^2
    integral = SymbolicSolver.integrate("2*x", "x")
    assert "x**2" in integral

    # Solve equation: 2*x + 10 = 0 -> x = -5
    sol = SymbolicSolver.solve_equation("2*x + 10", "x")
    assert "-5" in str(sol)

    # Verification auditor: symbolic derivative vs finite difference
    def f(x):
        return x ** 3 - 5 * x + 7

    audit = VerificationAuditor.verify_derivative("x**3 - 5*x + 7", f, at_x=2.0)
    assert audit["matches"] is True
    assert abs(audit["symbolic_val"] - 7.0) < 1e-4
    assert audit["relative_error"] < 1e-4


def test_03_numerical_solver_roots_and_ivp():
    # Root finding for f(x) = x^2 - 9 -> root at 3.0
    root = NumericalSolver.find_root(lambda x: x ** 2 - 9.0, x0=2.0)
    assert abs(root - 3.0) < 1e-5

    # ODE IVP: dy/dt = -0.5 * y, y(0) = 10 -> y(t) = 10 * exp(-0.5 * t)
    sol = NumericalSolver.solve_ode_ivp(
        dydt_fn=lambda t, y: [-0.5 * y[0]],
        y0=[10.0],
        t_span=(0.0, 4.0),
        num_points=41,
    )
    assert sol.success is True
    # At t = 2, y should be approx 10 * exp(-1) = 3.6788
    idx = (np.abs(sol.t - 2.0)).argmin()
    assert abs(sol.y[0][idx] - (10.0 * math.exp(-1.0))) < 0.05


# ============================================================================
# Category B: Structured Reasoning Engine (Phase 14.2)
# ============================================================================

def test_04_structured_reasoning_formulation_and_solving():
    engine = get_reasoning_engine()

    prob = ProblemDefinition(
        problem_id="prob_structural_01",
        title="Cantilever Beam Stress Analysis",
        category=ProblemCategory.ENGINEERING,
        objective="Determine maximum bending stress under point load P",
        givens={"load_N": 5000.0, "length_m": 2.0, "section_modulus_m3": 0.0001},
        unknowns=["max_stress_Pa"],
        assumptions=["Linear elastic material", "Small deflections"],
        constraints=["Stress < Yield Strength (250 MPa)"],
        selected_methods=["analytical", "verification"],
    )

    report = engine.solve_problem(prob)
    assert report.is_verified is True
    assert len(report.steps) > 0
    md = report.to_markdown()
    assert "Cantilever Beam Stress Analysis" in md
    assert "Assumptions:" in md


# ============================================================================
# Category C: Causal & Counterfactual Engine (Phase 14.4)
# ============================================================================

def test_05_causal_graph_confounder_and_intervention():
    engine = get_causal_engine()
    graph = CausalGraph(name="EngineCooling")

    # Add variables
    graph.add_variable("AmbientTemp", 25.0, unit="degC")
    graph.add_variable("CoolantFlow", 10.0, unit="L/min")
    graph.add_variable("EngineTemp", 90.0, unit="degC")
    graph.add_variable("WearRate", 0.05, unit="mm/yr")

    # Causal links:
    # AmbientTemp -> EngineTemp (positive link)
    # CoolantFlow -> EngineTemp (negative link)
    # EngineTemp -> WearRate (positive link)
    graph.add_causal_link("AmbientTemp", "EngineTemp", weight=0.4, mechanism="ambient heat flux")
    graph.add_causal_link("CoolantFlow", "EngineTemp", weight=-2.0, mechanism="forced convection")
    graph.add_causal_link("EngineTemp", "WearRate", weight=0.01, mechanism="thermal stress")

    engine.register_graph(graph)

    # Pearl's do-calculus intervention: do(CoolantFlow = 15.0) (increase flow by +5)
    # Delta CoolantFlow = +5
    # Delta EngineTemp = +5 * (-2.0) = -10.0 -> new EngineTemp = 80.0
    # Delta WearRate = -10.0 * 0.01 = -0.1 -> new WearRate = -0.05 (or delta -0.1)
    res = engine.evaluate_counterfactual("EngineCooling", "CoolantFlow", 15.0)
    assert res.counterfactual_state["CoolantFlow"] == 15.0
    assert abs(res.state_deltas["EngineTemp"] - (-10.0)) < 1e-4
    assert res.counterfactual_state["EngineTemp"] == 80.0
    assert "WearRate" in res.impacted_variables


# ============================================================================
# Category D: Universal Simulation Engine (Phase 14.5)
# ============================================================================

def test_06_simulation_adapters_circuit_thermal_orbital_mc():
    sim_engine = get_simulation_engine()

    # 1. RLC circuit simulation
    rlc_res = sim_engine.run_simulation(
        sim_type="circuit",
        parameters={"r": 10.0, "l": 0.001, "c": 0.00001, "vin": 12.0},
        duration=0.005,
    )
    assert rlc_res.success is True
    assert rlc_res.is_physically_consistent is True
    assert "v_c" in rlc_res.trajectories
    assert "i_l" in rlc_res.trajectories

    # 2. Thermal simulation
    therm_res = sim_engine.run_simulation(
        sim_type="thermal",
        parameters={"power": 50.0, "r_th": 1.2, "c_th": 30.0, "t_ambient": 25.0},
        duration=60.0,
    )
    assert therm_res.success is True
    assert therm_res.metrics["steady_state_temp_C"] == 25.0 + 50.0 * 1.2
    assert therm_res.metrics["t_steady_state"] == 4.0 * (1.2 * 30.0)

    # 3. Orbital propagation (LEO 400 km)
    orb_res = sim_engine.run_simulation(
        sim_type="orbital",
        parameters={"alt_km": 400.0},
        duration=2.0,
    )
    assert orb_res.success is True
    # Circular orbital velocity at 400 km is ~7670 m/s
    assert abs(orb_res.metrics["v_circ_mps"] - 7670.0) < 50.0

    # 4. Monte Carlo uncertainty sampling
    mc_res = sim_engine.run_simulation(
        sim_type="monte_carlo",
        parameters={"mean": 100.0, "std": 10.0, "num_trials": 5000, "seed": 42},
    )
    assert mc_res.success is True
    metrics = mc_res.metrics
    assert abs(metrics["mean"] - 100.0) < 1.0
    assert abs(metrics["std_dev"] - 10.0) < 1.0
    assert metrics["percentiles"]["P50"] > metrics["percentiles"]["P10"]


# ============================================================================
# Category E: Digital Twin Architecture (Phase 14.6)
# ============================================================================

def test_07_digital_twin_telemetry_drift_and_calibration():
    registry = get_digital_twin_registry()
    twin = DigitalTwin(name="BatteryPackTwin", system_type="energy_storage")

    # Set parameters and states
    twin.set_parameter("root", "internal_resistance", 0.05)
    twin.set_state("root", "cell_temperature", 35.0, unit="degC", min_limit=0.0, max_limit=60.0)
    twin.set_state("root", "state_of_charge", 0.85, unit="ratio", min_limit=0.1, max_limit=1.0)
    registry.register(twin)

    # Ingest measured telemetry and simulated records
    t_now = 1000.0
    twin.record_simulated_telemetry(timestamp=t_now, variable="cell_temperature", value=36.0)
    twin.ingest_measured_telemetry([
        {"timestamp": t_now, "variable": "cell_temperature", "value": 45.0}  # 25% discrepancy
    ])

    discrepancies = twin.detect_discrepancies("cell_temperature", relative_tolerance=0.15)
    assert len(discrepancies) == 1
    assert discrepancies[0].is_anomaly is True

    # Parameter calibration via curve_fit
    # True relation: V = 12.0 - I * R_true where R_true = 0.08
    def v_model(i_current, r_val):
        return 12.0 - i_current * r_val

    i_data = [10.0, 20.0, 30.0, 40.0, 50.0]
    v_measured = [12.0 - i * 0.08 for i in i_data]

    cal_res = twin.calibrate_parameter(
        component_path="root",
        param_name="internal_resistance",
        fit_fn=v_model,
        time_series=i_data,
        measured_values=v_measured,
        initial_guess=0.02,
    )
    assert cal_res["converged"] is True
    assert abs(cal_res["calibrated_value"] - 0.08) < 1e-4

    # Health evaluation
    health = twin.compute_health_index()
    assert health.health_index > 0.0
    assert health.status in ("NOMINAL", "DEGRADED")


# ============================================================================
# Category F: Predictive Intelligence (Phase 14.7)
# ============================================================================

def test_08_predictive_intelligence_forecasting_and_metrics():
    engine = get_predictive_engine()

    # Linear series: y = 2.0 * t + 5.0 with small noise
    t_hist = list(range(20))
    y_hist = [2.0 * t + 5.0 for t in t_hist]

    res = engine.forecast(
        values=y_hist,
        horizon=5,
        target_name="throughput",
        model_type="linear",
    )
    assert res.target_variable == "throughput"
    assert len(res.predictions) == 5
    # Next step (t=20) should be ~45.0
    assert abs(res.predictions[0].point_estimate - 45.0) < 0.1
    assert res.metrics.r_squared > 0.99
    assert res.metrics.mae < 0.01

    # Anomaly detection check
    noisy_series = np.array([10.0, 10.2, 9.8, 10.1, 50.0, 10.0, 9.9])
    anomalies = engine.detect_anomalies(noisy_series)
    assert 4 in anomalies  # index 4 is 50.0


# ============================================================================
# Category G: Scenario Engine & Tornado Sensitivity (Phase 14.8)
# ============================================================================

def test_09_scenario_engine_and_sensitivity_ranking():
    engine = get_scenario_engine()

    # Model: Profit = Revenue(price, units) - Cost(fixed_cost, unit_cost * units)
    def model_fn(params: dict[str, float]) -> dict[str, float]:
        price = params["price"]
        units = params["units"]
        unit_cost = params["unit_cost"]
        fixed_cost = params["fixed_cost"]
        revenue = price * units
        cost = fixed_cost + unit_cost * units
        profit = revenue - cost
        return {"revenue": revenue, "cost": cost, "profit": profit}

    base_params = {
        "price": 100.0,
        "units": 1000.0,
        "unit_cost": 40.0,
        "fixed_cost": 20000.0,
    }

    scenarios = [
        ScenarioDefinition(name="Optimistic", parameter_overrides={"price": 120.0, "units": 1200.0}),
        ScenarioDefinition(name="Pessimistic", parameter_overrides={"price": 85.0, "units": 800.0}),
    ]

    report = engine.evaluate_scenarios(
        base_parameters=base_params,
        scenarios=scenarios,
        model_fn=model_fn,
        target_metric="profit",
    )
    assert len(report.outcomes) == 3  # Base + 2 scenarios
    assert len(report.sensitivities) == 4
    # Top sensitive parameter should be either units or price
    assert report.sensitivities[0].parameter in ("units", "price", "unit_cost")
    assert report.sensitivities[0].delta_metric > 0


# ============================================================================
# Category H: Decision Intelligence & MCDA (Phase 14.9)
# ============================================================================

def test_10_decision_intelligence_wsm_and_topsis():
    engine = get_decision_engine()

    criteria = [
        Criterion(name="performance", weight=0.5, direction="maximize"),
        Criterion(name="cost", weight=0.3, direction="minimize"),
        Criterion(name="reliability", weight=0.2, direction="maximize"),
    ]

    alternatives = [
        AlternativeOption(name="SystemA", scores={"performance": 90.0, "cost": 5000.0, "reliability": 0.99}),
        AlternativeOption(name="SystemB", scores={"performance": 70.0, "cost": 2000.0, "reliability": 0.95}),
        AlternativeOption(name="SystemC", scores={"performance": 40.0, "cost": 6000.0, "reliability": 0.80}),
    ]

    # Weighted Sum Model
    wsm_report = engine.evaluate_wsm(alternatives, criteria)
    assert len(wsm_report.rankings) == 3
    assert wsm_report.best_option in ("SystemA", "SystemB")
    # SystemC is strictly worse than SystemA in performance, cost, and reliability -> SystemC is dominated
    assert "SystemC" not in wsm_report.pareto_frontier

    # TOPSIS Method
    topsis_report = engine.evaluate_topsis(alternatives, criteria)
    assert len(topsis_report.rankings) == 3
    assert topsis_report.rankings[0].score > topsis_report.rankings[-1].score


# ============================================================================
# Category I: Optimization Engine (Phase 14.10)
# ============================================================================

def test_11_optimization_lp_and_knapsack():
    engine = get_optimization_engine()

    # Linear Program:
    # Maximize 3*x1 + 2*x2
    # Subject to:
    #   2*x1 + x2 <= 100
    #   x1 + x2 <= 80
    #   x1, x2 >= 0
    lp_res = engine.solve_linear_program(
        c=[3.0, 2.0],
        variable_names=["x1", "x2"],
        A_ub=[[2.0, 1.0], [1.0, 1.0]],
        b_ub=[100.0, 80.0],
        bounds=[(0, None), (0, None)],
        maximize=True,
    )
    assert lp_res.success is True
    # Optimal corner point: intersection of 2*x1 + x2 = 100 and x1 + x2 = 80 -> x1 = 20, x2 = 60
    # Obj = 3*20 + 2*60 = 180
    assert abs(lp_res.objective_value - 180.0) < 1e-3
    assert abs(lp_res.variables["x1"] - 20.0) < 1e-3
    assert abs(lp_res.variables["x2"] - 60.0) < 1e-3

    # Knapsack Problem
    items = [
        {"name": "Laptop", "weight": 3.0, "value": 1500.0},
        {"name": "Monitor", "weight": 5.0, "value": 800.0},
        {"name": "Battery", "weight": 2.0, "value": 500.0},
    ]
    knap_res = engine.solve_knapsack(items, capacity=5.0)
    assert knap_res.success is True
    # Optimal combination for cap 5: Laptop (3kg, 1500) + Battery (2kg, 500) = 5kg, value 2000
    assert abs(knap_res.objective_value - 2000.0) < 1e-3
    assert knap_res.variables["Laptop"] == 1.0
    assert knap_res.variables["Battery"] == 1.0
    assert knap_res.variables["Monitor"] == 0.0


# ============================================================================
# Category J: Strategic Planning & Critical Path Method (Phase 14.11)
# ============================================================================

def test_12_strategic_planner_cpm_and_bottlenecks():
    planner = get_strategic_planner()

    # Tasks:
    # A (dur=3)
    # B (dur=2, pred=A)
    # C (dur=4, pred=A)
    # D (dur=2, pred=[B, C])
    # Path A -> B -> D duration = 3 + 2 + 2 = 7
    # Path A -> C -> D duration = 3 + 4 + 2 = 9 (Critical Path)
    tasks = [
        PlannedTask(id="A", name="Design", duration=3.0, predecessors=[]),
        PlannedTask(id="B", name="Procurement", duration=2.0, predecessors=["A"]),
        PlannedTask(id="C", name="Prototyping", duration=4.0, predecessors=["A"]),
        PlannedTask(id="D", name="Integration", duration=2.0, predecessors=["B", "C"]),
    ]

    plan = planner.compute_schedule(project_name="Phase14Launch", tasks=tasks)
    assert plan.total_duration == 9.0
    assert plan.critical_path == ["A", "C", "D"]
    assert plan.tasks["B"].total_slack == 2.0  # B has 2 days slack
    assert plan.tasks["C"].is_critical is True
    assert "gantt" in plan.mermaid_gantt


# ============================================================================
# Category K: Action Discovery & Tool Invocation Integration (Phase 14.12)
# ============================================================================

def test_13_action_registry_reasoning_tools_execution():
    actions = discover_actions(Path("actions"))
    assert actions.has("reasoning_tools") is True

    # 1. Execute calculate_units action
    res_units = actions.run("reasoning_tools", {
        "action": "calculate_units",
        "parameters": {"a": "15 m", "op": "+", "b": "35 m"}
    })
    assert "status=done" in res_units
    assert "50 m" in res_units
    assert "magnitude=50.0" in res_units

    # 2. Execute simulate action
    res_sim = actions.run("reasoning_tools", {
        "action": "simulate",
        "parameters": {"type": "circuit", "parameters": {"r": 10.0, "l": 0.001, "c": 0.00001, "vin": 12.0}}
    })
    assert "status=done" in res_sim
    assert "simulation_type=circuit" in res_sim

    # 3. Execute predict action
    res_pred = actions.run("reasoning_tools", {
        "action": "predict",
        "parameters": {"values": [10.0, 20.0, 30.0, 40.0, 50.0], "horizon": 3, "target": "sales"}
    })
    assert "status=done" in res_pred
    assert "target=sales" in res_pred

    # 4. Execute optimize action
    res_opt = actions.run("reasoning_tools", {
        "action": "optimize",
        "parameters": {
            "type": "knapsack",
            "items": [
                {"name": "A", "weight": 2.0, "value": 100.0},
                {"name": "B", "weight": 3.0, "value": 150.0},
            ],
            "capacity": 5.0,
        }
    })
    assert "status=done" in res_opt
    assert "objective=250.0" in res_opt
