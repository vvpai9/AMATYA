# AMATYA Architecture Map

**Project:** AMATYA (अमात्य — evolved from Mark-LVI by FatihMakes)
**Base repo:** `~/Projects/Mark-LVI` (fork of `FatihMakes/Mark-LVI`)
**Git remote:** `https://github.com/FatihMakes/Mark-LVI.git`
**Target:** KDE Neon, KDE Plasma 6.8.x, Wayland, PipeWire 1.6.x, Linux, Python 3.12
**Hardware:** Intel Core i5-11300H (8 threads), 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile / Max-Q (~4 GB VRAM)

---

## 1. Repository Structure

```
Mark-LVI/
├── main.py                      # Core loop: Gemini Live / local voice session, audio I/O, tool dispatch, CentralOrchestrator hook
├── ui.py                        # PyQt6 HUD: holographic avatar, waveform, Command-Centre telemetry, Autonomy level, Emergency Stop
├── setup.py                     # OS-aware installer
├── README.md                    # User & developer documentation
├── ARCHITECTURE.md              # Architecture map & phase plan (this file)
├── DEVELOPMENT_LOG.md           # Engineering audit, bug fixes, implementation & verification log
├── requirements.txt             # Dependencies
├── actions/                     # 28 bundled auto-discovered skills (TOOL + SKILL_METADATA dicts)
│   ├── browser_control.py       # Playwright web automation
│   ├── cmd_control.py           # Terminal / bash automation
│   ├── code_helper.py           # Code generation & Wayland-safe clipboard fallback
│   ├── computer_control.py      # Keyboard/mouse/clipboard/screenshot with kwin-mcp & cross-platform fallbacks
│   ├── computer_settings.py     # Brightness/volume/window ops with kwin-mcp fallback
│   ├── creator.py               # CREATOR software engineering & document generation action
│   ├── desktop_agent.py         # Autonomous observe→plan→act→verify Wayland agent action
│   ├── device_control.py        # Connected devices: KDE Connect, ADB, Redmi TV, SSH, LAN discovery
│   ├── file_controller.py       # File management
│   ├── finder.py                # File search
│   ├── flight_finder.py         # Travel flight lookup
│   ├── home_automation.py       # Smart home devices, routines, camera privacy gate, simulated home
│   ├── jyotisha.py              # Vedic Jyotisha birth chart computation, Shodashavarga D1..D60, Shadbala, Dashas
│   ├── knowledge_base.py        # Hybrid semantic + lexical RAG knowledge base action
│   ├── kwin_desktop.py          # Wayland-native KWin / AT-SPI2 / EIS desktop automation
│   ├── model_router.py          # 11-role local/cloud AI model router action
│   ├── open_app.py              # App launcher & process controller
│   ├── orchestrator.py          # CentralOrchestrator & contextual pronoun resolution action
│   ├── phone_ring.py            # Phone ringing & VoIP calling (AgentRing, KDE Connect, ADB, Ntfy.sh)
│   ├── reminder.py              # Scheduled reminders with Linux notify-send support
│   ├── screen_processor.py      # Vision analysis of screen / camera
│   ├── send_message.py          # Messaging automation
│   ├── system_monitor.py        # System telemetry
│   ├── voice_auth.py            # Speaker enrollment, verification, anti-spoofing, PIN & autonomy control
│   ├── weather_report.py        # Weather report
│   ├── web_search.py            # DuckDuckGo / search integration
│   ├── whatsapp_connector.py    # WhatsApp Web integration
│   └── youtube_video.py         # YouTube playback & summarization
├── core/                        # Core infrastructure & intelligence engines
│   ├── action_loader.py         # Auto-discovers actions/*.py + validates SKILL_METADATA
│   ├── confirm.py               # UI confirmation gate
│   ├── creator.py               # CREATOR software engineering engine + Command Risk Classification
│   ├── desktop_agent.py         # Observe→plan→act→verify autonomous desktop agent (AT-SPI2 first)
│   ├── device_manager.py        # Multi-protocol discovery & control (KDE Connect, ADB, Redmi TV, SSH, Tailscale, ARP)
│   ├── doc_generator.py         # Document creation & parsing (PDF, DOCX, XLSX, PPTX, CSV, Markdown, ZIP)
│   ├── echo_guard.py            # Self-echo acoustic guard
│   ├── gemini.py                # Gemini model ladder & cooldowns
│   ├── home_automation.py       # Home Assistant REST/WS, MQTT, routines, state verification & simulator
│   ├── jyotisha.py              # Swiss Ephemeris astronomical engine, Sidereal Lahiri & Tropical Western calculators
│   ├── kwin_mcp_client.py       # MCP stdio client for kwin-mcp v0.12.0 (session-isolated)
│   ├── model_router.py          # 11-role hardware-aware model router (GTX 1650 4GB + 16GB RAM aware)
│   ├── orchestrator.py          # CentralOrchestrator, ContextTracker & pronoun/reference resolution
│   ├── phone_ring.py            # Cross-platform phone ringing engine (AgentRing VoIP, KDE Connect, ADB, Ntfy.sh)
│   ├── platform_support.py      # OS, Wayland, kwin-mcp & PipeWire capability probe
│   ├── plugin_loader.py         # Auto-discovers plugins/*.py + validates SKILL_METADATA
│   ├── prompt.txt               # AMATYA system prompt
│   ├── rag.py                   # Local hybrid semantic + lexical BM25 RAG store
│   ├── screen_automation.py     # Multi-monitor discovery, continuous observation, before/after verification
│   ├── security.py              # 6 Permission Tiers, 5 Autonomy Levels, PBKDF2 PIN auth, secret redaction & audit log
│   ├── undo.py                  # Shared reversible operation stack
│   ├── viseme.py                # Audio-to-lip-sync envelope tracker
│   ├── vision.py                # Wayland screen/monitor/window/region capture, OCR, VLM & diffing
│   ├── voice_auth.py            # 64-D speaker embedding, enrollment, verification, replay & playback detection
│   └── wake_word.py             # Configurable wake word detector (openWakeWord / custom models)
├── config/
│   ├── api_keys.json            # User credentials & settings (git-ignored)
│   ├── connected_devices.json   # Connected device registry (phone, Redmi TV, SSH workstations)
│   ├── home_devices.json        # Smart home device registry (living room, bedroom, study, entrance, kitchen)
│   └── home_routines.json       # Multi-device smart home routines (morning, evening, leaving_home, returning_home, sleep)
├── dashboard/
│   ├── server.py                # FastAPI remote dashboard + /api/command-centre + /api/emergency-stop + /api/autonomy
│   └── static/                  # Mobile web HUD
├── memory/
│   ├── config_manager.py        # Thread-safe configuration manager + voice & wake-word preferences
│   └── memory_manager.py        # Long-term structured memory with automatic secret redaction
├── providers/                   # Pluggable local/cloud STT, LLM & TTS engines
└── tests/
    └── test_amatya_suite.py     # End-to-end automated verification suite (8 comprehensive test suites)
```

