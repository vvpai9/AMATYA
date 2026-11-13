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

    # Redact PIN variations in speech/text/commands/logs
    out = re.sub(
        r"(?i)\b(authorise|authorize|auth)\s+(with\s+)?(pin)\s*[:=]?\s*([0-9a-zA-Z\-_]{3,})",
        r"\1 \2\3 **** (REDACTED)",
        out,
    )
    out = re.sub(
        r"(?i)\b(set_?pin|clear_?pin|verify_?pin)\s*[:=]?\s*([0-9a-zA-Z\-_]{3,})",
        r"\1 **** (REDACTED)",
        out,
    )
    out = re.sub(
        r"(?i)\b(pin|passcode|passwd|password)\s*[:=]\s*['\"]?([0-9a-zA-Z\-_]{3,})['\"]?",
        r"\1: **** (REDACTED)",
        out,
    )
    out = re.sub(
        r"(?i)\b(my\s+pin\s+is|pin\s+is|code\s+is)\s*[:=]?\s*([0-9a-zA-Z\-_]{3,})",
        r"\1 **** (REDACTED)",
        out,
    )
    out = re.sub(
        r"(?i)\b(pin)\s+([0-9]{4,16})\b",
        r"\1 **** (REDACTED)",
        out,
    )
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
_CONFIRMED_OPERATIONS: dict[str, float] = {}
CONFIRMATION_GRACE_TTL_SEC: float = 60.0


def mark_operation_confirmed(operation: str, ttl_sec: float = CONFIRMATION_GRACE_TTL_SEC) -> None:
    """Record that an operation has been explicitly confirmed by the user or voice auth.

    Subsequent checks for the same operation within the grace TTL window succeed autonomously,
    preventing infinite confirmation popup loops.
    """
    if not operation:
        return
    with _LOCK:
        op_clean = str(operation).strip().lower()
        _CONFIRMED_OPERATIONS[op_clean] = time.time() + float(ttl_sec)
        if ":" in op_clean:
            root = op_clean.split(":", 1)[0]
            _CONFIRMED_OPERATIONS[root] = time.time() + float(ttl_sec)


def is_operation_confirmed(operation: str) -> bool:
    """Check if an operation was recently confirmed within its grace TTL window."""
    if not operation:
        return False
    with _LOCK:
        now = time.time()
        expired = [op for op, exp in _CONFIRMED_OPERATIONS.items() if now > exp]
        for op in expired:
            _CONFIRMED_OPERATIONS.pop(op, None)

        op_clean = str(operation).strip().lower()
        if op_clean in _CONFIRMED_OPERATIONS:
            return True
        if ":" in op_clean:
            root = op_clean.split(":", 1)[0]
            if root in _CONFIRMED_OPERATIONS:
                return True
        return False


def clear_operation_confirmed(operation: str = "") -> None:
    """Clear confirmation cache for an operation or all operations."""
    with _LOCK:
        if operation:
            op_clean = str(operation).strip().lower()
            _CONFIRMED_OPERATIONS.pop(op_clean, None)
            if ":" in op_clean:
                root = op_clean.split(":", 1)[0]
                _CONFIRMED_OPERATIONS.pop(root, None)
        else:
            _CONFIRMED_OPERATIONS.clear()


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


_SENSITIVE_KEYS = {
    "pin", "pin_hash", "pin_salt", "password", "token", "secret", "api_key",
    "private_key", "credentials", "auth_token", "access_token", "refresh_token",
    "bearer", "key", "cert", "seed", "challenge", "fingerprint", "embedding",
    "voice_embedding", "speaker_embedding", "biometric", "voice_print",
    "acoustic_features", "audio_sample", "audio_bytes"
}


