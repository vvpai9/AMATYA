"""
core/digital_twin.py — Digital Twin Architecture for AMATYA Phase 14.

Provides deterministic component hierarchies, state variable monitoring,
telemetry stream ingestion (measured vs. simulated), discrepancy/drift detection,
parameter calibration via SciPy optimization, and state-of-health degradation indexing.
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import curve_fit, minimize

logger = logging.getLogger(__name__)


@dataclass
class StateVariable:
    name: str
    unit: str
    value: float
    min_limit: Optional[float] = None
    max_limit: Optional[float] = None
    description: str = ""

    def is_out_of_bounds(self) -> bool:
        if self.min_limit is not None and self.value < self.min_limit:
            return True
        if self.max_limit is not None and self.value > self.max_limit:
            return True
        return False


@dataclass
class TelemetryRecord:
    timestamp: float
    variable: str
    value: float
    source: str  # "measured" | "simulated"


@dataclass
class Discrepancy:
    variable: str
    timestamp: float
    measured_value: float
    simulated_value: float
    residual: float
    relative_error: float
    is_anomaly: bool
    description: str


@dataclass
class HealthStatus:
    system_name: str
    health_index: float  # 0.0 (failed) to 1.0 (pristine)
    status: str  # "NOMINAL", "DEGRADED", "CRITICAL"
    anomalies: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


class TwinComponent:
    """A hierarchical subsystem or physical component in a digital twin."""

    def __init__(self, name: str, component_type: str = "generic"):
        self.name = name
        self.component_type = component_type
        self.parameters: Dict[str, float] = {}
        self.states: Dict[str, StateVariable] = {}
        self.subcomponents: Dict[str, TwinComponent] = {}
        self.metadata: Dict[str, Any] = {}

    def set_parameter(self, name: str, value: float) -> None:
        self.parameters[name] = float(value)

    def get_parameter(self, name: str, default: float = 0.0) -> float:
        return self.parameters.get(name, default)

    def set_state(self, name: str, value: float, unit: str = "", min_limit: Optional[float] = None, max_limit: Optional[float] = None) -> None:
        self.states[name] = StateVariable(
            name=name,
            unit=unit,
            value=float(value),
            min_limit=min_limit,
            max_limit=max_limit
        )

    def get_state(self, name: str) -> Optional[StateVariable]:
        return self.states.get(name)

    def add_subcomponent(self, component: TwinComponent) -> None:
        self.subcomponents[component.name] = component

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "parameters": self.parameters,
            "states": {k: asdict(v) for k, v in self.states.items()},
            "subcomponents": {k: v.to_dict() for k, v in self.subcomponents.items()},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TwinComponent:
        comp = cls(name=data["name"], component_type=data.get("component_type", "generic"))
        comp.parameters = dict(data.get("parameters", {}))
        for k, v in data.get("states", {}).items():
            comp.states[k] = StateVariable(**v)
        for k, v in data.get("subcomponents", {}).items():
            comp.subcomponents[k] = cls.from_dict(v)
        comp.metadata = dict(data.get("metadata", {}))
        return comp


class DigitalTwin:
    """
    AMATYA Digital Twin Model.
    Maintains synchronized state between physical telemetry and physical/mathematical model.
    """

    def __init__(self, name: str, system_type: str = "generic", version: str = "1.0.0"):
        self.name = name
        self.system_type = system_type
        self.version = version
        self.root = TwinComponent(name="root", component_type=system_type)
        self.measured_telemetry: List[TelemetryRecord] = []
        self.simulated_telemetry: List[TelemetryRecord] = []
        self.calibration_history: List[Dict[str, Any]] = []

    def set_parameter(self, component_path: str, param_name: str, value: float) -> None:
        comp = self._find_component(component_path)
        if comp:
            comp.set_parameter(param_name, value)

    def get_parameter(self, component_path: str, param_name: str, default: float = 0.0) -> float:
        comp = self._find_component(component_path)
        return comp.get_parameter(param_name, default) if comp else default

    def set_state(self, component_path: str, state_name: str, value: float, unit: str = "", min_limit: Optional[float] = None, max_limit: Optional[float] = None) -> None:
        comp = self._find_component(component_path)
        if comp:
            comp.set_state(state_name, value, unit=unit, min_limit=min_limit, max_limit=max_limit)

    def get_state(self, component_path: str, state_name: str) -> Optional[StateVariable]:
        comp = self._find_component(component_path)
        return comp.get_state(state_name) if comp else None

    def _find_component(self, path: str) -> Optional[TwinComponent]:
        if not path or path == "root":
            return self.root
        parts = path.strip("/").split("/")
        curr = self.root
        for p in parts:
            if p in curr.subcomponents:
                curr = curr.subcomponents[p]
            else:
                new_comp = TwinComponent(name=p)
                curr.add_subcomponent(new_comp)
                curr = new_comp
        return curr

    def ingest_measured_telemetry(self, records: List[Dict[str, Any]]) -> int:
        """Ingests measured physical telemetry timestamped records."""
        count = 0
        for r in records:
            ts = float(r.get("timestamp", time.time()))
            var = str(r["variable"])
            val = float(r["value"])
            self.measured_telemetry.append(TelemetryRecord(
                timestamp=ts,
                variable=var,
                value=val,
                source="measured"
            ))
            count += 1
        return count

    def record_simulated_telemetry(self, timestamp: float, variable: str, value: float) -> None:
        self.simulated_telemetry.append(TelemetryRecord(
            timestamp=float(timestamp),
            variable=str(variable),
            value=float(value),
            source="simulated"
        ))

    def detect_discrepancies(self, variable: str, relative_tolerance: float = 0.15) -> List[Discrepancy]:
        """
        Compares measured vs simulated telemetry streams for a given variable.
        Detects anomalies and drift.
        """
        meas = [r for r in self.measured_telemetry if r.variable == variable]
        sim = [r for r in self.simulated_telemetry if r.variable == variable]
        if not meas or not sim:
            return []

        # Map simulated records by closest timestamp
        sim_times = np.array([r.timestamp for r in sim])
        sim_vals = np.array([r.value for r in sim])

        discrepancies: List[Discrepancy] = []
        for m in meas:
            idx = np.argmin(np.abs(sim_times - m.timestamp))
            s_val = sim_vals[idx]
            m_val = m.value
            residual = m_val - s_val
            denom = abs(s_val) if abs(s_val) > 1e-9 else (abs(m_val) if abs(m_val) > 1e-9 else 1.0)
            rel_err = abs(residual) / denom
            is_anomaly = bool(rel_err > relative_tolerance)
            discrepancies.append(Discrepancy(
                variable=variable,
                timestamp=m.timestamp,
                measured_value=m_val,
                simulated_value=float(s_val),
                residual=float(residual),
                relative_error=float(rel_err),
                is_anomaly=is_anomaly,
                description=(
                    f"Drift anomaly: {rel_err*100:.1f}% divergence (meas={m_val:.3f}, sim={s_val:.3f})"
                    if is_anomaly else "Nominal agreement"
                )
            ))
        return discrepancies

    def calibrate_parameter(
        self,
        component_path: str,
        param_name: str,
        fit_fn: Callable[[np.ndarray, float], np.ndarray],
        time_series: List[float],
        measured_values: List[float],
        initial_guess: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Calibrates a physical model parameter against measured telemetry data using SciPy non-linear curve fitting.
        """
        x_data = np.array(time_series, dtype=float)
        y_data = np.array(measured_values, dtype=float)

        try:
            popt, pcov = curve_fit(fit_fn, x_data, y_data, p0=[initial_guess])
            new_val = float(popt[0])
            pred_before = fit_fn(x_data, initial_guess)
            pred_after = fit_fn(x_data, new_val)

            residual_before = float(np.mean((y_data - pred_before) ** 2))
            residual_after = float(np.mean((y_data - pred_after) ** 2))

            self.set_parameter(component_path, param_name, new_val)

            record = {
                "timestamp": time.time(),
                "component": component_path,
                "parameter": param_name,
                "old_value": initial_guess,
                "calibrated_value": new_val,
                "mse_before": residual_before,
                "mse_after": residual_after,
                "converged": True,
            }
            self.calibration_history.append(record)
            return record
        except Exception as e:
            logger.error(f"Parameter calibration failed: {e}")
            return {
                "timestamp": time.time(),
                "component": component_path,
                "parameter": param_name,
                "error": str(e),
                "converged": False,
            }

    def compute_health_index(self) -> HealthStatus:
        """
        Evaluates state of health across all components and state variables.
        Returns health index (0.0 to 1.0) and diagnostics.
        """
        anomalies: List[str] = []
        comp_scores: Dict[str, float] = {}

        def check_comp(comp: TwinComponent) -> float:
            score = 1.0
            for name, state in comp.states.items():
                if state.is_out_of_bounds():
                    score -= 0.3
                    anomalies.append(f"{comp.name}.{name} value {state.value} out of bounds [{state.min_limit}, {state.max_limit}]")
                elif state.min_limit is not None and state.max_limit is not None:
                    # Check if near boundary (within 10% of limits)
                    span = state.max_limit - state.min_limit
                    if span > 0:
                        margin = min(state.value - state.min_limit, state.max_limit - state.value)
                        if margin < 0.1 * span:
                            score -= 0.1
                            anomalies.append(f"{comp.name}.{name} operating near limit margin ({margin:.2f})")

            for sub_name, sub in comp.subcomponents.items():
                sub_score = check_comp(sub)
                score = min(score, sub_score)
            return max(0.0, score)

        overall_score = check_comp(self.root)
        comp_scores[self.root.name] = overall_score

        if overall_score >= 0.85:
            status = "NOMINAL"
        elif overall_score >= 0.5:
            status = "DEGRADED"
        else:
            status = "CRITICAL"

        recommendations = []
        if anomalies:
            recommendations.append(f"Investigate {len(anomalies)} anomalies detected across components.")
        if status == "CRITICAL":
            recommendations.append("Immediate inspection/throttling required to prevent hardware failure.")

        return HealthStatus(
            system_name=self.name,
            health_index=round(overall_score, 3),
            status=status,
            anomalies=anomalies,
            component_scores=comp_scores,
            recommendations=recommendations,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "system_type": self.system_type,
            "version": self.version,
            "root": self.root.to_dict(),
            "measured_count": len(self.measured_telemetry),
            "simulated_count": len(self.simulated_telemetry),
            "calibration_history": self.calibration_history,
        }

    def save(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, filepath: Path) -> DigitalTwin:
        data = json.loads(filepath.read_text())
        twin = cls(name=data["name"], system_type=data.get("system_type", "generic"), version=data.get("version", "1.0.0"))
        twin.root = TwinComponent.from_dict(data["root"])
        twin.calibration_history = data.get("calibration_history", [])
        return twin


class DigitalTwinRegistry:
    """Registry managing active digital twins."""

    _instance: Optional[DigitalTwinRegistry] = None

    def __init__(self):
        self._twins: Dict[str, DigitalTwin] = {}

    @classmethod
    def get_instance(cls) -> DigitalTwinRegistry:
        if cls._instance is None:
            cls._instance = DigitalTwinRegistry()
        return cls._instance

    def register(self, twin: DigitalTwin) -> None:
        self._twins[twin.name] = twin

    def get(self, name: str) -> Optional[DigitalTwin]:
        return self._twins.get(name)

    def list_twins(self) -> List[str]:
        return list(self._twins.keys())

    def remove(self, name: str) -> bool:
        return self._twins.pop(name, None) is not None


def get_digital_twin_registry() -> DigitalTwinRegistry:
    return DigitalTwinRegistry.get_instance()