---

## 2. Completed Architectural Phases

### Phase 1 — Foundation & Branding (COMPLETE)
- Preserved `FatihMakes/Mark-LVI` attribution and architecture while evolving user-facing identity to **AMATYA (अमात्य)**.
- Preserved `hey_jarvis` as the default `openwakeword` model identifier while exposing configurable wake-word models and user-facing wake phrases (`"AMATYA"`).
- Preserved user memory (`memory/long_term.json`) and credentials (`config/api_keys.json`).

### Phase 2 — Wayland-Native Desktop Automation (COMPLETE & VERIFIED LIVE)
- **KWin MCP v0.12.0 Schema Compatibility (`core/kwin_mcp_client.py`, `actions/kwin_desktop.py`):**
  - Updated all client methods to match `kwin-mcp` v0.12.0 tool schemas (`action`, `button`, `from_x`/`from_y`/`to_x`/`to_y`, `vertical`/`horizontal`, `wayland_clipboard` `get`/`set`, `launch_application`, `find_ui_elements`, `wait_for_ui_element`, `read_screen_text`, `dbus_call`).
  - Added `isolate_dbus=False` so `kwin-mcp` attaches to the live KDE Plasma 6 Wayland session and sees all real open windows while injecting real libei input.
- **Capture Modes (`core/vision.py`, `core/screen_automation.py`):**
  - Full desktop, individual monitor (`eDP-1`, `HDMI-A-1`, etc. via `kscreen-doctor -j` + Pillow crop), active window, and rectangular region capture.