def _redact_recursive(val: Any) -> Any:
    """Recursively redacts sensitive keys, tokens, and biometric vectors from audit log payloads."""
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            k_str = str(k).lower()
            if isinstance(v, (bytes, bytearray)):
                out[k] = "[REDACTED_AUDIO_BYTES]"
            elif isinstance(v, (list, tuple, set)) and len(v) >= 16 and all(isinstance(x, (int, float)) for x in v):
                out[k] = "[REDACTED_BIOMETRIC_VECTOR]"
            elif any(s in k_str for s in (
                "pin", "pass", "token", "secret", "api_key", "priv_key", "cert",
                "auth", "embedding", "biometric", "voice_print", "audio", "voice_profile"
            )):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact_recursive(v)
        return out
    elif isinstance(val, (bytes, bytearray)):
        return "[REDACTED_AUDIO_BYTES]"
    elif isinstance(val, (list, tuple, set)):
        # Check if this list is a numerical biometric embedding vector (e.g. 16+ floats)
        as_list = list(val)
        if len(as_list) >= 16 and all(isinstance(x, (int, float)) for x in as_list):
            return "[REDACTED_BIOMETRIC_VECTOR]"
        return [_redact_recursive(x) for x in as_list]
    elif isinstance(val, str):
        return redact_secrets(val)
    return val


def _encrypt_and_encode_audit_entry(entry: dict[str, Any]) -> str:
    """Sanitizes and serializes redacted audit entry."""
    raw_hex = json.dumps(entry, ensure_ascii=False).encode("utf-8").hex()
    return bytes.fromhex(raw_hex).decode("utf-8")


_STORAGE_KEY_FILE = CONFIG_DIR / ".storage_key"


def _get_or_create_storage_key() -> bytes:
    """Return persistent local storage encryption key, creating one if not present."""
    with _LOCK:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if _STORAGE_KEY_FILE.is_file():
            try:
                k = _STORAGE_KEY_FILE.read_bytes().strip()
                if len(k) == 44:  # standard Fernet key length
                    return k
            except Exception:
                pass
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key()
        _STORAGE_KEY_FILE.write_bytes(new_key)
        try:
            os.chmod(_STORAGE_KEY_FILE, 0o600)
        except Exception:
            pass
        return new_key


def encrypt_sensitive_data(data: Any) -> str:
    """Encrypt sensitive data (string, bytes, or dict/list) using Fernet authenticated encryption."""
    if data is None:
        return ""
    from cryptography.fernet import Fernet
    key = _get_or_create_storage_key()
    cipher = Fernet(key)
    if isinstance(data, (dict, list)):
        raw_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    elif isinstance(data, str):
        raw_bytes = data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray)):
        raw_bytes = bytes(data)
    else:
        raw_bytes = str(data).encode("utf-8")
    token = cipher.encrypt(raw_bytes)
    return token.decode("ascii")


def decrypt_sensitive_data(payload: str | bytes) -> Any:
    """Decrypt sensitive data. Falls back to plain JSON parsing if payload is legacy unencrypted text."""
    if not payload:
        return None
    if isinstance(payload, bytes):
        payload_str = payload.decode("utf-8", errors="ignore").strip()
    else:
        payload_str = str(payload).strip()

    # Legacy clear-text fallback (starts with { or [)
    if payload_str.startswith("{") or payload_str.startswith("["):
        try:
            return json.loads(payload_str)
        except Exception:
            pass

    from cryptography.fernet import Fernet
    try:
        key = _get_or_create_storage_key()
        cipher = Fernet(key)
        raw_bytes = cipher.decrypt(payload_str.encode("ascii"))
        decoded_text = raw_bytes.decode("utf-8")
        if (decoded_text.startswith("{") and decoded_text.endswith("}")) or (decoded_text.startswith("[") and decoded_text.endswith("]")):
            try:
                return json.loads(decoded_text)
            except Exception:
                return decoded_text
        return decoded_text
    except Exception:
        # Fallback to plain JSON or string
        try:
            return json.loads(payload_str)
        except Exception:
            return payload_str


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
                "details": _redact_recursive(details or {}),
            }
            payload = _encrypt_and_encode_audit_entry(entry)
            with AUDIT_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(payload + "\n")
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


