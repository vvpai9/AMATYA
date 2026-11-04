"""
AMATYA Security, Permission Tiers, PIN Verification & Audit Logging (core/security.py)
======================================================================================
Implements Section 5.4 (Permission-based authentication) and Section 13 (Security,
Privacy, Safety and Autonomy Controls):

Permission Tiers:
  0. GENERAL_CONVERSATION  — No additional authentication after session is active.
  1. PERSONAL_INFO         — Verified user voice or active authenticated session.
  2. PRIVATE_FILES         — Verified user voice or confirmation.
  3. REMOTE_DEVICE_CONTROL — Verified user voice or confirmation.
  4. SENSITIVE_SYSTEM      — Verified user voice PLUS explicit confirmation or PIN.
  5. CRITICAL_SECURITY     — Explicit confirmation AND PIN or system authentication.

Autonomy Levels (Section 13.1):
  1. observe_only          — Only observe and explain; block side-effecting actions.
  2. recommend             — Recommend actions without executing side-effecting ones.
  3. confirm               — Ask confirmation before sensitive actions (Tiers >= 2).
  4. autonomous_low_risk   — Execute low-risk actions (Tiers 0-2) autonomously; confirm >= 3.
  5. autonomous_workflows  — Execute approved workflows (Tiers 0-3) autonomously; confirm >= 4.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from memory.config_manager import (
    BASE_DIR,
    CONFIG_DIR,
    get_autonomy_level,
    get_voice_auth_enabled,
    save_autonomy_level,
)

SECURITY_POLICY_FILE = CONFIG_DIR / "security_policy.json"
AUDIT_LOG_FILE = BASE_DIR / "memory" / "audit.log"

_LOCK = threading.RLock()


class PermissionTier(IntEnum):
    GENERAL_CONVERSATION = 0
    PERSONAL_INFO = 1
    PRIVATE_FILES = 2
    REMOTE_DEVICE_CONTROL = 3
    SENSITIVE_SYSTEM = 4
    CRITICAL_SECURITY = 5


TIER_LABELS: dict[PermissionTier, str] = {
    PermissionTier.GENERAL_CONVERSATION: "General Conversation",
    PermissionTier.PERSONAL_INFO: "Reading Personal Information",
    PermissionTier.PRIVATE_FILES: "Modifying Private Files",
    PermissionTier.REMOTE_DEVICE_CONTROL: "Controlling Remote Devices",
    PermissionTier.SENSITIVE_SYSTEM: "Sensitive System Changes",
    PermissionTier.CRITICAL_SECURITY: "Critical Security Actions",
}

# Patterns that indicate credentials, tokens, API keys, or private keys
_SECRET_PATTERNS = [
    re.compile(r"\b(?:AIza|AQ\.)[0-9A-Za-z\-_]{28,}\b"),            # Google / Gemini API key
    re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"),                      # OpenAI / Anthropic key
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{25,}\b"),                  # GitHub token
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{15,}\b"),               # Slack token
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(api[_\-]?key|secret[_\-]?key|access[_\-]?token|bearer[_\-]?token|password|passwd|pin[_\-]?code)\s*(?:=|:|\bis\b)\s*['\"]?([^\s'\";,]{4,})"
    ),
]


def contains_secret(text: str) -> bool:
    """Return True if text appears to contain an API key, password, token, or private key."""
    if not text or not isinstance(text, str):
        return False
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def redact_secrets(text: str) -> str:
    """Redact API keys, passwords, tokens, and private keys from text."""
    if not text or not isinstance(text, str):
        return text
    out = text
    for pat in _SECRET_PATTERNS[:5]:
        out = pat.sub("[REDACTED_SECRET]", out)
    out = _SECRET_PATTERNS[5].sub(r"\1=[REDACTED_SECRET]", out)
    return out


@dataclass
class SessionAuthState:
    verified_user: str = ""
    voice_confidence: float = 0.0
    anti_spoof_passed: bool = False
    verified_at: float = 0.0
    pin_verified_at: float = 0.0
    session_ttl_sec: float = 900.0  # 15 minutes

    def is_voice_active(self) -> bool:
        if not self.verified_user or self.verified_at <= 0:
            return False
        return (time.time() - self.verified_at) <= self.session_ttl_sec

    def is_pin_active(self, ttl_sec: float = 300.0) -> bool:
        if self.pin_verified_at <= 0:
            return False
        return (time.time() - self.pin_verified_at) <= ttl_sec


_SESSION_STATE = SessionAuthState()


def _load_policy() -> dict[str, Any]:
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not SECURITY_POLICY_FILE.exists():
            return {}
        try:
            return json.loads(SECURITY_POLICY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_policy(data: dict[str, Any]) -> None:
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SECURITY_POLICY_FILE.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        try:
            os.chmod(SECURITY_POLICY_FILE, 0o600)
        except Exception:
            pass


def log_audit_event(
    event_type: str,
    operation: str,
    tier: int | PermissionTier,
    allowed: bool,
    reason: str = "",
    user: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Append a structured JSON line to memory/audit.log with 0600 permissions."""
    with _LOCK:
        try:
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "epoch": round(time.time(), 3),
                "event_type": event_type,
                "operation": redact_secrets(str(operation)),
                "tier": int(tier),
                "tier_label": TIER_LABELS.get(PermissionTier(int(tier)), str(tier)),
                "autonomy_level": get_autonomy_level(),
                "allowed": bool(allowed),
                "user": user or _SESSION_STATE.verified_user or "unverified",
                "reason": redact_secrets(str(reason)),
                "details": details or {},
            }
            with AUDIT_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            try:
                os.chmod(AUDIT_LOG_FILE, 0o600)
            except Exception:
                pass
        except Exception:
            pass


