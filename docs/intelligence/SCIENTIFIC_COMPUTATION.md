# AMATYA Scientific Computation & Dimensional Analysis (Phase 14.3)

## 1. Overview
The Scientific Computation module (`core/scientific_computation.py`) provides exact mathematical computation, differential calculus, numerical ODE integration, and physical unit dimensional analysis using `sympy`, `scipy`, and `numpy`.

---

## 2. Dimensional Analysis Layer (`UnitQuantity`)
Dimensional analysis prevents incompatible arithmetic operations at runtime:
- **Base Dimensions:** Mass ($M$), Length ($L$), Time ($T$), Electric Current ($I$), Temperature ($\Theta$), Substance Amount ($N$), Luminous Intensity ($J$).
- Dimensional vector: `(M, L, T, I, Theta, N, J)`.
- Physical units are registered with exact conversion factors to SI base units.

### Compatibility Rules
1. **Addition & Subtraction ($A \pm B$):** Allowed strictly when $\text{dim}(A) = \text{dim}(B)$. Attempting `12 V + 2 A` raises `DimensionalInconsistencyError`.
2. **Multiplication ($A \times B$):** Yields quantity with vector $\text{dim}(A) + \text{dim}(B)$.
   - Example: $2.5\text{ A} \times 10.0\text{ }\Omega = 25.0\text{ V}$.
3. **Division ($A / B$):** Yields quantity with vector $\text{dim}(A) - \text{dim}(B)$.
   - Example: $25.0\text{ V} / 2.5\text{ A} = 10.0\text{ }\Omega$.

---

## 3. Symbolic Computation Engine (`SymbolicSolver`)
Powered by SymPy:
- `solve_equation(equation_str, var)`: Solves polynomial, transcendental, and systems of equations analytically.
- `differentiate(expr_str, var, order)`: Computes exact analytical derivatives.
- `integrate(expr_str, var, lower, upper)`: Analytical definite and indefinite integration.
- `limit(expr_str, var, target)`: Analytical limits with directional evaluation.
- `simplify(expr_str)`: Symbolic simplification and trigonometric identities.

---

## 4. High-Precision Numerical Solvers (`NumericalSolver`)
Powered by SciPy:
- `find_root(func, x0, var)`: Newton-Raphson and Brent root finding.
- `minimize(func_str, x0, bounds)`: L-BFGS-B and SLSQP continuous optimization.
- `solve_ode_ivp(dydt_fn, y0, t_span, num_points)`: Runge-Kutta 4th/5th order (RK45) adaptive step numerical integration.

---

## 5. Dual-Method Verification (`VerificationAuditor`)
Analytical solutions are verified independently against numerical approximations:
- Analytical derivative $f'(x)$ is verified against central finite difference:
  $$\frac{f(x + h) - f(x - h)}{2h} + O(h^2)$$
- Solutions are validated only if relative error $\epsilon_{rel} < 10^{-4}$.

