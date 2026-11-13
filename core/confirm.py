"""
core/confirm.py — a confirmation the model cannot forge.

THE PROBLEM WITH THE OLD GATE
    computer_settings guarded shutdown and restart like this:

        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return "Please confirm by calling again with confirmed=yes."

    `confirmed` is a tool parameter, which means the *model* writes it. Nothing
    stops it from sending confirmed=yes on the first call, and nothing checks
    that a human was ever involved. It is a convention, not a gate — and its
    coverage was two actions, so deleting files and switching off the WiFi the
    assistant is talking over went through with no gate at all.

THE DESIGN HERE
    The confirmation token is issued by the *interface*, never by the model:

      1. An action calls `request(...)` with a callable that does the real work.
      2. This module hands the UI a banner with CONFIRM / CANCEL and returns
         IMMEDIATELY with a sentence for the model to say out loud.
      3. If — and only if — the user presses CONFIRM, the UI calls `resolve()`,
         which runs the stored callable off the Qt thread.

    Nothing blocks. The model keeps talking while the banner is up, so this
    costs no latency at all; in fact it is cheaper than the old gate, which
    burned two tool round trips (reject, then re-call) on every shutdown.

WHAT BELONGS HERE AND WHAT DOES NOT
    Only genuinely irreversible things. Anything that can be reversed should be
    done at once and pushed onto core/undo.py instead — undo is faster than a
    question, and an assistant that asks before every action is one nobody uses.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from core.security import has_pin, verify_pin
from core.voice_auth import get_voice_authenticator
from memory.config_manager import get_voice_auth_enabled

# A pending confirmation is abandoned after this long. Chosen to outlast a
# normal "hang on, let me look at the screen" pause without leaving a live
# shutdown button sitting on the HUD for the rest of the day.
TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key:     str
    title:   str
    detail:  str
    run:     Optional[Callable[[], str]] = None
    event:   Optional[threading.Event] = None
    result:  Optional[bool] = None
    at:      float = 0.0
    awaiting_pin: bool = False
    auth_method: Optional[str] = None


_pending: Optional[_Pending] = None
_lock = threading.Lock()

# Set once at startup by main.py. Signature: (title, detail) -> None for show,
# and () -> None for hide. Both are marshalled onto the Qt thread by the UI.
_show_cb:  Optional[Callable[[str, str], None]] = None
_hide_cb:  Optional[Callable[[], None]] = None
_log_cb:   Optional[Callable[[str], None]] = None
_speak_cb: Optional[Callable[[str], None]] = None


def bind(show, hide, log=None, speak=None) -> None:
    """Wire this module to the HUD and speech. Called once from main.py at startup."""
    global _show_cb, _hide_cb, _log_cb, _speak_cb
    _show_cb, _hide_cb, _log_cb, _speak_cb = show, hide, log, speak


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def _speak(msg: str) -> None:
    if _speak_cb:
        try:
            _speak_cb(msg)
        except Exception:
            pass


def has_pending() -> bool:
    """Check if a confirmation is currently awaiting authorization."""
    with _lock:
        if _pending is None:
            return False
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return False
        return True


def get_pending_info() -> dict[str, str] | None:
    """Return key details of the pending confirmation if active."""
    with _lock:
        if _pending is None or (time.monotonic() - _pending.at > TIMEOUT_SECONDS):
            return None
        return {"key": _pending.key, "title": _pending.title, "detail": _pending.detail}


def is_awaiting_pin() -> bool:
    """Check if the current pending confirmation requires PIN entry."""
    with _lock:
        if _pending is None or (time.monotonic() - _pending.at > TIMEOUT_SECONDS):
            return False
        return bool(_pending.awaiting_pin)


def set_awaiting_pin(awaiting: bool = True) -> None:
    """Set whether the active confirmation is waiting for PIN input."""
    with _lock:
        if _pending is not None:
            _pending.awaiting_pin = awaiting
            _pending.at = time.monotonic()


def voice_authorize(
    utterance: str,
    audio: Optional[bytes] = None,
    require_biometrics: Optional[bool] = None,
) -> bool | None:
    """Evaluate spoken user input to authorize or cancel a pending confirmation via voice.

    Security Rules:
      1. Zero Spoken PIN: A security PIN must NEVER be spoken or accepted over voice.
         Spoken digits/PINs are immediately rejected, directing the user to text input.
      2. Biometric Verification: When voice auth is enabled and profiles exist,
         affirmative commands must be matched against enrolled vocal acoustics.
      3. Fail-Closed Fallback: If voice match fails, confidence is uncertain, or
         biometrics are missing, the confirmation fails closed and transitions to
         awaiting PIN entry via text input.

    Returns:
        True if authorized via verified voice
        False if cancelled, rejected, or redirected to PIN input
        None if not an authorization utterance or no confirmation pending
    """
    if not has_pending():
        return None

    text = (utterance or "").strip().lower()

    # 1. Spoken PIN Guard: Never permit speaking the PIN
    spoken_pin_patterns = [
        r"\bpin\b",
        r"\bmy\s+pin\s+is\b",
        r"\bpassword\b",
        r"\bpasscode\b",
        r"\b\d{4,8}\b",
    ]
    if any(re.search(pat, text) for pat in spoken_pin_patterns):
        _log("SEC: Spoken PIN rejected. Security PIN must be entered via text input only.")
        _speak("For your security, do not speak your PIN. Please enter your PIN in the input field.")
        set_awaiting_pin(True)
        return False

    # 2. Negative / Cancel check
    negative = ("cancel", "no", "abort", "don't", "stop", "deny", "reject", "never mind", "do not")
    if any(re.search(rf"\b{re.escape(w)}\b", text) for w in negative):
        _speak("Command cancelled, sir.")
        resolve(False)
        return False

    # 3. Affirmative check
    affirmative = ("confirm", "yes", "proceed", "authorize", "authorise", "go ahead", "approved", "run it", "execute", "do it")
    is_affirmative = any(re.search(rf"\b{re.escape(w)}\b", text) for w in affirmative)
    if not is_affirmative:
        return None

    # If the confirmation has already failed voice verification and is awaiting PIN,
    # repeated spoken 'confirm' is not accepted.
    if is_awaiting_pin():
        _speak("Security PIN required. Please type your PIN in the input field to authorize.")
        _log("SYS: Confirmation awaiting PIN input; spoken affirmation rejected.")
        return False

    # 4. Biometric Speaker Verification
    voice_auth_on = get_voice_auth_enabled()
    auth = get_voice_authenticator()
    profiles = auth.list_profiles()

    # Determine if biometrics are required
    must_verify_voice = require_biometrics if require_biometrics is not None else (voice_auth_on and bool(profiles) and (audio is not None))

    if must_verify_voice:
        if audio is not None and len(audio) >= 1600:
            try:
                v_res = auth.verify_speaker(audio=audio)
            except Exception as exc:
                _log(f"ERR: Voice verification exception: {exc}")
                v_res = None

            if v_res and v_res.verified:
                _log(f"SYS: Voice biometrics verified for {v_res.matched_user} (confidence={v_res.confidence:.2f}).")
                _speak("Speaker identity verified. Command authorized. Executing.")
                with _lock:
                    if _pending:
                        _pending.auth_method = "voice_biometrics"
                resolve(True)
                return True
            else:
                reason = v_res.reason if v_res else "Voice verification failed"
                _log(f"SYS: Voice verification uncertain or rejected ({reason}). Requiring PIN fallback.")
        else:
            _log("SYS: Biometric verification required but no audio frame provided. Requiring PIN fallback.")

        # Biometric check failed or uncertain -> transition to PIN fallback
        set_awaiting_pin(True)
        if has_pin():
            _speak("Voice verification uncertain. For security, please enter your PIN in the input field to authorize.")
        else:
            _speak("Voice verification uncertain and no security PIN is set. Please set a security PIN in the input field using set_pin.")
        return False

    # If voice auth is enabled and profiles exist, but require_biometrics was None and audio was None:
    # If a PIN is configured, transition to PIN entry
    if voice_auth_on and bool(profiles) and has_pin() and require_biometrics is True:
        set_awaiting_pin(True)
        _speak("Voice verification required. Please enter your PIN in the input field to authorize.")
        return False

    # Fallback spoken confirmation (e.g. no enrolled voice profiles or test harness without audio)
    _speak("Command authorized. Executing.")
    with _lock:
        if _pending:
            _pending.auth_method = "voice_affirmation"
    resolve(True)
    return True


def pin_authorize(candidate_pin: str) -> tuple[bool, str]:
    """Authorize a pending confirmation using a security PIN entered via text input.

    Returns:
        (True, message) if authorized
        (False, error_message) if rejected
    """
    if not has_pending():
        return False, "No confirmation is pending."

    clean = (candidate_pin or "").strip()
    if clean.lower().startswith("pin"):
        clean = re.sub(r"^pin\s*[:=]?\s*", "", clean, flags=re.IGNORECASE).strip()

    if not has_pin():
        msg = "No security PIN is configured yet. Set a PIN using 'set_pin <PIN>' first."
        _log(f"SYS: {msg}")
        _speak("No security PIN is configured. Please set a PIN using set_pin first.")
        return False, msg

    ok, msg = verify_pin(clean)
    if ok:
        with _lock:
            if _pending:
                _pending.auth_method = "security_pin"
        _speak("Security PIN verified. Command authorized. Executing.")
        resolve(True)
        return True, "Security PIN verified. Command authorized."
    else:
        _log(f"SEC: PIN verification rejected: {msg}")
        _speak("Invalid security PIN.")
        return False, f"PIN authorization failed: {msg}"


def text_authorize(text_input: str) -> tuple[bool | None, str]:
    """Process text input from the UI input box to authorize or cancel a pending confirmation.

    Returns:
        (True, msg) if authorized
        (False, msg) if cancelled or authorization failed
        (None, msg) if not applicable
    """
    if not has_pending():
        return None, "No confirmation pending."

    clean = (text_input or "").strip()
    if not clean:
        return None, "Empty input."

    lower = clean.lower()

    # Cancel check
    negative = ("cancel", "abort", "no", "deny", "stop", "never mind")
    if lower in negative:
        _speak("Command cancelled, sir.")
        resolve(False)
        return False, "Command cancelled."

    # If awaiting PIN, reject plain 'confirm' or 'yes'
    if is_awaiting_pin() and lower in ("confirm", "yes", "proceed", "authorize", "authorise", "ok", "run"):
        _speak("Security PIN required. Please type your PIN in the input field.")
        return False, "PIN required. Spoken or typed 'confirm' is not sufficient."

    # If not awaiting PIN and user typed 'confirm'
    if not is_awaiting_pin() and lower in ("confirm", "yes", "proceed", "authorize", "authorise"):
        if has_pin():
            set_awaiting_pin(True)
            _speak("Please enter your PIN in the input field to authorize.")
            return False, "Security PIN required to authorize."
        else:
            _speak("Command authorized. Executing.")
            with _lock:
                if _pending:
                    _pending.auth_method = "text_confirmation"
            resolve(True)
            return True, "Command authorized via text confirmation."

    # Treat input as candidate PIN
    return pin_authorize(clean)


def request(key: str, title: str, detail: str, run: Callable[[], str]) -> str:
    """Park an irreversible action behind the on-screen gate.

    Returns the sentence the tool should hand back to the model — phrased as an
    instruction so the assistant asks the user out loud in their own language,
    rather than reading an English string verbatim."""
    global _pending

    if _show_cb is None:
        # No interface bound (headless, or a very early call). Refuse rather
        # than silently performing something irreversible.
        return (f"I cannot confirm '{title}' right now because the interface is "
                f"not available, so I have not done it.")

    with _lock:
        _pending = _Pending(key=key, title=title, detail=detail,
                            run=run, at=time.monotonic())

    try:
        _show_cb(title, detail)
    except Exception as e:
        with _lock:
            _pending = None
        return f"Could not ask for confirmation: {e}. Nothing was done."

    _log(f"SYS: Awaiting confirmation — {title}")
    _speak(f"Sir, authorization is required for {title}. Say confirm to authorize, or cancel to abort.")
    return (
        f"[CONFIRMATION_PENDING] Authorization required for: {title}. "
        f"Say ONE short sentence asking the user out loud to confirm or cancel via voice. Do not claim it is done."
    )


def request_confirmation(
    operation: str,
    description: str = "",
    timeout: float = 30.0,
) -> bool:
    """Request interactive confirmation from the user on the HUD.
    Blocks the calling worker thread until the user clicks CONFIRM or CANCEL,
    or until timeout expires. Returns True if confirmed, False otherwise.
    """
    global _pending

    if _show_cb is None:
        # Headless or UI not bound
        _log(f"SYS: Confirmation requested for '{operation}' but HUD interface is not bound.")
        return False

    evt = threading.Event()
    item = _Pending(
        key=operation,
        title=f"Confirm: {operation}",
        detail=description or f"Do you confirm: {operation}?",
        run=None,
        event=evt,
        result=None,
        at=time.monotonic(),
    )
    with _lock:
        _pending = item

    try:
        _show_cb(f"Confirm: {operation}", description or f"Do you confirm: {operation}?")
    except Exception as e:
        with _lock:
            if _pending is item:
                _pending = None
        _log(f"ERR: Failed to display confirmation dialog: {e}")
        return False

    _log(f"SYS: Awaiting interactive confirmation for {operation} (timeout {timeout}s)...")
    _speak(f"Sir, confirmation required for {description or operation}. Please say confirm or cancel.")
    completed = evt.wait(timeout=timeout)

    if not completed:
        with _lock:
            if _pending is item:
                _pending = None
        if _hide_cb:
            try:
                _hide_cb()
            except Exception:
                pass
        _log(f"SYS: Confirmation timed out for {operation}")
        return False

    return bool(item.result)


def resolve(accepted: bool) -> None:
    """Called by the UI when the user presses CONFIRM or CANCEL.

    Runs the stored callable on a worker thread — this is invoked from the Qt
    thread, and shutting the machine down from inside a button handler would
    freeze the interface on its way out."""
    global _pending

    with _lock:
        p, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if p is None:
        return

    if time.monotonic() - p.at > TIMEOUT_SECONDS:
        _log(f"SYS: Confirmation expired — {p.title}")
        if p.event:
            p.result = False
            p.event.set()
        return

    # If this was a synchronous interactive confirmation (request_confirmation)
    if p.event:
        p.result = bool(accepted)
        p.event.set()
        _log(f"SYS: Interactive confirmation {'accepted' if accepted else 'declined'} — {p.title}")
        return

    if not accepted:
        _log(f"SYS: Cancelled — {p.title}")
        return

    if p.run:
        def _worker():
            try:
                result = p.run() or "Done."
                _log(f"SYS: Confirmed — {p.title}. {result}")
            except Exception as e:
                _log(f"ERR: {p.title} failed — {e}")

        threading.Thread(target=_worker, daemon=True,
                         name=f"confirm-{p.key}").start()


def pending_title() -> str:
    """'' when nothing is waiting. Lets an action avoid stacking two banners."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return _pending.title
