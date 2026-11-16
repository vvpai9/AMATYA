# AMATYA Autonomy, Adaptive Workflows & Proactive Intelligence

## Overview
AMATYA Phase 12 balances high autonomy with transparent user oversight. Autonomous operations never bypass security policy, and proactive interventions respect user focus and quiet hours.

---

## 1. Adaptive Workflow Engine (`core/workflow_engine.py`)

### 1.1 Routine Structure
A routine defines a repeatable, multi-step operation:
- **`workflow_id`:** Unique routine identifier.
- **`triggers`:** Trigger definitions (`manual`, `schedule`, `event`, `sensor`).
- **`steps`:** Ordered sequence of tool invocations with argument templates.
- **`required_permission_tier`:** Permission gate (Tiers 1–5).
- **`approved_by_user`:** Boolean flag. Dangerous or unapproved routines cannot be executed without explicit authorization.

### 1.2 Repetition Learning
1. The engine logs every tool invocation with its action parameter.
2. A sliding window monitors the most recent invocations within a 1-hour window.
3. If an identical 2-step tool sequence is observed 3 times (e.g. `kwin_desktop.list` followed by `kwin_desktop.snapshot`), the engine flags a candidate routine.
4. The candidate routine is submitted to the user as an actionable suggestion requiring approval before registration.

---

## 2. Proactive Intelligence Engine (`core/proactive_engine.py`)

### 2.1 Notification Priority Tiers
| Tier | Name | Example Trigger | Delivery Behavior |
|------|------|-----------------|-------------------|
| 1 | `INFORMATIONAL` | RAM dropped below 40%, background indexing done | Suppressed during quiet hours; subtle HUD banner |
| 2 | `USEFUL_SUGGESTION` | Paused task available for resumption | Suppressed during quiet hours; conversational prompt |
| 3 | `WARNING` | Device battery <= 15%, non-critical task failed | Suppressed during quiet hours; audio chime + HUD |
| 4 | `URGENT` | Routine awaiting user authorization | Delivered during quiet hours; spoken prompt |
| 5 | `CRITICAL` | Security breach, system hazard, emergency stop | Immediate spoken alert + modal display override |

### 2.2 Quiet Hours Enforcement
- **Default Window:** 23:00 to 07:00 (local time).
- Priorities 1 through 3 are held in queue and only evaluated for delivery once quiet hours conclude.
- Critical and Urgent safety notifications always break through.

### 2.3 Phrasing Guidelines (JARVIS Persona)
- **Observations:** *"Sir, an observation: [message]"*
- **Recommendations:** *"Sir, I have a recommendation: [message]"*
- **Awaiting Approval:** *"Sir, your authorization is requested: [message]"*
- **Completed Routines:** *"Sir, completed autonomous routine: [message]"*

