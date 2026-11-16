# Global Radio Streaming & Media Control

AMATYA includes a built-in worldwide radio directory and local media control suite (`core/radio_aerospace.py`, `actions/radio_and_aerospace.py`, `actions/media_controller.py`).

---

## 1. Worldwide Radio Station Streaming

AMATYA interfaces with the community-driven **Radio Browser** directory containing over 30,000 public broadcast radio streams worldwide.

### Features
- **Search by Genre:** Classical, Jazz, Synthwave, Lo-Fi, Ambient, Rock, News, Electronic.
- **Search by Country & Language:** BBC, NPR, France Musique, Radio Mirchi, etc.
- **Low-Latency Streaming:** Plays streams directly in the background using `mpv`, `ffplay`, or system audio pipelines without opening heavy browser tabs.
- **HUD Integration:** Station name, bitrate, and live audio spikes render dynamically on the HUD.

### Voice Commands:
- *"Play jazz radio"*
- *"Play BBC World Service radio"*
- *"Play classical music station"*
- *"Play synthwave radio"*
- *"Stop radio"* / *"Stop music"*

---

## 2. Desktop Media Control

AMATYA controls local desktop media players (Spotify, VLC, Audacious, web video players) using MPRIS D-Bus on Linux and OS media key bridges on Windows and macOS:

### Voice Commands:
- *"Pause playback"*
- *"Resume playback"*
- *"Next track"* / *"Skip song"*
- *"Previous track"*
- *"Mute audio"* / *"Unmute audio"*
- *"Set volume to 50 percent"*
