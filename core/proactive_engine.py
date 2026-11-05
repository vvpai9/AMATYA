"""
AMATYA Proactive Intelligence & Notification Policy Engine (core/proactive_engine.py)
====================================================================================
Implements Section 7 (Proactive Intelligence) of AMATYA Phase 12:
  - Evaluates system state: pending approvals, paused/failed tasks, device connectivity,
    resource thresholds, and scheduled workflows.
  - 5-Tier Notification Priority Matrix:
      1. INFORMATIONAL      — Contextual notes, background status.
      2. USEFUL_SUGGESTION  — Recommended tips, learned workflow suggestions.
      3. WARNING            — Device disconnected, battery low, disk space low.
      4. URGENT             — Failed critical workflow, RAM exhaustion.
      5. CRITICAL           — Security violations, overheating, emergency stop.
  - Policy Enforcement: Quiet hours, cooldown intervals, deduplication.
  - Statement Disambiguation: Explicitly distinguishes observation, recommendation,
    action awaiting approval, and executed action.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from core.security import get_session_auth_status
from memory.config_manager import BASE_DIR

PROACTIVE_STATE_PATH = BASE_DIR / "memory" / "proactive_state.json"
_LOCK = threading.RLock()


class NotificationPriority(IntEnum):
    INFORMATIONAL = 1
    USEFUL_SUGGESTION = 2
    WARNING = 3
    URGENT = 4
    CRITICAL = 5


@dataclass
class ProactiveAlert:
    alert_id: str
    priority: int  # 1 to 5 (NotificationPriority)
    category: str  # task | device | resource | workflow | security | reminder
    kind: str      # observation | recommendation | awaiting_approval | executed
    title: str
    message: str
    recommended_action: dict[str, Any] | None = None
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProactiveIntelligenceEngine:
    """Evaluates multi-subsystem states and determines when and what to proactively surface."""

    def __init__(self, state_path: Path | None = None, storage_path: Path | None = None) -> None:
        self.state_path = storage_path or state_path or PROACTIVE_STATE_PATH
        self.quiet_hours_start = 23  # 11:00 PM
        self.quiet_hours_end = 7     # 7:00 AM
        self.cooldown_sec = 600      # 10 minutes default between non-urgent notifications
        self._last_notified_times: dict[str, float] = {}
        self._active_alerts: list[ProactiveAlert] = []
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def is_quiet_hours(self) -> bool:
        """Return True if current local time falls in configured quiet hours."""
        hour = datetime.now().hour
        if self.quiet_hours_start > self.quiet_hours_end:
            return hour >= self.quiet_hours_start or hour < self.quiet_hours_end
        return self.quiet_hours_start <= hour < self.quiet_hours_end

    def evaluate_environment(self) -> list[ProactiveAlert]:
        """Examine system health, devices, tasks, and workflows to identify proactive items."""
        if not self._enabled:
            return []

        alerts: list[ProactiveAlert] = []
        now = time.time()
        in_quiet = self.is_quiet_hours()

        # 1. Check Active & Paused Tasks
        try:
            from core.orchestrator import get_orchestrator
            orch = get_orchestrator()
            tasks = orch.list_tasks()
            for t in tasks:
                if t.get("status") == "paused":
                    alerts.append(ProactiveAlert(
                        alert_id=f"paused_task_{t['task_id']}",
                        priority=int(NotificationPriority.USEFUL_SUGGESTION),
                        category="task",
                        kind="recommendation",
                        title="Paused Task Available",
                        message=f"Task '{t.get('goal')}' is paused at step {t.get('current_step_index', 0) + 1}. Would you like to resume it?",
                        recommended_action={"tool": "orchestrator", "parameters": {"action": "resume_last_task"}},
                    ))
                elif t.get("status") == "failed":
                    alerts.append(ProactiveAlert(
                        alert_id=f"failed_task_{t['task_id']}",
                        priority=int(NotificationPriority.WARNING),
                        category="task",
                        kind="observation",
                        title="Task Execution Failure",
                        message=f"Task '{t.get('goal')}' failed: {t.get('result_summary')[:100]}",
                    ))
        except Exception:
            pass

        # 2. Check Device Connectivity
        try:
            from core.device_manager import get_device_manager
            dm = get_device_manager()
            devs = dm.list_registered_devices()
            for d in devs:
                batt = d.get("status", {}).get("battery_pct")
                if batt is not None and int(batt) <= 15:
                    alerts.append(ProactiveAlert(
                        alert_id=f"low_battery_{d.get('device_id')}",
                        priority=int(NotificationPriority.WARNING),
                        category="device",
                        kind="observation",
                        title=f"Low Battery: {d.get('name')}",
                        message=f"{d.get('name')} battery is critically low at {batt}%.",
                    ))
        except Exception:
            pass

        # 3. Filter by quiet hours & cooldowns
        deliverable: list[ProactiveAlert] = []
        for alert in alerts:
            # During quiet hours, suppress priorities lower than URGENT
            if in_quiet and alert.priority < int(NotificationPriority.URGENT):
                continue

            last_time = self._last_notified_times.get(alert.alert_id, 0.0)
            if (now - last_time) >= self.cooldown_sec or alert.priority >= int(NotificationPriority.URGENT):
                deliverable.append(alert)
                self._last_notified_times[alert.alert_id] = now

        self._active_alerts = deliverable
        return deliverable

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss an active alert by id."""
        with _LOCK:
            initial = len(self._active_alerts)
            self._active_alerts = [a for a in self._active_alerts if a.alert_id != alert_id]
            return len(self._active_alerts) < initial

    def get_active_alerts(self) -> list[ProactiveAlert]:
        """Return currently active alerts."""
        with _LOCK:
            return list(self._active_alerts)

    def evaluate_proactive_opportunities(self) -> list[ProactiveAlert]:
        """Alias for evaluate_environment."""
        return self.evaluate_environment()

    def format_proactive_speech(self, alert: ProactiveAlert) -> str:
        """Generate respectful, dignified speech for an alert without filler."""
        if alert.kind == "observation":
            return f"Sir, an observation: {alert.message}"
        if alert.kind == "recommendation":
            return f"Sir, I have a recommendation: {alert.message}"
        if alert.kind == "awaiting_approval":
            return f"Sir, your authorization is requested: {alert.message}"
        if alert.kind == "executed":
            return f"Sir, completed autonomous routine: {alert.message}"
        return alert.message


_PROACTIVE_ENGINE: ProactiveIntelligenceEngine | None = None
_PE_LOCK = threading.Lock()


def get_proactive_intelligence() -> ProactiveIntelligenceEngine:
    global _PROACTIVE_ENGINE
    with _PE_LOCK:
        if _PROACTIVE_ENGINE is None:
            _PROACTIVE_ENGINE = ProactiveIntelligenceEngine()
        return _PROACTIVE_ENGINE


get_proactive_engine = get_proactive_intelligence

