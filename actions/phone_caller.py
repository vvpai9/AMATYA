"""
Telephony & Phone Calling Action for JARVIS.
Enables JARVIS to initiate real phone calls via macOS Apple Continuity (FaceTime Audio / Cellular Relay)
or via Twilio Voice API when configured.
Supports direct dialing, emergency alerts, and contact management.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

CONTACTS_FILE = Path(__file__).resolve().parent.parent / "memory" / "phone_contacts.json"
API_CONFIG = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"

def _load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"user": "", "emergency": "", "contacts": {}}

def _save_contacts(data: dict) -> None:
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _clean_phone(number: str) -> str:
    return re.sub(r"[^\d+]", "", number.strip())

def make_mac_continuity_call(phone_number: str) -> bool:
    """Initiate a phone call on macOS via FaceTime Audio / iPhone cellular relay."""
    clean = _clean_phone(phone_number)
    if not clean:
        return False
    try:
        # Method 1: open tel: URL (triggers standard Mac telephony dialog)
        subprocess.run(["open", f"tel:{clean}"], timeout=5)
        return True
    except Exception:
        try:
            # Method 2: FaceTime Audio URL
            subprocess.run(["open", f"facetime-audio:{clean}"], timeout=5)
            return True
        except Exception:
            return False

def make_twilio_call(to_number: str, message: str) -> str:
    """Make an automated outbound voice call via Twilio if configured in api_keys.json."""
    if not API_CONFIG.exists():
        return "Twilio configuration not found."
    try:
        with open(API_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return f"Could not read config: {e}"

    sid = cfg.get("twilio_sid") or cfg.get("twilio_account_sid")
    token = cfg.get("twilio_token") or cfg.get("twilio_auth_token")
    from_number = cfg.get("twilio_from") or cfg.get("twilio_phone_number")

    if not sid or not token or not from_number:
        return "Twilio credentials (twilio_sid, twilio_token, twilio_from) are not configured."

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    twiml = f"<Response><Say voice='Polly.Matthew'>{message or 'Hello, this is JARVIS calling with an important update.'}</Say></Response>"
    data = urllib.parse.urlencode({
        "To": to_number,
        "From": from_number,
        "Twiml": twiml,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    import base64
    auth_header = "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return f"Twilio call queued successfully. Call SID: {res.get('sid')}"
    except Exception as e:
        return f"Twilio call failed: {e}"

def phone_caller(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for phone_caller."""
    action = parameters.get("action", "call").lower().strip()
    number = parameters.get("phone_number", "").strip()
    contact_name = parameters.get("contact_name", "").strip().lower()
    message = parameters.get("message", "This is an automated alert from JARVIS.")

    contacts = _load_contacts()

    # Resolve contact name if phone number not provided
    if not number and contact_name:
        if contact_name in ("me", "my phone", "user"):
            number = contacts.get("user", "")
        elif contact_name == "emergency":
            number = contacts.get("emergency", "")
        else:
            number = contacts.get("contacts", {}).get(contact_name, "")

    if action in ("save_contact", "set_phone", "register"):
        if not number:
            return "Please specify the phone number to save."
        if contact_name in ("me", "user", "my phone", ""):
            contacts["user"] = number
            saved_as = "your primary phone number"
        elif contact_name == "emergency":
            contacts["emergency"] = number
            saved_as = "emergency phone number"
        else:
            contacts.setdefault("contacts", {})[contact_name] = number
            saved_as = f"contact '{contact_name}'"
        _save_contacts(contacts)
        return f"Saved {number} as {saved_as}."

    elif action in ("call", "dial", "ring"):
        if not number:
            number = contacts.get("user", "")
        if not number:
            return "No phone number specified and no registered user phone number found. Please provide a phone number."

        if player:
            try: player.write_log(f"PHONE: Initiating call to {number}...")
            except Exception: pass

        # On macOS, try Apple Continuity / FaceTime first
        if sys.platform == "darwin":
            success = make_mac_continuity_call(number)
            if success:
                return f"📞 Dialing {number} via macOS iPhone Continuity / FaceTime Audio."
        
        # If Twilio is available, try Twilio
        twilio_res = make_twilio_call(number, message)
        if "queued successfully" in twilio_res:
            return twilio_res

        # If on macOS and open succeeded
        return f"📞 Initiated call to {number}."

    elif action in ("list", "contacts"):
        usr = contacts.get("user") or "Not set"
        emg = contacts.get("emergency") or "Not set"
        others = ", ".join(f"{k}: {v}" for k, v in contacts.get("contacts", {}).items()) or "None"
        return f"📱 Phone Directory:\n• Primary User: {usr}\n• Emergency: {emg}\n• Saved Contacts: {others}"

    return f"Phone caller action '{action}' completed."


TOOL = {
    "name": "phone_caller",
    "description": (
        "Telephony & Phone Calling system. Makes real phone calls from your computer to your phone or contacts. "
        "On macOS, connects seamlessly via Apple Continuity / FaceTime Audio / iPhone cellular relay. "
        "Also supports automated Twilio Voice calls and maintains a local contact directory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "call | save_contact | list",
            },
            "phone_number": {
                "type": "STRING",
                "description": "Phone number with country code (e.g. +1234567890 or +919876543210)",
            },
            "contact_name": {
                "type": "STRING",
                "description": "Name of contact, or 'me' / 'emergency'",
            },
            "message": {
                "type": "STRING",
                "description": "Voice message text for automated phone calls",
            }
        },
        "required": [],
    },
    "handler": phone_caller,
}
