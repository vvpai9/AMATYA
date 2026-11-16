# Autonomy Levels & Permission Governance

AMATYA implements a transparent, 5-tier autonomy framework designed to balance proactive intelligence with complete user sovereignty.

---

## 1. The Five Autonomy Levels

| Level | Code | Name | Description | Execution Policy |
|---|---|---|---|---|
| **L1** | `observe` | **Observe** | Passive monitor & listener | Read-only. Does not execute commands or modify system state. Answers informational queries. |
| **L2** | `recommend` | **Recommend** | Proactive advisor | Formulates multi-step plans and actionable suggestions. Waits for user confirmation before executing any action. |
| **L3** | `confirm` | **Confirm (Default)** | Balanced assistant | Runs safe queries, read-only tools, and informational searches autonomously. Prompts user confirmation for file writes, network requests, and external APIs. |
| **L4** | `low_risk` | **Low-Risk** | Semi-autonomous operator | Autonomously executes read actions, local directory navigation, diagnostic telemetry, and low-risk desktop tasks. Prompts confirmation only for high-impact or destructive actions. |
| **L5** | `full_auto` | **Full Auto** | Fully autonomous companion | Executes all permitted workflows, background research, and automation end-to-end without stopping. Emergency halt remains active at all times. |

---

## 2. Where to View Current Autonomy Level

AMATYA displays the active autonomy level across 4 prominent surfaces:
1. **HUD Controls Drawer:** Tap the sliders icon in the top header. The `🛡 AUTONOMY` button displays the current tier (e.g. `L3: CONFIRM`).
2. **Left Status Column:** Displays `AUTONOMY: [TIER]` alongside security and authorization status.
3. **Bottom Status Strip:** Displays real-time autonomy badge.
4. **Web Dashboard Header:** Shows a color-coded autonomy pill at the top right of `http://127.0.0.1:8000`.

---

## 3. How to Change Autonomy Levels

### Via Voice Commands:
- *"Set autonomy level to 1"* / *"Change autonomy to observe"*
- *"Set autonomy level to 2"* / *"Set autonomy to recommend"*
- *"Set autonomy level to 3"* / *"Set autonomy to confirm"*
- *"Set autonomy level to 4"* / *"Set autonomy to low-risk"*
- *"Set autonomy level to 5"* / *"Enable full auto mode"*

### Via HUD Interface:
- Open the **CONTROLS** drawer in the top bar.
- Click the **`🛡 AUTONOMY`** button to cycle sequentially through the 5 levels (`L1 → L2 → L3 → L4 → L5 → L1`).

### Via Configuration File:
Set the `"autonomy_level"` key in `config/api_keys.json`:
```json
{
  "autonomy_level": "confirm"
}
```
Valid values: `"observe"`, `"recommend"`, `"confirm"`, `"low_risk"`, `"full_auto"`.

---

## 4. Emergency Stop (`🛑 STOP`)

Regardless of the active autonomy level, AMATYA includes an immediate failsafe:
- **Spoken Command:** *"Emergency stop!"*, *"Abort all actions!"*, *"Halt!"*
- **HUD Button:** Click the red **`🛑 EMERGENCY STOP`** button in the Controls drawer.
- **Loopback Control:** Send an interrupt request:
  ```bash
  curl -X POST http://127.0.0.1:8765/interrupt
  ```
This terminates all running subagents, cancels pending tool invocations, silences active speech synthesis, and safely returns AMATYA to the idle state.
