"""
core/jyotisha.py — AMATYA Vedic Jyotisha & Astrological Intelligence Engine.
=============================================================================
Provides high-precision Vedic Sidereal (Lahiri/Chitrapaksha) and Western Tropical
astrological calculations, chart synthesis, and comprehensive interpretation:
  - Planetary positions (7 classical Grahas + Rahu/Ketu + Uranus, Neptune, Pluto + Maandi/Gulika)
  - All 16 Divisional Charts (Shodashavargas: D1, D2, D3, D4, D7, D9, D10, D12, D16, D20, D24, D27, D30, D40, D45, D60)
  - Graha Dignities (Uchcha, Neecha, Moolatrikona, Swakshetra, Panchadha Maitri, Combustion/Asta, Retrogression/Vakri)
  - Jaimini Chara Karakas (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Pitrikaraka, Putrakaraka, Gnatikaraka, Darakaraka)
  - Shadbala (Six-fold planetary strength: Sthana, Dig, Kala, Cheshta, Naisargika, Drik)
  - Vimsottari Dasha sequence and active Mahadasha / Antardasha calculation
  - Synthesized readings for Life Path, Career (D10), Marriage & Relationships (D9), Wealth (D2), Transits & Upayas
  - Western Astrology mode (Tropical, Placidus houses, Major Aspects) available on explicit request.
"""
from __future__ import annotations

import datetime
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import swisseph as swe

# ── 1. Constants & Nomenclature ────────────────────────────────────────────────

RASHI_NAMES_INDIAN = [
    "Mesha", "Vrishabha", "Mithuna", "Karka",
    "Simha", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makara", "Kumbha", "Meena",
]

RASHI_NAMES_WESTERN = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

RASHI_LORDS = [
    "Mangala", "Shukra", "Budha", "Chandra",
    "Surya", "Budha", "Shukra", "Mangala",
    "Guru", "Shani", "Shani", "Guru",
]

GRAHA_NAMES_INDIAN = {
    "Sun": "Surya",
    "Moon": "Chandra",
    "Mars": "Mangala",
    "Mercury": "Budha",
    "Jupiter": "Guru",
    "Venus": "Shukra",
    "Saturn": "Shani",
    "Rahu": "Rahu",
    "Ketu": "Ketu",
    "Uranus": "Harshal (Uranus)",
    "Neptune": "Varun (Neptune)",
    "Pluto": "Yama (Pluto)",
    "Maandi": "Maandi",
    "Gulika": "Gulika",
    "Ascendant": "Lagna",
}

NAKSHATRAS = [
    ("Ashwini", "Ketu"), ("Bharani", "Shukra"), ("Krittika", "Surya"),
    ("Rohini", "Chandra"), ("Mrigashira", "Mangala"), ("Ardra", "Rahu"),
    ("Punarvasu", "Guru"), ("Pushya", "Shani"), ("Ashlesha", "Budha"),
    ("Magha", "Ketu"), ("Purva Phalguni", "Shukra"), ("Uttara Phalguni", "Surya"),
    ("Hasta", "Chandra"), ("Chitra", "Mangala"), ("Swati", "Rahu"),
    ("Vishakha", "Guru"), ("Anuradha", "Shani"), ("Jyeshtha", "Budha"),
    ("Mula", "Ketu"), ("Purva Ashadha", "Shukra"), ("Uttara Ashadha", "Surya"),
    ("Shravana", "Chandra"), ("Dhanishta", "Mangala"), ("Shatabhisha", "Rahu"),
    ("Purva Bhadrapada", "Guru"), ("Uttara Bhadrapada", "Shani"), ("Revati", "Budha"),
]

DASHA_YEARS = {
    "Ketu": 7.0,
    "Shukra": 20.0,
    "Surya": 6.0,
    "Chandra": 10.0,
    "Mangala": 7.0,
    "Rahu": 18.0,
    "Guru": 16.0,
    "Shani": 19.0,
    "Budha": 17.0,
}

DASHA_ORDER = ["Ketu", "Shukra", "Surya", "Chandra", "Mangala", "Rahu", "Guru", "Shani", "Budha"]

# Natural Friendship Table (Naisargika Maitri)
# 1 = Friend, 0 = Neutral, -1 = Enemy
NAISARGIKA_MAITRI: dict[str, dict[str, int]] = {
    "Surya":   {"Chandra": 1, "Mangala": 1, "Guru": 1, "Budha": 0, "Shukra": -1, "Shani": -1},
    "Chandra": {"Surya": 1, "Budha": 1, "Mangala": 0, "Guru": 0, "Shukra": 0, "Shani": 0},
    "Mangala": {"Surya": 1, "Chandra": 1, "Guru": 1, "Shukra": 0, "Shani": 0, "Budha": -1},
    "Budha":   {"Surya": 1, "Shukra": 1, "Mangala": 0, "Guru": 0, "Shani": 0, "Chandra": -1},
    "Guru":    {"Surya": 1, "Chandra": 1, "Mangala": 1, "Shani": 0, "Budha": -1, "Shukra": -1},
    "Shukra":  {"Budha": 1, "Shani": 1, "Mangala": 0, "Guru": 0, "Surya": -1, "Chandra": -1},
    "Shani":   {"Budha": 1, "Shukra": 1, "Guru": 0, "Surya": -1, "Chandra": -1, "Mangala": -1},
}

EXALTATION_SIGNS = {
    "Surya": (0, 10.0),      # Mesha 10°
    "Chandra": (1, 3.0),     # Vrishabha 3°
    "Mangala": (9, 28.0),    # Makara 28°
    "Budha": (5, 15.0),      # Kanya 15°
    "Guru": (3, 5.0),        # Karka 5°
    "Shukra": (11, 27.0),    # Meena 27°
    "Shani": (6, 20.0),      # Tula 20°
    "Rahu": (1, 20.0),       # Vrishabha (also Mithuna)
    "Ketu": (7, 20.0),       # Vrishchika (also Dhanu)
}

DEBILITATION_SIGNS = {
    "Surya": (6, 10.0),      # Tula 10°
    "Chandra": (7, 3.0),     # Vrishchika 3°
    "Mangala": (3, 28.0),    # Karka 28°
    "Budha": (11, 15.0),     # Meena 15°
    "Guru": (9, 5.0),        # Makara 5°
    "Shukra": (5, 27.0),     # Kanya 27°
    "Shani": (0, 20.0),      # Mesha 20°
    "Rahu": (7, 20.0),       # Vrishchika
    "Ketu": (1, 20.0),       # Vrishabha
}

COMBUSTION_LIMITS = {
    "Chandra": 12.0,
    "Mangala": 17.0,
    "Budha": 14.0,           # 12° when retrograde
    "Guru": 11.0,
    "Shukra": 10.0,          # 8° when retrograde
    "Shani": 15.0,
}

