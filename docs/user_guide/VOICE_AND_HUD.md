# Voice Interaction & HUD Command-Centre

AMATYA provides a seamless multimodal voice and visual user interface featuring real-time audio analysis, speech synthesis, and 4 futuristic HUD visualization styles.

---

## 1. Voice Interaction & Wake Words

AMATYA operates on an asynchronous voice pipeline (`core/voice_auth.py`, `core/audio_processor.py`) running in a dedicated worker thread while the Qt GUI updates smoothly on the main thread.

### Natural Wakewords & Push-to-Talk
- **Wakewords:** *"Amatya"*, *"Hey Amatya"*, *"Jarvis"*, *"Hey Jarvis"*.
- **Push-to-Talk:** Tap the Spacebar or click the microphone icon in the HUD footer.
- **Microphone Mute:** Tap the Mute button in the HUD controls drawer or call `http://127.0.0.1:8765/mute`.

---

## 2. Sleep & Wake Modes

When AMATYA is in **Sleep Mode**, the audio pipeline automatically mutes the microphone input stream, halting all background listening and speech recognition.

### Voice Commands
- **Put AMATYA to Sleep:**
  - *"Go to sleep"*
  - *"Sleep mode"*
  - *"Stand down"*
  *(AMATYA acknowledges: "Going to sleep. Wake me when you need me, sir." and immediately mutes the microphone).*
- **Wake Up:**
  - Tap the Wake button in the HUD or click the central display.
  - Call the local control loopback endpoint: `curl http://127.0.0.1:8765/mute`

> [!NOTE]
> Sleep mode strictly suppresses unsolicited speech output and prevents accidental activations while the user is watching television, listening to music, or in meetings.

---

## 3. Four Centrepiece HUD Visualisations

The central HUD canvas (`gui/hud.py`, `core/orb_hud.py`) supports 4 distinct visualization styles:

### 1. ⚙️ Classic Mark-LVI Flat Reactor Core (`reactor_classic`)
- Multi-layer sweeping arc system with 72-point radial graduations.
- Rotating atmosphere body with audio amplitude-reactive frequency spike rings.
- Authentic Iron Man Mark-LVI flat holographic HUD aesthetic.

### 2. ◉ 3-D Gyroscope Reactor Core (`reactor_3d`)
- Foreshortened 3D holographic sphere with dual gyroscope rings spinning on independent axes.
- Equatorial orbital particle tracers and glowing plasma nucleus.

### 3. 🌐 Wireframe Holographic Orb (`orb`)
- Full 3D icosahedron wireframe mesh with Loop subdivision (`core/orb_hud.py`).
- Audio-reactive amplitude deformation with real-time vertex displacement.
- Rotating latitude/longitude orbital rings and dynamic particle field.

### 4. 🧑 Animated Face Avatar (`face`)
- Expressive software-rendered holographic head with audio-reactive mouth visemes and gaze tracking.

---

## 4. How to Switch HUD Modes

### Via Voice:
- *"Switch HUD"* (cycles to the next visualization style)
- *"Switch to orb"* / *"Wireframe mode"*
- *"Classic reactor"* / *"Switch to flat reactor"*
- *"3D reactor"* / *"Switch to gyroscope"*
- *"Avatar mode"* / *"Show face"*

### Via GUI Controls:
- In the HUD window top bar, click the **CONTROLS** drawer button (slider icon).
- Click the **HUD Style** button to toggle through the 4 styles in sequence.
- Changes persist across reboots in `config/api_keys.json` under `"hud_style"`.

---

## 5. Typography & Outage Alert Cards

- **Typography:** The HUD utilizes calibrated monospace font scales (`gui/style.py`), preventing text truncation and cluttered headers.
- **Incident & Outage Alerts:** Service disruptions detected by synthetic probes and Downdetector are displayed as clean, structured telemetry cards rather than dense text paragraphs.
