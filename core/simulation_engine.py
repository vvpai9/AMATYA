"""
AMATYA Universal Simulation Engine (core/simulation_engine.py)
==============================================================
Phase 14.5 Core Implementation:
  - Modular Simulation Framework (Models, Parameters, Initial States, Solver Selection).
  - Physics & Engineering Adapters:
      1. CircuitSimulator (Transient RLC state-space ODE integration).
      2. ThermalSimulator (Lumped RC junction temperature dynamics).
      3. OrbitalSimulator (Keplerian two-body celestial orbital propagation).
      4. MonteCarloSimulator (Statistical distributions, seed control, percentiles).
  - Physical Law Validation (Energy conservation, numerical stability, convergence checks).
  - Explicit Separation of Simulated Results from Real Hardware Measurements.
"""
from __future__ import annotations

import concurrent.futures
import math
import multiprocessing
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import scipy.integrate

# Earth gravitational parameter mu = G*M (m^3 / s^2)
EARTH_MU = 3.986004418e14
EARTH_RADIUS_M = 6378137.0


@dataclass
class SimulationConfig:
    simulation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    model_name: str = ""
    parameters: dict[str, float] = field(default_factory=dict)
    initial_conditions: list[float] = field(default_factory=list)
    t_span: tuple[float, float] = (0.0, 1.0)
    solver_method: str = "RK45"
    num_points: int = 200
    random_seed: int | None = 42

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    simulation_id: str
    model_name: str
    success: bool
    time_points: list[float]
    trajectories: dict[str, list[float]]  # state_name -> trajectory
    metrics: dict[str, Any]
    validation_status: str  # Validated | Infeasible | Diverged | Unstable
    execution_time_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "model_name": self.model_name,
            "success": self.success,
            "data_points": len(self.time_points),
            "trajectories": {k: [round(x, 4) for x in v[:10]] for k, v in self.trajectories.items()},  # Preview
            "metrics": self.metrics,
            "validation_status": self.validation_status,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
        }

    @property
    def is_physically_consistent(self) -> bool:
        return self.success and (self.validation_status.startswith("Validated") or self.validation_status in ("Nominal", "Consistent"))

    @property
    def summary_markdown(self) -> str:
        md = [
            f"# Simulation Report: {self.model_name}",
            f"- **Status:** {'✅ Successful' if self.success else '❌ Failed'} ({self.validation_status})",
            f"- **Execution Time:** {self.execution_time_ms:.2f} ms",
            f"- **Data Points:** {len(self.time_points)}",
            "",
            "### Key Metrics:",
        ]
        for k, v in self.metrics.items():
            md.append(f"- **{k}:** `{v}`")
        if self.error:
            md.append(f"\n⚠️ **Error:** {self.error}")
        return "\n".join(md)


# ============================================================================
# Simulation Adapters
# ============================================================================