def read_audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent audit log entries."""
    with _LOCK:
        if not AUDIT_LOG_FILE.exists():
            return []
        try:
            lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
            entries = []
            for line in lines[-max(1, int(limit)):]:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        continue
            return entries
        except Exception:
            return []


# ── PIN Management (PBKDF2-HMAC-SHA256) ──────────────────────────────────────

def has_pin() -> bool:
    pol = _load_policy()
    return bool(pol.get("pin_hash") and pol.get("pin_salt"))


def set_pin(pin: str) -> tuple[bool, str]:
    """Set or update the security PIN (4-16 digits/characters)."""
    clean = (pin or "").strip()
    if len(clean) < 4 or len(clean) > 32:
        return False, "PIN must be between 4 and 32 characters."
    salt = secrets.token_bytes(16)
    iterations = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", clean.encode("utf-8"), salt, iterations)
    pol = _load_policy()
    pol["pin_salt"] = salt.hex()
    pol["pin_hash"] = dk.hex()
    pol["pin_iterations"] = iterations
    pol["pin_updated_at"] = time.time()
    _save_policy(pol)
    log_audit_event(
        "pin_configured",
        "set_pin",
        PermissionTier.CRITICAL_SECURITY,
        True,
        "Security PIN configured.",
    )
    return True, "Security PIN set and stored with PBKDF2-HMAC-SHA256 (0600 permissions)."


def verify_pin(pin: str) -> tuple[bool, str]:
    """Verify a candidate PIN against the stored PBKDF2-HMAC-SHA256 hash."""
    clean = (pin or "").strip()
    pol = _load_policy()
    salt_hex = pol.get("pin_salt")
    hash_hex = pol.get("pin_hash")
    iterations = int(pol.get("pin_iterations", 200_000))
    if not salt_hex or not hash_hex:
        return False, "No security PIN is configured yet."
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", clean.encode("utf-8"), salt, iterations)
        matched = hmac.compare_digest(candidate, expected)
    except Exception as exc:
        return False, f"PIN verification error: {exc}"

    if matched:
        with _LOCK:
            _SESSION_STATE.pin_verified_at = time.time()
        log_audit_event(
            "pin_verified",
            "verify_pin",
            PermissionTier.SENSITIVE_SYSTEM,
            True,
            "PIN verified successfully.",
        )
        return True, "PIN verified."
    else:
        log_audit_event(
            "pin_failed",
            "verify_pin",
            PermissionTier.SENSITIVE_SYSTEM,
            False,
            "Invalid PIN provided.",
        )
        return False, "Invalid PIN."


def clear_pin(current_pin: str) -> tuple[bool, str]:
    """Remove stored PIN after verifying current_pin."""
    ok, msg = verify_pin(current_pin)
    if not ok:
        return False, msg
    pol = _load_policy()
    pol.pop("pin_salt", None)
    pol.pop("pin_hash", None)
    pol.pop("pin_iterations", None)
    _save_policy(pol)
    with _LOCK:
        _SESSION_STATE.pin_verified_at = 0.0
    log_audit_event(
        "pin_cleared",
        "clear_pin",
        PermissionTier.CRITICAL_SECURITY,
        True,
        "Security PIN removed.",
    )
    return True, "Security PIN removed."


# ── Session Authentication State ─────────────────────────────────────────────

def mark_voice_verified(
    user_name: str,
    confidence: float,
    anti_spoof_passed: bool = True,
    ttl_sec: float = 900.0,
) -> None:
    with _LOCK:
        _SESSION_STATE.verified_user = user_name
        _SESSION_STATE.voice_confidence = float(confidence)
        _SESSION_STATE.anti_spoof_passed = bool(anti_spoof_passed)
        _SESSION_STATE.verified_at = time.time()
        _SESSION_STATE.session_ttl_sec = float(ttl_sec)
    log_audit_event(
        "voice_verified",
        "speaker_verification",
        PermissionTier.PERSONAL_INFO,
        True,
        f"Speaker verified as '{user_name}' (score={confidence:.3f}, anti_spoof={anti_spoof_passed})",
        user=user_name,
    )


def clear_session_auth() -> None:
    with _LOCK:
        _SESSION_STATE.verified_user = ""
        _SESSION_STATE.voice_confidence = 0.0
        _SESSION_STATE.anti_spoof_passed = False
        _SESSION_STATE.verified_at = 0.0
        _SESSION_STATE.pin_verified_at = 0.0


def get_session_auth_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "voice_auth_enabled": get_voice_auth_enabled(),
            "verified_user": _SESSION_STATE.verified_user if _SESSION_STATE.is_voice_active() else "",
            "voice_confidence": round(_SESSION_STATE.voice_confidence, 4),
            "anti_spoof_passed": _SESSION_STATE.anti_spoof_passed,
            "voice_session_active": _SESSION_STATE.is_voice_active(),
            "pin_configured": has_pin(),
            "pin_session_active": _SESSION_STATE.is_pin_active(),
            "autonomy_level": get_autonomy_level(),
        }


# ── Permission Check Engine ──────────────────────────────────────────────────

def check_permission(
    operation: str,
    tier: int | PermissionTier,
    description: str = "",
    pin: str | None = None,
    interactive_confirm: bool = True,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Evaluate whether `operation` at `tier` is permitted under the current
    autonomy level, voice authentication status, PIN, and confirmation gate.

    Returns:
      {
        "allowed": bool,
        "tier": int,
        "tier_label": str,
        "autonomy_level": str,
        "reason": str,
        "requires_confirmation": bool,
        "requires_voice_auth": bool,
        "requires_pin": bool,
      }
    """
    ptier = PermissionTier(int(tier))
    autonomy = get_autonomy_level()
    voice_auth_on = get_voice_auth_enabled()
    voice_ok = _SESSION_STATE.is_voice_active() and _SESSION_STATE.anti_spoof_passed

    # If a PIN was explicitly supplied with the call, verify it right away
    if pin:
        verify_pin(pin)
    pin_ok = _SESSION_STATE.is_pin_active()

    # 1. Check Autonomy Level blocks for side-effecting operations (Tiers >= 2)
    if ptier >= PermissionTier.PRIVATE_FILES:
        if autonomy == "observe_only":
            reason = (
                f"Blocked by Autonomy Level 1 (observe_only): '{operation}' "
                f"modifies state ({TIER_LABELS[ptier]})."
            )
            log_audit_event("permission_denied", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": False,
                "requires_voice_auth": False,
                "requires_pin": False,
            }
        if autonomy == "recommend":
            reason = (
                f"Autonomy Level 2 (recommend): '{operation}' is recommended "
                f"({description or TIER_LABELS[ptier]}), not executed automatically."
            )
            log_audit_event("permission_recommend_only", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": True,
                "requires_voice_auth": False,
                "requires_pin": False,
            }

    # 2. Tier 0: General Conversation
    if ptier == PermissionTier.GENERAL_CONVERSATION:
        return {
            "allowed": True,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": "General conversation permitted.",
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # 3. Tier 1: Reading Personal Information
    # Requires verified user voice (when voice_auth_enabled) or active authenticated session
    if ptier == PermissionTier.PERSONAL_INFO:
        if voice_auth_on and not (voice_ok or pin_ok):
            reason = (
                f"Voice authentication required for '{operation}' ({TIER_LABELS[ptier]}). "
                "Please verify your voice or provide your PIN."
            )
            log_audit_event("permission_denied", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": False,
                "requires_voice_auth": True,
                "requires_pin": False,
            }
        log_audit_event("permission_granted", operation, ptier, True, "Personal info access permitted.")
        return {
            "allowed": True,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": "Permitted under active session.",
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # 4. Tier 2 (Private Files) & Tier 3 (Remote Device Control)
    # Require verified user voice OR confirmation depending on autonomy level
    if ptier in (PermissionTier.PRIVATE_FILES, PermissionTier.REMOTE_DEVICE_CONTROL):
        auto_allowed = (
            (ptier == PermissionTier.PRIVATE_FILES and autonomy in ("autonomous_low_risk", "autonomous_workflows"))
            or (ptier == PermissionTier.REMOTE_DEVICE_CONTROL and autonomy == "autonomous_workflows")
        )
        if voice_auth_on and not (voice_ok or pin_ok or confirmed):
            if not interactive_confirm:
                reason = f"Voice verification or confirmation required for '{operation}'."
                log_audit_event("permission_denied", operation, ptier, False, reason)
                return {
                    "allowed": False,
                    "tier": int(ptier),
                    "tier_label": TIER_LABELS[ptier],
                    "autonomy_level": autonomy,
                    "reason": reason,
                    "requires_confirmation": True,
                    "requires_voice_auth": True,
                    "requires_pin": False,
                }
        if not auto_allowed and not (voice_ok or pin_ok or confirmed):
            if interactive_confirm:
                try:
                    from core.confirm import request_confirmation
                    approved = request_confirmation(
                        operation,
                        description or f"{TIER_LABELS[ptier]}: {operation}",
                    )
                except Exception:
                    approved = False
                if not approved:
                    reason = f"User declined or confirmation timed out for '{operation}'."
                    log_audit_event("permission_denied", operation, ptier, False, reason)
                    return {
                        "allowed": False,
                        "tier": int(ptier),
                        "tier_label": TIER_LABELS[ptier],
                        "autonomy_level": autonomy,
                        "reason": reason,
                        "requires_confirmation": True,
                        "requires_voice_auth": voice_auth_on,
                        "requires_pin": False,
                    }
        log_audit_event("permission_granted", operation, ptier, True, f"Permitted ({autonomy}).")
        return {
            "allowed": True,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": f"Permitted ({TIER_LABELS[ptier]}).",
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # 5. Tier 4: Sensitive System Changes
    # Verified user voice PLUS explicit confirmation or PIN
    if ptier == PermissionTier.SENSITIVE_SYSTEM:
        if voice_auth_on and not (voice_ok or pin_ok or confirmed):
            reason = (
                f"Sensitive system operation '{operation}' requires verified voice, PIN, or confirmation."
            )
            log_audit_event("permission_denied", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": True,
                "requires_voice_auth": True,
                "requires_pin": has_pin(),
            }
        if not (pin_ok or confirmed):
            if interactive_confirm:
                try:
                    from core.confirm import request_confirmation
                    approved = request_confirmation(
                        operation,
                        description or f"Sensitive system operation: {operation}",
                    )
                except Exception:
                    approved = False
                if not approved:
                    reason = f"Explicit confirmation required and not granted for '{operation}'."
                    log_audit_event("permission_denied", operation, ptier, False, reason)
                    return {
                        "allowed": False,
                        "tier": int(ptier),
                        "tier_label": TIER_LABELS[ptier],
                        "autonomy_level": autonomy,
                        "reason": reason,
                        "requires_confirmation": True,
                        "requires_voice_auth": voice_auth_on,
                        "requires_pin": has_pin(),
                    }
            else:
                reason = f"Explicit confirmation or PIN required for '{operation}'."
                log_audit_event("permission_denied", operation, ptier, False, reason)
                return {
                    "allowed": False,
                    "tier": int(ptier),
                    "tier_label": TIER_LABELS[ptier],
                    "autonomy_level": autonomy,
                    "reason": reason,
                    "requires_confirmation": True,
                    "requires_voice_auth": voice_auth_on,
                    "requires_pin": has_pin(),
                }

        log_audit_event("permission_granted", operation, ptier, True, "Sensitive system action confirmed.")
        return {
            "allowed": True,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": "Sensitive system action authorized.",
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # 6. Tier 5: Critical Security Actions
    # Explicit confirmation AND PIN (if configured)
    if has_pin() and not pin_ok:
        reason = f"Critical security operation '{operation}' requires a valid security PIN."
        log_audit_event("permission_denied", operation, ptier, False, reason)
        return {
            "allowed": False,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": reason,
            "requires_confirmation": True,
            "requires_voice_auth": voice_auth_on,
            "requires_pin": True,
        }
    if not (pin_ok or confirmed):
        if interactive_confirm:
            try:
                from core.confirm import request_confirmation
                approved = request_confirmation(
                    operation,
                    description or f"CRITICAL SECURITY ACTION: {operation}",
                )
            except Exception:
                approved = False
            if not approved:
                reason = f"Critical security operation '{operation}' was not confirmed."
                log_audit_event("permission_denied", operation, ptier, False, reason)
                return {
                    "allowed": False,
                    "tier": int(ptier),
                    "tier_label": TIER_LABELS[ptier],
                    "autonomy_level": autonomy,
                    "reason": reason,
                    "requires_confirmation": True,
                    "requires_voice_auth": voice_auth_on,
                    "requires_pin": has_pin(),
                }
        else:
            reason = f"Critical security operation '{operation}' requires explicit confirmation or PIN."
            log_audit_event("permission_denied", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": True,
                "requires_voice_auth": voice_auth_on,
                "requires_pin": has_pin(),
            }
            log_audit_event("permission_denied", operation, ptier, False, reason)
            return {
                "allowed": False,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": reason,
                "requires_confirmation": True,
                "requires_voice_auth": voice_auth_on,
                "requires_pin": has_pin(),
            }

    log_audit_event("permission_granted", operation, ptier, True, "Critical security action authorized.")
    return {
        "allowed": True,
        "tier": int(ptier),
        "tier_label": TIER_LABELS[ptier],
        "autonomy_level": autonomy,
        "reason": "Critical security action authorized.",
        "requires_confirmation": False,
        "requires_voice_auth": False,
        "requires_pin": False,
    }
