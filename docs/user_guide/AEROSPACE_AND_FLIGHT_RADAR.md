# Aerospace, Orbital Satellites & Flightradar24 Airspace Tracking

AMATYA features live aerospace observation tools combining commercial aviation tracking, satellite orbital telemetry, and space weather monitoring (`actions/radio_and_aerospace.py`, `actions/satellite_tracker.py`).

---

## 1. Commercial Airspace Tracking (Flightradar24)

AMATYA connects directly to live **Flightradar24** radar feeds to monitor commercial flights overhead:

### Key Features
- **Accurate Barometric Altitude:** Accurately distinguishes between airborne flights in cruise/climb/descent and scheduled or on-ground flights reporting 0 ft barometric altitude.
- **Flight Information:**
  - Flight number and callsign (e.g. `AIC101`, `BAW48`, `UAE502`).
  - Operating airline / carrier.
  - Aircraft ICAO type (e.g. `A320`, `B77W`, `A359`, `B738`).
  - Origin and destination airports (`Origin → Destination`).
  - True altitude (feet), ground speed (knots), and heading.
- **Resilient Fallback:** Automatically queries the OpenSky Network if Flightradar24 rate limits are encountered.

### Voice Commands:
- *"Scan local airspace"*
- *"What planes are flying overhead?"*
- *"Track flight AIC101"*
- *"Check status of flight BAW48"*

---

## 2. Orbital Satellite Telemetry & Pass Predictions

AMATYA tracks low-Earth orbit and deep-space objects via NORAD two-line element (TLE) orbital calculations:

### Supported Constellations & Satellites
- **International Space Station (ISS)**
- **Tiangong Space Station (CSS)**
- **Hubble Space Telescope (HST)**
- **Starlink Constellations**

### Information Provided
- Instantaneous latitude, longitude, and orbital altitude.
- Orbital speed ($km/s$ and $km/h$).
- Flyover pass predictions for the user's localized coordinates (rise time, culmination altitude, set time).

### Voice Commands:
- *"Where is the International Space Station right now?"*
- *"Track the Hubble Space Telescope"*
- *"When is the next space station pass over my location?"*

---

## 3. NOAA Space Weather Telemetry

Queries the NOAA Space Weather Prediction Center (SWPC) for solar activity and geomagnetic conditions:
- **Planetary K-index (Kp):** Measures geomagnetic storm intensity (Kp 0–9).
- **Solar Flare Activity:** Telemetry on active C, M, and X-class solar flares.
- **Radio Blackouts & Aurora Forecast:** Potential impacts on HF communications and satellite GPS signals.

### Voice Commands:
- *"Check space weather"*
- *"Report solar storms and geomagnetic activity"*
