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


def voice_authorize(utterance: str) -> bool | None:
    """Evaluate spoken user input to authorize or cancel a pending confirmation via voice.

    Returns:
        True if authorized via voice
        False if cancelled via voice
        None if not an authorization utterance or no confirmation pending
    """
    if not has_pending():
        return None

    text = (utterance or "").strip().lower()
    affirmative = ("confirm", "yes", "proceed", "authorize", "authorise", "go ahead", "approved", "run it", "execute", "do it")
    if any(re.search(rf"\b{re.escape(w)}\b", text) for w in affirmative):
        _speak("Command authorized. Executing.")
        resolve(True)
        return True

    negative = ("cancel", "no", "abort", "don't", "stop", "deny", "reject", "never mind", "do not")
    if any(re.search(rf"\b{re.escape(w)}\b", text) for w in negative):
        _speak("Command cancelled, sir.")
        resolve(False)
        return False

    return None


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
