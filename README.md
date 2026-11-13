# AMATYA (अमात्य) — Universal Personal AI Operating Companion

**Built upon [FatihMakes's Mark-LVII](https://github.com/FatihMakes/Mark-LVII)** — AMATYA evolves Mark-LVII into a local-first, universal autonomous personal AI operating companion designed for **all Linux distributions** (Ubuntu, Debian, Fedora, Arch, KDE Neon, openSUSE, GNOME, KDE Plasma, X11, Wayland), **Windows 10/11**, and **macOS** (Apple Silicon & Intel). AMATYA provides identical core functionality across operating systems, combining universal desktop automation, biometric speaker verification, permission-tiered security, a hardware-aware local AI model router, smart home orchestration, connected device control (Android phone, Android TV, SSH hosts), and **CREATOR** (an autonomous software engineering and multi-format document engine).

---

## Universal Cross-Platform Architecture

AMATYA operates natively across all major desktop environments by detecting the host operating system and dynamically binding to native system subsystems:

| Subsystem | Linux (Wayland / X11) | Windows (10 / 11) | macOS (Apple Silicon / Intel) |
|---|---|---|---|
| **Audio Capture / Playback** | PipeWire / PulseAudio / ALSA | WASAPI / DirectSound (`pycaw`) | CoreAudio (`osascript` / `afplay`) |
| **Screen Capture** | KWin ScreenShot2 / `grim` / `spectacle` / `scrot` | Windows Graphics Capture / `mss` / `PIL.ImageGrab` | Native `screencapture -x` |
| **Desktop & UI Input** | KWin EIS `libei` / AT-SPI2 / `xdotool` | UIAutomation / `pywinauto` / `pywin32` | AppleScript / Accessibility API (`osascript`) |
| **Clipboard Sync** | `wl-clipboard` (Wayland) / `xclip` (X11) | PowerShell `Get-Clipboard` / Win32 API | Native `pbcopy` / `pbpaste` |
| **System Notifications** | `notify-send` / FreeDesktop D-Bus | Windows 10/11 Toast Notifications (`win10toast`) | `osascript -e 'display notification'` |
| **Android TV Automation** | Pure Python `androidtvremote2` (TLS 6466/6467) | Pure Python `androidtvremote2` (TLS 6466/6467) | Pure Python `androidtvremote2` (TLS 6466/6467) |
| **Phone VoIP & Ringing** | KDE Connect / ADB / AgentRing / Ntfy.sh | KDE Connect for Win / ADB / AgentRing / Ntfy.sh | KDE Connect for Mac / ADB / AgentRing / Ntfy.sh |

---

## Core Capabilities

### 1. Universal Desktop Automation (`core/desktop_agent.py`, `actions/desktop.py`, `core/kwin_mcp_client.py`)
- **Multi-OS UI Inspection:** Inspects windows, buttons, text fields, and accessibility trees using AT-SPI2 on Linux, UIAutomation on Windows, and AppleScript on macOS.
- **KDE Plasma 6 Wayland Desktop Automation:** Native Model Context Protocol client (`kwin-mcp`) driving window focus, raising active application windows, screenshots, and input emulation on Wayland where legacy X11 tools fail.
- **Visual Intelligence:** Full desktop, multi-monitor, active window, or rectangular region capture paired with OCR and multimodal vision model analysis.
- **Autonomous Desktop Agent:** Accessibility-first `Observe → Plan → Act → Verify` loop with 5 autonomy levels (`L0 OBSERVE` through `L4 FULL AUTO`), emergency cancellation, and full session history.

### 2. Voice-First Interaction, Speaker Verification & Security
- **Configurable Wake Word & Voice (`core/wake_word.py`, `memory/config_manager.py`):** Preserves `hey_jarvis` as the default `openwakeword` model ID while keeping **AMATYA** as the user-facing identity; supports custom ONNX/TFLite models, speech speed, voice style, verbosity (`concise`/`normal`/`detailed`), and barge-in interruption.
- **Speaker Verification & Anti-Spoofing (`core/voice_auth.py`, `actions/voice_auth.py`):**
  - Multi-sample enrollment and 64-D acoustic speaker embeddings (MFCCs, Delta-MFCCs, autocorrelation F0 pitch stats, zero-meaned formant band ratios, spectral centroid/rolloff).
  - Replay-attack detection cache, playback spectral heuristics, and randomized challenge-response phrase generation.
- **6 Permission Tiers & 5 Autonomy Levels (`core/security.py`):**
  - Tiers `0` (`CONVERSATION`) through `5` (`CRITICAL_SECURITY`) with PBKDF2-HMAC-SHA256 PIN verification, automatic secret redaction, and structured JSONL audit logs (`memory/audit.log`).
- **Encrypted Local Storage at Rest (`core/security.py`, `memory/memory_manager.py`, `core/geolocation.py`):**
  - Resolves CWE-312 and CWE-359 by encrypting long-term memory (`long_term.json`) and device geolocation cache (`device_location.json`) using authenticated Fernet cryptography with strict `0o600` POSIX file permissions. Protects sensitive coordinates, personal profiles, and session histories from unauthorized local access.

### 3. Central Intelligence, Local AI Router & Hybrid RAG
- **11-Role Hardware-Aware Model Router (`core/model_router.py`, `actions/model_router.py`):**
  - Detects CPU, RAM, and GPU VRAM via NVIDIA `pynvml` or system profilers and dynamically routes tasks across conversation, reasoning, coding, vision, OCR, STT, TTS, wake-word, and embeddings.
- **Contextual Reference Resolution (`core/orchestrator.py`, `actions/orchestrator.py`):**
  - Resolves contextual references such as *"Open that"*, *"Close the previous window"*, *"Continue what you were doing"*, *"Check the same project again"*, and *"Send that file to my phone"*.
- **Hybrid RAG Knowledge Base (`core/rag.py`, `actions/knowledge_base.py`):**
  - Indexes project files, notes, and directories into a local hybrid semantic + lexical BM25 knowledge store.

### 4. Smart Home Automation (`core/home_automation.py`, `actions/home_automation.py`)
- Supports **Home Assistant REST/WebSocket API**, **MQTT**, and a clearly labeled **Simulated Home Environment** (`[SIMULATED HOME ENVIRONMENT]`) when no live broker is reachable.
- Post-command state verification, camera privacy gate (`TIER_3_SENSITIVE`), and multi-step routines (`morning`, `evening`, `leaving_home`, `returning_home`, `sleep`) with confirmation gates for locks, alarms, and cameras.

### 5. Connected Devices & Android TV Automation (`core/tv_control.py`, `actions/device_control.py`)
- **Android TV Remote v2 Automation:**
  - Direct, pure Python mutual-TLS control via `androidtvremote2` on port 6466 and pairing on port 6467.
  - **Zero-Setup Prompt:** When no TV is configured initially, AMATYA prompts the user with step-by-step setup guidance.
  - **Two-Step Secure Pairing:**
    1. Initiate pairing: `device_control action="setup_tv" ip_address="<TV_IP>"` (displays a 6-character code on your TV screen).
    2. Complete pairing: `device_control action="pair_tv" code="<CODE>"`.
  - **Complete TV Controls:** Power on/off, volume stepping with live level feedback, D-pad navigation (`UP`, `DOWN`, `LEFT`, `RIGHT`, `ENTER`, `BACK`, `HOME`), app launching (YouTube, Netflix, Prime Video, VLC), and media URL casting.
- **Android Phone & Network Ecosystem:**
  - Phone integration via **KDE Connect** (`kdeconnect-cli`), **ADB**, and **AgentRing VoIP** for file sharing, Find-My-Phone alerts, clipboard sync, battery monitoring, and urgent notifications.
  - Non-interactive SSH command execution, system status checks, and SCP file transfers for remote computers.

### 6. CREATOR — Software Engineering & Document Engine (`core/creator.py`, `core/doc_generator.py`)
- **Software Engineering:** Repository architecture summary, symbol search, safe file editing with automatic Python AST syntax validation and backup rollback, git status/diff, and test execution with **Command Risk Classification** (`SAFE_READ`, `SAFE_BUILD`, `MODIFY`, `DESTRUCTIVE`).
- **Multi-Format Documents:** Generate and inspect **PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP** files locally.
- **Dynamic Content & Summary Bridging:** Auto-bridges summarized text directly from generated files into presentations and reports without falling back to placeholder content.
- **Strict File Deletion Protection:** Deletion of any file or directory requires mandatory confirmation and supports spoken voice authorization (`confirm.voice_authorize`).

### 7. Vedic Jyotisha & Astrological Intelligence (`core/jyotisha.py`, `actions/jyotisha.py`)
- **Vedic Sidereal Calculations (Lahiri / Chitrapaksha Ayanamsha):** High-precision planetary longitudes, Lagna, and Bhavas computed using Swiss Ephemeris (`pyswisseph`).
- **All 16 Shodashavarga Divisional Charts:** Full computation and interpretation of D1 (Rashi), D2 (Hora), D3 (Drekkana), D4 (Chaturthamsa), D7 (Saptamsha), D9 (Navamsha), D10 (Dashamsha), D12, D16, D20, D24, D27, D30, D40, D45, and D60 (Shashtiamsha).
- **Planetary Strengths & Karakas:** Six-fold **Shadbala** (Sthana, Dig, Kala, Cheshta, Naisargika, Drik) in Virupas/Rupas and Jaimini **Chara Karakas** (Atmakaraka..Darakaraka).
- **Vimsottari Dasha Engine:** Computes birth dasha balance, the complete 120-year cycle of Mahadashas and Antardashas, and active transit periods.

### 8. Mobile Calling, Phone Ringing & AgentRing VoIP (`core/phone_ring.py`, `actions/phone_ring.py`)
- **AgentRing VoIP Integration:** Lets AMATYA call your mobile phone over self-hosted VoIP when tasks complete or critical input is needed, with real-time AI voice bridging and zero carrier/Twilio fees.
- **Cross-Platform Fallbacks:** Direct local Wi-Fi / LAN ringing via KDE Connect, ADB audio boost, and Ntfy.sh HTTP push.

### 9. Futuristic Command-Centre HUD (`ui.py`, `dashboard/server.py`)
- Holographic rotating globe with real-time audio-reactive lip-sync:
  - **`⊞ COMMAND CENTRE`:** Live telemetry overlay displaying security tier, voice auth status, GPU/RAM model router status, connected devices, smart home summary, and active tasks.
  - **`🛡 AUTONOMY`:** One-click cycling across all 5 autonomy levels (`L0 OBSERVE` → `L4 FULL AUTO`).
  - **`🛑 EMERGENCY STOP`:** Immediately halts all running desktop agents, background tasks, and speech output.

### 10. Fast Directory Navigation & DesktopAuto (`core/zoxide_nav.py`, `actions/desktop_nav.py`)
- **Frecency-Based Smart Jumping:** Integrates `zoxide` with pure-Python resilient fallback engine. Learns user directory access habits over time and enables instant jumping using partial keywords (e.g. *"Jump to amatya"*).
- **Direct System Launcher Integration:** Seamlessly opens target directories in native desktop file managers (Dolphin, Nautilus, Thunar, Windows File Explorer, macOS Finder) or launches terminal emulators (Konsole, GNOME Terminal, Kitty, Alacritty, PowerShell, Terminal) with a single voice or tool command.
- **Deep File Controller Integration:** `actions/file_controller.py` automatically resolves ambiguous paths via frecency search and records folder access history in real time.

### 11. OSINT & Open Intelligence (`actions/osint_tools.py`, `agents/osint_investigator.md`)
- **Domain & Infrastructure Reconnaissance:** Deep DNS queries across all records (A, AAAA, MX, NS, TXT, SOA, CNAME), reverse DNS, WHOIS registry lookup, SSL/TLS certificate inspection, and sub-domain enumeration.
- **Network & IP Intelligence:** Geolocation, Autonomous System Number (ASN), CIDR ranges, and reverse IP lookups.
- **Metadata Extraction & Historical Archives:** EXIF / GPS / device extraction from media and Wayback Machine historical archive snapshot querying.
- **Specialized OSINT Investigator Agent:** Dedicated autonomous subagent with failure-resilient passive reconnaissance workflows.

### 12. World News, Local Briefings & Global Outage Monitoring (`core/news_service.py`, `actions/news_service.py`)
- **Thrice-Daily & Startup Briefings:** Automated briefings scheduled morning, afternoon, and evening, plus a comprehensive debrief on AMATYA startup across user-selected categories (geopolitics, wars, tech, sports, business, science).
- **Dual Outage Monitoring (Downdetector & Synthetic Probes):** Real-time global outage detection cross-referencing official status APIs, HTTP/SSL latency probes, and live **Downdetector** user disruption spikes for major platforms (Microsoft 365, Outlook, Copilot, Google, Cloudflare, AWS, GitHub, YouTube, Reddit, X/Twitter, Claude, OpenAI). Flags incidents even during microservice or authentication breakdowns when homepages appear responsive.
- **Device Geolocation Awareness:** Seamlessly resolves user coordinates and local region context to automatically tailor regional news and local time.

### 13. Global Radio Discovery & Aerospace Trajectory Tracking (`core/radio_aerospace.py`, `actions/radio_and_aerospace.py`)
- **Global Radio Station Directory & Streaming:** Community-driven Radio Browser integration to search and stream worldwide radio stations directly from the HUD.
- **Flightradar24 Commercial Airspace Tracking:** Real-time local airspace scanning via live Flightradar24 radar feeds displaying commercial flight numbers, operating carriers, aircraft types (e.g. `A320`, `B738`), routes (`Origin → Destination`), altitude, speed, and heading. Includes individual flight tracking by callsign with resilient fallback to OpenSky Network.
- **Orbital Trajectory & Aerospace Tracking:** Real-time telemetry, latitude/longitude/altitude calculations, and flyover pass predictions for the International Space Station (ISS) and space stations.

---

## Operating System Setup Guides

### 1. Linux Setup (Ubuntu, Debian, Fedora, Arch, KDE Neon, openSUSE)

#### Step 1: Install System Dependencies
- **Ubuntu / Debian / KDE Neon:**
  ```bash
  sudo apt update
  sudo apt install -y python3-dev python3-venv git ffmpeg portaudio19-dev libasound2-dev wl-clipboard zoxide
  # Or install the latest zoxide binary directly:
  # curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh
  ```
- **Fedora / RHEL:**
  ```bash
  sudo dnf install -y python3-devel git ffmpeg-free portaudio-devel alsa-lib-devel wl-clipboard zoxide
  ```
- **Arch Linux:**
  ```bash
  sudo pacman -S --needed python git ffmpeg portaudio alsa-lib wl-clipboard zoxide
  ```

#### Step 2: Clone & Set Up Virtual Environment
```bash
git clone https://github.com/vvpai9/AMATYA.git
cd AMATYA

python3 -m venv AMATYA
source AMATYA/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### Step 3: Run AMATYA
```bash
./AMATYA/bin/python main.py
```

---

### 2. Windows Setup (Windows 10 & Windows 11)

#### Step 1: Prerequisites
- Install **Python 3.11 or 3.12** from [python.org](https://www.python.org/downloads/) (check *"Add python.exe to PATH"* during installation).
- Install **Git for Windows** from [git-scm.com](https://git-scm.com/).
- Install **Zoxide** for lightning-fast directory navigation via winget:
  ```powershell
  winget install ajeetdsouza.zoxide
  ```
- Ensure **Visual C++ Redistributable 2015–2022** is installed.
- Ensure microphone permissions are enabled under: `Settings → Privacy & security → Microphone → Let desktop apps access your microphone`.

#### Step 2: Clone & Set Up Virtual Environment (PowerShell)
```powershell
git clone https://github.com/vvpai9/AMATYA.git
cd AMATYA

python -m venv AMATYA
.\AMATYA\Scripts\Activate.ps1
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### Step 3: Run AMATYA
```powershell
.\AMATYA\Scripts\python.exe main.py
```

---

### 3. macOS Setup (Sonoma, Ventura, Sequoia on Apple Silicon & Intel)

#### Step 1: Prerequisites via Homebrew
```bash
# Install Homebrew if not already present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.12, ffmpeg, portaudio, git, and zoxide
brew install python@3.12 ffmpeg portaudio git zoxide
```

#### Step 2: System Permissions
Open `System Settings → Privacy & Security`:
- **Microphone:** Allow Terminal / iTerm2.
- **Accessibility:** Allow Terminal / iTerm2 (required for desktop automation).
- **Screen Recording:** Allow Terminal / iTerm2 (required for screen understanding).

#### Step 3: Clone & Set Up Virtual Environment
```bash
git clone https://github.com/vvpai9/AMATYA.git
cd AMATYA

python3 -m venv AMATYA
source AMATYA/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### Step 4: Run AMATYA
```bash
./AMATYA/bin/python main.py
```

---

## TV Automation Setup & Usage

AMATYA controls any Android TV (Redmi, Sony, Philips, TCL, Chromecast with Google TV, Xiaomi, Nvidia Shield) natively over Wi-Fi:

1. **Initial Status Check:**
   When no TV is configured yet, asking to control the TV will respond:
   > *"No Android TV is configured yet. Please configure your TV by running: `device_control with action='setup_tv' and ip_address='<TV_IP>'`."*

2. **Start Pairing:**
   ```bash
   # From voice or tool call:
   device_control action="setup_tv" ip_address="192.168.1.5"
   ```
   AMATYA generates the secure mutual-TLS client certificates and triggers the pairing request. A 6-character code appears on your TV screen.

3. **Complete Pairing:**
   ```bash
   device_control action="pair_tv" code="ABC123"
   ```
   AMATYA stores the authenticated certificates under `config/tv_certs/` and marks the TV ready.

4. **Available Commands:**
   - `"Turn on the TV"` / `"Turn off the TV"` (`action="tv_power"`)
   - `"Set TV volume to 25"` (`action="tv_volume" volume_pct=25`)
   - `"Open YouTube on the TV"` (`action="tv_launch_app" app_name="youtube"`)
   - `"Check TV status"` (`action="tv_status"`)

---

## Fast Directory Navigation (Zoxide) & DesktopAuto

AMATYA includes frecency-based directory navigation powered by `zoxide` with seamless desktop integration:

1. **Voice & Natural Language Jumping:**
   - *"Jump to amatya"* (`action="jump" query="amatya"`)
   - *"Jump to projects and open file manager"* (`action="jump" query="projects" open_file_manager=true`)
   - *"Open terminal in mark lvi"* (`action="jump" query="mark-lvi" open_terminal=true`)
   - *"List my most frequent folders"* (`action="list"`)

2. **Cross-Platform File Manager & Terminal Launching:**
   - **Linux:** Automatically launches Dolphin, Nautilus, Thunar, or `xdg-open`; terminals include Konsole, GNOME Terminal, Kitty, Alacritty, or xterm.
   - **Windows:** Launches File Explorer and PowerShell / Windows Terminal directly at the resolved path.
   - **macOS:** Launches Finder (`open`) and Terminal.app.

3. **Zero Configuration Fallback:**
   - Works immediately out-of-the-box without external binaries via AMATYA's internal JSON frecency engine (`core/zoxide_nav.py`).
   - Automatically switches to native `zoxide` CLI when installed for maximum speed.

---

## Verification & Automated Test Suite

Run the full automated test suite (165 unit & acceptance tests across 14 test suites):
```bash
PYTHONPATH=. ./AMATYA/bin/pytest tests/
```

To run individual test suites:
```bash
# Zoxide navigation and desktop automation tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_zoxide_nav.py

# Android TV automation & pairing tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_tv_automation.py

# OSINT intelligence and reconnaissance tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_osint.py

# Radio and aerospace trajectory tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_radio_and_aerospace.py

# World news and outage monitor tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_news.py

# Universal core acceptance tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_amatya_suite.py
```

---

## Built Upon Mark-LVII

AMATYA is a fork and evolution of **[Mark-LVII by FatihMakes](https://github.com/FatihMakes/Mark-LVII)**. All credit for the foundational architecture goes to FatihMakes. For upstream Mark-LVII documentation, original setup guides, provider configuration, and project background, see the **[Mark-LVII README](https://github.com/FatihMakes/Mark-LVII/blob/main/readme.md)**.

---

## License

Personal and non-commercial use only. Based on Mark-LVII by FatihMakes (CC BY-NC 4.0).
