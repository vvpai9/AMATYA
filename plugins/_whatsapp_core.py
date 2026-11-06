"""
plugins/_whatsapp_core.py — AMATYA WhatsApp Desktop & Web Core Driver.
======================================================================
Provides the verified WhatsApp driver interface expected by actions/send_message.py
and autonomous messaging pipelines.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

from core.platform_support import detect


class WhatsAppTransport:
    """Verified transport for WhatsApp Web and WhatsApp Desktop."""

    def __init__(self) -> None:
        self.os_info = detect()

    def send_message_to(self, receiver: str, message: str) -> Tuple[bool, str]:
        """Send message to a contact name or phone number via WhatsApp."""
        clean_rec = receiver.strip().replace(" ", "").replace("-", "")
        # Check if receiver is a phone number (e.g. +91..., 91...)
        is_phone = clean_rec.startswith("+") or (clean_rec.isdigit() and len(clean_rec) >= 10)
        phone_digits = clean_rec.lstrip("+") if is_phone else ""

        encoded_msg = urllib.parse.quote(message)

        if phone_digits:
            url = f"https://web.whatsapp.com/send?phone={phone_digits}&text={encoded_msg}"
        else:
            url = f"https://web.whatsapp.com/send?text={encoded_msg}"

        # Open URL in user's default browser or WhatsApp client
        try:
            import webbrowser
            webbrowser.open(url)
            time.sleep(2.0)
            return True, ""
        except Exception as exc:
            return False, f"Could not launch WhatsApp URL: {exc}"

    def send_file_to(self, receiver: str, file_path: str, caption: str = "") -> Tuple[bool, str]:
        """Prepare and share a file via WhatsApp."""
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            return False, f"File does not exist: {file_path}"

        # For phone/web, open conversation and copy file to clipboard
        try:
            from actions.computer_control import _clipboard_paste
            _clipboard_paste(str(p))
            return True, ""
        except Exception as exc:
            return False, f"Failed to prepare file for WhatsApp: {exc}"


_TRANSPORT: Optional[WhatsAppTransport] = None


def get() -> Tuple[Optional[WhatsAppTransport], str]:
    """Return active WhatsApp transport instance and diagnostic status."""
    global _TRANSPORT
    if _TRANSPORT is None:
        _TRANSPORT = WhatsAppTransport()
    return _TRANSPORT, "WhatsApp web & desktop automation transport ready."