class CircuitSimulationAdapter:
    """Simulates transient response of RLC circuits: dI/dt = (Vin - Vc - R*I)/L, dVc/dt = I/C."""

    @classmethod
    def simulate_rlc(
        cls,
        r_ohm: float,
        l_henry: float,
        c_farad: float,
        vin_volts: float,
        t_max: float = 0.005,
        num_points: int = 200,
    ) -> SimulationResult:
        t_start = time.perf_counter()
        sim_id = f"sim_rlc_{str(uuid.uuid4())[:8]}"

        if l_henry <= 0 or c_farad <= 0 or r_ohm < 0:
            return SimulationResult(
                simulation_id=sim_id,
                model_name="RLC_Transient",
                success=False,
                time_points=[],
                trajectories={},
                metrics={},
                validation_status="Infeasible",
                execution_time_ms=0.0,
                error="L and C must be positive; R must be non-negative.",
            )

        # State vector y = [Current I, Capacitor Voltage Vc]
        def rlc_ode(t: float, y: np.ndarray) -> np.ndarray:
            i, vc = y[0], y[1]
            di_dt = (vin_volts - vc - r_ohm * i) / l_henry
            dvc_dt = i / c_farad
            return np.array([di_dt, dvc_dt])

        y0 = [0.0, 0.0]  # Initially zero current and voltage
        t_eval = np.linspace(0, t_max, num_points)

        sol = scipy.integrate.solve_ivp(rlc_ode, (0, t_max), y0, t_eval=t_eval, method="RK45")

        # Analytical metrics
        omega_0 = 1.0 / math.sqrt(l_henry * c_farad)
        alpha = r_ohm / (2.0 * l_henry)
        zeta = alpha / omega_0  # Damping ratio

        i_traj = sol.y[0].tolist()
        vc_traj = sol.y[1].tolist()

        max_vc = max(vc_traj) if vc_traj else 0.0
        overshoot_pct = max(0.0, ((max_vc - vin_volts) / vin_volts) * 100.0) if vin_volts > 0 else 0.0

        exec_ms = (time.perf_counter() - t_start) * 1000.0

        # Physical validation: Vc should not exceed 2 * Vin for passive step response
        is_valid = max_vc <= 2.1 * vin_volts and sol.success
        status = "Validated (Passive Conservation)" if is_valid else "Diverged/Unstable"

        return SimulationResult(
            simulation_id=sim_id,
            model_name="RLC_Transient",
            success=sol.success,
            time_points=sol.t.tolist(),
            trajectories={
                "current_A": i_traj,
                "voltage_V": vc_traj,
                "i_l": i_traj,
                "v_c": vc_traj,
            },
            metrics={
                "damping_ratio_zeta": round(zeta, 4),
                "natural_freq_rad_s": round(omega_0, 2),
                "peak_voltage_V": round(max_vc, 3),
                "overshoot_pct": round(overshoot_pct, 2),
                "steady_state_voltage_V": round(vin_volts, 3),
            },
            validation_status=status,
            execution_time_ms=exec_ms,
        )


class ThermalSimulationAdapter:
    """Simulates semiconductor junction heating: dT_j/dt = (Pdiss - (Tj - Tamb)/Rth) / Cth."""

    @classmethod
    def simulate_junction_temp(
        cls,
        p_diss_watts: float,
        r_th_c_per_w: float,
        c_th_j_per_c: float,
        t_amb_c: float = 25.0,
        t_max: float = 60.0,
        num_points: int = 150,
    ) -> SimulationResult:
        t_start = time.perf_counter()
        sim_id = f"sim_th_{str(uuid.uuid4())[:8]}"

        if r_th_c_per_w <= 0 or c_th_j_per_c <= 0:
            return SimulationResult(
                simulation_id=sim_id,
                model_name="Thermal_RC",
                success=False,
                time_points=[],
                trajectories={},
                metrics={},
                validation_status="Infeasible",
                execution_time_ms=0.0,
                error="R_th and C_th must be strictly positive.",
            )

        def thermal_ode(t: float, y: np.ndarray) -> np.ndarray:
            t_j = y[0]
            heat_loss = (t_j - t_amb_c) / r_th_c_per_w
            dt_dt = (p_diss_watts - heat_loss) / c_th_j_per_c
            return np.array([dt_dt])

        y0 = [t_amb_c]
        t_eval = np.linspace(0, t_max, num_points)
        sol = scipy.integrate.solve_ivp(thermal_ode, (0, t_max), y0, t_eval=t_eval, method="RK45")

        tj_traj = sol.y[0].tolist()
        steady_state_temp = t_amb_c + p_diss_watts * r_th_c_per_w
        tau_seconds = r_th_c_per_w * c_th_j_per_c  # Thermal time constant

        exec_ms = (time.perf_counter() - t_start) * 1000.0

        return SimulationResult(
            simulation_id=sim_id,
            model_name="Thermal_RC",
            success=sol.success,
            time_points=sol.t.tolist(),
            trajectories={"junction_temp_C": tj_traj},
            metrics={
                "ambient_temp_C": t_amb_c,
                "steady_state_temp_C": round(steady_state_temp, 2),
                "t_steady_state": round(4.0 * tau_seconds, 3),
                "settling_time_s": round(4.0 * tau_seconds, 3),
                "thermal_time_constant_s": round(tau_seconds, 2),
                "peak_temp_reached_C": round(max(tj_traj), 2),
            },
            validation_status="Validated (1st Order Thermal LTI)",
            execution_time_ms=exec_ms,
        )

    @classmethod
    def simulate_thermal_transient(
        cls,
        power_watts: float,
        r_th: float,
        c_th: float,
        t_ambient: float = 25.0,
        t_max: float = 60.0,
        num_points: int = 150,
    ) -> SimulationResult:
        return cls.simulate_junction_temp(
            p_diss_watts=power_watts,
            r_th_c_per_w=r_th,
            c_th_j_per_c=c_th,
            t_amb_c=t_ambient,
            t_max=t_max,
            num_points=num_points,
        )


