---
name: armor-diagnostics
description: "Real-time hardware health inspection, CPU frequency scaling, per-sensor thermal zone mapping, battery wear analysis, GPU power/VRAM diagnostics, and complete Iron Man Mark-class armor integrity reporting. Use whenever the user asks for 'armor status', 'system health', 'battery wear', 'thermal check', 'fan speed', or hardware diagnostics."
license: Apache-2.0
---

# Stark Armor Telemetry & Hardware Health Diagnostics

Provides deep physical hardware telemetry, system thermal envelope monitoring, and subsystem integrity grading for the host machine.

## Key Capabilities

1. **Mark Armor Status (`armor_status`):**
   - Synthesizes CPU load, core frequencies, maximum thermal junction temperatures, RAM saturation, storage space, and GPU power draw into a unified Armor Integrity percentage.

2. **Thermal Zone Sensor Mapping (`thermal_map`):**
   - Directly probes `/sys/class/thermal/thermal_zone*` and core temperature sensors to detect thermal throttling risks.

3. **Power Subsystem & Arc Reactor Diagnostics (`battery_health`):**
   - Tracks battery wear percentage, charge cycle counts, AC connection status, and remaining runtime.

4. **GPU Auxiliary Telemetry:**
   - Reports NVIDIA VRAM allocation, GPU core clock temperatures, and power draw in Watts.