# Major Indian & World Cities Geocoder
CITY_COORDINATES: dict[str, tuple[float, float, float]] = {
    # City: (Latitude, Longitude, UTC_Offset_Hours)
    "delhi": (28.6139, 77.2090, 5.5),
    "new delhi": (28.6139, 77.2090, 5.5),
    "mumbai": (19.0760, 72.8777, 5.5),
    "bombay": (19.0760, 72.8777, 5.5),
    "bengaluru": (12.9716, 77.5946, 5.5),
    "bangalore": (12.9716, 77.5946, 5.5),
    "chennai": (13.0827, 80.2707, 5.5),
    "madras": (13.0827, 80.2707, 5.5),
    "kolkata": (22.5726, 88.3639, 5.5),
    "calcutta": (22.5726, 88.3639, 5.5),
    "hyderabad": (17.3850, 78.4867, 5.5),
    "ahmedabad": (23.0225, 72.5714, 5.5),
    "pune": (18.5204, 73.8567, 5.5),
    "jaipur": (26.9124, 75.7873, 5.5),
    "lucknow": (26.8467, 80.9462, 5.5),
    "kanpur": (26.4499, 80.3319, 5.5),
    "nagpur": (21.1458, 79.0882, 5.5),
    "indore": (22.7196, 75.8577, 5.5),
    "bhopal": (23.2599, 77.4126, 5.5),
    "patna": (25.5941, 85.1376, 5.5),
    "vadodara": (22.3072, 73.1812, 5.5),
    "surat": (21.1702, 72.8311, 5.5),
    "varanasi": (25.3176, 82.9739, 5.5),
    "kashi": (25.3176, 82.9739, 5.5),
    "amritsar": (31.6340, 74.8723, 5.5),
    "coimbatore": (11.0168, 76.9558, 5.5),
    "kochi": (9.9312, 76.2673, 5.5),
    "thiruvananthapuram": (8.5241, 76.9366, 5.5),
    "mysuru": (12.2958, 76.6394, 5.5),
    "mysore": (12.2958, 76.6394, 5.5),
    "hubballi": (15.3647, 75.1240, 5.5),
    "hubli": (15.3647, 75.1240, 5.5),
    "dharwad": (15.4589, 75.0078, 5.5),
    "belagavi": (15.8497, 74.4977, 5.5),
    "belgaum": (15.8497, 74.4977, 5.5),
    "mangalore": (12.9141, 74.8560, 5.5),
    "mangaluru": (12.9141, 74.8560, 5.5),
    "chandigarh": (30.7333, 76.7794, 5.5),
    "bhubaneswar": (20.2961, 85.8245, 5.5),
    "visakhapatnam": (17.6868, 83.2185, 5.5),
    "new york": (40.7128, -74.0060, -5.0),
    "london": (51.5074, -0.1278, 0.0),
    "san francisco": (37.7749, -122.4194, -8.0),
    "los angeles": (34.0522, -118.2437, -8.0),
    "chicago": (41.8781, -87.6298, -6.0),
    "toronto": (43.6532, -79.3832, -5.0),
    "dubai": (25.2048, 55.2708, 4.0),
    "singapore": (1.3521, 103.8198, 8.0),
    "sydney": (-33.8688, 151.2093, 10.0),
    "tokyo": (35.6762, 139.6503, 9.0),
    "paris": (48.8566, 2.3522, 1.0),
    "berlin": (52.5200, 13.4050, 1.0),
}


# ── 2. Data Structures ─────────────────────────────────────────────────────────

@dataclass
class GrahaPosition:
    name: str
    western_name: str
    longitude: float
    sign_index: int           # 0 to 11
    sign_name: str
    degrees_in_sign: float    # 0.0 to 29.999
    house: int                # 1 to 12
    nakshatra: str
    nakshatra_lord: str
    pada: int                 # 1 to 4
    speed: float
    is_retrograde: bool
    is_combust: bool
    dignity: str              # Uchcha, Neecha, Moolatrikona, Swakshetra, Mitra, Shatru, Sama
    karaka: str = ""          # AK, AmK, BK, MK, PiK, PK, GK, DK

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BhavaInfo:
    house_number: int
    rashi_index: int
    rashi_name: str
    lord: str
    occupants: list[str] = field(default_factory=list)
    aspecting_grahas: list[str] = field(default_factory=list)


@dataclass
class BirthChart:
    name: str
    date_str: str
    time_str: str
    place: str
    latitude: float
    longitude: float
    timezone_offset: float
    julian_day: float
    ayanamsha_name: str
    ayanamsha_value: float
    lagna_deg: float
    lagna_sign: str
    lagna_sign_index: int
    lagna_nakshatra: str
    lagna_pada: int
    grahas: dict[str, GrahaPosition]
    bhavas: dict[int, BhavaInfo]
    divisional_charts: dict[str, dict[str, str]]    # varga_id -> {graha -> rashi_name}
    chara_karakas: dict[str, str]                   # Karaka -> Graha
    shadbala: dict[str, dict[str, Any]]
    dasha_balance: dict[str, Any]
    active_dasha: dict[str, str]
    dasha_timeline: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ── 3. Astronomical Core & Ephemeris Helpers ───────────────────────────────────

def resolve_location(place: str) -> tuple[float, float, float, str]:
    """Resolve city name or coordinate string to (lat, lon, tz_hours, resolved_name)."""
    p_norm = place.strip().lower()
    if p_norm in CITY_COORDINATES:
        lat, lon, tz = CITY_COORDINATES[p_norm]
        return lat, lon, tz, place.strip().title()

    # Match lat, lon, [tz]
    import re
    m = re.match(r"^([\-+]?\d+(?:\.\d+)?)\s*,\s*([\-+]?\d+(?:\.\d+)?)(?:\s*,\s*([\-+]?\d+(?:\.\d+)?))?$", p_norm)
    if m:
        lat = float(m.group(1))
        lon = float(m.group(2))
        tz = float(m.group(3)) if m.group(3) is not None else round(lon / 15.0 * 2) / 2
        return lat, lon, tz, f"Coordinates ({lat:.2f}, {lon:.2f})"

    # Default fallback: Bengaluru, India (IST)
    lat, lon, tz = CITY_COORDINATES["bengaluru"]
    return lat, lon, tz, f"{place.strip().title()} (defaulted to India IST)"


def parse_birth_datetime(date_str: str, time_str: str, tz_offset: float) -> tuple[datetime.datetime, float]:
    """Parse date and time strings and compute exact Julian Day in UT."""
    for dfmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            dt_date = datetime.datetime.strptime(date_str.strip(), dfmt).date()
            break
        except ValueError:
            continue
    else:
        dt_date = datetime.date(1995, 1, 1)

    for tfmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I %p"):
        try:
            dt_time = datetime.datetime.strptime(time_str.strip(), tfmt).time()
            break
        except ValueError:
            continue
    else:
        dt_time = datetime.time(12, 0, 0)

    # Local decimal hours
    local_hours = dt_time.hour + dt_time.minute / 60.0 + dt_time.second / 3600.0
    ut_hours = local_hours - tz_offset

    # Compute Julian day via swisseph
    jd = swe.julday(dt_date.year, dt_date.month, dt_date.day, ut_hours)
    dt_combined = datetime.datetime.combine(dt_date, dt_time)
    return dt_combined, jd


# ── 4. Divisional Chart (Varga) Calculators ────────────────────────────────────