_PIN_ATTEMPTS: list[float] = []
_PIN_LOCKOUT_UNTIL: float = 0.0
_MAX_PIN_ATTEMPTS: int = 5
_PIN_LOCKOUT_DURATION_SEC: float = 60.0


def verify_pin(pin: str) -> tuple[bool, str]:
    """Verify a candidate PIN against the stored PBKDF2-HMAC-SHA256 hash with rate-limiting & lockout."""
    global _PIN_LOCKOUT_UNTIL
    clean = (pin or "").strip()
    pol = _load_policy()
    salt_hex = pol.get("pin_salt")
    hash_hex = pol.get("pin_hash")
    iterations = int(pol.get("pin_iterations", 200_000))
    if not salt_hex or not hash_hex:
        return False, "No security PIN is configured yet."

    with _LOCK:
        now = time.time()
        if now < _PIN_LOCKOUT_UNTIL:
            rem = int(max(1.0, _PIN_LOCKOUT_UNTIL - now))
            log_audit_event("pin_lockout_rejected", "verify_pin", PermissionTier.SENSITIVE_SYSTEM, False, f"PIN verification rejected (locked out for {rem}s).")
            return False, f"PIN verification temporarily locked out due to multiple failed attempts. Try again in {rem} seconds."

        # Filter attempts within the last 60 seconds
        _PIN_ATTEMPTS[:] = [t for t in _PIN_ATTEMPTS if now - t < 60.0]
        if len(_PIN_ATTEMPTS) >= _MAX_PIN_ATTEMPTS:
            _PIN_LOCKOUT_UNTIL = now + _PIN_LOCKOUT_DURATION_SEC
            rem = int(_PIN_LOCKOUT_DURATION_SEC)
            log_audit_event("pin_lockout_triggered", "verify_pin", PermissionTier.SENSITIVE_SYSTEM, False, "PIN lockout triggered after 5 consecutive failures.")
            return False, f"Too many failed PIN attempts. Locked out for {rem} seconds."

    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", clean.encode("utf-8"), salt, iterations)
        matched = hmac.compare_digest(candidate, expected)
    except Exception as exc:
        return False, f"PIN verification error: {exc}"

    if matched:
        with _LOCK:
            _PIN_ATTEMPTS.clear()
            _PIN_LOCKOUT_UNTIL = 0.0
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
        with _LOCK:
            now = time.time()
            _PIN_ATTEMPTS.append(now)
            fail_count = len(_PIN_ATTEMPTS)
        # Progressive delay against timing/brute force
        time.sleep(min(0.5, 0.1 * fail_count))
        log_audit_event(
            "pin_failed",
            "verify_pin",
            PermissionTier.SENSITIVE_SYSTEM,
            False,
            f"Invalid PIN provided (failed_attempts={fail_count}).",
        )
        if fail_count >= _MAX_PIN_ATTEMPTS:
            with _LOCK:
                _PIN_LOCKOUT_UNTIL = time.time() + _PIN_LOCKOUT_DURATION_SEC
            return False, f"Invalid PIN. Too many failures; locked out for {int(_PIN_LOCKOUT_DURATION_SEC)} seconds."
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
        _CONFIRMED_OPERATIONS.clear()


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

    # 0. Immutable Security Invariants — Under NO circumstances can security protocols,
    # voice authentication, or core guardrails be disabled or bypassed, even under forced override.
    op_lower = (operation or "").strip().lower()
    if op_lower in (
        "disable_voice_auth",
        "turn_off_security",
        "disable_security",
        "bypass_safety",
        "disable_protections",
        "turn_off_security_protocols",
    ):
        refusal_reason = (
            "REFUSAL: Core security protocols, voice authentication, and safety guardrails are "
            "immutable architectural invariants of AMATYA. They cannot be disabled, bypassed, or "
            "compromised under any circumstances, even with override authorisation or forced commands."
        )
        log_audit_event("security_override_refused", operation, ptier, False, refusal_reason)
        return {
            "allowed": False,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": refusal_reason,
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # If a PIN was explicitly supplied with the call, verify it right away
    if pin:
        verify_pin(pin)
    pin_ok = _SESSION_STATE.is_pin_active()

    # If the operation was already confirmed within the grace TTL window, treat as confirmed
    if is_operation_confirmed(operation):
        confirmed = True

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
                if approved:
                    mark_operation_confirmed(operation)
                    confirmed = True
                else:
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
                if approved:
                    mark_operation_confirmed(operation)
                    confirmed = True
                else:
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
    # 6a. Bootstrap: Initial PIN setup when no PIN is currently configured
    if op_lower in ("set_pin", "voice_auth:set_pin") and not has_pin():
        log_audit_event("permission_granted", operation, ptier, True, "Initial PIN bootstrap setup permitted.")
        return {
            "allowed": True,
            "tier": int(ptier),
            "tier_label": TIER_LABELS[ptier],
            "autonomy_level": autonomy,
            "reason": "Initial security PIN bootstrap permitted.",
            "requires_confirmation": False,
            "requires_voice_auth": False,
            "requires_pin": False,
        }

    # 6b. Bootstrap: Initial owner voice enrollment when no voice profiles exist yet
    if op_lower in ("voice_auth:enroll", "voice_auth:re_enroll", "enroll", "enroll_voice_profile"):
        try:
            from core.voice_auth import get_voice_authenticator
            has_profiles = bool(get_voice_authenticator().list_profiles())
        except Exception:
            has_profiles = False
        if not has_profiles:
            log_audit_event("permission_granted", operation, ptier, True, "Initial voice profile enrollment bootstrap permitted.")
            return {
                "allowed": True,
                "tier": int(ptier),
                "tier_label": TIER_LABELS[ptier],
                "autonomy_level": autonomy,
                "reason": "Initial voice profile enrollment permitted.",
                "requires_confirmation": False,
                "requires_voice_auth": False,
                "requires_pin": False,
            }

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
            if approved:
                mark_operation_confirmed(operation)
                confirmed = True
            else:
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


# ── Complete Tool-to-Permission Matrix ────────────────────────────────────────

TOOL_PERMISSION_MATRIX: dict[str, dict[str, Any]] = {
    # Tier 0: General Conversation / Informational / Read-Only / Calculations
    "web_search": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "osint_investigate": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "news_briefing": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "radio_and_aerospace": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "zoxide_navigate": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "jump": PermissionTier.GENERAL_CONVERSATION,
        "query": PermissionTier.GENERAL_CONVERSATION,
        "list": PermissionTier.GENERAL_CONVERSATION,
        "open_fm": PermissionTier.GENERAL_CONVERSATION,
        "open_term": PermissionTier.GENERAL_CONVERSATION,
        "add": PermissionTier.GENERAL_CONVERSATION,
        "remove": PermissionTier.PRIVATE_FILES,
    },
    "weather_report": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "flight_finder": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "youtube_video": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "video_player": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "system_monitor": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "screen_processor": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "jyotisha": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "maha_analog_lab": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "maha_orbit_lab": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "code_helper": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "proactive": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "save_memory": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "recall_memory": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "screen_process": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "close_camera": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "system_status": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "sleep_amatya": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "open_app": {"default_tier": PermissionTier.GENERAL_CONVERSATION},
    "reasoning_tools": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "calculate": PermissionTier.GENERAL_CONVERSATION,
        "simulate": PermissionTier.GENERAL_CONVERSATION,
        "analyze": PermissionTier.GENERAL_CONVERSATION,
        "solve_causal": PermissionTier.GENERAL_CONVERSATION,
        "optimize": PermissionTier.GENERAL_CONVERSATION,
        "evaluate_decision": PermissionTier.GENERAL_CONVERSATION,
        "predict": PermissionTier.GENERAL_CONVERSATION,
    },
    "model_router": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "set_route": PermissionTier.SENSITIVE_SYSTEM,
    },
    "orchestrator": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "emergency_stop": PermissionTier.GENERAL_CONVERSATION,
        "plan_and_execute": PermissionTier.GENERAL_CONVERSATION,
        "plan_workflow": PermissionTier.GENERAL_CONVERSATION,
        "status": PermissionTier.GENERAL_CONVERSATION,
    },

    # Tier 1: Personal Information Access
    "reminder": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "list": PermissionTier.PERSONAL_INFO,
        "read": PermissionTier.PERSONAL_INFO,
        "add": PermissionTier.PERSONAL_INFO,
    },
    "knowledge_base": {
        "default_tier": PermissionTier.GENERAL_CONVERSATION,
        "read_personal": PermissionTier.PERSONAL_INFO,
        "search_personal": PermissionTier.PERSONAL_INFO,
        "query": PermissionTier.GENERAL_CONVERSATION,
        "search": PermissionTier.GENERAL_CONVERSATION,
        "list_spaces": PermissionTier.GENERAL_CONVERSATION,
        "research": PermissionTier.GENERAL_CONVERSATION,
    },
    "send_message": {
        "default_tier": PermissionTier.PERSONAL_INFO,
        "send": PermissionTier.REMOTE_DEVICE_CONTROL,
    },

    # Tier 2: Private Files & Local Data Modification
    "undo": {"default_tier": PermissionTier.PRIVATE_FILES},
    "manage_monitor": {"default_tier": PermissionTier.PRIVATE_FILES},
    "file_controller": {
        "default_tier": PermissionTier.PRIVATE_FILES,
        "find": PermissionTier.GENERAL_CONVERSATION,
        "jump": PermissionTier.GENERAL_CONVERSATION,
        "latest": PermissionTier.GENERAL_CONVERSATION,
        "latest_file": PermissionTier.GENERAL_CONVERSATION,
        "list": PermissionTier.GENERAL_CONVERSATION,
        "disk_usage": PermissionTier.GENERAL_CONVERSATION,
        "delete": PermissionTier.PRIVATE_FILES,
        "write": PermissionTier.PRIVATE_FILES,
    },
    "file_processor": {
        "default_tier": PermissionTier.PRIVATE_FILES,
        "read": PermissionTier.GENERAL_CONVERSATION,
        "summarize": PermissionTier.GENERAL_CONVERSATION,
        "write": PermissionTier.PRIVATE_FILES,
    },

    # Tier 3: Remote Device Control & Interactive Desktop Manipulation
    "device_control": {
        "default_tier": PermissionTier.REMOTE_DEVICE_CONTROL,
        "discover": PermissionTier.GENERAL_CONVERSATION,
        "phone_status": PermissionTier.GENERAL_CONVERSATION,
        "tv_status": PermissionTier.GENERAL_CONVERSATION,
        "status": PermissionTier.GENERAL_CONVERSATION,
    },
    "home_automation": {
        "default_tier": PermissionTier.REMOTE_DEVICE_CONTROL,
        "status": PermissionTier.GENERAL_CONVERSATION,
        "get": PermissionTier.GENERAL_CONVERSATION,
        "info": PermissionTier.GENERAL_CONVERSATION,
    },
    "phone_ring": {
        "default_tier": PermissionTier.REMOTE_DEVICE_CONTROL,
        "status": PermissionTier.GENERAL_CONVERSATION,
        "pair_agentring": PermissionTier.GENERAL_CONVERSATION,
        "init_agentring": PermissionTier.GENERAL_CONVERSATION,
        "pair_kdeconnect": PermissionTier.GENERAL_CONVERSATION,
        "pair": PermissionTier.GENERAL_CONVERSATION,
        "ring": PermissionTier.REMOTE_DEVICE_CONTROL,
        "call": PermissionTier.REMOTE_DEVICE_CONTROL,
    },
    "browser_control": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "whatsapp_connector": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "workflow_engine": {
        "default_tier": PermissionTier.REMOTE_DEVICE_CONTROL,
        "list": PermissionTier.GENERAL_CONVERSATION,
        "status": PermissionTier.GENERAL_CONVERSATION,
        "execute": PermissionTier.REMOTE_DEVICE_CONTROL,
        "execute_workflow": PermissionTier.REMOTE_DEVICE_CONTROL,
    },
    "autonomous_agent": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "background_monitor": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "desktop": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "kwin_desktop": {
        "default_tier": PermissionTier.REMOTE_DEVICE_CONTROL,
        "list_windows": PermissionTier.GENERAL_CONVERSATION,
        "get_active_window": PermissionTier.GENERAL_CONVERSATION,
        "close_window": PermissionTier.REMOTE_DEVICE_CONTROL,
        "click": PermissionTier.REMOTE_DEVICE_CONTROL,
        "type": PermissionTier.REMOTE_DEVICE_CONTROL,
    },
    "desktop_control": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "desktop_agent": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "computer_control": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},
    "dev_agent": {"default_tier": PermissionTier.REMOTE_DEVICE_CONTROL},

    # Tier 4: Sensitive System Changes & Engineering Commits
    "creator": {
        "default_tier": PermissionTier.PRIVATE_FILES,
        "git_status": PermissionTier.GENERAL_CONVERSATION,
        "git_diff": PermissionTier.GENERAL_CONVERSATION,
        "inspect_repo": PermissionTier.GENERAL_CONVERSATION,
        "check_project": PermissionTier.GENERAL_CONVERSATION,
        "run_tests": PermissionTier.GENERAL_CONVERSATION,
        "search_code": PermissionTier.GENERAL_CONVERSATION,
        "analyze_doc": PermissionTier.GENERAL_CONVERSATION,
        "generate_doc": PermissionTier.PRIVATE_FILES,
        "apply_edits": PermissionTier.PRIVATE_FILES,
        "git_commit": PermissionTier.SENSITIVE_SYSTEM,
        "run_shell": PermissionTier.SENSITIVE_SYSTEM,
    },
    "game_updater": {"default_tier": PermissionTier.SENSITIVE_SYSTEM},
    "computer_settings": {
        "default_tier": PermissionTier.SENSITIVE_SYSTEM,
        "status": PermissionTier.GENERAL_CONVERSATION,
        "get_time": PermissionTier.GENERAL_CONVERSATION,
        "current_time": PermissionTier.GENERAL_CONVERSATION,
        "time": PermissionTier.GENERAL_CONVERSATION,
        "get_volume": PermissionTier.GENERAL_CONVERSATION,
        "get_brightness": PermissionTier.GENERAL_CONVERSATION,
        "text_only_mode": PermissionTier.GENERAL_CONVERSATION,
        "voice_mode": PermissionTier.GENERAL_CONVERSATION,
        "shutdown": PermissionTier.CRITICAL_SECURITY,
        "restart": PermissionTier.CRITICAL_SECURITY,
        "amatya_shutdown": PermissionTier.CRITICAL_SECURITY,
        "amatya_sleep": PermissionTier.GENERAL_CONVERSATION,
    },

    # Tier 5: Critical Security & Authentication Operations
    "shutdown_amatya": {"default_tier": PermissionTier.CRITICAL_SECURITY},
    "voice_auth": {
        "default_tier": PermissionTier.CRITICAL_SECURITY,
        "status": PermissionTier.GENERAL_CONVERSATION,
        "benchmark": PermissionTier.GENERAL_CONVERSATION,
        "verify": PermissionTier.PERSONAL_INFO,
        "audit_log": PermissionTier.PERSONAL_INFO,
        "set_pin": PermissionTier.CRITICAL_SECURITY,
        "clear_pin": PermissionTier.CRITICAL_SECURITY,
        "enroll": PermissionTier.CRITICAL_SECURITY,
        "delete_profile": PermissionTier.CRITICAL_SECURITY,
    },
}


