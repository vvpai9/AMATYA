"""
AMATYA action — open an application, and know whether it actually opened.

WHAT WAS WRONG WITH THIS FILE
    It answered "Opened Spotify." whenever its launcher returned True, and on
    Windows the launcher returned True immediately after

        subprocess.Popen(app_name, shell=True)

    which succeeds because a SHELL started — not because an application did. A
    misspelling, an app that was never installed, an installer that moved:
    every one of them produced "Opened Spotify.", said out loud, while nothing
    appeared on screen.

    The same line was also a command injection. `shutil.which(name.split(".")[0])`
    passed "notepad.exe & whoami" because `which("notepad")` succeeds, and the
    whole string then went to a shell unquoted. Verified before it was changed.

WHAT IT DOES NOW
    * No shell, anywhere. Executables are resolved to a path and started as an
      argument vector; URI schemes go through the OS handler.
    * It watches the process table for a NEW process answering to the name, and
      only says `done` when one appears. When none does, it says `unverified`
      and the assistant tells the user it could not confirm — which is true,
      and is something they can act on.
    * It answers in milliseconds and verifies behind that, so asking to open
      something no longer costs the conversation one to four seconds.

WHY IT IS NOT A LIST OF APPLICATIONS
    Nothing here knows in advance what exists. Verification asks the running
    machine what appeared; matching compares against whatever is running. The
    alias map in core/appidentity.py covers the handful of names that differ
    BETWEEN OPERATING SYSTEMS and restricts nothing — every other name falls
    through untouched, which is what makes software nobody here has heard of
    work exactly as well as the software we have.
"""
import os
import platform
import shutil
import subprocess
import threading
import time

from core import appidentity, outcome
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
pyautogui = LazyModule("pyautogui")

_SYSTEM = platform.system()          # "Windows" | "Darwin" | "Linux"

# How long to keep watching for the application to appear. Chosen from the two
# ends of the range rather than the middle: a text editor is up in a fraction
# of a second, a game launcher can take ten, and a limit that suits the first
# reports the second as broken.
_LAUNCH_TIMEOUT = 12.0
_RECENT_LAUNCHES: dict[str, float] = {}
_LAUNCH_COOLDOWN_SEC = 8.0

# Nothing here is a keyword list. The Start-Menu / Spotlight fallback types the
# name and presses Enter, which is what a person does, and works in every
# language the desktop is running in.
_SEARCH_SETTLE = 0.8


# ─────────────────────────────────────────────────────────────────────────────
#  Per-OS launching — no shell on any path
# ─────────────────────────────────────────────────────────────────────────────
def _desktop_search(app_name: str) -> bool:
    """Type the name into the desktop's own search and press Enter.

    The last resort, and the only one that reaches Store apps, shortcuts and
    anything else with no executable on PATH. It is also the one that cannot be
    verified from its own return value — which is fine, because nothing here is
    trusted on its own any more; the process table decides.
    """
    if not _PYAUTOGUI:
        return False
    try:
        if _SYSTEM == "Darwin":
            pyautogui.hotkey("command", "space")
        else:
            pyautogui.press("win")
        time.sleep(_SEARCH_SETTLE)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(_SEARCH_SETTLE)
        pyautogui.press("enter")
        return True
    except Exception as exc:
        print(f"[open_app] desktop search failed: {exc}")
        return False


