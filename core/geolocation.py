"""
core/geolocation.py — Device Geolocation and Positioning Service for AMATYA
==========================================================================
Provides accurate real-time device location, geographic coordinates, and regional
context for aerospace flight tracking, local news, weather, and time calculations.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from memory.config_manager import CONFIG_DIR

logger = logging.getLogger(__name__)

LOCATION_CACHE_FILE = CONFIG_DIR / "device_location.json"
_LOCK = threading.RLock()
_CACHED_LOCATION: Optional[dict[str, Any]] = None

# Known timezone coordinates mapping for offline fallback
_TIMEZONE_FALLBACKS: dict[str, dict[str, Any]] = {
    "Asia/Kolkata": {
        "city": "Bengaluru",
        "region": "Karnataka",
        "country": "India",
        "country_code": "IN",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "timezone": "Asia/Kolkata",
        "display_name": "Karnataka, India",
    },
    "Asia/Calcutta": {
        "city": "Bengaluru",
        "region": "Karnataka",
        "country": "India",
        "country_code": "IN",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "timezone": "Asia/Kolkata",
        "display_name": "Karnataka, India",
    },
    "America/New_York": {
        "city": "New York",
        "region": "New York",
        "country": "United States",
        "country_code": "US",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timezone": "America/New_York",
        "display_name": "New York, USA",
    },
    "Europe/London": {
        "city": "London",
        "region": "England",
        "country": "United Kingdom",
        "country_code": "GB",
        "latitude": 51.5074,
        "longitude": -0.1278,
        "timezone": "Europe/London",
        "display_name": "London, UK",
    },
}


def _fetch_from_ip_api() -> Optional[dict[str, Any]]:
    """Query ip-api.com for rapid, detailed network geolocation."""
    try:
        url = "http://ip-api.com/json/?fields=status,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp"
        req = urllib.request.Request(url, headers={"User-Agent": "AMATYA-Geolocation/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success" and "lat" in data and "lon" in data:
                city = data.get("city") or ""
                region = data.get("regionName") or data.get("region") or ""
                country = data.get("country") or ""
                parts = [p for p in [city, region, country] if p]
                return {
                    "city": city,
                    "region": region,
                    "country": country,
                    "country_code": data.get("countryCode", ""),
                    "latitude": float(data["lat"]),
                    "longitude": float(data["lon"]),
                    "timezone": data.get("timezone", ""),
                    "zip": data.get("zip", ""),
                    "isp": data.get("isp", ""),
                    "display_name": ", ".join(parts) if parts else "Local Region",
                    "source": "network_ip",
                    "updated_at": datetime.now().isoformat(),
                }
    except Exception as exc:
        logger.debug(f"[Geolocation] ip-api query failed: {exc}")
    return None


def _fetch_from_ipapi_co() -> Optional[dict[str, Any]]:
    """Secondary fallback: query ipapi.co."""
    try:
        url = "https://ipapi.co/json/"
        req = urllib.request.Request(url, headers={"User-Agent": "AMATYA-Geolocation/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                city = data.get("city") or ""
                region = data.get("region") or ""
                country = data.get("country_name") or ""
                parts = [p for p in [city, region, country] if p]
                return {
                    "city": city,
                    "region": region,
                    "country": country,
                    "country_code": data.get("country_code", ""),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "timezone": data.get("timezone", ""),
                    "zip": data.get("postal", ""),
                    "isp": data.get("org", ""),
                    "display_name": ", ".join(parts) if parts else "Local Region",
                    "source": "network_ip",
                    "updated_at": datetime.now().isoformat(),
                }
    except Exception as exc:
        logger.debug(f"[Geolocation] ipapi.co query failed: {exc}")
    return None


def _get_system_timezone() -> str:
    """Read host system timezone name."""
    try:
        # Check /etc/timezone
        tz_file = Path("/etc/timezone")
        if tz_file.is_file():
            tz = tz_file.read_text(encoding="utf-8").strip()
            if tz:
                return tz
        # Check symlink /etc/localtime
        loc_file = Path("/etc/localtime")
        if loc_file.is_symlink():
            target = str(loc_file.resolve())
            if "zoneinfo/" in target:
                return target.split("zoneinfo/")[-1]
    except Exception:
        pass
    return time.tzname[0] if time.tzname else "UTC"


def get_device_location(force_refresh: bool = False) -> dict[str, Any]:
    """Retrieve full device geolocation info with caching and smart fallback."""
    global _CACHED_LOCATION

    with _LOCK:
        # 1. Memory cache check
        if _CACHED_LOCATION and not force_refresh:
            return _CACHED_LOCATION

        # 2. File cache check (< 24 hours old)
        if not force_refresh and LOCATION_CACHE_FILE.is_file():
            try:
                from core.security import decrypt_sensitive_data
                cached = decrypt_sensitive_data(LOCATION_CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and "latitude" in cached and "longitude" in cached:
                    # Validate freshness
                    up_str = cached.get("updated_at")
                    if up_str:
                        up_dt = datetime.fromisoformat(up_str)
                        if (datetime.now() - up_dt).total_seconds() < 86400:
                            _CACHED_LOCATION = cached
                            return cached
            except Exception:
                pass

        # 3. Check memory manager user override
        try:
            from memory.memory_manager import load_memory
            mem = load_memory()
            user_loc = mem.get("user_location") or mem.get("location")
            if isinstance(user_loc, dict) and "latitude" in user_loc:
                _CACHED_LOCATION = user_loc
                return user_loc
        except Exception:
            pass

        # 4. Live network geolocation probe
        loc = _fetch_from_ip_api() or _fetch_from_ipapi_co()
        if loc:
            _save_location(loc)
            _CACHED_LOCATION = loc
            return loc

        # 5. Stored cache fallback if network failed
        if LOCATION_CACHE_FILE.is_file():
            try:
                from core.security import decrypt_sensitive_data
                cached = decrypt_sensitive_data(LOCATION_CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and "latitude" in cached:
                    _CACHED_LOCATION = cached
                    return cached
            except Exception:
                pass

        # 6. System timezone fallback
        sys_tz = _get_system_timezone()
        tz_entry = _TIMEZONE_FALLBACKS.get(sys_tz)
        if tz_entry:
            res = dict(tz_entry)
            res["source"] = "system_timezone"
            res["updated_at"] = datetime.now().isoformat()
            _CACHED_LOCATION = res
            return res

        # Default global fallback
        default_loc = {
            "city": "",
            "region": "",
            "country": "Global",
            "country_code": "",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "timezone": sys_tz,
            "display_name": "Global (Local Region)",
            "source": "default",
            "updated_at": datetime.now().isoformat(),
        }
        _CACHED_LOCATION = default_loc
        return default_loc


def _save_location(data: dict[str, Any]) -> None:
    """Persist location data to encrypted cache and sync display name with memory."""
    try:
        from core.security import encrypt_sensitive_data
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        encrypted_payload = encrypt_sensitive_data(data)
        LOCATION_CACHE_FILE.write_text(encrypted_payload, encoding="utf-8")
        try:
            os.chmod(LOCATION_CACHE_FILE, 0o600)
        except Exception:
            pass

        # Sync location display name with memory manager (avoid storing raw coordinates in cleartext memory)
        from memory.memory_manager import load_memory, save_memory
        mem = load_memory()
        mem["user_location"] = data.get("display_name") or data.get("city") or "Local Region"
        save_memory(mem)
    except Exception:
        pass


def get_device_coordinates() -> tuple[float, float]:
    """Return device (latitude, longitude) coordinates as floats."""
    loc = get_device_location()
    return float(loc.get("latitude", 12.9716)), float(loc.get("longitude", 77.5946))


def get_device_location_name() -> str:
    """Return human-readable device location name (e.g. 'Mangaluru, Karnataka, India')."""
    loc = get_device_location()
    return loc.get("display_name") or loc.get("city") or loc.get("region") or loc.get("country") or "Local Region"


def set_device_location(
    city: str,
    region: str = "",
    country: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    """Manually configure or override device location."""
    global _CACHED_LOCATION
    with _LOCK:
        current = get_device_location()
        parts = [p for p in [city, region, country] if p]
        disp = ", ".join(parts) if parts else city

        updated = {
            "city": city,
            "region": region or current.get("region", ""),
            "country": country or current.get("country", ""),
            "country_code": current.get("country_code", ""),
            "latitude": latitude if latitude is not None else current.get("latitude", 12.9716),
            "longitude": longitude if longitude is not None else current.get("longitude", 77.5946),
            "timezone": current.get("timezone", _get_system_timezone()),
            "display_name": disp,
            "source": "manual",
            "updated_at": datetime.now().isoformat(),
        }
        _save_location(updated)
        _CACHED_LOCATION = updated
        return updated