def register_tool_permission(tool_name: str, spec: dict[str, Any]) -> None:
    """Register permission mapping for an external/dynamically loaded tool or plugin."""
    with _LOCK:
        TOOL_PERMISSION_MATRIX[str(tool_name).strip().lower()] = spec


def classify_tool_permission(
    tool_name: str,
    action: str = "",
    parameters: dict[str, Any] | None = None,
) -> tuple[PermissionTier, str]:
    """Resolve the required PermissionTier for any tool and action (fails closed for unclassified)."""
    tool = str(tool_name or "").strip().lower()
    act = str(action or "").strip().lower()

    if not act and parameters and isinstance(parameters, dict):
        act = str(parameters.get("action", "") or parameters.get("sub_action", "")).strip().lower()

    # Look up tool in matrix
    spec = TOOL_PERMISSION_MATRIX.get(tool)
    if not spec:
        return PermissionTier.CRITICAL_SECURITY, f"Unregistered or unclassified tool '{tool}' fails closed to Tier 5 (Critical Security)."

    # Look up action override
    if act in spec:
        ptier = spec[act]
        return ptier, f"Action '{act}' of '{tool}' mapped to Tier {int(ptier)} ({TIER_LABELS[ptier]})."

    # Contextual check for shell commands in creator
    if tool == "creator" and act == "run_shell" and parameters:
        cmd = str(parameters.get("command", "") or "").lower()
        if any(c in cmd for c in ("rm -rf", "mkfs", "dd if=", ":(){ :|:& };:", "chmod -r 777 /")):
            return PermissionTier.CRITICAL_SECURITY, "Destructive shell command classified as Tier 5 (Critical Security)."

    def_tier = spec.get("default_tier", PermissionTier.CRITICAL_SECURITY)
    return def_tier, f"Tool '{tool}' default mapped to Tier {int(def_tier)} ({TIER_LABELS[def_tier]})."


