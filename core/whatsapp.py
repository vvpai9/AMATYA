"""
core/whatsapp.py — AMATYA WhatsApp Autonomous Integration Engine.
==================================================================
Manages messaging, file sharing (Kundali charts, reports, PPTs), and autonomous
alert notifications via WhatsApp Web and Desktop.
"""
from __future__ import annotations

import json
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Optional

from core import outcome
from plugins._whatsapp_core import get as get_wa_transport


class WhatsAppManager:
    """Manages autonomous WhatsApp communication for AMATYA."""

    def __init__(self) -> None:
        self.transport, self.status_msg = get_wa_transport()

    def send_message(self, recipient: str, message: str) -> dict[str, Any]:
        """Dispatch a message to WhatsApp recipient (phone number or contact)."""
        if not self.transport:
            return {"ok": False, "error": self.status_msg}
        ok, err = self.transport.send_message_to(recipient, message)
        return {
            "ok": ok,
            "recipient": recipient,
            "message": message,
            "error": err,
        }

    def send_file(self, recipient: str, file_path: str, caption: str = "") -> dict[str, Any]:
        """Send a file (e.g. Kundali chart, PPT, or report) to WhatsApp recipient."""
        if not self.transport:
            return {"ok": False, "error": self.status_msg}
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        ok, err = self.transport.send_file_to(recipient, str(p), caption)
        return {
            "ok": ok,
            "recipient": recipient,
            "file": str(p),
            "error": err,
        }

    def send_autonomous_notification(self, title: str, details: str, recipient: str = "") -> dict[str, Any]:
        """Send an autonomous system completion notification via WhatsApp."""
        msg = f"🔔 [AMATYA AUTONOMOUS NOTIFICATION]\n* {title} *\n\n{details}"
        return self.send_message(recipient=recipient, message=msg)


_WA_MGR: Optional[WhatsAppManager] = None


def get_whatsapp_manager() -> WhatsAppManager:
    global _WA_MGR
    if _WA_MGR is None:
        _WA_MGR = WhatsAppManager()
    return _WA_MGR

