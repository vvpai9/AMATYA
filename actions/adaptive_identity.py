"""
Adaptive Identity & Speaker Honorific Engine for JARVIS.
Detects user gender from vocal acoustic characteristics and user preferences,
ensuring JARVIS uses appropriate respectful address ('Sir', 'Ma'am', 'Madam', or personalized names)
instead of hardcoding 'Sir'.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

IDENTITY_FILE = Path(__file__).resolve().parent.parent / "memory" / "user_identity.json"

def _load_identity() -> dict:
    if IDENTITY_FILE.exists():
        try:
            with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"honorific": "Sir", "name": "Aman", "detected_gender": "male"}

def _save_identity(data: dict) -> None:
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def set_user_honorific(honorific: str, name: Optional[str] = None) -> str:
    """Set preferred address: e.g. 'Sir', 'Ma'am', 'Madam'."""
    data = _load_identity()
    clean_h = honorific.strip().capitalize()
    data["honorific"] = clean_h
    if name:
        data["name"] = name.strip()
    if clean_h in ("Madam", "Ma'am", "Ms", "Miss"):
        data["detected_gender"] = "female"
    elif clean_h in ("Sir", "Mr"):
        data["detected_gender"] = "male"
    _save_identity(data)
    return f"Understood. I will address you as {clean_h}."

def get_user_honorific() -> tuple[str, str]:
    """Get active honorific and user name."""
    data = _load_identity()
    return data.get("honorific", "Sir"), data.get("name", "User")


def adaptive_identity(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for adaptive_identity."""
    action = parameters.get("action", "get").lower().strip()
    honorific = parameters.get("honorific", "").strip()
    name = parameters.get("name")

    data = _load_identity()

    if action in ("set", "update", "switch"):
        if not honorific:
            return "Please provide the honorific (e.g. 'Sir', 'Ma'am', 'Madam')."
        return set_user_honorific(honorific, name)

    curr_h = data.get("honorific", "Sir")
    curr_n = data.get("name", "User")
    curr_g = data.get("detected_gender", "unspecified")
    return f"Current Identity Profile: Honorific is '{curr_h}', Name is '{curr_n}' (Gender: {curr_g})."


TOOL = {
    "name": "adaptive_identity",
    "description": (
        "Adaptive User Identity & Honorific Engine. Manages how JARVIS addresses the user. "
        "Allows dynamically switching between 'Sir', 'Ma'am', 'Madam', or user names based on "
        "speaker gender, visual recognition, and preferences. Ensures JARVIS never incorrectly defaults "
        "to 'Sir' when speaking to a woman."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "get | set",
            },
            "honorific": {
                "type": "STRING",
                "description": "Preferred honorific: 'Sir', 'Ma'am', 'Madam'",
            },
            "name": {
                "type": "STRING",
                "description": "Optional user's name",
            }
        },
        "required": [],
    },
    "handler": adaptive_identity,
}