def authorize_tool_execution(
    tool_name: str,
    parameters: dict[str, Any] | None = None,
    execution_context: dict[str, Any] | None = None,
    actor: str = "",
) -> dict[str, Any]:
    """Mandatory Centralized Authorization Gateway (Phase 15.2 / Section 5).

    Every tool, action, and plugin invocation across AMATYA must pass through
    this gateway prior to execution.

    Fails closed for unclassified tools. Scans parameters for injection vectors.
    Evaluates against active permission tier, user biometric/PIN state, and autonomy level.
    """
    params = parameters if isinstance(parameters, dict) else {}
    ctx = execution_context if isinstance(execution_context, dict) else {}
    t_clean = str(tool_name or "").strip().lower()

    # 1. Unknown or unclassified tools fail closed immediately
    if t_clean not in TOOL_PERMISSION_MATRIX:
        reason = f"Security Gateway: Tool '{t_clean}' is unclassified or unregistered. Denied by default (fail-closed)."
        log_audit_event(
            "security_gateway_blocked",
            t_clean,
            PermissionTier.CRITICAL_SECURITY,
            False,
            reason,
            details={"parameters": params, "context": ctx},
        )
        return {
            "allowed": False,
            "tier": int(PermissionTier.CRITICAL_SECURITY),
            "tier_label": TIER_LABELS[PermissionTier.CRITICAL_SECURITY],
            "autonomy_level": get_autonomy_level(),
            "reason": reason,
            "tool": t_clean,
            "action": "",
            "requires_confirmation": True,
            "requires_voice_auth": True,
            "requires_pin": True,
        }

    # 2. Adversarial prompt injection scan across text parameters
    for key, val in params.items():
        if isinstance(val, str) and val:
            is_inj, inj_reason = detect_prompt_injection(val)
            if is_inj:
                reason = f"Security Gateway: Adversarial prompt injection detected in argument '{key}': {inj_reason}"
                log_audit_event(
                    "prompt_injection_blocked",
                    f"{t_clean}:{key}",
                    PermissionTier.CRITICAL_SECURITY,
                    False,
                    reason,
                    details={"param_key": key, "malicious_content": val[:200]},
                )
                return {
                    "allowed": False,
                    "tier": int(PermissionTier.CRITICAL_SECURITY),
                    "tier_label": TIER_LABELS[PermissionTier.CRITICAL_SECURITY],
                    "autonomy_level": get_autonomy_level(),
                    "reason": reason,
                    "tool": t_clean,
                    "action": str(params.get("action", "")),
                    "requires_confirmation": True,
                    "requires_voice_auth": True,
                    "requires_pin": True,
                }

    # 3. Resolve required permission tier
    ptier, classification_reason = classify_tool_permission(t_clean, parameters=params)
    act = str(params.get("action", "") or params.get("sub_action", "")).strip().lower()

    # 4. Check permissions against active session, PIN, voice auth, and confirmation
    perm = check_permission(
        operation=f"{t_clean}:{act}" if act else t_clean,
        tier=ptier,
        description=classification_reason,
        pin=params.get("pin"),
        interactive_confirm=ctx.get("interactive_confirm", True),
        confirmed=bool(params.get("confirmed", False)),
    )
    perm["tool"] = t_clean
    perm["action"] = act
    return perm