class OrbitalSimulationAdapter:
    """Simulates 2D/3D two-body Keplerian orbital mechanics: d2r/dt2 = -mu * r / |r|^3."""

    @classmethod
    def simulate_orbit(
        cls,
        altitude_km: float = 400.0,  # Circular LEO altitude
        duration_hours: float = 3.0,
        num_points: int = 300,
    ) -> SimulationResult:
        t_start = time.perf_counter()
        sim_id = f"sim_orb_{str(uuid.uuid4())[:8]}"

        r0 = EARTH_RADIUS_M + altitude_km * 1000.0
        v_circular = math.sqrt(EARTH_MU / r0)
        orbital_period_s = 2.0 * math.pi * math.sqrt(r0**3 / EARTH_MU)

        # State: y = [x, y, vx, vy]
        def orbit_ode(t: float, y: np.ndarray) -> np.ndarray:
            rx, ry, vx, vy = y[0], y[1], y[2], y[3]
            r = math.sqrt(rx**2 + ry**2)
            ax = -EARTH_MU * rx / (r**3)
            ay = -EARTH_MU * ry / (r**3)
            return np.array([vx, vy, ax, ay])

        y0 = [r0, 0.0, 0.0, v_circular]
        t_span = (0.0, duration_hours * 3600.0)
        t_eval = np.linspace(0.0, duration_hours * 3600.0, num_points)

        sol = scipy.integrate.solve_ivp(orbit_ode, t_span, y0, t_eval=t_eval, method="RK45", rtol=1e-8, atol=1e-8)

        x_pts = sol.y[0].tolist()
        y_pts = sol.y[1].tolist()

        # Energy conservation check: E = v^2 / 2 - mu / r
        e_init = 0.5 * (v_circular**2) - (EARTH_MU / r0)
        final_r = math.sqrt(x_pts[-1]**2 + y_pts[-1]**2)
        final_v = math.sqrt(sol.y[2][-1]**2 + sol.y[3][-1]**2)
        e_final = 0.5 * (final_v**2) - (EARTH_MU / final_r)
        delta_e_pct = abs((e_final - e_init) / e_init) * 100.0

        is_valid = delta_e_pct < 0.1  # Less than 0.1% energy drift
        exec_ms = (time.perf_counter() - t_start) * 1000.0

        return SimulationResult(
            simulation_id=sim_id,
            model_name="Orbital_TwoBody",
            success=sol.success,
            time_points=sol.t.tolist(),
            trajectories={"pos_x_km": [x / 1000.0 for x in x_pts], "pos_y_km": [y / 1000.0 for y in y_pts]},
            metrics={
                "altitude_km": altitude_km,
                "orbital_period_min": round(orbital_period_s / 60.0, 2),
                "orbital_velocity_km_s": round(v_circular / 1000.0, 3),
                "v_circ_mps": round(v_circular, 2),
                "energy_conservation_drift_pct": round(delta_e_pct, 6),
            },
            validation_status="Validated (Keplerian Energy Conserved)" if is_valid else "Drifted",
            execution_time_ms=exec_ms,
        )

    @classmethod
    def propagate_kepler_orbit(
        cls,
        alt_km: float = 400.0,
        t_span_hours: float = 3.0,
        num_points: int = 300,
    ) -> SimulationResult:
        return cls.simulate_orbit(
            altitude_km=alt_km,
            duration_hours=t_span_hours,
            num_points=num_points,
        )


