"""
AMATYA Common Perception Interface (core/perception.py)
=======================================================
Phase 16 Core Objective A.1:
Unified multimodal perception engine that ingests structured events from:
  - Text chat
  - Voice transcripts
  - Desktop screen & active window context
  - System hardware & telemetry alerts
  - Connected IoT / Android devices
  - Filesystem events
  - Notifications & background task results
  - Scheduled events
"""
from __future__ import annotations

import collections
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()


class PerceptionSource(str, Enum):
    TEXT_CHAT = "text_chat"
    VOICE = "voice"
    DESKTOP_SCREEN = "desktop_screen"
    SYSTEM_EVENT = "system_event"
    DEVICE_TRIGGER = "device_trigger"
    FILESYSTEM = "filesystem"
    NOTIFICATION = "notification"
    BACKGROUND_TASK = "background_task"
    SCHEDULED_EVENT = "scheduled_event"
    EXTERNAL_SOURCE = "external_source"


class TrustLevel(str, Enum):
    VERIFIED_LOCAL = "verified_local"    # Local system sensors, OS telemetry
    USER_INPUT = "user_input"            # Direct user typing or voice
    UNTRUSTED_EXTERNAL = "untrusted_ext" # External web, webhook, or network device


@dataclass
class PerceptionEvent:
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    source: PerceptionSource = PerceptionSource.TEXT_CHAT
    event_type: str = "general"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    trust_level: TrustLevel = TrustLevel.USER_INPUT
    priority: int = 5  # 1 (highest) to 10 (lowest)
    processed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        d["trust_level"] = self.trust_level.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PerceptionEvent:
        d = dict(data)
        d["source"] = PerceptionSource(d.get("source", "text_chat"))
        d["trust_level"] = TrustLevel(d.get("trust_level", "user_input"))
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields})


class PerceptionHub:
    """Central perception hub routing all sensory inputs to cognitive subscribers."""

    def __init__(self, max_history: int = 500) -> None:
        self.max_history = max_history
        self._history: collections.deque[PerceptionEvent] = collections.deque(maxlen=max_history)
        self._subscribers: Dict[str, List[Callable[[PerceptionEvent], None]]] = collections.defaultdict(list)
        self._global_subscribers: List[Callable[[PerceptionEvent], None]] = []

    def subscribe(
        self,
        event_filter: Optional[str] = None,
        callback: Optional[Callable[[PerceptionEvent], None]] = None,
    ) -> None:
        """Subscribe a callback to a specific source/event_type, or globally if filter is None."""
        if not callback:
            return
        with _LOCK:
            if event_filter is None:
                if callback not in self._global_subscribers:
                    self._global_subscribers.append(callback)
            else:
                if callback not in self._subscribers[event_filter]:
                    self._subscribers[event_filter].append(callback)

    def publish(self, event: PerceptionEvent) -> PerceptionEvent:
        """Publish a perception event to registered listeners and store in history."""
        with _LOCK:
            self._history.append(event)
            # Find relevant callbacks
            callbacks = list(self._global_subscribers)
            callbacks.extend(self._subscribers.get(event.source.value, []))
            callbacks.extend(self._subscribers.get(event.event_type, []))

        # Invoke callbacks outside lock
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"Error in perception subscriber on {event.event_id}: {e}")
        return event

    # ── Convenient Ingestion Helpers ─────────────────────────────────────────

    def ingest_user_text(self, text: str, user: str = "user") -> PerceptionEvent:
        """Ingest text input from terminal, GUI chat, or dashboard."""
        evt = PerceptionEvent(
            source=PerceptionSource.TEXT_CHAT,
            event_type="user_message",
            payload={"text": text.strip(), "user": user},
            trust_level=TrustLevel.USER_INPUT,
            priority=3,
        )
        return self.publish(evt)

    def ingest_voice_transcript(
        self,
        transcript: str,
        confidence: float = 1.0,
        anti_spoof_passed: bool = True,
        speaker: str = "user",
    ) -> PerceptionEvent:
        """Ingest transcribed voice audio."""
        evt = PerceptionEvent(
            source=PerceptionSource.VOICE,
            event_type="voice_transcript",
            payload={
                "transcript": transcript.strip(),
                "confidence": confidence,
                "anti_spoof_passed": anti_spoof_passed,
                "speaker": speaker,
            },
            trust_level=TrustLevel.USER_INPUT,
            priority=2,
        )
        return self.publish(evt)

    def ingest_window_change(
        self,
        window_title: str,
        window_id: str = "",
        app_name: str = "",
    ) -> PerceptionEvent:
        """Ingest active desktop window / workspace focus switch."""
        evt = PerceptionEvent(
            source=PerceptionSource.DESKTOP_SCREEN,
            event_type="active_window_changed",
            payload={
                "window_title": window_title.strip(),
                "window_id": str(window_id).strip(),
                "app_name": app_name.strip(),
            },
            trust_level=TrustLevel.VERIFIED_LOCAL,
            priority=6,
        )
        return self.publish(evt)

    def ingest_system_alert(
        self,
        subsystem: str,
        metric: str,
        value: float,
        threshold: float,
        level: str = "warning",
    ) -> PerceptionEvent:
        """Ingest hardware / system telemetry alerts (thermal, disk, memory)."""
        evt = PerceptionEvent(
            source=PerceptionSource.SYSTEM_EVENT,
            event_type="telemetry_alert",
            payload={
                "subsystem": subsystem,
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "level": level,
            },
            trust_level=TrustLevel.VERIFIED_LOCAL,
            priority=1 if level in ("critical", "emergency") else 4,
        )
        return self.publish(evt)

    def ingest_device_event(
        self,
        device_id: str,
        event_type: str,
        state: Dict[str, Any],
    ) -> PerceptionEvent:
        """Ingest event from connected Android or IoT device."""
        evt = PerceptionEvent(
            source=PerceptionSource.DEVICE_TRIGGER,
            event_type=event_type,
            payload={"device_id": device_id, "state": state},
            trust_level=TrustLevel.VERIFIED_LOCAL,
            priority=5,
        )
        return self.publish(evt)

    def ingest_background_result(
        self,
        task_id: str,
        status: str,
        result: Any,
    ) -> PerceptionEvent:
        """Ingest completion/failure event of a background task."""
        evt = PerceptionEvent(
            source=PerceptionSource.BACKGROUND_TASK,
            event_type="task_outcome",
            payload={"task_id": task_id, "status": status, "result": result},
            trust_level=TrustLevel.VERIFIED_LOCAL,
            priority=3,
        )
        return self.publish(evt)

    def get_recent_events(
        self,
        source: Optional[PerceptionSource] = None,
        limit: int = 50,
    ) -> List[PerceptionEvent]:
        """Query event history filtered by source."""
        with _LOCK:
            evts = list(self._history)
            if source:
                evts = [e for e in evts if e.source == source]
            return evts[-limit:]


_PERCEPTION_HUB = PerceptionHub()


def get_perception_hub() -> PerceptionHub:
    return _PERCEPTION_HUB

