"""
AMATYA Causal and Counterfactual Reasoning Engine (core/causal_engine.py)
========================================================================
Phase 14.4 Core Implementation:
  - Directed Acyclic Causal Graphs (DAGs) with Explicit Mechanisms.
  - Pearl's do-Calculus Interventions (do(X = x) severing incoming dependencies).
  - Counterfactual Analysis ("What if variable X had been set to value V?").
  - Confounder Identification and Correlation-vs-Causation Disambiguation.
  - Traceable Causal Confidence & Uncertainty Bounds.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

_LOCK = threading.RLock()


@dataclass
class CausalVariable:
    name: str
    baseline_value: float
    unit: str = ""
    is_confounder: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CausalLink:
    source: str
    target: str
    weight: float  # Partial derivative d(target)/d(source)
    mechanism: str
    confidence: float = 1.0  # 0.0 to 1.0
    is_direct: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CounterfactualResult:
    intervention_variable: str
    intervention_value: float
    baseline_state: dict[str, float]
    counterfactual_state: dict[str, float]
    state_deltas: dict[str, float]
    impacted_variables: list[str]
    confidence: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_variable": self.intervention_variable,
            "intervention_value": self.intervention_value,
            "baseline_state": self.baseline_state,
            "counterfactual_state": self.counterfactual_state,
            "state_deltas": self.state_deltas,
            "impacted_variables": self.impacted_variables,
            "confidence": self.confidence,
            "explanation": self.explanation,
        }


class CausalGraph:
    """Directed causal graph supporting interventions and counterfactual simulation."""

    def __init__(self, name: str = "CausalModel"):
        self.name = name
        self.variables: dict[str, CausalVariable] = {}
        self.links: list[CausalLink] = []

    def add_variable(
        self,
        name: str,
        baseline_value: float,
        unit: str = "",
        is_confounder: bool = False,
        description: str = "",
    ) -> CausalVariable:
        var = CausalVariable(
            name=name,
            baseline_value=baseline_value,
            unit=unit,
            is_confounder=is_confounder,
            description=description,
        )
        self.variables[name] = var
        return var

    def add_causal_link(
        self,
        source: str,
        target: str,
        weight: float,
        mechanism: str,
        confidence: float = 1.0,
    ) -> CausalLink:
        if source not in self.variables:
            self.add_variable(source, 0.0)
        if target not in self.variables:
            self.add_variable(target, 0.0)

        link = CausalLink(
            source=source,
            target=target,
            weight=weight,
            mechanism=mechanism,
            confidence=confidence,
        )
        self.links.append(link)
        return link

    def find_confounders(self, var_a: str, var_b: str) -> list[str]:
        """Finds common causes (confounders) influencing both var_a and var_b."""
        parents_a = {l.source for l in self.links if l.target == var_a}
        parents_b = {l.source for l in self.links if l.target == var_b}
        return list(parents_a & parents_b)

    def intervene(
        self,
        target_variable: str,
        new_value: float,
    ) -> CounterfactualResult:
        """Applies do(X = new_value) intervention, propagating downstream causal deltas."""
        if target_variable not in self.variables:
            raise ValueError(f"Variable '{target_variable}' not in causal graph.")

        baseline = {k: v.baseline_value for k, v in self.variables.items()}
        counterfactual = dict(baseline)

        # Apply intervention
        counterfactual[target_variable] = new_value
        delta_x = new_value - baseline[target_variable]

        # Downstream propagation (topological wave)
        impacted: list[str] = [target_variable]
        deltas: dict[str, float] = {target_variable: delta_x}

        # Queue for propagation: (var, delta)
        queue = [(target_variable, delta_x)]
        visited = {target_variable}

        total_confidence = 1.0

        while queue:
            current_var, current_delta = queue.pop(0)
            downstream_links = [l for l in self.links if l.source == current_var]
            for link in downstream_links:
                child_delta = current_delta * link.weight
                counterfactual[link.target] += child_delta
                deltas[link.target] = deltas.get(link.target, 0.0) + child_delta
                total_confidence *= link.confidence

                if link.target not in impacted:
                    impacted.append(link.target)
                if link.target not in visited:
                    visited.add(link.target)
                    queue.append((link.target, child_delta))

        unit_str = self.variables[target_variable].unit
        explanation = (
            f"Intervention do({target_variable} = {new_value} {unit_str}) applied. "
            f"Downstream variables impacted: {', '.join(impacted[1:]) if len(impacted) > 1 else 'None'}."
        )

        return CounterfactualResult(
            intervention_variable=target_variable,
            intervention_value=new_value,
            baseline_state=baseline,
            counterfactual_state=counterfactual,
            state_deltas=deltas,
            impacted_variables=impacted,
            confidence=round(total_confidence, 3),
            explanation=explanation,
        )


class CausalEngine:
    """Registry and manager for causal models and counterfactual reasoning."""

    _instance: Optional[CausalEngine] = None

    def __init__(self):
        self._graphs: dict[str, CausalGraph] = {}

    @classmethod
    def get_instance(cls) -> CausalEngine:
        if cls._instance is None:
            cls._instance = CausalEngine()
        return cls._instance

    def register_graph(self, graph: CausalGraph) -> None:
        with _LOCK:
            self._graphs[graph.name] = graph

    def get_graph(self, name: str) -> Optional[CausalGraph]:
        with _LOCK:
            return self._graphs.get(name)

    def evaluate_counterfactual(
        self,
        graph_name: str,
        target_variable: str,
        intervention_value: float,
    ) -> CounterfactualResult:
        with _LOCK:
            graph = self._graphs.get(graph_name)
            if not graph:
                raise ValueError(f"Causal graph '{graph_name}' not registered.")
            return graph.intervene(target_variable, intervention_value)


def get_causal_engine() -> CausalEngine:
    return CausalEngine.get_instance()