- **Wayland Fallbacks across Legacy Actions:**
  - Updated `actions/computer_control.py`, `actions/computer_settings.py`, `actions/code_helper.py`, and `actions/reminder.py` so clipboard (`wl-copy`/`wl-paste`/KWin), screenshots, active-window checks, and notifications (`notify-send`) work natively on KDE Plasma Wayland without X11 tools.
- **Accessibility-First Autonomous Desktop Agent (`core/desktop_agent.py`, `actions/desktop_agent.py`):**
  - Implements an `Observe → Plan → Act → Verify` loop that queries the AT-SPI2 accessibility tree (`find_ui_elements`) and OCR (`read_screen_text`) before falling back to coordinates.
  - Supports 5 Autonomy Levels (`OBSERVE_ONLY`, `SUGGEST_ONLY`, `CONFIRM_BEFORE_ACTING`, `SAFE_AUTONOMOUS`, `FULL_AUTONOMOUS`), task cancellation, and execution history.

### Phase 3 — Voice Intelligence, Speaker Verification & Permission Security (COMPLETE & VERIFIED)
- **Voice Preferences & Wake Word (`memory/config_manager.py`, `core/wake_word.py`, `main.py`):**
  - Configurable wake-word model, threshold, speech speed, voice style, verbosity level (`concise`, `normal`, `detailed`), and barge-in interruption toggle.
- **Speaker Verification & Anti-Spoofing (`core/voice_auth.py`, `actions/voice_auth.py`):**
  - Extracts 64-D speaker embeddings (20 MFCC means, 20 MFCC stds, 10 Delta-MFCCs, autocorrelation F0 pitch statistics, zero-meaned formant band ratios, spectral centroid/rolloff) and verifies speakers using a blended cosine + RBF Euclidean distance + F0 pitch proximity score (`0.9831` on legitimate speaker vs `0.4913` on impostor).
  - Includes SHA-256 + high-precision acoustic fingerprint replay detection, high-frequency rolloff playback heuristics, and randomized challenge-response phrase verification.
- **Permission Tiers & Security Policy (`core/security.py`):**
  - **6 Permission Tiers:** `TIER_0_CONVERSATION`, `TIER_1_LOW_RISK`, `TIER_2_MEDIUM_RISK`, `TIER_3_SENSITIVE`, `TIER_4_HIGH_RISK`, `TIER_5_CRITICAL_SECURITY`.
  - **PBKDF2-HMAC-SHA256 PIN Authentication** (200,000 rounds), secret redaction guard, and structured JSONL audit logging (`memory/audit.log`).

### Phase 4 — Central Intelligence, Local AI Model Router & Hybrid RAG (COMPLETE & VERIFIED)
- **11-Role Hardware-Aware Model Router (`core/model_router.py`, `actions/model_router.py`):**
  - Detects CPU, RAM (16 GB), and NVIDIA GPU VRAM via `nvidia-smi` (GTX 1650 Mobile ~4 GB VRAM) and routes across 11 specialized roles: `conversation`, `reasoning`, `coding`, `desktop_understanding`, `ocr`, `stt`, `tts`, `wake_word`, `speaker_verification`, `embeddings`, and `summarization`.
- **Hybrid RAG Store (`core/rag.py`, `actions/knowledge_base.py`):**
  - Indexes files, notes, and directories into overlapping chunks scored by hybrid cosine similarity (256-D character n-gram + word hashing embeddings or Ollama embeddings) and lexical BM25 overlap.
- **CentralOrchestrator & Contextual Reference Resolution (`core/orchestrator.py`, `actions/orchestrator.py`):**
  - Tracks active window, previous window, active project, active file, last URL, and multi-task queue.
  - Resolves natural contextual references (*"Open that"*, *"Close the previous window"*, *"Continue what you were doing"*, *"Check the same project again"*, *"Send that file to my phone"*).

