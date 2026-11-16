# Stark Armor Telemetry & Hardware Health Diagnostics

AMATYA provides real-time hardware telemetry and suit status monitoring via `actions/armor_diagnostics.py` and `skills/armor-diagnostics/`.

---

## 1. Diagnostics Capabilities

### 1. Armor Status (`armor_status`)
- Returns a comprehensive Stark-style armor scorecard and workstation telemetry:
  - System architecture and OS kernel version.
  - Active CPU core count and overall utilization percentage.
  - Memory consumption (used RAM, available RAM, swap buffer).
  - Primary disk capacity and free space.
  - System uptime and thermal state.

### 2. Core Thermal Mapping (`thermal_map`)
- Probes hardware thermal sensors (via `psutil`, `/sys/class/thermal`, and hardware monitors):
  - Per-core CPU temperatures.
  - Composite package temperature.
  - Thermal throttling warnings if thresholds ($85^\circ\text{C}$ or $95^\circ\text{C}$) are exceeded.
  - Cooling fan status where available.

### 3. Battery & Power Diagnostics (`battery_health`)
- Inspects power subsystems:
  - AC power adapter connection status (mains vs. battery).
  - Battery charge percentage.
  - Discharge rate and estimated remaining operational time.
  - Charging status and health degradation indicators.

### 4. GPU Diagnostics & VRAM Telemetry (`gpu_telemetry`)
- Inspects local graphics hardware (via `pynvml` or `nvidia-smi`):
  - GPU model and driver version.
  - Core GPU utilization percentage.
  - VRAM allocated, free, and total (MB/GB).
  - GPU core temperature and power draw in watts.

---

## 2. Spoken Voice Commands

- *"JARVIS, suit diagnostics"* / *"Report armor status"*
- *"Check core thermals"* / *"How hot is the CPU running?"*
- *"Check battery and power status"*
- *"Report GPU telemetry and VRAM"*
- *"Check system hardware health"*
