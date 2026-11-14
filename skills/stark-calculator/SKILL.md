---
name: stark-calculator
description: "Advanced scientific computing, symbolic calculus, differential equations, Taylor series, ballistic trajectory simulations with aerodynamic drag, and orbital mechanics across Earth, Mars, Moon, and other celestial bodies. Use whenever the user asks to 'calculate', 'integrate', 'differentiate', 'simulate trajectory', 'orbital velocity', 'escape velocity', or requests complex STEM/physics computations like Iron Man's JARVIS lab computer."
license: Apache-2.0
---

# Stark Laboratory Scientific Computing & Physics Simulator

Combines symbolic mathematics (`sympy`), scientific modeling (`scipy`), and physics kinematics into an integrated STEM calculation matrix.

## Supported Workflows

1. **Symbolic Mathematics & Calculus (`symbolic_math`):**
   - Exact algebraic solutions: `x**2 - 5*x + 6 = 0`
   - Symbolic differentiation: `diff` on functions like `sin(x)*exp(x)`
   - Definite and indefinite integration: `integrate`
   - Taylor and Maclaurin power series expansions: `series`

2. **Ballistic Trajectory Kinematics (`trajectory`):**
   - 2D kinematics with aerodynamic drag coefficient ($C_d$).
   - Outputs: Maximum altitude (apogee), flight time, total ground range, and initial kinetic energy.

3. **Orbital Mechanics & Escape Velocity (`orbital`):**
   - Computes circular orbital velocity ($v_{orb} = \sqrt{\frac{GM}{r}}$).
   - Computes parabolic escape velocity ($v_{esc} = \sqrt{\frac{2GM}{r}}$).
   - Computes orbital period in minutes across Earth, Moon, Mars, Jupiter, or the Sun.