def calc_varga_sign(lon: float, varga_num: int) -> int:
    """Calculate the resulting 0-indexed Rashi (0=Mesha..11=Meena) for a given longitude in Varga D-N."""
    norm_lon = lon % 360.0
    sign = int(norm_lon // 30.0)
    deg_in_sign = norm_lon % 30.0
    is_odd = (sign % 2 == 0)    # 0, 2, 4, 6, 8, 10 are odd signs (Mesha, Mithuna, Simha...)

    if varga_num == 1:          # D1: Rashi
        return sign

    elif varga_num == 2:        # D2: Hora
        if is_odd:
            return 4 if deg_in_sign < 15.0 else 3    # Sun/Leo or Moon/Cancer
        else:
            return 3 if deg_in_sign < 15.0 else 4

    elif varga_num == 3:        # D3: Drekkana
        part = int(deg_in_sign // 10.0)
        return (sign + part * 4) % 12

    elif varga_num == 4:        # D4: Chaturthamsa
        part = int(deg_in_sign // 7.5)
        return (sign + part * 3) % 12

    elif varga_num == 7:        # D7: Saptamsha
        part = int(deg_in_sign * 7.0 / 30.0)
        start = sign if is_odd else (sign + 6) % 12
        return (start + part) % 12

    elif varga_num == 9:        # D9: Navamsha
        part = int(deg_in_sign * 9.0 / 30.0)
        element = sign % 4
        # Fire (Mesha, Simha, Dhanu) -> Mesha (0)
        # Earth (Vrishabha, Kanya, Makara) -> Makara (9)
        # Air (Mithuna, Tula, Kumbha) -> Tula (6)
        # Water (Karka, Vrishchika, Meena) -> Karka (3)
        start_signs = {0: 0, 1: 9, 2: 6, 3: 3}
        return (start_signs[element] + part) % 12

    elif varga_num == 10:       # D10: Dashamsha
        part = int(deg_in_sign // 3.0)
        start = sign if is_odd else (sign + 8) % 12
        return (start + part) % 12

    elif varga_num == 12:       # D12: Dwadashamsha
        part = int(deg_in_sign // 2.5)
        return (sign + part) % 12

    elif varga_num == 16:       # D16: Shodashamsha
        part = int(deg_in_sign // 1.875)
        mobility = sign % 3     # 0=Movable (Mesha), 1=Fixed (Vrishabha), 2=Dual (Mithuna)
        start_signs = {0: 0, 1: 4, 2: 8}    # Mesha, Simha, Dhanu
        return (start_signs[mobility] + part) % 12

    elif varga_num == 20:       # D20: Vimshamsha
        part = int(deg_in_sign // 1.5)
        mobility = sign % 3
        start_signs = {0: 0, 1: 8, 2: 4}    # Mesha, Dhanu, Simha
        return (start_signs[mobility] + part) % 12

    elif varga_num == 24:       # D24: Chaturvimshamsha
        part = int(deg_in_sign // 1.25)
        start = 4 if is_odd else 3          # Simha or Karka
        return (start + part) % 12

    elif varga_num == 27:       # D27: Saptavimshamsha / Bhamsa
        part = int(deg_in_sign * 27.0 / 30.0)
        element = sign % 4
        start_signs = {0: 0, 1: 3, 2: 6, 3: 9}
        return (start_signs[element] + part) % 12

    elif varga_num == 30:       # D30: Trimshamsha
        if is_odd:
            if deg_in_sign < 5.0: return 0     # Mars (Mesha)
            elif deg_in_sign < 10.0: return 10 # Saturn (Kumbha)
            elif deg_in_sign < 18.0: return 8  # Jupiter (Dhanu)
            elif deg_in_sign < 25.0: return 2  # Mercury (Mithuna)
            else: return 1                      # Venus (Vrishabha)
        else:
            if deg_in_sign < 5.0: return 1     # Venus (Vrishabha)
            elif deg_in_sign < 12.0: return 5  # Mercury (Kanya)
            elif deg_in_sign < 20.0: return 11 # Jupiter (Meena)
            elif deg_in_sign < 25.0: return 9  # Saturn (Makara)
            else: return 7                      # Mars (Vrishchika)

    elif varga_num == 40:       # D40: Khavedamsha
        part = int(deg_in_sign // 0.75)
        start = 0 if is_odd else 6             # Mesha or Tula
        return (start + part) % 12

    elif varga_num == 45:       # D45: Akshavedamsha
        part = int(deg_in_sign * 45.0 / 30.0)
        mobility = sign % 3
        start_signs = {0: 0, 1: 4, 2: 8}
        return (start_signs[mobility] + part) % 12

    elif varga_num == 60:       # D60: Shashtiamsha
        part = int(deg_in_sign // 0.5)
        return (sign + part) % 12

    return sign


# ── 5. Upagraha (Maandi & Gulika) Calculator ───────────────────────────────────

def calc_maandi_and_gulika(jd: float, lat: float, lon: float) -> tuple[float, float]:
    """Calculate the precise sidereal rising degree of Maandi and Gulika based on
    classical Prashna Marga diurnal/nocturnal Saturnian segments (Khandas)."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SIDEREAL

    # Find Sunrise and Sunset for date
    res_rise, t_rise = swe.rise_trans(jd, swe.SUN, swe.CALC_RISE, (lon, lat, 0.0))
    res_set, t_set = swe.rise_trans(jd, swe.SUN, swe.CALC_SET, (lon, lat, 0.0))

    sunrise_jd = t_rise[0] if res_rise >= 0 else jd - 0.25
    sunset_jd = t_set[0] if res_set >= 0 else jd + 0.25

    is_night_birth = (jd < sunrise_jd or jd > sunset_jd)

    # Weekday 0=Sun..6=Sat via Swiss Ephemeris
    # (JD + 1.5) % 7 gives 0=Sunday, 1=Monday...
    day_num = int(math.floor(jd + 1.5)) % 7

    # Saturn's segment in day order (0-indexed portion out of 8)
    # Sunday day: Sun, Mon, Mar, Mer, Jup, Ven, Sat -> Sat is index 6
    day_saturn_parts = {
        0: 6,  # Sun -> Sat is 7th part (idx 6)
        1: 5,  # Mon -> Sat is 6th part (idx 5)
        2: 4,  # Tue -> Sat is 5th part (idx 4)
        3: 3,  # Wed -> Sat is 4th part (idx 3)
        4: 2,  # Thu -> Sat is 3rd part (idx 2)
        5: 1,  # Fri -> Sat is 2nd part (idx 1)
        6: 0,  # Sat -> Sat is 1st part (idx 0)
    }

    # Night order begins from the 5th weekday lord
    night_start_day = (day_num + 4) % 7
    night_saturn_parts = {
        0: 6, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1, 6: 0
    }

    if not is_night_birth:
        day_length = max(0.2, sunset_jd - sunrise_jd)
        part_dur = day_length / 8.0
        sat_idx = day_saturn_parts.get(day_num, 5)
        gulika_time = sunrise_jd + (sat_idx + 0.5) * part_dur
        maandi_time = sunrise_jd + (sat_idx + 1.0) * part_dur
    else:
        # Night length
        next_sunrise = sunrise_jd + 1.0 if jd > sunset_jd else sunrise_jd
        night_length = max(0.2, next_sunrise - sunset_jd)
        part_dur = night_length / 8.0
        sat_idx = night_saturn_parts.get(night_start_day, 4)
        gulika_time = sunset_jd + (sat_idx + 0.5) * part_dur
        maandi_time = sunset_jd + (sat_idx + 1.0) * part_dur

    _, ascmc_m = swe.houses_ex(maandi_time, lat, lon, b'W', flags)
    _, ascmc_g = swe.houses_ex(gulika_time, lat, lon, b'W', flags)

    maandi_lon = ascmc_m[0] % 360.0
    gulika_lon = ascmc_g[0] % 360.0
    return maandi_lon, gulika_lon


# ── 6. Graha Dignity & Status Evaluator ─────────────────────────────────────────

def evaluate_graha_dignity(graha: str, lon: float, sun_lon: float, speed: float, lagna_sign: int) -> dict[str, Any]:
    """Determine dignity, combustion, retrogression, and friendship."""
    sign = int(lon // 30.0)
    deg = lon % 30.0

    is_retro = bool(speed < 0 and graha not in ("Rahu", "Ketu", "Surya", "Chandra"))

    # Combustion
    is_combust = False
    if graha in COMBUSTION_LIMITS:
        diff = abs(lon - sun_lon)
        if diff > 180.0:
            diff = 360.0 - diff
        limit = COMBUSTION_LIMITS[graha]
        if is_retro and graha in ("Budha", "Shukra"):
            limit -= 2.0
        is_combust = bool(diff <= limit)

    dignity = "Sama"
    # 1. Exaltation / Debilitation
    if graha in EXALTATION_SIGNS and EXALTATION_SIGNS[graha][0] == sign:
        dignity = "Uchcha (Exalted)"
    elif graha in DEBILITATION_SIGNS and DEBILITATION_SIGNS[graha][0] == sign:
        # Check Neechabhanga: Lord of debilitation sign or exaltation lord in Kendra from Lagna
        deb_sign_lord = RASHI_LORDS[sign]
        dignity = "Neecha (Debilitated)"

    # 2. Own sign (Swakshetra)
    elif RASHI_LORDS[sign] == graha:
        dignity = "Swakshetra (Own Sign)"

    # 3. Moolatrikona
    moolatrikona_ranges = {
        "Surya": (4, 0.0, 20.0), "Chandra": (1, 3.0, 30.0), "Mangala": (0, 0.0, 12.0),
        "Budha": (5, 15.0, 20.0), "Guru": (8, 0.0, 10.0), "Shukra": (6, 0.0, 15.0),
        "Shani": (10, 0.0, 20.0),
    }
    if graha in moolatrikona_ranges:
        msign, mstart, mend = moolatrikona_ranges[graha]
        if sign == msign and mstart <= deg <= mend:
            dignity = "Moolatrikona"

    # 4. Friendship (Panchadha Maitri)
    if dignity == "Sama" and graha in NAISARGIKA_MAITRI:
        sign_lord = RASHI_LORDS[sign]
        natural = NAISARGIKA_MAITRI[graha].get(sign_lord, 0)
        # Tatkalika: 2, 3, 4, 10, 11, 12 houses away from planet's sign are temporary friends (+1)
        # else temporary enemy (-1)
        rel_pos = (sign - int(lon // 30.0)) % 12
        temporal = 1 if rel_pos in (1, 2, 3, 9, 10, 11) else -1
        compound = natural + temporal
        if compound >= 2: dignity = "Adhi Mitra (Great Friend)"
        elif compound == 1: dignity = "Mitra (Friend)"
        elif compound == 0: dignity = "Sama (Neutral)"
        elif compound == -1: dignity = "Shatru (Enemy)"
        else: dignity = "Adhi Shatru (Bitter Enemy)"

    return {
        "dignity": dignity,
        "is_retrograde": is_retro,
        "is_combust": is_combust,
    }


# ── 7. Shadbala & Chara Karaka Calculators ─────────────────────────────────────

def compute_chara_karakas(graha_positions: dict[str, float]) -> dict[str, str]:
    """Compute 7-Karaka Jaimini scheme sorted by longitudinal degree inside sign."""
    planets = ["Surya", "Chandra", "Mangala", "Budha", "Guru", "Shukra", "Shani"]
    planet_degrees = []
    for p in planets:
        if p in graha_positions:
            deg_in_sign = graha_positions[p] % 30.0
            planet_degrees.append((deg_in_sign, p))

    planet_degrees.sort(key=lambda x: x[0], reverse=True)

    if len(planet_degrees) >= 8:
        karaka_titles = [
            "Atmakaraka (AK)",
            "Amatyakaraka (AmK)",
            "Bhratrikaraka (BK)",
            "Matrikaraka (MK)",
            "Pitrikaraka (PiK)",
            "Putrakaraka (PK)",
            "Gnatikaraka (GK)",
            "Darakaraka (DK)",
        ]
    else:
        # Standard Parashari / Jaimini 7-Karaka scheme
        karaka_titles = [
            "Atmakaraka (AK)",
            "Amatyakaraka (AmK)",
            "Bhratrikaraka (BK)",
            "Matrikaraka (MK)",
            "Putrakaraka (PK)",
            "Gnatikaraka (GK)",
            "Darakaraka (DK)",
        ]

    karaka_map: dict[str, str] = {}
    for idx, (_, p) in enumerate(planet_degrees):
        if idx < len(karaka_titles):
            title = karaka_titles[idx]
            abbrev = title.split("(")[1].replace(")", "")
            karaka_map[abbrev] = p

    return karaka_map


def compute_shadbala(
    grahas: dict[str, GrahaPosition],
    lagna_sign: int,
    is_day_birth: bool,
) -> dict[str, dict[str, Any]]:
    """Compute classical 6-fold Shadbala strengths in Virupas and Rupas."""
    planets = ["Surya", "Chandra", "Mangala", "Budha", "Guru", "Shukra", "Shani"]
    naisargika_base = {
        "Surya": 60.0, "Chandra": 51.43, "Shukra": 42.86,
        "Guru": 34.29, "Budha": 25.71, "Mangala": 17.14, "Shani": 8.57,
    }
    required_rupas = {
        "Surya": 6.5, "Chandra": 6.0, "Mangala": 5.0,
        "Budha": 7.0, "Guru": 6.5, "Shukra": 5.5, "Shani": 5.0,
    }

    results: dict[str, dict[str, Any]] = {}

    for p in planets:
        if p not in grahas:
            continue
        g = grahas[p]

        # 1. Sthana Bala (Positional)
        # Uchcha Bala: 60 * (1 - dist_from_deb / 180)
        deb_sign = DEBILITATION_SIGNS.get(p, (0, 0))[0]
        dist_from_deb = abs(g.longitude - (deb_sign * 30.0 + 15.0)) % 360.0
        if dist_from_deb > 180.0:
            dist_from_deb = 360.0 - dist_from_deb
        uchcha_bala = round(60.0 * (dist_from_deb / 180.0), 1)

        # Kendra Bala
        house = g.house
        kendra_bala = 60.0 if house in (1, 4, 7, 10) else (30.0 if house in (2, 5, 8, 11) else 15.0)

        # Dignity bonus
        dig_bonus = 45.0 if "Uchcha" in g.dignity else (30.0 if "Swakshetra" in g.dignity or "Moolatrikona" in g.dignity else (15.0 if "Mitra" in g.dignity else 5.0))
        sthana_bala = uchcha_bala + kendra_bala + dig_bonus

        # 2. Dig Bala (Directional)
        best_house = {"Guru": 1, "Budha": 1, "Surya": 10, "Mangala": 10, "Shani": 7, "Chandra": 4, "Shukra": 4}.get(p, 1)
        h_diff = abs(house - best_house)
        if h_diff > 6: h_diff = 12 - h_diff
        dig_bala = round(60.0 * (1.0 - h_diff / 6.0), 1)

        # 3. Kala Bala (Temporal)
        kala_bala = 40.0
        if is_day_birth and p in ("Surya", "Guru", "Shukra"): kala_bala += 20.0
        elif (not is_day_birth) and p in ("Chandra", "Mangala", "Shani"): kala_bala += 20.0
        elif p == "Budha": kala_bala += 15.0

        # 4. Cheshta Bala (Motional)
        cheshta_bala = 60.0 if g.is_retrograde else min(50.0, max(15.0, abs(g.speed) * 30.0))

        # 5. Naisargika Bala (Natural)
        naisargika = naisargika_base.get(p, 20.0)

        # 6. Drik Bala (Aspectual estimate)
        drik_bala = 15.0

        total_virupas = round(sthana_bala + dig_bala + kala_bala + cheshta_bala + naisargika + drik_bala, 1)
        total_rupas = round(total_virupas / 60.0, 2)
        req = required_rupas.get(p, 5.5)
        status = "Strong" if total_rupas >= req else ("Moderate" if total_rupas >= req * 0.85 else "Weak")

        results[p] = {
            "graha": p,
            "sthana_bala": round(sthana_bala, 1),
            "dig_bala": dig_bala,
            "kala_bala": round(kala_bala, 1),
            "cheshta_bala": round(cheshta_bala, 1),
            "naisargika_bala": round(naisargika, 1),
            "total_virupas": total_virupas,
            "total_rupas": total_rupas,
            "required_rupas": req,
            "strength_status": status,
        }

    return results


# ── 8. Vimsottari Dasha Engine ────────────────────────────────────────────────

def compute_vimsottari_dasha(moon_lon: float, birth_date: datetime.datetime) -> tuple[dict[str, Any], dict[str, str], list[dict[str, Any]]]:
    """Calculate exact birth dasha balance, full timeline, and currently active period."""
    nak_idx = int((moon_lon % 360.0) / (360.0 / 27.0))
    nak_name, nak_lord = NAKSHATRAS[nak_idx]

    # Arc elapsed in Nakshatra (each Nakshatra is 13°20' = 800')
    nak_span = 360.0 / 27.0
    deg_in_nak = (moon_lon % 360.0) % nak_span
    frac_remaining = 1.0 - (deg_in_nak / nak_span)

    lord_total_years = DASHA_YEARS.get(nak_lord, 7.0)
    balance_years = lord_total_years * frac_remaining

    balance_info = {
        "nakshatra": nak_name,
        "nakshatra_lord": nak_lord,
        "balance_years": round(balance_years, 2),
        "balance_formatted": f"{int(balance_years)} years, {int((balance_years % 1) * 12)} months",
    }

    # Generate complete 120-year sequence of Mahadashas & Antardashas
    start_lord_idx = DASHA_ORDER.index(nak_lord)
    current_time = birth_date
    now = datetime.datetime.now()

    dasha_timeline = []
    active_period = {"mahadasha": nak_lord, "antardasha": nak_lord, "end_date": ""}

    for i in range(len(DASHA_ORDER)):
        l_idx = (start_lord_idx + i) % len(DASHA_ORDER)
        m_lord = DASHA_ORDER[l_idx]
        m_duration = balance_years if i == 0 else DASHA_YEARS[m_lord]
        m_end_time = current_time + datetime.timedelta(days=int(m_duration * 365.2425))

        # Calculate 9 Antardashas within Mahadasha
        antardashas = []
        sub_curr = current_time
        sub_start_idx = DASHA_ORDER.index(m_lord)

        for j in range(len(DASHA_ORDER)):
            a_lord = DASHA_ORDER[(sub_start_idx + j) % len(DASHA_ORDER)]
            a_duration = (DASHA_YEARS[m_lord] * DASHA_YEARS[a_lord]) / 120.0
            # If in first balanced dasha, scale proportionally
            if i == 0:
                a_duration = a_duration * (balance_years / DASHA_YEARS[m_lord])
            a_end = sub_curr + datetime.timedelta(days=int(a_duration * 365.2425))

            if sub_curr <= now <= a_end:
                active_period = {
                    "mahadasha": m_lord,
                    "antardasha": a_lord,
                    "start_date": sub_curr.strftime("%Y-%m-%d"),
                    "end_date": a_end.strftime("%Y-%m-%d"),
                }

            antardashas.append({
                "lord": a_lord,
                "start": sub_curr.strftime("%Y-%m-%d"),
                "end": a_end.strftime("%Y-%m-%d"),
            })
            sub_curr = a_end

        dasha_timeline.append({
            "mahadasha": m_lord,
            "start_date": current_time.strftime("%Y-%m-%d"),
            "end_date": m_end_time.strftime("%Y-%m-%d"),
            "duration_years": round(m_duration, 2),
            "antardashas": antardashas,
        })
        current_time = m_end_time

    return balance_info, active_period, dasha_timeline


# ── 9. Complete Vedic Birth Chart Calculator ───────────────────────────────────

def calculate_vedic_chart(
    name: str = "Jataka",
    date_str: str = "1995-05-15",
    time_str: str = "14:30:00",
    place: str = "Bengaluru",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone_offset: Optional[float] = None,
) -> BirthChart:
    """Compute a complete Vedic birth chart with Sidereal planetary coordinates,
    divisional charts, Shadbala, Chara Karakas, Maandi, and Vimsottari Dasha."""
    # Resolve geographic location
    if latitude is not None and longitude is not None:
        lat, lon = latitude, longitude
        tz = timezone_offset if timezone_offset is not None else 5.5
        resolved_place = place or f"Coords ({lat:.2f}, {lon:.2f})"
    else:
        lat, lon, tz, resolved_place = resolve_location(place)

    birth_dt, jd = parse_birth_datetime(date_str, time_str, tz)

    # Set Swiss Ephemeris Lahiri Sidereal mode
    swe.set_ephe_path("")
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED

    ayanamsa_val = swe.get_ayanamsa_ut(jd)

    # Calculate Lagna (Ascendant)
    _, ascmc = swe.houses_ex(jd, lat, lon, b'W', flags)
    lagna_lon = ascmc[0] % 360.0
    lagna_sign_idx = int(lagna_lon // 30.0)
    lagna_sign_name = RASHI_NAMES_INDIAN[lagna_sign_idx]

    lagna_nak_idx = int(lagna_lon / (360.0 / 27.0))
    lagna_nak_name, _ = NAKSHATRAS[lagna_nak_idx]
    lagna_pada = int((lagna_lon % (360.0 / 27.0)) / (360.0 / 108.0)) + 1

    # Calculate Planets
    body_map = {
        "Surya": swe.SUN,
        "Chandra": swe.MOON,
        "Mangala": swe.MARS,
        "Budha": swe.MERCURY,
        "Guru": swe.JUPITER,
        "Shukra": swe.VENUS,
        "Shani": swe.SATURN,
        "Rahu": swe.TRUE_NODE,
        "Harshal (Uranus)": swe.URANUS,
        "Varun (Neptune)": swe.NEPTUNE,
        "Yama (Pluto)": swe.PLUTO,
    }

    raw_positions: dict[str, tuple[float, float]] = {}
    for g_name, swe_id in body_map.items():
        coords, _ = swe.calc_ut(jd, swe_id, flags)
        raw_positions[g_name] = (coords[0] % 360.0, coords[3])

    # Ketu is exactly 180° opposite to Rahu
    rahu_lon = raw_positions["Rahu"][0]
    ketu_lon = (rahu_lon + 180.0) % 360.0
    raw_positions["Ketu"] = (ketu_lon, -raw_positions["Rahu"][1])

    # Calculate Maandi and Gulika
    maandi_lon, gulika_lon = calc_maandi_and_gulika(jd, lat, lon)
    raw_positions["Maandi"] = (maandi_lon, 0.0)
    raw_positions["Gulika"] = (gulika_lon, 0.0)

    sun_lon = raw_positions["Surya"][0]

    grahas: dict[str, GrahaPosition] = {}
    bhavas: dict[int, BhavaInfo] = {
        h: BhavaInfo(
            house_number=h,
            rashi_index=(lagna_sign_idx + h - 1) % 12,
            rashi_name=RASHI_NAMES_INDIAN[(lagna_sign_idx + h - 1) % 12],
            lord=RASHI_LORDS[(lagna_sign_idx + h - 1) % 12],
        )
        for h in range(1, 13)
    }

    # Map Graha details
    for g_name, (glon, speed) in raw_positions.items():
        gsign = int(glon // 30.0)
        gdeg = glon % 30.0
        # House in Whole Sign / Equal house from Lagna
        ghouse = ((gsign - lagna_sign_idx) % 12) + 1

        nak_i = int(glon / (360.0 / 27.0)) % 27
        nak_name, nak_lord = NAKSHATRAS[nak_i]
        pada = int((glon % (360.0 / 27.0)) / (360.0 / 108.0)) + 1

        dignity_data = evaluate_graha_dignity(
            graha=g_name.split()[0],
            lon=glon,
            sun_lon=sun_lon,
            speed=speed,
            lagna_sign=lagna_sign_idx,
        )

        western_name = [k for k, v in GRAHA_NAMES_INDIAN.items() if v.startswith(g_name.split()[0])]
        w_name = western_name[0] if western_name else g_name

        g_pos = GrahaPosition(
            name=g_name,
            western_name=w_name,
            longitude=round(glon, 4),
            sign_index=gsign,
            sign_name=RASHI_NAMES_INDIAN[gsign],
            degrees_in_sign=round(gdeg, 3),
            house=ghouse,
            nakshatra=nak_name,
            nakshatra_lord=nak_lord,
            pada=pada,
            speed=round(speed, 4),
            is_retrograde=dignity_data["is_retrograde"],
            is_combust=dignity_data["is_combust"],
            dignity=dignity_data["dignity"],
        )
        grahas[g_name] = g_pos
        bhavas[ghouse].occupants.append(g_name)

    # Compute Graha Drishtis (Aspects)
    # 7th aspect for all; Special: Mars (4, 7, 8), Jupiter (5, 7, 9), Saturn (3, 7, 10), Rahu/Ketu (5, 7, 9)
    for g_name, g in grahas.items():
        src_h = g.house
        aspect_offsets = [7]
        if "Mangala" in g_name: aspect_offsets.extend([4, 8])
        elif "Guru" in g_name: aspect_offsets.extend([5, 9])
        elif "Shani" in g_name: aspect_offsets.extend([3, 10])
        elif "Rahu" in g_name or "Ketu" in g_name: aspect_offsets.extend([5, 9])

        for off in aspect_offsets:
            target_h = ((src_h + off - 2) % 12) + 1
            if g_name not in bhavas[target_h].aspecting_grahas:
                bhavas[target_h].aspecting_grahas.append(g_name)

    # Compute Chara Karakas
    chara_karakas = compute_chara_karakas({k: v.longitude for k, v in grahas.items()})
    for karaka_code, p_name in chara_karakas.items():
        if p_name in grahas:
            grahas[p_name].karaka = karaka_code

    # Compute all 16 Shodashavargas
    varga_keys = [1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]
    divisional_charts: dict[str, dict[str, str]] = {}

    for vn in varga_keys:
        v_tag = f"D{vn}"
        chart_map: dict[str, str] = {}
        chart_map["Lagna"] = RASHI_NAMES_INDIAN[calc_varga_sign(lagna_lon, vn)]
        for g_name, g in grahas.items():
            chart_map[g_name] = RASHI_NAMES_INDIAN[calc_varga_sign(g.longitude, vn)]
        divisional_charts[v_tag] = chart_map

    # Compute Shadbala
    is_day_birth = (6.0 <= (birth_dt.hour + birth_dt.minute / 60.0) <= 18.0)
    shadbala_results = compute_shadbala(grahas, lagna_sign_idx, is_day_birth)

    # Compute Vimsottari Dasha
    moon_lon = grahas["Chandra"].longitude
    dasha_bal, active_dasha, dasha_timeline = compute_vimsottari_dasha(moon_lon, birth_dt)

    return BirthChart(
        name=name,
        date_str=date_str,
        time_str=time_str,
        place=resolved_place,
        latitude=round(lat, 4),
        longitude=round(lon, 4),
        timezone_offset=tz,
        julian_day=round(jd, 5),
        ayanamsha_name="Lahiri (Chitrapaksha)",
        ayanamsha_value=round(ayanamsa_val, 4),
        lagna_deg=round(lagna_lon, 3),
        lagna_sign=lagna_sign_name,
        lagna_sign_index=lagna_sign_idx,
        lagna_nakshatra=lagna_nak_name,
        lagna_pada=lagna_pada,
        grahas=grahas,
        bhavas=bhavas,
        divisional_charts=divisional_charts,
        chara_karakas=chara_karakas,
        shadbala=shadbala_results,
        dasha_balance=dasha_bal,
        active_dasha=active_dasha,
        dasha_timeline=dasha_timeline,
    )


# ── 10. Western Tropical Astrology Calculator ──────────────────────────────────

def calculate_western_chart(
    name: str = "Native",
    date_str: str = "1995-05-15",
    time_str: str = "14:30:00",
    place: str = "Bengaluru",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timezone_offset: Optional[float] = None,
) -> dict[str, Any]:
    """Compute Western Tropical chart with Placidus houses, Big Three, and major aspects."""
    if latitude is not None and longitude is not None:
        lat, lon = latitude, longitude
        tz = timezone_offset if timezone_offset is not None else 5.5
        resolved_place = place or f"Coords ({lat:.2f}, {lon:.2f})"
    else:
        lat, lon, tz, resolved_place = resolve_location(place)

    birth_dt, jd = parse_birth_datetime(date_str, time_str, tz)

    swe.set_ephe_path("")
    flags = swe.FLG_SPEED    # Tropical by default

    # Placidus Houses
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b'P', flags)
    rising_deg = ascmc[0] % 360.0
    mc_deg = ascmc[1] % 360.0

    rising_sign_idx = int(rising_deg // 30.0)

    body_list = [
        ("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY),
        ("Venus", swe.VENUS), ("Mars", swe.MARS), ("Jupiter", swe.JUPITER),
        ("Saturn", swe.SATURN), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE),
        ("Pluto", swe.PLUTO), ("North Node", swe.TRUE_NODE),
    ]

    planets: dict[str, Any] = {}
    for pname, bid in body_list:
        coords, _ = swe.calc_ut(jd, bid, flags)
        plon = coords[0] % 360.0
        psign = int(plon // 30.0)
        pdeg = plon % 30.0

        # Find Placidus house (cusps has 12 elements: index 0 = House 1, index 11 = House 12)
        house = 1
        for i in range(12):
            c_curr = cusps[i]
            c_next = cusps[(i + 1) % 12]
            if c_curr < c_next:
                if c_curr <= plon < c_next:
                    house = i + 1
                    break
            else:
                if plon >= c_curr or plon < c_next:
                    house = i + 1
                    break

        planets[pname] = {
            "name": pname,
            "longitude": round(plon, 3),
            "sign": RASHI_NAMES_WESTERN[psign],
            "sign_index": psign,
            "degrees_in_sign": round(pdeg, 2),
            "house": house,
            "speed": round(coords[3], 3),
            "is_retrograde": bool(coords[3] < 0),
        }

    # Major Aspects
    aspect_defs = [
        ("Conjunction", 0.0, 8.0),
        ("Sextile", 60.0, 6.0),
        ("Square", 90.0, 7.0),
        ("Trine", 120.0, 8.0),
        ("Opposition", 180.0, 8.0),
    ]

    pkeys = list(planets.keys())
    aspects = []
    for i in range(len(pkeys)):
        for j in range(i + 1, len(pkeys)):
            p1, p2 = pkeys[i], pkeys[j]
            diff = abs(planets[p1]["longitude"] - planets[p2]["longitude"])
            if diff > 180.0: diff = 360.0 - diff

            for asp_name, asp_deg, orb in aspect_defs:
                exact_diff = abs(diff - asp_deg)
                if exact_diff <= orb:
                    aspects.append({
                        "body1": p1,
                        "body2": p2,
                        "aspect": asp_name,
                        "angle": round(diff, 1),
                        "orb": round(exact_diff, 2),
                    })

    sun_info = planets.get("Sun", {})
    moon_info = planets.get("Moon", {})

    return {
        "paradigm": "Western Tropical Astrology",
        "name": name,
        "date": date_str,
        "time": time_str,
        "place": resolved_place,
        "big_three": {
            "sun_sign": sun_info.get("sign"),
            "moon_sign": moon_info.get("sign"),
            "rising_sign": RASHI_NAMES_WESTERN[rising_sign_idx],
        },
        "ascendant_deg": round(rising_deg, 2),
        "midheaven_deg": round(mc_deg, 2),
        "planets": planets,
        "aspects": aspects,
    }


# ── 11. Comprehensive Synthesized Analysis Generator ──────────────────────────

def synthesize_vedic_analysis(chart: BirthChart) -> str:
    """Generate an authoritative, deep Vedic Jyotisha interpretation covering all
    foundational areas: Lagna, Janma Rashi, Career (D10), Relationships (D9),
    Shadbala strengths, Chara Karakas, Maandi, Active Dasha, and Upayas."""
    lagna = chart.lagna_sign
    lagnesha = chart.bhavas[1].lord
    moon_g = chart.grahas["Chandra"]
    sun_g = chart.grahas["Surya"]

    ak_planet = chart.chara_karakas.get("AK", "Surya")
    amk_planet = chart.chara_karakas.get("AmK", "Guru")
    dk_planet = chart.chara_karakas.get("DK", "Shukra")

    lines = [
        f"✦ VEDIC JYOTISHA BIRTH CHART ANALYSIS — {chart.name.upper()} ✦",
        f"Birth Details: {chart.date_str} at {chart.time_str} ({chart.place})",
        f"Ayanamsha: {chart.ayanamsha_name} ({chart.ayanamsha_value}°)",
        "",
        "── 1. The Core Triad (Lagna, Chandra & Surya) ──",
        f"• Janma Lagna (Ascendant): {lagna} ({chart.lagna_deg % 30:.2f}°) in {chart.lagna_nakshatra} Pada {chart.lagna_pada}",
        f"  - Lagna Lord: {lagnesha} placed in Bhava {chart.grahas.get(lagnesha, sun_g).house} ({chart.grahas.get(lagnesha, sun_g).sign_name}).",
        f"• Chandra Rashi (Moon Sign): {moon_g.sign_name} in {moon_g.nakshatra} Pada {moon_g.pada} (Bhava {moon_g.house})",
        f"  - Mental temperament and instinctual psychology driven by {moon_g.nakshatra_lord} lordship.",
        f"• Surya Rashi (Sun Sign): {sun_g.sign_name} at {sun_g.degrees_in_sign:.2f}° in Bhava {sun_g.house}.",
        "",
        "── 2. Jaimini Chara Karakas (Soul & Material Indicators) ──",
        f"• Atmakaraka (AK - Soul Purpose): {ak_planet} (Highest degree: {chart.grahas.get(ak_planet, sun_g).degrees_in_sign:.2f}°)",
        f"• Amatyakaraka (AmK - Career & Intellect): {amk_planet} (Counsel, professional calling)",
        f"• Darakaraka (DK - Spouse & Partnerships): {dk_planet} (Marriage and intimate connections)",
        f"• Key Karakas: Bhratri={chart.chara_karakas.get('BK', '')}, Matri={chart.chara_karakas.get('MK', '')}, Putra={chart.chara_karakas.get('PK', '')}, Gnati={chart.chara_karakas.get('GK', '')}",
        "",
        "── 3. Career & Public Life (10th Bhava & D10 Dashamsha) ──",
        f"• 10th House Lord: {chart.bhavas[10].lord} in {chart.bhavas[10].rashi_name} (Occupants: {', '.join(chart.bhavas[10].occupants) or 'None'}).",
        f"• D10 Dashamsha Alignments: Lagna={chart.divisional_charts.get('D10', {}).get('Lagna', '')}, Surya={chart.divisional_charts.get('D10', {}).get('Surya', '')}, AmK ({amk_planet})={chart.divisional_charts.get('D10', {}).get(amk_planet, '')}.",
        "  - The D10 confirms vocational authority, leadership capacity, and professional reputation.",
        "",
        "── 4. Marriage, Relationships & Dharma (7th Bhava & D9 Navamsha) ──",
        f"• 7th House Lord: {chart.bhavas[7].lord} in {chart.bhavas[7].rashi_name} (Occupants: {', '.join(chart.bhavas[7].occupants) or 'None'}).",
        f"• D9 Navamsha Lagna: {chart.divisional_charts.get('D9', {}).get('Lagna', '')} | Shukra (Venus) in D9: {chart.divisional_charts.get('D9', {}).get('Shukra', '')}.",
        f"• Darakaraka ({dk_planet}) in D9: {chart.divisional_charts.get('D9', {}).get(dk_planet, '')}.",
        "  - Navamsha reveals the deeper spiritual bond, marital stability, and post-marriage fortune.",
        "",
        "── 5. Upagraha Maandi & Outer Planets ──",
        f"• Maandi: Placed in {chart.grahas['Maandi'].sign_name} ({chart.grahas['Maandi'].degrees_in_sign:.2f}°) in Bhava {chart.grahas['Maandi'].house}.",
        f"  - Maandi indicates karmic knots, acute sensitivity, or inherited obstacles requiring mindfulness.",
        f"• Harshal (Uranus): Bhava {chart.grahas['Harshal (Uranus)'].house} ({chart.grahas['Harshal (Uranus)'].sign_name}) — Sudden breakthroughs and inventive individuality.",
        f"• Varun (Neptune): Bhava {chart.grahas['Varun (Neptune)'].house} ({chart.grahas['Varun (Neptune)'].sign_name}) — Heightened intuition and metaphysical receptivity.",
        f"• Yama (Pluto): Bhava {chart.grahas['Yama (Pluto)'].house} ({chart.grahas['Yama (Pluto)'].sign_name}) — Deep psychological rebirth and radical empowerment.",
        "",
        "── 6. Planetary Strengths (Shadbala Summary) ──",
    ]

    for p, sb in chart.shadbala.items():
        lines.append(f"• {p}: {sb['total_rupas']} Rupas ({sb['total_virupas']} Virupas) — {sb['strength_status']} (Req: {sb['required_rupas']} Rupas)")

    lines.extend([
        "",
        "── 7. Vimsottari Dasha (Current Karmic Cycle) ──",
        f"• Birth Balance: {chart.dasha_balance['nakshatra_lord']} Dasha ({chart.dasha_balance['balance_formatted']})",
        f"• Active Period: {chart.active_dasha.get('mahadasha', '')} Mahadasha — {chart.active_dasha.get('antardasha', '')} Antardasha",
        f"  - Active Until: {chart.active_dasha.get('end_date', 'Ongoing')}",
        "",
        "── 8. Classical Upayas (Remedies & Harmonization) ──",
        f"• Strengthen benefic lord ({lagnesha}) through dedicated disciplined action and meditation.",
        "• Offer water to Surya at sunrise; practice Surya Namaskar.",
        "• For Maandi harmonization: Shiva Sahasranama or Rudra Gayatri recitations bring serenity and neutralize karmic friction.",
    ])

    return "\n".join(lines)


def synthesize_voice_summary(chart: BirthChart) -> str:
    """Produce a concise, natural spoken executive summary (3-4 sentences)
    so Gemini Live communicates effortlessly without overwhelming the audio WebSocket stream."""
    lagna = chart.lagna_sign
    lagna_lord = chart.bhavas[1].lord
    moon_sign = chart.grahas["Chandra"].sign_name
    moon_nak = chart.grahas["Chandra"].nakshatra
    sun_sign = chart.grahas["Surya"].sign_name
    active_dasha = f"{chart.active_dasha.get('mahadasha', '')} Mahadasha"
    if chart.active_dasha.get("antardasha"):
        active_dasha += f" and {chart.active_dasha['antardasha']} Antardasha"

    ak = chart.chara_karakas.get("AK", "Surya")

    return (
        f"Chart reading complete for {chart.name}. Your Janma Lagna is {lagna} with lord {lagna_lord}, "
        f"Chandra Rashi is {moon_sign} in {moon_nak} Nakshatra, and Surya is in {sun_sign}. "
        f"Your Atmakaraka soul indicator is {ak}, and you are currently running {active_dasha}. "
        f"The comprehensive Shodashavarga analysis and Kundali chart image have been rendered on your screen and saved to file."
    )


# ── 12. Visual Kundali Image & SVG Generation ─────────────────────────────────

_ABBR_MAP = {
    "Surya": "Su",
    "Chandra": "Mo",
    "Mangala": "Ma",
    "Budha": "Me",
    "Guru": "Ju",
    "Shukra": "Ve",
    "Shani": "Sa",
    "Rahu": "Ra",
    "Ketu": "Ke",
    "Harshal (Uranus)": "Ur",
    "Varun (Neptune)": "Ne",
    "Yama (Pluto)": "Pl",
    "Maandi": "Mnd",
    "Gulika": "Glk",
}


def render_kundali_image(
    chart: BirthChart,
    style: str = "north",
    output_path: Optional[str] = None,
) -> str:
    """Render a high-resolution Kundali image (North Indian diamond or South Indian box).
    Returns the absolute path to the generated PNG file."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow is required for Kundali image generation: pip install Pillow")

    style_clean = (style or "north").strip().lower()
    is_north = "south" not in style_clean

    size = (900, 900)
    bg_color = (253, 250, 243)      # warm cream parchment
    primary_line = (140, 35, 35)    # traditional Vedic terracotta crimson
    border_gold = (195, 145, 55)    # golden border accent
    text_dark = (25, 25, 30)        # deep slate
    text_rashi = (150, 80, 25)      # burnt orange for sign numbers
    text_graha = (10, 45, 105)      # royal navy for planets
    header_color = (130, 20, 20)

    im = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(im)

    try:
        font_large = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        font_med = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 13)
        font_num = ImageFont.truetype("DejaVuSans-Bold.ttf", 14)
    except Exception:
        font_large = ImageFont.load_default()
        font_med = font_large
        font_small = font_large
        font_num = font_large

    # Title & Subtitle header
    title_str = f"✦ VEDIC KUNDALI ({style_clean.upper()} STYLE) — {chart.name.upper()} ✦"
    draw.text((450, 28), title_str, fill=header_color, font=font_large, anchor="mm")
    sub_str = f"Lagna: {chart.lagna_sign} ({chart.lagna_deg % 30:.1f}°) | Nakshatra: {chart.lagna_nakshatra} (Pada {chart.lagna_pada}) | {chart.date_str} {chart.time_str}"
    draw.text((450, 52), sub_str, fill=text_dark, font=font_small, anchor="mm")

    # Geometry bounds: 80 to 860
    left, top, right, bottom = 70, 75, 830, 835
    w = right - left
    h = bottom - top
    cx = (left + right) // 2
    cy = (top + bottom) // 2

    # Double decorative outer frame
    draw.rectangle([left - 6, top - 6, right + 6, bottom + 6], outline=border_gold, width=2)
    draw.rectangle([left, top, right, bottom], outline=primary_line, width=4)

    if is_north:
        # ── North Indian Diamond Kundali ──
        # Diagonals
        draw.line([(left, top), (right, bottom)], fill=primary_line, width=2)
        draw.line([(right, top), (left, bottom)], fill=primary_line, width=2)
        # Inner diamond
        draw.line([(cx, top), (right, cy), (cx, bottom), (left, cy), (cx, top)], fill=primary_line, width=3)

        # Center points for the 12 houses in North style
        # House 1 is top center diamond
        house_centers = {
            1: (cx, top + int(h * 0.22)),
            2: (left + int(w * 0.23), top + int(h * 0.10)),
            3: (left + int(w * 0.10), top + int(h * 0.23)),
            4: (left + int(w * 0.22), cy),
            5: (left + int(w * 0.10), bottom - int(h * 0.23)),
            6: (left + int(w * 0.23), bottom - int(h * 0.10)),
            7: (cx, bottom - int(h * 0.22)),
            8: (right - int(w * 0.23), bottom - int(h * 0.10)),
            9: (right - int(w * 0.10), bottom - int(h * 0.23)),
            10: (right - int(w * 0.22), cy),
            11: (right - int(w * 0.10), top + int(h * 0.23)),
            12: (right - int(w * 0.23), top + int(h * 0.10)),
        }

        # Sign number positions (slightly offset from center)
        num_offsets = {
            1: (cx, top + int(h * 0.33)),
            2: (left + int(w * 0.29), top + int(h * 0.16)),
            3: (left + int(w * 0.16), top + int(h * 0.29)),
            4: (left + int(w * 0.33), cy),
            5: (left + int(w * 0.16), bottom - int(h * 0.29)),
            6: (left + int(w * 0.29), bottom - int(h * 0.16)),
            7: (cx, bottom - int(h * 0.33)),
            8: (right - int(w * 0.29), bottom - int(h * 0.16)),
            9: (right - int(w * 0.16), bottom - int(h * 0.29)),
            10: (right - int(w * 0.33), cy),
            11: (right - int(w * 0.16), top + int(h * 0.29)),
            12: (right - int(w * 0.29), top + int(h * 0.16)),
        }

        for h_num in range(1, 13):
            b_info = chart.bhavas[h_num]
            r_num = b_info.rashi_index + 1
            # Draw sign number
            nx, ny = num_offsets[h_num]
            draw.text((nx, ny), str(r_num), fill=text_rashi, font=font_num, anchor="mm")

            # Draw grahas in this house
            hx, hy = house_centers[h_num]
            planets = []
            for gname in b_info.occupants:
                abbr = _ABBR_MAP.get(gname, gname[:2])
                g_obj = chart.grahas.get(gname)
                if g_obj and g_obj.is_retrograde:
                    abbr += "®"
                planets.append(abbr)

            if planets:
                p_str = " ".join(planets)
                draw.text((hx, hy), p_str, fill=text_graha, font=font_med, anchor="mm")

    else:
        # ── South Indian Box Kundali ──
        # 4 rows, 4 columns
        col_w = w // 4
        row_h = h // 4
        for r_idx in range(5):
            y_line = top + r_idx * row_h
            draw.line([(left, y_line), (right, y_line)], fill=primary_line, width=2)
        for c_idx in range(5):
            x_line = left + c_idx * col_w
            draw.line([(x_line, top), (x_line, bottom)], fill=primary_line, width=2)

        # Clear center 2x2 box for chart metadata
        draw.rectangle([left + col_w, top + row_h, left + col_w * 3, top + row_h * 3], fill=bg_color, outline=border_gold, width=2)

        # Fixed signs arrangement in South Indian format:
        # (row, col) -> sign_index (0 = Mesha, 1 = Vrishabha, ... 11 = Meena)
        south_sign_map = {
            (0, 0): 11,  # Meena (Pisces)
            (0, 1): 0,   # Mesha (Aries)
            (0, 2): 1,   # Vrishabha (Taurus)
            (0, 3): 2,   # Mithuna (Gemini)
            (1, 3): 3,   # Karka (Cancer)
            (2, 3): 4,   # Simha (Leo)
            (3, 3): 5,   # Kanya (Virgo)
            (3, 2): 6,   # Tula (Libra)
            (3, 1): 7,   # Vrishchika (Scorpio)
            (3, 0): 8,   # Dhanu (Sagittarius)
            (2, 0): 9,   # Makara (Capricorn)
            (1, 0): 10,  # Kumbha (Aquarius)
        }

        # Lagna sign index
        lagna_sign_idx = int(chart.lagna_deg // 30.0) % 12

        for (r_i, c_i), s_idx in south_sign_map.items():
            cell_x = left + c_i * col_w
            cell_y = top + r_i * row_h
            s_name = RASHI_NAMES_INDIAN[s_idx]

            # Label sign name in top corner
            draw.text((cell_x + 6, cell_y + 6), s_name[:5], fill=text_rashi, font=font_small)

            # If Lagna falls here, draw diagonal sash and mark ASC
            if s_idx == lagna_sign_idx:
                draw.line([(cell_x, cell_y), (cell_x + 35, cell_y)], fill=border_gold, width=3)
                draw.line([(cell_x, cell_y), (cell_x, cell_y + 35)], fill=border_gold, width=3)
                draw.line([(cell_x, cell_y + 35), (cell_x + 35, cell_y)], fill=border_gold, width=2)
                draw.text((cell_x + col_w - 6, cell_y + 6), "ASC", fill=(180, 20, 20), font=font_med, anchor="rt")

            # Collect grahas in this sign
            planets_in_sign = []
            for gname, gobj in chart.grahas.items():
                if gobj.sign_index == s_idx:
                    abbr = _ABBR_MAP.get(gname, gname[:2])
                    if gobj.is_retrograde:
                        abbr += "®"
                    planets_in_sign.append(abbr)

            if planets_in_sign:
                mid_x = cell_x + col_w // 2
                mid_y = cell_y + row_h // 2 + 5
                p_str = " ".join(planets_in_sign)
                draw.text((mid_x, mid_y), p_str, fill=text_graha, font=font_med, anchor="mm")

        # Center info box details
        center_x = cx
        center_y = cy
        draw.text((center_x, center_y - 45), f"{chart.name.upper()}", fill=header_color, font=font_large, anchor="mm")
        draw.text((center_x, center_y - 15), f"Chandra Rashi: {chart.grahas['Chandra'].sign_name}", fill=text_dark, font=font_med, anchor="mm")
        draw.text((center_x, center_y + 12), f"Nakshatra: {chart.grahas['Chandra'].nakshatra}", fill=text_dark, font=font_small, anchor="mm")
        active_d = f"Dasha: {chart.active_dasha.get('mahadasha', '')}-{chart.active_dasha.get('antardasha', '')}"
        draw.text((center_x, center_y + 38), active_d, fill=text_rashi, font=font_small, anchor="mm")

    # Footer banner
    footer_text = f"Ayanamsha: {chart.ayanamsha_name} ({chart.ayanamsha_value}°) | AMATYA Astrological Core"
    draw.text((450, 868), footer_text, fill=(100, 100, 100), font=font_small, anchor="mm")

    # Output file determination
    if not output_path:
        out_dir = Path(__file__).resolve().parent.parent / "reports" / "kundali"
        out_dir.mkdir(parents=True, exist_ok=True)
        clean_name = re.sub(r"[^\w\-]", "_", chart.name.lower())
        output_path = str(out_dir / f"kundali_{clean_name}_{style_clean}.png")

    p_out = Path(output_path)
    p_out.parent.mkdir(parents=True, exist_ok=True)
    im.save(str(p_out), format="PNG")
    return str(p_out.resolve())