### Phase 5 — Smart Home Automation (COMPLETE & VERIFIED)
- **Home Automation Engine (`core/home_automation.py`, `actions/home_automation.py`, `config/home_devices.json`, `config/home_routines.json`):**
  - Supports Home Assistant REST/WebSocket API, MQTT (`mosquitto_pub`), and a clearly labeled **Simulated Home Environment** (`[SIMULATED HOME ENVIRONMENT]`) for safe offline testing.
  - Includes post-command state verification, camera privacy gate (`TIER_3_SENSITIVE`), and routines (`morning`, `evening`, `leaving_home`, `returning_home`, `sleep`) with automatic confirmation checks on security-critical steps (locks/alarms/cameras).

### Phase 6 — Connected Devices & Network Control (COMPLETE & VERIFIED LIVE)
- **Device Ecosystem Manager (`core/device_manager.py`, `actions/device_control.py`, `config/connected_devices.json`):**
  - Multi-protocol discovery across **KDE Connect** (`kdeconnect-cli`), **ADB**, **LAN ARP table (`ip neigh`)**, **mDNS (`avahi-browse`)**, and **Tailscale**.
  - **Android Phone Control:** File transfer (`--share` / `adb push`), Find-My-Phone ring (`--ring`), clipboard sync, app launch, and battery check.
  - **Redmi Android TV Control:** Power toggle, volume/mute, D-Pad navigation, direct launch of YouTube, Netflix, Prime Video, Disney+ Hotstar, VLC, Kodi, and URL casting via ADB over LAN.
  - **Remote Computers:** Non-interactive SSH command execution, remote resource inspection, and SCP file transfer.
- **Universal Phone Ring & VoIP Calling Engine (`core/phone_ring.py`, `actions/phone_ring.py`):**
  - Multi-tier phone ringing cascade: **AgentRing** (open-source WebRTC/LiveKit VoIP audio calls with AI voice), **KDE Connect** (LAN Wi-Fi ring bypassing silent mode), **ADB** (volume boost to max + alarm audio intent), and **Ntfy.sh** (zero-dependency remote push notification with `Priority: urgent` overriding DND).
  - Cross-platform binary resolution and fallback execution across **Linux**, **Windows** (`kdeconnect-cli.exe`, `adb.exe`, PowerShell clipboard `Get-Clipboard`/`Set-Clipboard`, `ImageGrab.grab`), and **macOS** (`kdeconnect-cli`, `pbcopy`/`pbpaste`, native `screencapture -x`).

### Phase 7 — CREATOR Software Engineering & Document Engine (COMPLETE & VERIFIED)
- **CREATOR Engine (`core/creator.py`, `actions/creator.py`):**
  - Project architecture inspection, regex symbol search, safe file editing with automatic Python AST syntax validation and backup rollback, git status/diff, and test runner with **Command Risk Classification** (`SAFE_READ`, `SAFE_BUILD`, `MODIFY`, `DESTRUCTIVE`).
- **Document Engine (`core/doc_generator.py`):**
  - Generates and analyzes **PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP** files locally.

### Phase 8 — Declarative Skills, Command-Centre HUD & Automated Test Suite (COMPLETE & VERIFIED)
- **Declarative Skill Metadata (`core/action_loader.py`, `core/plugin_loader.py`):**
  - Validates optional `SKILL_METADATA` (`category`, `permission_tier`, `requires_network`, `requires_wayland`, `version`) across all 26 bundled actions.
- **Command-Centre HUD & Emergency Stop (`ui.py`, `dashboard/server.py`):**
  - Added `/api/command-centre`, `/api/emergency-stop`, and `/api/autonomy` to the FastAPI dashboard and added the `⊞ COMMAND CENTRE` live telemetry overlay, `🛡 AUTONOMY` selector, and `🛑 EMERGENCY STOP` button to the PyQt6 HUD.
- **End-to-End Verification Suite (`tests/test_amatya_suite.py`):**
  - 8 comprehensive unit/integration test suites verifying all subsystems in `./AMATYA/bin/python -m unittest discover -s tests -v`.
