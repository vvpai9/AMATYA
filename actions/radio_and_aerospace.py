"""
actions/radio_and_aerospace.py — AMATYA Radio Services & Aerospace Trajectory Action
==================================================================================
Handles:
  1. Radio discovery, listing stations on the HUD, and audio playback control.
  2. Tracking flights, space stations (ISS, Tiangong), and satellite trajectories
     with proximity alerts and HUD telemetry visualization.
"""
from __future__ import annotations

from typing import Any

from core import radio_aerospace


def radio_control_action(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Discover radio stations, list on HUD, and manage playback."""
    params = parameters or {}
    action = str(params.get("action") or "search").strip().lower()
    query = str(params.get("query") or params.get("station") or "").strip()
    volume = int(params.get("volume", 80))

    if action in ("search", "list", "discover"):
        stations = radio_aerospace.search_radio_stations(query, limit=12)
        if not stations:
            return f"No radio stations found matching '{query}'."

        md_lines = [
            f"# 📻 AMATYA Radio Station Directory",
            f"**Search Query:** `{query or 'Popular Curated & Open Stations'}` | **Stations Found:** `{len(stations)}`",
            "---",
            "| Station Name | Genre / Tags | Country | Bitrate |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for s in stations:
            md_lines.append(f"| **{s['name']}** | {s.get('genre')} | {s.get('country')} | {s.get('bitrate')} |")

        md_lines.append("\n*To connect to a station, say:* `Play radio <Station Name>`")

        if player is not None:
            try:
                player.show_content("Radio Stations Directory", "\n".join(md_lines))
                player.write_log(f"RADIO: Listed {len(stations)} available stations on HUD.")
            except Exception:
                pass

        sample_names = ", ".join(s['name'] for s in stations[:3])
        return f"Found {len(stations)} radio stations on the HUD, including {sample_names}. Say play radio with your chosen station to connect."

    elif action in ("play", "connect", "listen"):
        if not query:
            return "Please specify which radio station you would like to play, sir."
        ok, msg = radio_aerospace.play_radio(query, volume=volume, player=player)
        return msg

    elif action in ("stop", "pause", "disconnect", "off"):
        return radio_aerospace.stop_radio(player=player)

    elif action in ("status", "current", "info"):
        st = radio_aerospace.get_radio_status()
        if st["is_playing"] and st["station"]:
            s = st["station"]
            return f"Currently playing '{s['name']}' ({s.get('genre')}) at volume {st['volume']}%."
        return "Radio playback is currently stopped."

    return "Unknown radio action. Available actions: search, list, play, stop, status."


def track_trajectories_action(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Track flights, satellites, and space stations trajectories with HUD alerts."""
    params = parameters or {}
    target = str(params.get("target") or "iss").strip().lower()

    if target in ("iss", "space_station", "international_space_station"):
        data = radio_aerospace.get_iss_trajectory()
        md_lines = [
            f"# 🛰️ International Space Station (ISS) Live Trajectory",
            f"**Timestamp:** `{data['timestamp']}` | **NORAD ID:** `{data['norad_id']}`",
            "---",
            f"- **Latitude:** `{data['latitude']}°`",
            f"- **Longitude:** `{data['longitude']}°`",
            f"- **Orbital Altitude:** `{data['altitude_km']} km`",
            f"- **Ground Velocity:** `{data['velocity_kmh']} km/h` (~7.66 km/s)",
            f"- **Optical Visibility:** `{data['visibility'].title()}`",
            f"- **Overhead Status:** `{'⚠️ CURRENTLY OVERHEAD' if data['is_overhead'] else 'Outside Direct Line of Sight'}`",
        ]
        if player is not None:
            try:
                player.show_content("ISS Trajectory Tracker", "\n".join(md_lines))
                if data["is_overhead"]:
                    player.write_log(f"ALERT: International Space Station is currently passing overhead!")
            except Exception:
                pass
        return (
            f"The International Space Station is at coordinates {data['latitude']} degrees latitude, "
            f"{data['longitude']} degrees longitude, travelling at {data['velocity_kmh']} kilometers per hour "
            f"at an altitude of {data['altitude_km']} kilometers."
        )

    elif target in ("satellites", "space_stations", "constellations"):
        sats = radio_aerospace.get_satellite_trajectories()
        md_lines = [
            f"# 🛰️ Orbital Space Stations & Satellite Trajectories",
            "---",
            "| Target | NORAD ID | Latitude | Longitude | Altitude | Velocity |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for s in sats:
            md_lines.append(f"| **{s['target']}** | {s['norad_id']} | {s['latitude']}° | {s['longitude']}° | {s['altitude_km']} km | {s['velocity_kmh']} km/h |")

        if player is not None:
            try:
                player.show_content("Orbital Trajectories Tracker", "\n".join(md_lines))
                player.write_log("AEROSPACE: Orbital tracking telemetry refreshed on HUD.")
            except Exception:
                pass
        return f"Tracking {len(sats)} orbital space stations and satellites. Real-time telemetry is live on your HUD."

    elif target in ("overhead_flights", "airspace", "flights"):
        from core.geolocation import get_device_location_name, get_device_coordinates
        loc_name = get_device_location_name()
        lat, lon = get_device_coordinates()

        flights = radio_aerospace.get_overhead_flights(user_lat=lat, user_lon=lon)
        provider = flights[0].get("source", "Flightradar24 / OpenSky") if flights else "Flightradar24"
        md_lines = [
            f"# ✈️ Local Airspace Trajectory Tracker",
            f"**Sector:** `{loc_name}` (`{lat:.2f}°, {lon:.2f}°`) | **Active Targets:** `{len(flights)}` | **Radar:** `{provider}`",
            "---",
            "| Flight / Callsign | Route | Aircraft | Altitude | Velocity | Heading | Source |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for f in flights:
            route = f.get("route") or f.get("origin_country") or "En Route"
            model = f.get("model") or "Airliner"
            src = f.get("source") or provider
            md_lines.append(f"| **{f['callsign']}** | {route} | {model} | {f['altitude_ft']:,} ft | {f['velocity_kmh']} km/h | {f['heading_deg']}° | {src} |")

        if player is not None:
            try:
                player.show_content(f"Airspace: {loc_name}", "\n".join(md_lines))
                player.write_log(f"AIRSPACE: Tracking {len(flights)} active flights over {loc_name} via {provider}.")
            except Exception:
                pass
        return f"Currently tracking {len(flights)} airborne flights in the local airspace over {loc_name} via {provider} on your HUD."

    else:
        # Target is a specific flight callsign (e.g. 'AI101', 'BAW123')
        flight = radio_aerospace.track_flight(target)
        provider = flight.get("source", "Flightradar24 / OpenSky")
        flight_num = flight.get("flight_number") or flight["callsign"]
        airline = flight.get("airline") or flight.get("origin_country") or "Commercial Airline"
        route = flight.get("route") or (f"{flight.get('origin', '')} → {flight.get('destination', '')}".strip(" →"))

        md_lines = [
            f"# ✈️ Flight Telemetry: {flight_num} ({flight['callsign']})",
            f"**Operator:** `{airline}` | **Source:** `{provider}`",
            "---",
        ]
        if route:
            md_lines.append(f"- **Route:** `{route}`")
        if flight.get("origin"):
            md_lines.append(f"- **Origin Airport:** `{flight['origin']}`")
        if flight.get("destination"):
            md_lines.append(f"- **Destination Airport:** `{flight['destination']}`")
        if flight.get("model"):
            md_lines.append(f"- **Aircraft Type:** `{flight['model']}`")
        if flight.get("registration"):
            md_lines.append(f"- **Registration:** `{flight['registration']}`")
        if flight.get("icao24"):
            md_lines.append(f"- **ICAO24 Address:** `{flight['icao24']}`")
        if flight.get("altitude_ft") is not None:
            md_lines.append(f"- **Current Altitude:** `{flight['altitude_ft']:,} ft` ({flight.get('altitude_m', 0):,} m)")
        if flight.get("velocity_kmh") is not None:
            md_lines.append(f"- **Ground Speed:** `{flight['velocity_kmh']} km/h` ({flight.get('velocity_kts', 0)} knots)")
        if flight.get("heading_deg") is not None:
            md_lines.append(f"- **Current Heading:** `{flight['heading_deg']}°`")
        if flight.get("latitude") is not None and flight.get("longitude") is not None:
            md_lines.append(f"- **Coordinates:** `{flight['latitude']}°, {flight['longitude']}°`")
        if flight.get("vertical_rate_mps") is not None:
            md_lines.append(f"- **Vertical Rate:** `{flight['vertical_rate_mps']} m/s`")

        if player is not None:
            try:
                player.show_content(f"Flight: {flight_num}", "\n".join(md_lines))
                player.write_log(f"FLIGHT: Locked telemetry for flight {flight_num} via {provider}")
            except Exception:
                pass

        if route:
            return (
                f"Flight {flight_num} operated by {airline} flying {route} is tracked via {provider} "
                f"cruising at {flight['altitude_ft']:,} feet at {flight['velocity_kmh']} kilometers per hour."
            )
        return (
            f"Flight {flight_num} is cruising at {flight['altitude_ft']:,} feet "
            f"at a ground speed of {flight['velocity_kmh']} kilometers per hour, heading {flight['heading_deg']} degrees."
        )


SKILL_METADATA = {
    "capabilities": [
        "radio_streaming",
        "station_discovery",
        "flight_tracking",
        "iss_trajectory",
        "satellite_tracking",
        "aerospace_telemetry",
    ],
    "permissions": ["network_access", "audio_playback"],
    "dependencies": [],
    "supported_actions": ["radio", "stations", "play_radio", "iss", "flights", "satellites"],
    "security_level": "normal",
}

TOOL = {
    "name": "radio_and_aerospace",
    "description": (
        "Discover and stream global radio stations on the HUD, and track live aerospace "
        "trajectories including the International Space Station (ISS), satellites, and commercial flights."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "enum": ["radio", "aerospace"],
                "description": "Choose 'radio' for radio station search/playback, or 'aerospace' for trajectory tracking.",
            },
            "radio_action": {
                "type": "STRING",
                "enum": ["search", "list", "play", "stop", "status"],
                "description": "Action for radio control.",
            },
            "station": {
                "type": "STRING",
                "description": "Radio station name or genre to search or play.",
            },
            "aerospace_target": {
                "type": "STRING",
                "description": "Trajectory target: 'iss', 'satellites', 'overhead_flights', or a specific flight callsign (e.g. 'AI101').",
            },
            "volume": {
                "type": "INTEGER",
                "description": "Volume percentage (0-100) for radio streaming.",
            },
        },
    },
    "handler": lambda parameters, player=None, **kwargs: (
        track_trajectories_action({"target": parameters.get("aerospace_target", "iss")}, player=player, **kwargs)
        if parameters.get("mode") == "aerospace" or parameters.get("aerospace_target")
        else radio_control_action({
            "action": parameters.get("radio_action", "search"),
            "query": parameters.get("station", ""),
            "volume": parameters.get("volume", 80),
        }, player=player, **kwargs)
    ),
}