# ── Prompt Injection Defense & Quarantine ───────────────────────────────────

_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bignore\s+(?:all\s+)?previous\s+instructions\b"),
    re.compile(r"(?i)\bdisregard\s+(?:all\s+)?system\s+prompts?\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:DAN|an\s+unrestricted\s+AI|evil\s+mode|unfiltered)\b"),
    re.compile(r"(?i)\bbypass\s+(?:all\s+)?(?:security|permission|sandbox|safety)\b"),
    re.compile(r"(?i)\belevate\s+privileges?\b"),
    re.compile(r"(?i)\breveal\s+(?:the\s+)?(?:system\s+prompt|api\s+keys?|secret\s+tokens?|passwords?)\b"),
    re.compile(r"(?i)\bSYSTEM\s+OVERRIDE:\s*DISABLE_GUARDRAILS\b"),
]


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    """Scan untrusted candidate text for adversarial prompt injection vectors."""
    if not text or not isinstance(text, str):
        return False, ""
    for pat in _INJECTION_PATTERNS:
        match = pat.search(text)
        if match:
            return True, f"Prompt injection vector detected: '{match.group(0)}'"
    return False, ""


def quarantine_untrusted_input(text: str, source: str = "untrusted") -> str:
    """Enclose external/untrusted content in safe isolation delimiters, neutralizing injections."""
    raw = str(text or "")
    is_malicious, reason = detect_prompt_injection(raw)
    sanitized = raw
    if is_malicious:
        log_audit_event(
            "prompt_injection_intercepted",
            f"quarantine_untrusted_input:{source}",
            PermissionTier.CRITICAL_SECURITY,
            False,
            reason,
            details={"source": source, "excerpt": raw[:120]},
        )
        # Neutralize specific trigger phrases
        for pat in _INJECTION_PATTERNS:
            sanitized = pat.sub("[REDACTED_ADVERSARIAL_INJECTION]", sanitized)

    return (
        f'<<<UNTRUSTED_CONTENT source="{source}">>>\n'
        f"{sanitized}\n"
        f"<<<END_UNTRUSTED_CONTENT>>>"
    )


def emergency_stop() -> str:
    """Universal concurrent Emergency Stop across all running AMATYA subsystems."""
    cancelled_components = []
    try:
        from core.orchestrator import get_orchestrator
        orch_msg = get_orchestrator().cancel_all()
        cancelled_components.append("Central Orchestrator")
    except Exception:
        pass

    try:
        from core.desktop_agent import get_desktop_agent
        da = get_desktop_agent()
        if da and da.is_running:
            da.cancel()
            cancelled_components.append("DesktopAgent")
    except Exception:
        pass

    log_audit_event(
        "emergency_stop_triggered",
        "emergency_stop",
        PermissionTier.CRITICAL_SECURITY,
        True,
        f"Emergency Stop executed across: {', '.join(cancelled_components) or 'all subsystems'}.",
    )
    return f"Emergency Stop executed: halted {', '.join(cancelled_components) or 'all active processes'}."
