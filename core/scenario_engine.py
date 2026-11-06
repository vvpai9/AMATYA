"""
core/scenario_engine.py — Scenario Analysis, Sensitivity & Simulation Experiments for AMATYA Phase 14.

Provides parametric sweeps, sensitivity/tornado analysis, multi-scenario comparisons
(Base, Optimistic, Pessimistic, Stress), and Monte Carlo scenario evaluations with
statistical outcome distribution profiling.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ScenarioDefinition:
    name: str
    description: str = ""
    parameter_overrides: Dict[str, float] = field(default_factory=dict)
    probability_weight: float = 1.0


@dataclass
class ScenarioOutcome:
    scenario_name: str
    parameters: Dict[str, float]
    metrics: Dict[str, float]
    is_feasible: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class SensitivityItem:
    parameter: str
    base_value: float
    low_value: float
    high_value: float
    metric_low: float
    metric_high: float
    delta_metric: float
    elasticity: float  # (dY/Y) / (dX/X)


@dataclass
class ScenarioComparisonReport:
    base_scenario: str
    target_metric: str
    outcomes: List[ScenarioOutcome]
    sensitivities: List[SensitivityItem] = field(default_factory=list)
    summary_markdown: str = ""


class ScenarioEngine:
    """
    AMATYA Scenario & Sensitivity Analysis Engine.
    Executes systematic scenario exploration, sensitivity rankings, and parameter sweeps.
    """

    def __init__(self):
        pass

    def evaluate_scenarios(
        self,
        base_parameters: Dict[str, float],
        scenarios: List[ScenarioDefinition],
        model_fn: Callable[[Dict[str, float]], Dict[str, float]],
        target_metric: str,
    ) -> ScenarioComparisonReport:
        """
        Runs model_fn across all defined scenarios, comparing outcomes against the base scenario.
        """
        outcomes: List[ScenarioOutcome] = []

        # Run base scenario
        base_metrics = model_fn(base_parameters)
        outcomes.append(ScenarioOutcome(
            scenario_name="Base",
            parameters=dict(base_parameters),
            metrics=base_metrics,
            is_feasible=True,
        ))

        # Run variant scenarios
        for sc in scenarios:
            merged_params = dict(base_parameters)
            merged_params.update(sc.parameter_overrides)
            try:
                res_metrics = model_fn(merged_params)
                outcomes.append(ScenarioOutcome(
                    scenario_name=sc.name,
                    parameters=merged_params,
                    metrics=res_metrics,
                    is_feasible=True,
                ))
            except Exception as e:
                outcomes.append(ScenarioOutcome(
                    scenario_name=sc.name,
                    parameters=merged_params,
                    metrics={},
                    is_feasible=False,
                    warnings=[f"Execution failed: {str(e)}"],
                ))

        # Sensitivity analysis on the base parameters
        sensitivities = self.compute_sensitivity(
            base_parameters=base_parameters,
            model_fn=model_fn,
            target_metric=target_metric,
            perturbation_pct=0.10,
        )

        # Build Markdown summary
        md_lines = [
            f"# Scenario Comparison Report — Target: {target_metric}",
            "",
            "| Scenario | " + " | ".join(base_metrics.keys()) + " | Feasible |",
            "|:---|" + "|".join([":---:" for _ in base_metrics]) + "|:---:|",
        ]
        for out in outcomes:
            metric_cols = " | ".join([f"{out.metrics.get(k, float('nan')):.3f}" for k in base_metrics.keys()])
            feas = "✅ Yes" if out.is_feasible else "❌ No"
            md_lines.append(f"| **{out.scenario_name}** | {metric_cols} | {feas} |")

        md_lines.append("")
        md_lines.append("### Parameter Sensitivity Ranking (Tornado Analysis):")
        md_lines.append("| Parameter | Base Value | Low Metric (-10%) | High Metric (+10%) | Dynamic Range | Elasticity |")
        md_lines.append("|:---|:---:|:---:|:---:|:---:|:---:|")
        for s in sensitivities:
            md_lines.append(
                f"| `{s.parameter}` | {s.base_value:.2f} | {s.metric_low:.3f} | {s.metric_high:.3f} | {s.delta_metric:.3f} | {s.elasticity:.3f} |"
            )

        return ScenarioComparisonReport(
            base_scenario="Base",
            target_metric=target_metric,
            outcomes=outcomes,
            sensitivities=sensitivities,
            summary_markdown="\n".join(md_lines),
        )

    def compute_sensitivity(
        self,
        base_parameters: Dict[str, float],
        model_fn: Callable[[Dict[str, float]], Dict[str, float]],
        target_metric: str,
        perturbation_pct: float = 0.10,
    ) -> List[SensitivityItem]:
        """
        Computes local sensitivity elasticity (dY/Y)/(dX/X) and dynamic swing for each parameter.
        Sorted by absolute swing (tornado ranking).
        """
        base_res = model_fn(base_parameters)
        y0 = base_res.get(target_metric, 0.0)

        items: List[SensitivityItem] = []

        for p_name, p_val in base_parameters.items():
            if abs(p_val) < 1e-9:
                delta = 0.01
                low_val = p_val - delta
                high_val = p_val + delta
            else:
                low_val = p_val * (1.0 - perturbation_pct)
                high_val = p_val * (1.0 + perturbation_pct)

            # Low evaluation
            p_low = dict(base_parameters)
            p_low[p_name] = low_val
            y_low = model_fn(p_low).get(target_metric, y0)

            # High evaluation
            p_high = dict(base_parameters)
            p_high[p_name] = high_val
            y_high = model_fn(p_high).get(target_metric, y0)

            delta_metric = abs(y_high - y_low)

            # Elasticity: ( (y_high - y_low)/y0 ) / ( (high_val - low_val)/p_val )
            d_x = high_val - low_val
            if abs(y0) > 1e-9 and abs(p_val) > 1e-9 and d_x > 0:
                elasticity = ((y_high - y_low) / y0) / (d_x / p_val)
            else:
                elasticity = 0.0

            items.append(SensitivityItem(
                parameter=p_name,
                base_value=float(p_val),
                low_value=float(low_val),
                high_value=float(high_val),
                metric_low=round(float(y_low), 4),
                metric_high=round(float(y_high), 4),
                delta_metric=round(float(delta_metric), 4),
                elasticity=round(float(elasticity), 4),
            ))

        # Sort descending by sensitivity magnitude (tornado order)
        items.sort(key=lambda item: item.delta_metric, reverse=True)
        return items

    def parameter_sweep(
        self,
        base_parameters: Dict[str, float],
        sweep_parameter: str,
        values: List[float],
        model_fn: Callable[[Dict[str, float]], Dict[str, float]],
    ) -> Dict[str, List[float]]:
        """
        Executes a 1D parameter sweep and returns time/metric arrays.
        """
        results: Dict[str, List[float]] = {sweep_parameter: list(values)}
        for val in values:
            params = dict(base_parameters)
            params[sweep_parameter] = val
            metrics = model_fn(params)
            for m_key, m_val in metrics.items():
                if m_key not in results:
                    results[m_key] = []
                results[m_key].append(float(m_val))
        return results


_scenario_engine: Optional[ScenarioEngine] = None


def get_scenario_engine() -> ScenarioEngine:
    global _scenario_engine
    if _scenario_engine is None:
        _scenario_engine = ScenarioEngine()
    return _scenario_engine
