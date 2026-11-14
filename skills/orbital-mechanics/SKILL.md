---
name: orbital-mechanics
description: "Real-time telemetry tracking for low-Earth orbit spacecraft (ISS, Tiangong Space Station, Hubble Space Telescope, Starlink), sub-satellite ground track coordinates, altitude, orbital velocity, and NOAA space weather indices. Use whenever the user asks to 'track ISS', 'where is the space station', 'satellite pass', 'orbital telemetry', or 'space weather'."
license: Apache-2.0
---

# Stark Global Aerospace & Orbital Satellite Tracker

Provides real-time telemetry, orbital coordinates, and sub-satellite coordinates for prominent orbital spacecraft.

## Key Capabilities

1. **Live Spacecraft Telemetry (`track_satellite`):**
   - Tracks the International Space Station (ISS, NORAD 25544).
   - Tracks Tiangong Chinese Space Station (CSS, NORAD 48274).
   - Tracks the Hubble Space Telescope (HST, NORAD 20580).
   - Provides sub-satellite coordinates (latitude, longitude), altitude in km, and velocity in km/h.

2. **NOAA Space Weather Indices (`space_weather`):**
   - G-Scale: Geomagnetic storms and magnetosphere disturbances.
   - S-Scale: Solar radiation storms.
   - R-Scale: Radio blackout events from solar X-ray flares.