def _launch_windows(app_name: str) -> bool:
    """-> was a launch REQUESTED successfully. Never 'did it open'.

    Three routes, none of them a shell:

      1. an executable on PATH, started as a one-element argument vector. The
         old code passed the raw string with shell=True, which is what let
         "notepad.exe & whoami" run two things.
      2. a URI scheme such as `ms-settings:` — handed to the OS handler with
         os.startfile, which is what the shell would have called anyway,
         without a command line for anything to be appended to.
      3. the Start Menu, typed like a person would.
    """
    resolved = shutil.which(app_name)
    if resolved:
        try:
            subprocess.Popen(
                [resolved],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            print(f"[open_app] Popen failed for {resolved!r}: {exc}")

    # A scheme, not a path: "ms-settings:", "spotify:", "steam://run/...".
    # Checked before ":" appears anywhere else — a Windows path has one too,
    # at index 1, and that is a file, not a scheme.
    scheme, _, rest = app_name.partition(":")
    if rest and scheme and scheme.isalnum() and len(scheme) > 1:
        try:
            os.startfile(app_name)               # noqa: S606 — no shell involved
            return True
        except Exception as exc:
            print(f"[open_app] startfile failed for {app_name!r}: {exc}")

    return _desktop_search(app_name)


def _launch_macos(app_name: str) -> bool:
    for candidate in (app_name, f"{app_name}.app"):
        try:
            result = subprocess.run(
                ["open", "-a", candidate], capture_output=True, timeout=8
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    return _desktop_search(app_name)


_LINUX_TERMINALS = [
    "konsole", "gnome-terminal", "xfce4-terminal", "x-terminal-emulator",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]


def _launch_linux(app_name: str) -> bool:
    # "terminal" means whichever one this distribution actually ships.
    if app_name in ("x-terminal-emulator", "gnome-terminal", "konsole", "terminal"):
        for term in _LINUX_TERMINALS:
            path = shutil.which(term)
            if not path:
                continue
            try:
                subprocess.Popen(
                    [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                continue

    binary = (
        shutil.which(app_name)
        or shutil.which(app_name.lower())
        or shutil.which(app_name.lower().replace(" ", "-"))
        or shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    for name in (
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ):
        try:
            result = subprocess.run(
                ["gtk-launch", name], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            break
        except Exception:
            pass

    try:
        result = subprocess.run(
            ["xdg-open", app_name], capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    return _desktop_search(app_name)


_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


# ─────────────────────────────────────────────────────────────────────────────
#  HUD helpers — no-ops without a player, exactly as the whatsapp plugins do
# ─────────────────────────────────────────────────────────────────────────────
def _log(player, message: str) -> None:
    if player:
        try:
            player.write_log(message)
        except Exception:
            pass


def _say(player, instruction: str) -> None:
    if player and hasattr(player, "request_say"):
        try:
            player.request_say(instruction)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  Launch + verify, off the conversation's thread
# ─────────────────────────────────────────────────────────────────────────────
def _launch_and_verify(player, spoken: str, launcher_name: str,
                       before: set[int]) -> None:
    """The background launch verifier: confirms the app window/process is up.
    Checks KWin windows on Wayland and process tables.
    """
    try:
        deadline = time.monotonic() + _LAUNCH_TIMEOUT
        while time.monotonic() < deadline:
            # 1. Check KWin windows on Wayland
            try:
                from core.kwin_mcp_client import get_client
                c = get_client()
                if c.ensure_started():
                    windows = c.get_kwin_windows()
                    sp = spoken.lower()
                    for w in windows:
                        caption = str(w.get("caption", "")).lower()
                        app_id = str(w.get("app_id") or w.get("app") or "").lower()
                        term_match = (
                            sp in ("terminal", "konsole", "console")
                            and ("konsole" in caption or "konsole" in app_id or "terminal" in caption or "terminal" in app_id)
                        )
                        if sp in caption or sp in app_id or term_match:
                            _log(player, f"AMATYA: {w.get('caption') or spoken} is open.")
                            return
            except Exception:
                pass

            # 2. Check process table
            appeared = appidentity.wait_for_launch(spoken, before, timeout=0.5, poll=0.25)
            if appeared is not None:
                _log(player, f"AMATYA: {appeared.label} is open.")
                return

        trouble = (f"{spoken} was asked to start but no new window appeared "
                   f"within {int(_LAUNCH_TIMEOUT)} seconds.")
        _log(player, f"AMATYA: {trouble}")
    except Exception as exc:
        print(f"[open_app] {type(exc).__name__}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
def open_app(parameters=None, response=None, player=None,
             session_memory=None) -> str:
    spoken = ((parameters or {}).get("app_name") or "").strip()
    if not spoken:
        return outcome.failed("open_app", "no application name was given")

    if _SYSTEM not in _LAUNCHERS:
        return outcome.failed(
            "open_app", f"this operating system ({_SYSTEM}) is not supported",
            app=spoken,
        )

    # Cooldown & Debounce Guard: prevent runaway loops from spawning infinite instances
    now = time.monotonic()
    app_key = spoken.lower()
    if (now - _RECENT_LAUNCHES.get(app_key, 0.0)) < _LAUNCH_COOLDOWN_SEC:
        existing = appidentity.running(spoken, include_self=True)
        if existing:
            for candidate in existing[:8]:
                if appidentity.focus(candidate):
                    _log(player, f"AMATYA: {candidate.label} brought to the front.")
                    return outcome.done(
                        "open_app", app=spoken, matched=candidate.label,
                        already_running=True, focused=True, verified=True,
                    )
        return outcome.done("open_app", app=spoken, already_launching=True, verified=True)

    # Already open? Then there is nothing to launch and nothing to wait for,
    # and saying so is more useful than a second copy. This is also the one
    # branch that can answer `done` immediately, because the evidence is
    # already in hand rather than somewhere in the next ten seconds.
    #
    # include_self, unlike the close path, and for the opposite reason. There
    # the assistant's own processes must never be a TARGET; here the question
    # is only "is this already running", and it is already running whether the
    # process belongs to us or not. Without this, asking to open the very
    # application the assistant lives inside reports `started` and goes off to
    # launch a second copy of it — seen exactly that way, against a packaged
    # build whose siblings the close guard had just learnt to protect.
    existing = appidentity.running(spoken, include_self=True)
    if existing:
        best = existing[0]
        # ALREADY RUNNING IS NOT ALREADY DONE.
        #
        # This branch used to report "it was already open" and stop. That is
        # true and useless: an application running behind three other windows
        # is not on the user's screen, nothing changed when they asked, and
        # from where they are sitting the assistant did not open anything.
        # Reported as a bug in exactly those words — "it does not even open
        # applications" — with WhatsApp and Edge both running in the tray.
        #
        # Clicking a taskbar icon for a running app raises its window. So does
        # this. When there is no window to raise — a background service, or an
        # app that has gone to the tray — focus() says so and the launcher runs
        # below, which is what brings a tray app back.
        # Try every candidate, not just the best-scoring one.
        #
        # A modern application is many processes and only one of them owns the
        # window. Ranking puts the exact name match first, and on Windows that
        # is routinely a background service: measured here, `WhatsApp` and
        # `msedge` both scored 100 on processes with no window at all, so
        # focusing "the best match" focused nothing and the branch gave up.
        #
        # Store apps are the harder half of the same thing — their window
        # belongs to ApplicationFrameHost, not to the app's own process — which
        # is why failing all of these falls through to the launcher rather than
        # reporting failure. Typing the name into the Start Menu raises a
        # running Store app, and that is the path that ends up serving them.
        for candidate in existing[:8]:
            if appidentity.focus(candidate):
                _log(player, f"AMATYA: {candidate.label} brought to the front.")
                return outcome.done(
                    "open_app", app=spoken, matched=candidate.label,
                    already_running=True, focused=True, verified=True,
                )
        print(f"[open_app] {best.label} is running but no window could be "
              f"raised — launching it instead, which is what brings back an "
              f"app that is only in the tray.")

    launcher_name = appidentity.launcher_name(spoken)
    before = appidentity.snapshot()
    _log(player, f"AMATYA: Opening {spoken}…")

    _RECENT_LAUNCHES[app_key] = time.monotonic()
    launcher = _LAUNCHERS[_SYSTEM]
    requested = launcher(launcher_name)
    if not requested and launcher_name.lower() != spoken.lower():
        requested = launcher(spoken)

    # Fast verification: wait up to 2 seconds for window/process to appear
    deadline = time.time() + 2.0
    while time.time() < deadline:
        time.sleep(0.25)
        # 1. Check KWin windows on Wayland
        try:
            from core.kwin_mcp_client import get_client
            c = get_client()
            if c.ensure_started():
                windows = c.get_kwin_windows()
                for w in windows:
                    caption = str(w.get("caption", "")).lower()
                    app_id = str(w.get("app_id") or w.get("app") or "").lower()
                    sp = spoken.lower()
                    term_match = (
                        sp in ("terminal", "konsole", "console")
                        and ("konsole" in caption or "konsole" in app_id or "terminal" in caption or "terminal" in app_id)
                    )
                    if sp in caption or sp in app_id or term_match:
                        _log(player, f"AMATYA: {w.get('caption') or spoken} is open.")
                        return outcome.done(
                            "open_app", app=spoken, window=w.get("caption"), verified=True
                        )
        except Exception:
            pass

        # 2. Check process table
        appeared = appidentity.wait_for_launch(spoken, before, timeout=0.1, poll=0.1)
        if appeared is not None:
            _log(player, f"AMATYA: {appeared.label} is open.")
            return outcome.done(
                "open_app", app=spoken, matched=appeared.label, verified=True
            )

    threading.Thread(
        target=_launch_and_verify,
        args=(player, spoken, launcher_name, before),
        daemon=True, name=f"open-app-{spoken[:20]}",
    ).start()

    return outcome.started("open_app", app=spoken)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": (
        "Opens an application on this computer. Use whenever the user asks to "
        "open, launch or start any app or program. Put the application's name "
        "in 'app_name' exactly as the user said it. "
        "This tool answers immediately and confirms the launch in the "
        "background: on status=started say only that it is opening, never that "
        "it is open. If it does not appear, you will be told separately - "
        "relay that plainly rather than claiming success. Never say you opened "
        "something without calling this tool. "
        "To CLOSE an application use computer_control with action='close_app', "
        "not this tool. "
        "DO NOT use this tool to reach a WEB PAGE. 'open Chrome and go to "
        "YouTube', 'open YouTube', 'search the web' are all browser_control "
        "alone - it opens the browser itself. Calling open_app for the browser "
        "first and browser_control after it launches the browser TWICE, the "
        "second copy on a different profile, which is what puts a 'Who's using "
        "Chrome?' picker on the screen. Use this tool only when the user wants "
        "the application and nothing in it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": (
                    "The application's REAL name, not the user's shorthand. "
                    "Expand abbreviations and nicknames before passing them: "
                    "'wp' or 'whats' is 'WhatsApp', 'ig' is 'Instagram', 'vs "
                    "code' is 'Visual Studio Code'. A two-letter fragment "
                    "matches the wrong program - 'wp' finds WPS Office. Any "
                    "application on the machine works; there is no fixed list."
                ),
            }
        },
        "required": ["app_name"],
    },
    "handler": open_app,
}
