"""
actions/jyotisha.py — AMATYA Vedic Jyotisha & Birth Chart Intelligence Action.
================================================================================
Imparts Vedic Jyotisha and birth chart reading, computation, and analysis capabilities
to AMATYA:
  - Defaults strictly to Vedic Jyotisha (Parashari, Lahiri/Chitrapaksha Ayanamsha)
  - Western Tropical astrology mode available when explicitly requested
  - Computes exact Sidereal planetary longitudes, Lagna, and Bhavas from birth details
  - Analyzes all 16 Divisional Charts (Shodashavargas: D1 to D60), not just D1
  - Incorporates Harshal (Uranus), Varun (Neptune), Yama (Pluto), and Maandi/Gulika
  - Computes Shadbala (six-fold strength) and Jaimini Chara Karakas
  - Evaluates Graha Dignities (Uchcha, Neecha, Moolatrikona, Swakshetra, Combustion, Vakri)
  - Vimsottari Dasha calculation with active Mahadasha / Antardasha periods
  - Uses classical Indian nomenclature (Mesha..Meena, Surya..Shani)
"""
from __future__ import annotations

import json
from typing import Any

from core import outcome
from core.jyotisha import (
    calculate_vedic_chart,
    calculate_western_chart,
    render_kundali_image,
    resolve_location,
    synthesize_vedic_analysis,
    synthesize_voice_summary,
)

SKILL_METADATA = {
    "name": "jyotisha",
    "version": "1.0.0",
    "description": (
        "Vedic Jyotisha birth chart computation, Shodashavarga analysis (D1 to D60), "
        "Shadbala planetary strengths, Chara Karakas, Maandi effects, and Vimsottari Dasha. "
        "Switches to Western astrology only when explicitly requested."
    ),
    "capabilities": [
        "vedic_horoscope_calculation",
        "birth_chart_analysis",
        "divisional_charts_shodashavarga",
        "shadbala_strength_evaluation",
        "chara_karaka_computation",
        "maandi_upagraha_analysis",
        "vimsottari_dasha_calculation",
        "western_tropical_chart",
    ],
    "permissions": [],
    "dependencies": ["pyswisseph"],
    "supported_actions": [
        "calculate_chart",
        "read_chart",
        "divisional_charts",
        "shadbala",
        "dasha_timeline",
        "western_chart",
    ],
    "security_level": "normal",
}

TOOL = {
    "name": "jyotisha",
    "description": (
        "Vedic Jyotisha birth chart computation and analysis engine. "
        "Calculates Sidereal planetary positions, Lagna, all 16 divisional charts (D1..D60), "
        "Shadbala, Chara Karakas, Maandi/Gulika, outer planets (Uranus, Neptune, Pluto), and "
        "Vimsottari Dasha from birth details (date, time, place). "
        "Actions: 'calculate_chart', 'read_chart', 'divisional_charts', 'shadbala', 'dasha_timeline', 'western_chart'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to execute: 'calculate_chart' (computes complete Vedic chart), "
                    "'read_chart' (synthesizes deep astrological interpretation), "
                    "'divisional_charts' (all 16 Shodashavargas D1..D60), "
                    "'shadbala' (six-fold strengths & Chara Karakas), "
                    "'dasha_timeline' (Vimsottari Mahadashas & active period), "
                    "or 'western_chart' (Tropical chart with Placidus houses & aspects)."
                ),
            },
            "name": {
                "type": "STRING",
                "description": "Name of the person / native (default: 'Jataka').",
            },
            "date": {
                "type": "STRING",
                "description": "Date of birth in YYYY-MM-DD or DD-MM-YYYY format (e.g. '1995-05-15').",
            },
            "time": {
                "type": "STRING",
                "description": "Time of birth in HH:MM or HH:MM:SS format (e.g. '14:30:00').",
            },
            "place": {
                "type": "STRING",
                "description": "Place / City of birth (e.g. 'Bengaluru', 'Delhi', 'Mumbai', 'London', 'New York').",
            },
            "latitude": {
                "type": "NUMBER",
                "description": "Optional exact latitude in decimal degrees.",
            },
            "longitude": {
                "type": "NUMBER",
                "description": "Optional exact longitude in decimal degrees.",
            },
            "timezone_offset": {
                "type": "NUMBER",
                "description": "Optional UTC timezone offset in hours (e.g. 5.5 for IST).",
            },
            "varga": {
                "type": "STRING",
                "description": "Optional specific divisional chart to focus on (e.g. 'D9', 'D10', 'D2', 'all').",
            },
            "chart_data": {
                "type": "STRING",
                "description": "Optional manual chart text or JSON to interpret if already calculated.",
            },
        },
        "required": ["action"],
    },
    "handler": None,    # bound below
}