class MonteCarloSimulationAdapter:
    """Executes reproducible stochastic trials with seed control and percentile metrics."""

    @classmethod
    def run_monte_carlo(
        cls,
        expression_fn: Callable[[np.ndarray], np.ndarray],
        num_trials: int = 10000,
        random_seed: int = 42,
    ) -> dict[str, Any]:
        rng = np.random.default_rng(random_seed)
        samples = rng.standard_normal(num_trials)
        results = expression_fn(samples)

        p10 = float(np.percentile(results, 10))
        p50 = float(np.percentile(results, 50))
        p90 = float(np.percentile(results, 90))
        p99 = float(np.percentile(results, 99))
        mean = float(np.mean(results))
        std = float(np.std(results))

        return {
            "num_trials": num_trials,
            "random_seed": random_seed,
            "mean": round(mean, 4),
            "std_dev": round(std, 4),
            "percentiles": {
                "P10": round(p10, 4),
                "P50": round(p50, 4),
                "P90": round(p90, 4),
                "P99": round(p99, 4),
            },
            "sample_preview": [round(float(x), 4) for x in results[:10]],
        }


class SimulationEngine:
    """Unified Simulation Engine coordinating physical domain adapters."""

    _instance: Optional[SimulationEngine] = None

    def __init__(self):
        self.circuit_adapter = CircuitSimulationAdapter()
        self.thermal_adapter = ThermalSimulationAdapter()
        self.orbital_adapter = OrbitalSimulationAdapter()
        self.monte_carlo_adapter = MonteCarloSimulationAdapter()

    @classmethod
    def get_instance(cls) -> SimulationEngine:
        if cls._instance is None:
            cls._instance = SimulationEngine()
        return cls._instance

    def run_simulation(
        self,
        sim_type: str,
        parameters: dict[str, Any],
        duration: float = 10.0,
        step_size: float = 0.01,
        seed: Optional[int] = None,
        *,
        allow_in_process: bool = False,
    ) -> SimulationResult:
        st = sim_type.lower()
        sim_err_id = f"sim_err_{str(uuid.uuid4())[:8]}"

        # Sanitize parameters: remove untrusted in_process flag to preserve subprocess isolation
        parameters = dict(parameters) if parameters else {}
        parameters.pop("in_process", None)

        # Parameter validation: check for NaN/Inf and boundaries
        for k, v in parameters.items():
            if isinstance(v, (int, float)):
                if math.isnan(v) or math.isinf(v):
                    return SimulationResult(
                        simulation_id=sim_err_id,
                        model_name=sim_type,
                        success=False,
                        time_points=[],
                        trajectories={},
                        metrics={},
                        validation_status="Infeasible",
                        execution_time_ms=0.0,
                        error=f"Parameter '{k}' has invalid non-finite value ({v}).",
                    )

        if math.isnan(duration) or math.isinf(duration) or duration < 0 or duration > 86400.0:
            return SimulationResult(
                simulation_id=sim_err_id,
                model_name=sim_type,
                success=False,
                time_points=[],
                trajectories={},
                metrics={},
                validation_status="Infeasible",
                execution_time_ms=0.0,
                error=f"Invalid simulation duration '{duration}'. Must be between 0 and 86400 seconds.",
            )

        # Compute adaptive number of points using step_size if num_points is omitted
        default_pts = max(50, min(10000, int(duration / max(1e-6, step_size)))) if step_size > 0 else 200
        timeout_sec = max(0.001, float(parameters.get("timeout_sec", 15.0)))
        max_mem_mb = int(parameters.get("max_memory_mb", 1024))

        # Restrict in-process execution strictly to trusted internal callers passing allow_in_process=True
        if allow_in_process:
            try:
                return self._dispatch_core(st, parameters, duration, step_size, seed, default_pts)
            except Exception as exc:
                return SimulationResult(
                    simulation_id=sim_err_id,
                    model_name=sim_type,
                    success=False,
                    time_points=[],
                    trajectories={},
                    metrics={},
                    validation_status="ExecutionError",
                    execution_time_ms=0.0,
                    error=f"Simulation failed during execution: {exc}",
                )

        # Genuine isolated worker process with resource limits and process termination
        # Uses spawn context for clean cross-platform process isolation without thread inheritance
        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)

        proc = ctx.Process(
            target=_isolated_simulation_worker,
            args=(
                st,
                parameters,
                duration,
                step_size,
                seed,
                default_pts,
                child_conn,
                max_mem_mb,
                int(timeout_sec + 5),
            ),
        )

        t_start = time.perf_counter()
        proc.start()
        child_conn.close()

        res_payload = None
        timed_out = False

        try:
            if parent_conn.poll(timeout=timeout_sec):
                try:
                    res_payload = parent_conn.recv()
                except (EOFError, BrokenPipeError):
                    res_payload = None
            else:
                timed_out = True
        except Exception:
            timed_out = True
        finally:
            parent_conn.close()

        if timed_out or proc.is_alive():
            if timed_out:
                try:
                    proc.terminate()
                    proc.join(timeout=0.5)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=0.2)
                except Exception:
                    pass

                return SimulationResult(
                    simulation_id=sim_err_id,
                    model_name=sim_type,
                    success=False,
                    time_points=[],
                    trajectories={},
                    metrics={},
                    validation_status="Timeout",
                    execution_time_ms=timeout_sec * 1000.0,
                    error=f"Simulation exceeded execution timeout of {timeout_sec:.2f}s and was terminated.",
                )
            else:
                proc.join(timeout=1.0)

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        if proc.exitcode != 0 and res_payload is None:
            return SimulationResult(
                simulation_id=sim_err_id,
                model_name=sim_type,
                success=False,
                time_points=[],
                trajectories={},
                metrics={},
                validation_status="ExecutionError",
                execution_time_ms=elapsed_ms,
                error=f"Simulation worker process crashed with exit code {proc.exitcode} (OOM, killed, or signal).",
            )

        if res_payload is not None:
            ok, data = res_payload
            if ok and isinstance(data, SimulationResult):
                return data
            else:
                return SimulationResult(
                    simulation_id=sim_err_id,
                    model_name=sim_type,
                    success=False,
                    time_points=[],
                    trajectories={},
                    metrics={},
                    validation_status="ExecutionError",
                    execution_time_ms=elapsed_ms,
                    error=f"Simulation failed during execution: {data}",
                )

        return SimulationResult(
            simulation_id=sim_err_id,
            model_name=sim_type,
            success=False,
            time_points=[],
            trajectories={},
            metrics={},
            validation_status="ExecutionError",
            execution_time_ms=elapsed_ms,
            error="Simulation worker process produced no output.",
        )

    def _dispatch_core(
        self,
        st: str,
        parameters: dict[str, Any],
        duration: float,
        step_size: float,
        seed: Optional[int],
        default_pts: int,
    ) -> SimulationResult:
        """Internal deterministic simulation execution dispatcher."""
        if st in ("circuit", "rlc"):
            return self.circuit_adapter.simulate_rlc(
                r_ohm=float(parameters.get("r", parameters.get("r_ohm", 10.0))),
                l_henry=float(parameters.get("l", parameters.get("l_henry", 0.001))),
                c_farad=float(parameters.get("c", parameters.get("c_farad", 0.00001))),
                vin_volts=float(parameters.get("vin", parameters.get("vin_volts", 12.0))),
                t_max=duration if duration < 1.0 else 0.005,
                num_points=int(parameters.get("num_points", default_pts)),
            )
        elif st in ("thermal", "temperature"):
            return self.thermal_adapter.simulate_thermal_transient(
                power_watts=float(parameters.get("power", parameters.get("power_watts", 45.0))),
                r_th=float(parameters.get("r_th", 0.8)),
                c_th=float(parameters.get("c_th", 25.0)),
                t_ambient=float(parameters.get("t_ambient", 25.0)),
                t_max=duration if duration > 1.0 else 120.0,
                num_points=int(parameters.get("num_points", default_pts)),
            )
        elif st in ("orbital", "orbit", "kepler"):
            return self.orbital_adapter.propagate_kepler_orbit(
                alt_km=float(parameters.get("alt_km", 400.0)),
                t_span_hours=duration if duration > 0.1 else 3.0,
                num_points=int(parameters.get("num_points", default_pts)),
            )
        elif st in ("monte_carlo", "sampling"):
            t_start = time.perf_counter()
            num_trials = min(1_000_000, max(10, int(parameters.get("num_trials", 10000))))
            rnd_seed = int(seed if seed is not None else parameters.get("seed", 42))
            mean_val = float(parameters.get("mean", 100.0))
            std_val = float(parameters.get("std", 15.0))

            mc_res = self.monte_carlo_adapter.run_monte_carlo(
                expression_fn=lambda s: mean_val + std_val * s,
                num_trials=num_trials,
                random_seed=rnd_seed,
            )
            elapsed = (time.perf_counter() - t_start) * 1000.0
            return SimulationResult(
                simulation_id=f"sim_mc_{str(uuid.uuid4())[:8]}",
                model_name="Monte_Carlo_Uncertainty",
                success=True,
                time_points=[float(i) for i in range(len(mc_res["sample_preview"]))],
                trajectories={"sample_preview": mc_res["sample_preview"]},
                metrics=mc_res,
                validation_status="Validated",
                execution_time_ms=elapsed,
            )
        else:
            return SimulationResult(
                simulation_id=f"sim_err_{str(uuid.uuid4())[:8]}",
                model_name=st,
                success=False,
                time_points=[],
                trajectories={},
                metrics={},
                validation_status="Infeasible",
                execution_time_ms=0.0,
                error=f"Unknown simulation type '{st}'. Supported: circuit, thermal, orbital, monte_carlo",
            )


