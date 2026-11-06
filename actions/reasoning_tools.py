"""
actions/reasoning_tools.py — Advanced Reasoning, Simulation & Decision Intelligence Action Module for AMATYA Phase 14.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from core import outcome
from core.causal_engine import CausalGraph, CausalVariable, get_causal_engine
from core.decision_intelligence import (
    AlternativeOption,
    Criterion,
    get_decision_engine,
)
from core.digital_twin import DigitalTwin, get_digital_twin_registry
from core.optimization_engine import get_optimization_engine
from core.predictive_intelligence import get_predictive_engine
from core.reasoning_engine import (
    ProblemCategory,
    ProblemDefinition,
    get_reasoning_engine,
)
from core.scenario_engine import ScenarioDefinition, get_scenario_engine
from core.scientific_computation import (
    NumericalSolver,
    SymbolicSolver,
    UnitQuantity,
)
from core.simulation_engine import get_simulation_engine
from core.strategic_planner import PlannedTask, get_strategic_planner

logger = logging.getLogger(__name__)

SKILL_METADATA = {
    "name": "reasoning_tools",
    "version": "14.1.0",
    "description": (
        "Advanced reasoning, deterministic scientific computation, physical simulations, "
        "causal counterfactual inference, time-series prediction, MCDA decision intelligence, "
        "constraint optimization, digital twins, and strategic project scheduling for AMATYA."
    ),
    "capabilities": [
        "symbolic_mathematics",
        "numerical_ode_solving",
        "dimensional_analysis",
        "causal_intervention",
        "circuit_simulation",
        "thermal_simulation",
        "orbital_simulation",
        "monte_carlo_sampling",
        "time_series_forecasting",
        "mcda_topsis_decision",
        "linear_nonlinear_optimization",
        "digital_twin_tracking",
        "critical_path_scheduling",
    ],
    "permissions": ["compute", "memory_write"],
    "dependencies": ["numpy", "scipy", "sympy"],
    "supported_actions": [
        "solve_problem",
        "calculate_units",
        "simulate",
        "counterfactual",
        "predict",
        "evaluate_decision",
        "optimize",
        "digital_twin",
        "schedule_project",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "reasoning_tools",
    "description": (
        "Advanced deterministic reasoning, simulation, forecasting, optimization, and decision tools. "
        "Actions: 'solve_problem', 'calculate_units', 'simulate', 'counterfactual', 'predict', "
        "'evaluate_decision', 'optimize', 'digital_twin', 'schedule_project'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "The reasoning action: 'solve_problem', 'calculate_units', 'simulate', "
                    "'counterfactual', 'predict', 'evaluate_decision', 'optimize', "
                    "'digital_twin', 'schedule_project'."
                ),
            },
            "parameters": {
                "type": "OBJECT",
                "description": "JSON object holding arguments specific to the requested reasoning action.",
            },
        },
        "required": ["action"],
    },
}


def execute(parameters: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """Dispatches reasoning actions safely without throwing exceptions."""
    params = parameters or {}
    action = params.get("action", "")
    args = params.get("parameters", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}

    player = kwargs.get("player")

    try:
        if action == "solve_problem":
            return _handle_solve_problem(args, player)
        elif action == "calculate_units":
            return _handle_calculate_units(args, player)
        elif action == "simulate":
            return _handle_simulate(args, player)
        elif action == "counterfactual":
            return _handle_counterfactual(args, player)
        elif action == "predict":
            return _handle_predict(args, player)
        elif action == "evaluate_decision":
            return _handle_evaluate_decision(args, player)
        elif action == "optimize":
            return _handle_optimize(args, player)
        elif action == "digital_twin":
            return _handle_digital_twin(args, player)
        elif action == "schedule_project":
            return _handle_schedule_project(args, player)
        else:
            return outcome.failed(
                action or "reasoning_tools",
                f"Unknown action '{action}'. Supported: {', '.join(SKILL_METADATA['supported_actions'])}"
            )
    except Exception as e:
        logger.exception(f"Error in reasoning_tools action '{action}': {e}")
        return outcome.failed(action or "reasoning_tools", f"Reasoning tool execution failed: {str(e)}")


def _handle_solve_problem(args: Dict[str, Any], player: Any) -> str:
    engine = get_reasoning_engine()
    problem_type = args.get("category", "MATHEMATICAL")
    try:
        cat = ProblemCategory[problem_type.upper()]
    except Exception:
        cat = ProblemCategory.MATHEMATICAL

    prob = ProblemDefinition(
        problem_id=args.get("id", "prob_1"),
        title=args.get("title", "Problem"),
        category=cat,
        objective=args.get("objective", ""),
        givens=args.get("givens", {}),
        unknowns=args.get("unknowns", []),
        assumptions=args.get("assumptions", []),
        constraints=args.get("constraints", []),
        selected_methods=args.get("methods", ["analytical"]),
    )

    # If symbolic equation is provided
    equation = args.get("equation")
    solve_for = args.get("solve_for")
    if equation and solve_for:
        sol = SymbolicSolver.solve_equation(equation, solve_for)
        prob.analytical_steps.append(f"Solved equation {equation} for {solve_for} -> {sol}")

    report = engine.solve_problem(prob)
    if player and hasattr(player, "show_content"):
        player.show_content(f"AMATYA Reasoning: {prob.title}", report.to_markdown())

    return outcome.done(
        "solve_problem",
        status="solved",
        problem_id=prob.problem_id,
        summary=report.conclusions[:150] if report.conclusions else "Problem formulated and analyzed.",
    )


def _handle_calculate_units(args: Dict[str, Any], player: Any) -> str:
    expr_a = args.get("a")
    op = args.get("op", "+")
    expr_b = args.get("b")

    qa = UnitQuantity.parse(expr_a)
    qb = UnitQuantity.parse(expr_b)

    if op == "+":
        res = qa + qb
    elif op == "-":
        res = qa - qb
    elif op == "*":
        res = qa * qb
    elif op == "/":
        res = qa / qb
    else:
        return outcome.failed("calculate_units", f"Unsupported unit operator '{op}'")

    msg = f"{qa} {op} {qb} = {res}"
    if player and hasattr(player, "write_log"):
        player.write_log(f"[Units] {msg}")

    return outcome.done("calculate_units", result=str(res), magnitude=res.magnitude, unit=res.unit_str)


def _handle_simulate(args: Dict[str, Any], player: Any) -> str:
    sim_type = args.get("type", "circuit")
    engine = get_simulation_engine()

    sim_res = engine.run_simulation(
        sim_type=sim_type,
        parameters=args.get("parameters", {}),
        duration=float(args.get("duration", 10.0)),
        step_size=float(args.get("step_size", 0.01)),
        seed=args.get("seed"),
    )

    if player and hasattr(player, "show_content"):
        player.show_content(f"AMATYA Simulation: {sim_type.upper()}", sim_res.summary_markdown)

    return outcome.done(
        "simulate",
        status="simulated",
        simulation_type=sim_type,
        is_physical=sim_res.is_physically_consistent,
        metrics=json.dumps(sim_res.metrics),
    )


def _handle_counterfactual(args: Dict[str, Any], player: Any) -> str:
    engine = get_causal_engine()
    graph_name = args.get("graph", "default")
    target_var = args.get("variable")
    intervention_val = float(args.get("value", 0.0))

    graph = engine.get_graph(graph_name)
    if not graph:
        # Build graph on the fly if spec provided
        graph = CausalGraph(name=graph_name)
        vars_list = args.get("variables", [])
        for v in vars_list:
            graph.add_variable(name=v["name"], baseline_value=float(v.get("value", 0.0)), unit=v.get("unit", ""))
        links = args.get("links", [])
        for l in links:
            graph.add_causal_link(
                source=l["source"],
                target=l["target"],
                weight=float(l.get("weight", 1.0)),
                mechanism=l.get("mechanism", "direct"),
            )
        engine.register_graph(graph)

    res = engine.evaluate_counterfactual(graph_name, target_var, intervention_val)
    if player and hasattr(player, "show_content"):
        player.show_content(f"AMATYA Counterfactual: do({target_var}={intervention_val})", res.explanation)

    return outcome.done(
        "counterfactual",
        status="counterfactual_evaluated",
        target=target_var,
        intervention=intervention_val,
        deltas=json.dumps(res.state_deltas),
    )


def _handle_predict(args: Dict[str, Any], player: Any) -> str:
    engine = get_predictive_engine()
    values = [float(v) for v in args.get("values", [])]
    horizon = int(args.get("horizon", 5))
    target_name = args.get("target", "metric")
    model_type = args.get("model", "auto")

    res = engine.forecast(
        values=values,
        horizon=horizon,
        target_name=target_name,
        model_type=model_type,
    )

    pred_summary = [p.point_estimate for p in res.predictions]
    if player and hasattr(player, "write_log"):
        player.write_log(f"[Forecast] {target_name} ({res.model_name}) -> {pred_summary}")

    return outcome.done(
        "predict",
        status="predicted",
        model=res.model_name,
        target=target_name,
        predictions=json.dumps(pred_summary),
        rmse=res.metrics.rmse,
        r2=res.metrics.r_squared,
    )


def _handle_evaluate_decision(args: Dict[str, Any], player: Any) -> str:
    engine = get_decision_engine()
    method = args.get("method", "wsm").lower()

    crit_data = args.get("criteria", [])
    criteria = [
        Criterion(name=c["name"], weight=float(c.get("weight", 1.0)), direction=c.get("direction", "maximize"))
        for c in crit_data
    ]

    alt_data = args.get("alternatives", [])
    alternatives = [
        AlternativeOption(name=a["name"], scores={k: float(v) for k, v in a.get("scores", {}).items()})
        for a in alt_data
    ]

    if method == "topsis":
        report = engine.evaluate_topsis(alternatives, criteria)
    else:
        report = engine.evaluate_wsm(alternatives, criteria)

    if player and hasattr(player, "show_content"):
        player.show_content("AMATYA Decision Analysis", report.summary_markdown)

    return outcome.done(
        "evaluate_decision",
        status="evaluated",
        method=report.method,
        best_option=report.best_option,
        pareto_frontier=",".join(report.pareto_frontier),
    )


def _handle_optimize(args: Dict[str, Any], player: Any) -> str:
    engine = get_optimization_engine()
    prob_type = args.get("type", "linear").lower()

    if prob_type == "linear":
        c = args.get("c", [])
        var_names = args.get("variables", [f"x{i}" for i in range(len(c))])
        A_ub = args.get("A_ub")
        b_ub = args.get("b_ub")
        A_eq = args.get("A_eq")
        b_eq = args.get("b_eq")
        bounds = args.get("bounds")
        maximize = bool(args.get("maximize", False))
        res = engine.solve_linear_program(
            c=c,
            variable_names=var_names,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=bounds,
            maximize=maximize,
        )
    elif prob_type == "knapsack":
        items = args.get("items", [])
        capacity = float(args.get("capacity", 0.0))
        res = engine.solve_knapsack(items, capacity)
    else:
        return outcome.failed("optimize", f"Unsupported optimization problem type '{prob_type}'")

    if player and hasattr(player, "show_content"):
        player.show_content("AMATYA Optimization", res.summary_markdown)

    return outcome.done(
        "optimize",
        status="optimized",
        success=res.success,
        objective=res.objective_value,
        variables=json.dumps(res.variables),
    )


def _handle_digital_twin(args: Dict[str, Any], player: Any) -> str:
    registry = get_digital_twin_registry()
    sub_action = args.get("sub_action", "create")
    name = args.get("name", "system_twin")

    if sub_action == "create":
        twin = DigitalTwin(name=name, system_type=args.get("system_type", "generic"))
        params = args.get("parameters", {})
        for k, v in params.items():
            twin.set_parameter("root", k, float(v))
        registry.register(twin)
        return outcome.done("digital_twin", status="created", name=name)

    twin = registry.get(name)
    if not twin:
        return outcome.failed("digital_twin", f"Digital Twin '{name}' not found.")

    if sub_action == "telemetry":
        records = args.get("records", [])
        ingested = twin.ingest_measured_telemetry(records)
        return outcome.done("digital_twin", status="telemetry_ingested", count=ingested)
    elif sub_action == "health":
        health = twin.compute_health_index()
        return outcome.done("digital_twin", status="health_evaluated", health_index=health.health_index, health_status=health.status)
    elif sub_action == "discrepancies":
        var = args.get("variable", "")
        tol = float(args.get("tolerance", 0.15))
        discrepancies = twin.detect_discrepancies(var, tol)
        return outcome.done(
            "digital_twin",
            status="discrepancies_checked",
            count=len(discrepancies),
            anomalies=sum(1 for d in discrepancies if d.is_anomaly),
        )
    else:
        return outcome.failed("digital_twin", f"Unknown digital_twin sub_action '{sub_action}'")


def _handle_schedule_project(args: Dict[str, Any], player: Any) -> str:
    planner = get_strategic_planner()
    proj_name = args.get("project_name", "Project")
    task_specs = args.get("tasks", [])
    tasks = [
        PlannedTask(
            id=t["id"],
            name=t.get("name", t["id"]),
            duration=float(t.get("duration", 1.0)),
            predecessors=t.get("predecessors", []),
            resource_demands={k: float(v) for k, v in t.get("resources", {}).items()},
        )
        for t in task_specs
    ]
    res_caps = {k: float(v) for k, v in args.get("resource_capacities", {}).items()}

    plan = planner.compute_schedule(proj_name, tasks, res_caps)
    if player and hasattr(player, "show_content"):
        player.show_content(f"AMATYA Schedule: {proj_name}", plan.summary_markdown)

    return outcome.done(
        "schedule_project",
        status="scheduled",
        project=proj_name,
        duration=plan.total_duration,
        critical_path=" -> ".join(plan.critical_path),
        bottlenecks=len(plan.bottlenecks),
    )