def jyotisha(parameters: dict[str, Any] | None = None, **kwargs: Any) -> str:
    """Execute Jyotisha astrological tool operations."""
    params = dict(parameters or {})
    if kwargs:
        params.update(kwargs)

    action = str(params.get("action", "read_chart") or "read_chart").strip().lower()
    name = str(params.get("name", "Jataka") or "Jataka").strip()
    date_str = str(params.get("date", "1995-05-15") or "1995-05-15").strip()
    time_str = str(params.get("time", "12:00:00") or "12:00:00").strip()
    place = str(params.get("place", "Bengaluru") or "Bengaluru").strip()

    lat = params.get("latitude")
    lon = params.get("longitude")
    tz = params.get("timezone_offset")

    # If Western astrology explicitly requested via action or flag
    if action in ("western_chart", "western", "tropical"):
        try:
            w_chart = calculate_western_chart(
                name=name,
                date_str=date_str,
                time_str=time_str,
                place=place,
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                timezone_offset=float(tz) if tz is not None else None,
            )
            b3 = w_chart["big_three"]
            summary_lines = [
                f"✦ WESTERN TROPICAL HOROSCOPE — {name.upper()} ✦",
                f"Born: {date_str} at {time_str} in {w_chart['place']}",
                f"• Sun Sign: {b3['sun_sign']} | Moon Sign: {b3['moon_sign']} | Rising Sign (Ascendant): {b3['rising_sign']}",
                f"• Midheaven (MC): {w_chart['midheaven_deg']:.2f}°",
                "",
                "── Planetary Placements (Placidus Houses) ──",
            ]
            for pname, pinfo in w_chart["planets"].items():
                retro_str = " (Rx)" if pinfo["is_retrograde"] else ""
                summary_lines.append(f"• {pname}: {pinfo['sign']} {pinfo['degrees_in_sign']:.2f}° (House {pinfo['house']}){retro_str}")

            summary_lines.append("\n── Major Aspects ──")
            for asp in w_chart["aspects"][:8]:
                summary_lines.append(f"• {asp['body1']} {asp['aspect']} {asp['body2']} (orb {asp['orb']}°)")

            return outcome.done(
                "jyotisha",
                result="\n".join(summary_lines),
                data=w_chart,
            )
        except Exception as exc:
            return outcome.failed("jyotisha", f"Failed to compute Western chart: {exc}")

    # Standard Vedic Jyotisha Path
    try:
        chart = calculate_vedic_chart(
            name=name,
            date_str=date_str,
            time_str=time_str,
            place=place,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            timezone_offset=float(tz) if tz is not None else None,
        )
    except Exception as exc:
        return outcome.failed("jyotisha", f"Error computing Vedic birth chart: {exc}")

    if action in ("calculate_chart", "chart", "kundali", "kundli", "birth_chart"):
        graha_summary = []
        for gname in ["Surya", "Chandra", "Mangala", "Budha", "Guru", "Shukra", "Shani", "Rahu", "Ketu", "Harshal (Uranus)", "Varun (Neptune)", "Yama (Pluto)", "Maandi"]:
            if gname in chart.grahas:
                g = chart.grahas[gname]
                retro = " [Vakri]" if g.is_retrograde else ""
                comb = " [Asta]" if g.is_combust else ""
                karaka = f" [{g.karaka}]" if g.karaka else ""
                graha_summary.append(
                    f"• {g.name}: {g.sign_name} ({g.degrees_in_sign:.2f}°) in Bhava {g.house} — "
                    f"{g.nakshatra} (Pada {g.pada}){retro}{comb}{karaka} ({g.dignity})"
                )

        result_text = (
            f"✦ VEDIC KUNDALI / BIRTH CHART — {chart.name.upper()} ✦\n"
            f"Birth: {chart.date_str} {chart.time_str} | Place: {chart.place} (Lat: {chart.latitude}, Lon: {chart.longitude})\n"
            f"Ayanamsha: {chart.ayanamsha_name} ({chart.ayanamsha_value}°)\n"
            f"Lagna: {chart.lagna_sign} ({chart.lagna_deg % 30:.2f}°) | Nakshatra: {chart.lagna_nakshatra} Pada {chart.lagna_pada}\n"
            f"Chandra Rashi: {chart.grahas['Chandra'].sign_name} ({chart.grahas['Chandra'].nakshatra})\n\n"
            f"── Planetary Positions (Grahas & Upagrahas) ──\n"
            + "\n".join(graha_summary)
            + f"\n\nActive Dasha: {chart.active_dasha['mahadasha']} Mahadasha - {chart.active_dasha['antardasha']} Antardasha (until {chart.active_dasha['end_date']})"
        )
        return outcome.done("jyotisha", result=result_text, data=chart.to_dict())

    style = str(params.get("style", "north") or "north").strip().lower()

    if action in ("render_chart", "kundali_image", "chart_image", "draw_chart", "image"):
        try:
            img_path = render_kundali_image(chart, style=style)
            player = kwargs.get("player")
            if player and hasattr(player, "show_content"):
                player.show_content(f"VEDIC KUNDALI ({style.upper()})", f"Kundali chart rendered to:\n{img_path}")
            return outcome.done(
                "jyotisha",
                result=f"Kundali ({style.upper()} Indian style) generated successfully for {chart.name}.\nSaved to: {img_path}",
                data={"image_path": img_path, "style": style, "chart": chart.to_dict()},
            )
        except Exception as exc:
            return outcome.failed("jyotisha", f"Failed to generate Kundali image: {exc}")

    if action in ("read_chart", "analyze_chart", "reading", "interpret"):
        reading_text = synthesize_vedic_analysis(chart)
        try:
            img_path = render_kundali_image(chart, style=style)
        except Exception:
            img_path = ""

        # Persist comprehensive reading to reports
        try:
            from pathlib import Path
            import re
            r_dir = Path.home() / "Projects/Mark-LVI/reports/kundali"
            r_dir.mkdir(parents=True, exist_ok=True)
            clean_name = re.sub(r"[^\w\-]", "_", chart.name.lower())
            r_file = r_dir / f"reading_{clean_name}_{chart.date_str}.txt"
            r_file.write_text(reading_text, encoding="utf-8")
        except Exception:
            pass

        # Display on UI HUD if player is available
        player = kwargs.get("player")
        if player and hasattr(player, "show_content"):
            player.show_content(f"VEDIC JYOTISHA — {chart.name.upper()}", reading_text)

        # Generate concise spoken summary so Gemini Live never hangs or stalls
        voice_summary = synthesize_voice_summary(chart)
        return outcome.done(
            "jyotisha",
            result=voice_summary,
            data={**chart.to_dict(), "reading_text": reading_text, "image_path": img_path},
        )

    if action in ("divisional_charts", "vargas", "shodashavarga"):
        target_varga = str(params.get("varga", "all") or "all").upper().strip()
        varga_lines = [f"✦ SHODASHAVARGA DIVISIONAL CHARTS — {chart.name.upper()} ✦"]
        
        varga_descriptions = {
            "D1": "Rashi (Physical vitality & general destiny)",
            "D2": "Hora (Wealth, prosperity & movable assets)",
            "D3": "Drekkana (Siblings, courage, vitality)",
            "D4": "Chaturthamsa (Fixed assets, property & fortune)",
            "D7": "Saptamsha (Children, lineage & progeny)",
            "D9": "Navamsha (Spouse, marriage, dharma & soul potential)",
            "D10": "Dashamsha (Career, profession, power & status)",
            "D12": "Dwadashamsha (Parents, ancestors & past life karma)",
            "D16": "Shodashamsha (Conveyances, comforts & luxuries)",
            "D20": "Vimshamsha (Spiritual progress, upasana & devotion)",
            "D24": "Chaturvimshamsha (Learning, intellect & higher knowledge)",
            "D27": "Saptavimshamsha (Physical stamina, strengths & weaknesses)",
            "D30": "Trimshamsha (Evils, misfortunes & challenges)",
            "D40": "Khavedamsha (Auspicious and inauspicious karmas)",
            "D45": "Akshavedamsha (Moral character & integrity)",
            "D60": "Shashtiamsha (All areas of life, deep past karma)",
        }

        vargas_to_show = [target_varga] if target_varga in chart.divisional_charts else chart.divisional_charts.keys()

        for vk in vargas_to_show:
            v_map = chart.divisional_charts[vk]
            desc = varga_descriptions.get(vk, "Divisional Chart")
            varga_lines.append(f"\n[{vk}] — {desc}:")
            varga_lines.append(f"  Lagna: {v_map.get('Lagna', '')}")
            graha_parts = [f"{g}: {v_map.get(g, '')}" for g in ["Surya", "Chandra", "Mangala", "Budha", "Guru", "Shukra", "Shani", "Rahu", "Ketu", "Maandi"] if g in v_map]
            varga_lines.append("  " + " | ".join(graha_parts))

        return outcome.done(
            "jyotisha",
            result="\n".join(varga_lines),
            data=chart.divisional_charts,
        )

    if action in ("shadbala", "planetary_strengths", "strengths"):
        sb_lines = [
            f"✦ SHADBALA & CHARA KARAKAS — {chart.name.upper()} ✦",
            "── Jaimini Chara Karakas (Soul & Worldly Roles) ──",
        ]
        karaka_full_names = {
            "AK": "Atmakaraka (AK)",
            "AmK": "Amatyakaraka (AmK)",
            "BK": "Bhratrikaraka (BK)",
            "MK": "Matrikaraka (MK)",
            "PiK": "Pitrikaraka (PiK)",
            "PK": "Putrakaraka (PK)",
            "GK": "Gnatikaraka (GK)",
            "DK": "Darakaraka (DK)",
        }
        for kcode, p in chart.chara_karakas.items():
            k_disp = karaka_full_names.get(kcode, kcode)
            sb_lines.append(f"• {k_disp}: {p} ({chart.grahas[p].sign_name} {chart.grahas[p].degrees_in_sign:.2f}°)")

        sb_lines.append("\n── Shadbala (Six-Fold Planetary Strengths) ──")
        for p, sb in chart.shadbala.items():
            sb_lines.append(
                f"• {p}: {sb['total_rupas']} Rupas ({sb['total_virupas']} Virupas) — Status: {sb['strength_status']} "
                f"[Sthana={sb['sthana_bala']}, Dig={sb['dig_bala']}, Kala={sb['kala_bala']}, Cheshta={sb['cheshta_bala']}, Naisargika={sb['naisargika_bala']}]"
            )

        return outcome.done(
            "jyotisha",
            result="\n".join(sb_lines),
            data={"chara_karakas": chart.chara_karakas, "shadbala": chart.shadbala},
        )

    if action in ("dasha_timeline", "vimsottari", "dasha"):
        active_d = chart.active_dasha
        timeline = chart.dasha_timeline
        dt_lines = [
            f"✦ VIMSOTTARI DASHA TIMELINE — {chart.name.upper()} ✦",
            f"Janma Nakshatra: {chart.dasha_balance['nakshatra']} (Lord: {chart.dasha_balance['nakshatra_lord']})",
            f"Birth Balance: {chart.dasha_balance['balance_formatted']}",
            f"\n★ CURRENT ACTIVE PERIOD: {active_d['mahadasha']} Mahadasha — {active_d['antardasha']} Antardasha (until {active_d['end_date']})\n",
            "── Mahadasha Periods ──",
        ]
        for m in timeline:
            dt_lines.append(f"• {m['mahadasha']} Mahadasha ({m['duration_years']} yrs): {m['start_date']} → {m['end_date']}")

        return outcome.done(
            "jyotisha",
            result="\n".join(dt_lines),
            data={"active_dasha": active_d, "timeline": timeline},
        )

    return outcome.failed("jyotisha", f"Unknown Jyotisha action: '{action}'. Try: calculate_chart, read_chart, divisional_charts, shadbala, dasha_timeline, western_chart.")


TOOL["handler"] = jyotisha
execute = jyotisha
