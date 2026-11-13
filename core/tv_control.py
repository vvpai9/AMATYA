"""
core/tv_control.py — Native Android TV & Smart Media Automation Subsystem for AMATYA.
====================================================================================
Cross-platform Android TV Remote v2 (TLS on port 6466, Pairing on port 6467)
and Cast integration using androidtvremote2, PyChromecast, and casttube.

Works universally across Linux, macOS, and Windows with pure Python / asyncio.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from memory.config_manager import CONFIG_DIR

try:
    from androidtvremote2 import AndroidTVRemote, exceptions as remote_exceptions
except ImportError:
    AndroidTVRemote = None  # type: ignore
    remote_exceptions = None  # type: ignore

log = logging.getLogger("amatya.tv")

# Default certificates directory inside AMATYA project config
TV_CERTS_DIR = CONFIG_DIR / "tv_certs"
DEFAULT_CERT_FILE = TV_CERTS_DIR / "cert.pem"
DEFAULT_KEY_FILE = TV_CERTS_DIR / "key.pem"

# Known Android TV App Packages & Deep Links
TV_APP_MAP: dict[str, str] = {
    "vlc": "org.videolan.vlc",
    "youtube": "com.google.android.youtube.tv",
    "netflix": "com.netflix.ninja",
    "prime": "com.amazon.amazonvideo.livingroom",
    "prime_video": "com.amazon.amazonvideo.livingroom",
    "spotify": "com.spotify.tv.android",
    "launcher": "com.google.android.tvlauncher",
    "home": "com.google.android.tvlauncher",
    "settings": "com.android.tv.settings",
}

APP_PACKAGE_TO_LABEL: dict[str, str] = {
    "org.videolan.vlc": "VLC",
    "com.google.android.youtube.tv": "YouTube",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.spotify.tv.android": "Spotify",
    "com.google.android.tvlauncher": "Android TV Launcher",
    "com.android.tv.settings": "Settings",
}

# AndroidTVRemote Keycode Mappings & Aliases
KEY_ALIASES: dict[str, str] = {
    "UP": "DPAD_UP",
    "DOWN": "DPAD_DOWN",
    "LEFT": "DPAD_LEFT",
    "RIGHT": "DPAD_RIGHT",
    "SELECT": "DPAD_CENTER",
    "ENTER": "ENTER",
    "CENTER": "DPAD_CENTER",
    "OK": "DPAD_CENTER",
    "HOME": "HOME",
    "BACK": "BACK",
    "POWER": "POWER",
    "MENU": "MENU",
    "VOLUME_UP": "VOLUME_UP",
    "VOLUME_DOWN": "VOLUME_DOWN",
    "MUTE": "VOLUME_MUTE",
    "PLAY_PAUSE": "MEDIA_PLAY_PAUSE",
    "PLAY": "MEDIA_PLAY",
    "PAUSE": "MEDIA_PAUSE",
    "STOP": "MEDIA_STOP",
    "NEXT": "MEDIA_NEXT",
    "PREVIOUS": "MEDIA_PREVIOUS",
    "REWIND": "MEDIA_REWIND",
    "FAST_FORWARD": "MEDIA_FAST_FORWARD",
}


class AndroidTVController:
    """Universal controller for Android TV over the Android TV Remote v2 protocol."""

    def __init__(
        self,
        host: str,
        cert_file: str | Path | None = None,
        key_file: str | Path | None = None,
        client_name: str = "AMATYA",
        key_delay: float = 0.5,
    ) -> None:
        if AndroidTVRemote is None:
            raise RuntimeError("androidtvremote2 package is not installed. Install with: pip install androidtvremote2")

        TV_CERTS_DIR.mkdir(parents=True, exist_ok=True)
        self.host = str(host or "").strip()
        self.cert_file = str(cert_file or DEFAULT_CERT_FILE)
        self.key_file = str(key_file or DEFAULT_KEY_FILE)
        self.client_name = client_name
        self.key_delay = key_delay

        # Carry over legacy atvremote certs if present and local certs not yet created
        self._ensure_certs_present()

        # Lazy initialization of remote to ensure event loop is available
        self._remote: AndroidTVRemote | None = None
        self._available = False

    def _get_remote(self) -> AndroidTVRemote:
        if self._remote is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
            self._remote = AndroidTVRemote(
                client_name=self.client_name,
                certfile=self.cert_file,
                keyfile=self.key_file,
                host=self.host,
                loop=loop,
                enable_ime=True,
                enable_voice=False,
            )
            self._remote.add_is_available_updated_callback(self._on_available)
        return self._remote

    @property
    def remote(self) -> AndroidTVRemote:
        return self._get_remote()

    def _ensure_certs_present(self) -> None:
        cert_p = Path(self.cert_file)
        key_p = Path(self.key_file)
        if not cert_p.exists() or not key_p.exists():
            legacy_cert = Path.home() / "atvremote" / "cert.pem"
            legacy_key = Path.home() / "atvremote" / "key.pem"
            if legacy_cert.exists() and legacy_key.exists():
                try:
                    shutil.copy2(legacy_cert, cert_p)
                    shutil.copy2(legacy_key, key_p)
                    key_p.chmod(0o600)
                    log.info("Migrated existing TV certificates from ~/atvremote to %s", TV_CERTS_DIR)
                except Exception as exc:
                    log.warning("Could not copy legacy certs: %s", exc)

    def _on_available(self, available: bool) -> None:
        self._available = available
        log.info("TV remote connection %s", "restored" if available else "lost")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_on(self) -> bool | None:
        try:
            return self.remote.is_on
        except Exception:
            return None

    @property
    def current_app(self) -> str | None:
        try:
            return self.remote.current_app
        except Exception:
            return None

    @property
    def volume(self) -> tuple[int | None, int | None]:
        try:
            info = self.remote.volume_info
            if isinstance(info, dict):
                return info.get("level"), info.get("max")
        except Exception:
            pass
        return None, None

    async def connect(self, settle: float = 0.5, timeout: float = 8.0, attempts: int = 2) -> bool:
        """Connect to Android TV with bounded timeout to prevent hanging."""
        for attempt in range(1, attempts + 1):
            try:
                await asyncio.wait_for(self.remote.async_connect(), timeout=timeout)
                self._available = True
                self.remote.keep_reconnecting()
                if settle > 0:
                    await asyncio.sleep(settle)
                return True
            except (asyncio.TimeoutError, Exception) as exc:
                log.warning("TV connect attempt %d/%d failed: %s", attempt, attempts, exc)
                if attempt < attempts:
                    await asyncio.sleep(1.0)
        return False

    def disconnect(self) -> None:
        try:
            self.remote.disconnect()
        except Exception:
            pass

    async def power_on(self, verify_seconds: int = 15, poll: float = 2.0) -> bool:
        """Ensure TV is powered on without accidental toggle."""
        if self.is_on is True:
            return True
        await self.send_key("POWER")
        deadline = asyncio.get_event_loop().time() + verify_seconds
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(poll)
            if self.is_on is True:
                return True
        return self.is_on is True

    async def power_off(self, verify_seconds: int = 10, poll: float = 2.0) -> bool:
        """Ensure TV is powered off / in standby."""
        if self.is_on is False:
            return True
        await self.send_key("POWER")
        deadline = asyncio.get_event_loop().time() + verify_seconds
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(poll)
            if self.is_on is False:
                return True
        return self.is_on is False

    async def send_key(self, name: str, twice: bool = False) -> bool:
        """Send remote control key command."""
        key_upper = str(name).strip().upper()
        resolved = KEY_ALIASES.get(key_upper, key_upper)
        repeat = 2 if (twice or resolved == "HOME") else 1
        for _ in range(repeat):
            try:
                self.remote.send_key_command(resolved)
                await asyncio.sleep(self.key_delay)
            except Exception as exc:
                log.warning("send_key '%s' error: %s", resolved, exc)
                return False
        return True

    async def send_text(self, text: str) -> bool:
        """Type text into active input field on TV."""
        try:
            self.remote.send_text(text)
            return True
        except Exception as exc:
            log.warning("send_text error: %s", exc)
            return False

    async def launch_app(self, app_name_or_link: str) -> bool:
        """Launch application by friendly name, package name, or intent URL."""
        target = str(app_name_or_link).strip().lower()
        package_or_url = TV_APP_MAP.get(target, app_name_or_link)
        try:
            self.remote.send_launch_app_command(package_or_url)
            await asyncio.sleep(1.0)
            return True
        except Exception as exc:
            log.warning("launch_app error for '%s': %s", package_or_url, exc)
            return False

    async def set_volume(self, target_pct: int, max_steps: int = 35) -> bool:
        """Step volume to reach desired target percentage."""
        lvl, max_lvl = self.volume
        if lvl is None or max_lvl is None:
            # Blind step based on percentage
            steps = max(1, min(10, int(target_pct / 10)))
            for _ in range(steps):
                await self.send_key("VOLUME_UP")
                await asyncio.sleep(0.3)
            return True

        target_level = max(0, min(int(round((target_pct / 100.0) * max_lvl)), max_lvl))
        for _ in range(max_steps):
            lvl, _ = self.volume
            if lvl is None or lvl == target_level:
                break
            await self.send_key("VOLUME_UP" if lvl < target_level else "VOLUME_DOWN")
            await asyncio.sleep(0.3)
        return True

    def get_status_dict(self) -> dict[str, Any]:
        lvl, max_lvl = self.volume
        vol_pct = int(round((lvl / max_lvl) * 100)) if (lvl is not None and max_lvl) else 15
        cur_pkg = self.current_app or ""
        app_label = APP_PACKAGE_TO_LABEL.get(cur_pkg, cur_pkg or "Home")
        return {
            "power": "on" if self.is_on else "standby",
            "is_on": bool(self.is_on),
            "current_app": app_label,
            "current_package": cur_pkg,
            "volume_pct": vol_pct,
            "raw_volume": lvl,
            "max_volume": max_lvl,
            "available": self._available,
        }


# Global active pairing session holder for two-step pairing (setup_tv -> pair_tv)
_ACTIVE_PAIRING_REMOTE: AndroidTVRemote | None = None
_ACTIVE_PAIRING_HOST: str = ""


async def async_start_pairing_flow(
    host: str,
    cert_file: str | Path | None = None,
    key_file: str | Path | None = None,
    client_name: str = "AMATYA",
) -> tuple[bool, str]:
    """Initiate Android TV pairing on port 6467. Generates certs and displays code on TV screen."""
    global _ACTIVE_PAIRING_REMOTE, _ACTIVE_PAIRING_HOST
    if AndroidTVRemote is None:
        return False, "androidtvremote2 is not installed. Run: pip install androidtvremote2"

    host = str(host or "").strip()
    if not host:
        return False, "Host IP address is required for pairing."

    TV_CERTS_DIR.mkdir(parents=True, exist_ok=True)
    c_file = str(cert_file or DEFAULT_CERT_FILE)
    k_file = str(key_file or DEFAULT_KEY_FILE)

    remote = AndroidTVRemote(
        client_name=client_name,
        certfile=c_file,
        keyfile=k_file,
        host=host,
    )
    try:
        await remote.async_generate_cert_if_missing()
        if Path(k_file).exists():
            Path(k_file).chmod(0o600)
    except Exception as exc:
        return False, f"Failed generating client certificates: {exc}"

    try:
        await asyncio.wait_for(remote.async_start_pairing(), timeout=10.0)
        _ACTIVE_PAIRING_REMOTE = remote
        _ACTIVE_PAIRING_HOST = host
        return True, (
            f"Pairing initiated with Android TV at {host}. "
            "A 6-character pairing code should now appear on your TV screen. "
            "Please enter it using: device_control action='pair_tv' code='<CODE>'."
        )
    except Exception as exc:
        return False, f"Failed initiating pairing with TV at {host}: {exc}"


async def async_finish_pairing_flow(code: str) -> tuple[bool, str, str]:
    """Complete pairing with code from TV screen."""
    global _ACTIVE_PAIRING_REMOTE, _ACTIVE_PAIRING_HOST
    if _ACTIVE_PAIRING_REMOTE is None:
        return False, "No active TV pairing session found. Please run action='setup_tv' first.", ""

    pairing_code = str(code or "").strip().upper()
    if not pairing_code:
        return False, "Pairing code cannot be empty.", ""

    try:
        await asyncio.wait_for(_ACTIVE_PAIRING_REMOTE.async_finish_pairing(pairing_code), timeout=12.0)
        host = _ACTIVE_PAIRING_HOST
        _ACTIVE_PAIRING_REMOTE = None
        _ACTIVE_PAIRING_HOST = ""
        return True, f"Successfully paired with Android TV at {host}!", host
    except Exception as exc:
        return False, f"Pairing failed with code '{pairing_code}': {exc}", _ACTIVE_PAIRING_HOST


def is_tv_configured(device_data: dict[str, Any] | None) -> bool:
    """Check whether a valid TV configuration exists with certificates and IP."""
    if not device_data:
        return False
    ip = device_data.get("ip_address", "").strip()
    if not ip or ip in ("192.168.1.200", "0.0.0.0", "127.0.0.1"):
        # Unconfigured template IP
        return False
    cert = device_data.get("cert_file") or str(DEFAULT_CERT_FILE)
    key = device_data.get("key_file") or str(DEFAULT_KEY_FILE)
    if not (Path(cert).exists() and Path(key).exists()):
        return False
    return bool(device_data.get("paired", False))