"""
core/decision_intelligence.py — Multi-Criteria Decision Analysis & Decision Intelligence for AMATYA Phase 14.

Provides deterministic decision matrix evaluation, Weighted Sum Model (WSM),
TOPSIS (Technique for Order Preference by Similarity to Ideal Solution),
Pareto frontier identification (multi-objective non-dominated sorting),
and risk-adjusted utility evaluation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Criterion:
    name: str
    weight: float
    direction: str = "maximize"  # "maximize" | "minimize"
    description: str = ""


@dataclass
class AlternativeOption:
    name: str
    scores: Dict[str, float]
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedOption:
    rank: int
    name: str
    score: float
    is_pareto_optimal: bool
    details: Dict[str, float] = field(default_factory=dict)


@dataclass
class DecisionReport:
    method: str
    criteria: List[Criterion]
    rankings: List[RankedOption]
    pareto_frontier: List[str]
    best_option: str
    summary_markdown: str


class DecisionEngine:
    """
    AMATYA Decision Intelligence Engine.
    Executes MCDA, TOPSIS, and Pareto dominance analysis.
    """

    def __init__(self):
        pass

    @staticmethod
    def identify_pareto_frontier(
        alternatives: List[AlternativeOption],
        criteria: List[Criterion]
    ) -> List[str]:
        """
        Finds the set of non-dominated (Pareto-optimal) alternatives.
        An alternative A dominates B if A is at least as good as B in all criteria
        and strictly better in at least one criterion.
        """
        names = [alt.name for alt in alternatives]
        n = len(alternatives)
        if n == 0:
            return []
        if n == 1:
            return [names[0]]

        # Standardize so that all criteria are to be maximized
        norm_matrix = np.zeros((n, len(criteria)))
        for j, crit in enumerate(criteria):
            vals = [alt.scores.get(crit.name, 0.0) for alt in alternatives]
            mult = 1.0 if crit.direction == "maximize" else -1.0
            norm_matrix[:, j] = [v * mult for v in vals]

        is_dominated = [False] * n
        for i in range(n):
            for k in range(n):
                if i == k:
                    continue
                # Check if k dominates i
                all_geq = np.all(norm_matrix[k, :] >= norm_matrix[i, :])
                any_gt = np.any(norm_matrix[k, :] > norm_matrix[i, :])
                if all_geq and any_gt:
                    is_dominated[i] = True
                    break

        frontier = [names[i] for i in range(n) if not is_dominated[i]]
        return frontier

    def evaluate_wsm(
        self,
        alternatives: List[AlternativeOption],
        criteria: List[Criterion]
    ) -> DecisionReport:
        """
        Weighted Sum Model (WSM) evaluation.
        Linear min-max normalization followed by dot product with normalized weights.
        """
        if not alternatives or not criteria:
            raise ValueError("Alternatives and criteria must not be empty.")

        n_alt = len(alternatives)
        n_crit = len(criteria)

        # Normalize criteria weights so they sum to 1.0
        raw_weights = np.array([max(0.0, c.weight) for c in criteria])
        w_sum = np.sum(raw_weights)
        norm_weights = raw_weights / w_sum if w_sum > 0 else np.ones(n_crit) / n_crit

        # Build raw matrix
        matrix = np.zeros((n_alt, n_crit))
        for i, alt in enumerate(alternatives):
            for j, c in enumerate(criteria):
                matrix[i, j] = alt.scores.get(c.name, 0.0)

        # Min-Max Normalization
        norm_matrix = np.zeros_like(matrix)
        for j, c in enumerate(criteria):
            col = matrix[:, j]
            min_val = np.min(col)
            max_val = np.max(col)
            span = max_val - min_val

            if span < 1e-9:
                norm_matrix[:, j] = 1.0
            else:
                if c.direction == "maximize":
                    norm_matrix[:, j] = (col - min_val) / span
                else:
                    norm_matrix[:, j] = (max_val - col) / span

        # Compute aggregate scores
        total_scores = np.dot(norm_matrix, norm_weights)

        # Identify Pareto frontier
        pareto_set = set(self.identify_pareto_frontier(alternatives, criteria))

        # Rank alternatives descending
        sort_order = np.argsort(-total_scores)

        rankings: List[RankedOption] = []
        for rank_idx, alt_idx in enumerate(sort_order):
            alt_name = alternatives[alt_idx].name
            score = float(total_scores[alt_idx])
            details = {c.name: float(matrix[alt_idx, j]) for j, c in enumerate(criteria)}
            rankings.append(RankedOption(
                rank=rank_idx + 1,
                name=alt_name,
                score=round(score, 4),
                is_pareto_optimal=(alt_name in pareto_set),
                details=details,
            ))

        best_opt = rankings[0].name if rankings else ""

        # Build Markdown summary
        md_lines = [
            "# Decision Intelligence Report (Weighted Sum Model)",
            "",
            f"**Recommended Option:** `{best_opt}` (Score: {rankings[0].score:.4f})",
            "",
            "### Criteria Weights:",
        ]
        for c, nw in zip(criteria, norm_weights):
            md_lines.append(f"- **{c.name}**: weight = {nw*100:.1f}%, direction = `{c.direction}`")

        md_lines.extend([
            "",
            "### Alternative Rankings:",
            "| Rank | Option | Total Score (0-1) | Pareto Optimal | " + " | ".join([c.name for c in criteria]) + " |",
            "|:---:|:---|:---:|:---:| " + " | ".join([":---:" for _ in criteria]) + " |",
        ])
        for r in rankings:
            crit_vals = " | ".join([f"{r.details.get(c.name, 0.0):.2f}" for c in criteria])
            pareto_str = "⭐ Yes" if r.is_pareto_optimal else "No"
            md_lines.append(f"| {r.rank} | **{r.name}** | {r.score:.4f} | {pareto_str} | {crit_vals} |")

        return DecisionReport(
            method="Weighted Sum Model (WSM)",
            criteria=criteria,
            rankings=rankings,
            pareto_frontier=list(pareto_set),
            best_option=best_opt,
            summary_markdown="\n".join(md_lines),
        )

    def evaluate_topsis(
        self,
        alternatives: List[AlternativeOption],
        criteria: List[Criterion]
    ) -> DecisionReport:
        """
        TOPSIS (Technique for Order Preference by Similarity to Ideal Solution).
        Calculates geometric distance to positive and negative ideal solutions.
        """
        if not alternatives or not criteria:
            raise ValueError("Alternatives and criteria must not be empty.")

        n_alt = len(alternatives)
        n_crit = len(criteria)

        # Normalize weights
        raw_weights = np.array([max(0.0, c.weight) for c in criteria])
        w_sum = np.sum(raw_weights)
        norm_weights = raw_weights / w_sum if w_sum > 0 else np.ones(n_crit) / n_crit

        # Raw matrix
        matrix = np.zeros((n_alt, n_crit))
        for i, alt in enumerate(alternatives):
            for j, c in enumerate(criteria):
                matrix[i, j] = alt.scores.get(c.name, 0.0)

        # Vector normalization
        denom = np.sqrt(np.sum(matrix ** 2, axis=0))
        denom[denom < 1e-9] = 1.0
        v_matrix = matrix / denom

        # Weighted normalized decision matrix
        w_matrix = v_matrix * norm_weights

        # Determine ideal positive (A+) and ideal negative (A-)
        ideal_pos = np.zeros(n_crit)
        ideal_neg = np.zeros(n_crit)

        for j, c in enumerate(criteria):
            col = w_matrix[:, j]
            if c.direction == "maximize":
                ideal_pos[j] = np.max(col)
                ideal_neg[j] = np.min(col)
            else:
                ideal_pos[j] = np.min(col)
                ideal_neg[j] = np.max(col)

        # Calculate Euclidean distances
        d_pos = np.sqrt(np.sum((w_matrix - ideal_pos) ** 2, axis=1))
        d_neg = np.sqrt(np.sum((w_matrix - ideal_neg) ** 2, axis=1))

        # Relative closeness to ideal
        denom_dist = d_pos + d_neg
        denom_dist[denom_dist < 1e-9] = 1.0
        closeness = d_neg / denom_dist

        pareto_set = set(self.identify_pareto_frontier(alternatives, criteria))
        sort_order = np.argsort(-closeness)

        rankings: List[RankedOption] = []
        for rank_idx, alt_idx in enumerate(sort_order):
            alt_name = alternatives[alt_idx].name
            score = float(closeness[alt_idx])
            details = {c.name: float(matrix[alt_idx, j]) for j, c in enumerate(criteria)}
            rankings.append(RankedOption(
                rank=rank_idx + 1,
                name=alt_name,
                score=round(score, 4),
                is_pareto_optimal=(alt_name in pareto_set),
                details=details,
            ))

        best_opt = rankings[0].name if rankings else ""

        md_lines = [
            "# Decision Intelligence Report (TOPSIS Method)",
            "",
            f"**Recommended Option:** `{best_opt}` (Relative Closeness: {rankings[0].score:.4f})",
            "",
            "### Rankings by Proximity to Ideal Solution:",
            "| Rank | Option | Closeness $C_i$ | Pareto Optimal |",
            "|:---:|:---|:---:|:---:|",
        ]
        for r in rankings:
            pareto_str = "⭐ Yes" if r.is_pareto_optimal else "No"
            md_lines.append(f"| {r.rank} | **{r.name}** | {r.score:.4f} | {pareto_str} |")

        return DecisionReport(
            method="TOPSIS",
            criteria=criteria,
            rankings=rankings,
            pareto_frontier=list(pareto_set),
            best_option=best_opt,
            summary_markdown="\n".join(md_lines),
        )


_decision_engine: Optional[DecisionEngine] = None


def get_decision_engine() -> DecisionEngine:
    global _decision_engine
    if _decision_engine is None:
        _decision_engine = DecisionEngine()
    return _decision_engine
