# Stark Laboratory & Scientific Computing

The Stark Laboratory (`actions/stark_lab.py`, `skills/stark-calculator/`) provides high-precision symbolic mathematics, kinematic physics simulations, and orbital mechanics calculations.

---

## 1. Capabilities

### 1. Symbolic Mathematics (`symbolic_math`)
Powered by `SymPy` with AST-isolated expression evaluation (`safe_sympify`), eliminating arbitrary code execution:
- **Derivatives:** First, second, and N-th order partial derivatives.
- **Integrals:** Indefinite integrals, definite integrals over specified bounds.
- **Equation Solving:** Linear systems, polynomial roots, transcendent equations.
- **Matrix Operations:** Determinants, eigenvalues, matrix inverses, cross products.
- **Calculus:** Limits, Taylor series expansions, algebraic simplification.

### 2. Kinematic Projectile Trajectory Simulation (`trajectory`)
Simulates 2D ballistic projectile physics using numerical Euler/Runge-Kutta integration:
- Takes mass ($m$), launch velocity ($v_0$), launch angle ($\theta$), aerodynamic drag coefficient ($C_d$), frontal area ($A$), and air density ($\rho$).
- Calculates real-world air resistance and gravitational acceleration.
- Returns trajectory telemetry:
  - **Apogee (Maximum Height)** and time to apogee.
  - **Total Range (Horizontal Distance)**.
  - **Time of Flight**.
  - **Impact Velocity & Angle**.

### 3. Keplerian Orbital Mechanics (`orbital`)
Computes two-body gravitational mechanics around Earth and planetary bodies:
- **Orbital Velocity:** Speed required for circular orbit at a given altitude:
  $$v = \sqrt{\frac{GM}{R + h}}$$
- **Orbital Period:** Time required for one complete orbit:
  $$T = 2\pi \sqrt{\frac{(R + h)^3}{GM}}$$
- **Escape Velocity:** Speed needed to escape gravitational field:
  $$v_{esc} = \sqrt{\frac{2GM}{R + h}}$$
- **Hohmann Transfer Delta-V:** Velocity impulses ($\Delta v_1$, $\Delta v_2$) needed to transfer between circular orbits.

---

## 2. Voice & Query Examples

- *"Solve the symbolic integral of x times cosine of x"*
- *"Calculate the derivative of x cubed minus 4x squared plus 7"*
- *"Find the roots of 2x squared minus 5x plus 3 equals 0"*
- *"Simulate projectile trajectory with velocity 120 m/s at 45 degrees"*
- *"Calculate orbital velocity and period at an altitude of 420 kilometers"*
- *"What is Earth's escape velocity from low Earth orbit?"*