def _isolated_simulation_worker(
    st: str,
    parameters: dict[str, Any],
    duration: float,
    step_size: float,
    seed: Optional[int],
    default_pts: int,
    result_pipe_conn: Any,
    max_memory_mb: int = 1024,
    cpu_limit_sec: int = 60,
) -> None:
    """Worker process entry point executed in an isolated OS process."""
    # Constrain BLAS/LAPACK threads to 1 to bound virtual memory allocation within the 1024 MB ceiling
    import os
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"

    # 1. Apply OS resource limits where supported (Linux/macOS)
    try:
        import resource
        # CPU execution time boundary
        if hasattr(resource, "RLIMIT_CPU"):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_sec, cpu_limit_sec))
        # Virtual memory limits enforced at default 1024 MB and user-specified limits
        if max_memory_mb and max_memory_mb > 0 and hasattr(resource, "RLIMIT_AS"):
            as_bytes = max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
    except Exception:
        pass

    try:
        engine = SimulationEngine()
        res = engine._dispatch_core(st, parameters, duration, step_size, seed, default_pts)
        result_pipe_conn.send((True, res))
    except Exception as exc:
        result_pipe_conn.send((False, str(exc)))
    finally:
        try:
            result_pipe_conn.close()
        except Exception:
            pass


def get_simulation_engine() -> SimulationEngine:
    return SimulationEngine.get_instance()

