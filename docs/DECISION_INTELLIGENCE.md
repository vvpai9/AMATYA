# AMATYA Decision Intelligence & MCDA (Phase 14.9)

## 1. Overview
The Decision Intelligence module (`core/decision_intelligence.py`) provides quantitative Multi-Criteria Decision Analysis (MCDA), Pareto frontier extraction, and multi-objective trade-off analysis.

---

## 2. Multi-Criteria Methods

### A. Weighted Sum Model (WSM)
1. **Normalization:** Linear min-max scaling across criteria $C_j$:
   - For maximization: $r_{ij} = \frac{x_{ij} - \min_k x_{kj}}{\max_k x_{kj} - \min_k x_{kj}}$
   - For minimization: $r_{ij} = \frac{\max_k x_{kj} - x_{ij}}{\max_k x_{kj} - \min_k x_{kj}}$
2. **Aggregation:**
   $$S_i = \sum_{j=1}^M w_j \cdot r_{ij}, \quad \text{where } \sum w_j = 1.0$$

### B. TOPSIS (Technique for Order Preference by Similarity to Ideal Solution)
1. **Vector Normalization:**
   $$v_{ij} = \frac{x_{ij}}{\sqrt{\sum_{k=1}^N x_{kj}^2}}$$
2. **Weighted Normalized Matrix:** $p_{ij} = w_j \cdot v_{ij}$.
3. **Ideal Positive ($A^+$) and Ideal Negative ($A^-$) Solutions:**
   $$A_j^+ = \max_i p_{ij} \text{ (or } \min_i \text{ for cost)}, \quad A_j^- = \min_i p_{ij} \text{ (or } \max_i \text{ for cost)}$$
4. **Euclidean Distances:**
   $$D_i^+ = \sqrt{\sum (p_{ij} - A_j^+)^2}, \quad D_i^- = \sqrt{\sum (p_{ij} - A_j^-)^2}$$
5. **Relative Closeness Coefficient:**
   $$C_i = \frac{D_i^-}{D_i^+ + D_i^-} \in [0, 1]$$
   Alternatives are ranked in descending order of $C_i$.

---

## 3. Pareto Dominance Analysis
An option $A$ dominates option $B$ ($A \succ B$) if:
$$\forall j \in \{1, \dots, M\}, \quad f_j(A) \ge f_j(B) \quad \text{and} \quad \exists k, \; f_k(A) > f_k(B)$$
The engine filters out all dominated options to isolate the exact Pareto-optimal frontier.
