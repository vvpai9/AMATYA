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

### 1. Universal Desktop Automation (`core/desktop_agent.py`, `actions/desktop.py`)
- **Multi-OS UI Inspection:** Inspects windows, buttons, text fields, and accessibility trees using AT-SPI2 on Linux, UIAutomation on Windows, and AppleScript on macOS.
- **Visual Intelligence:** Full desktop, multi-monitor, active window, or rectangular region capture paired with OCR and multimodal vision model analysis.
- **Autonomous Desktop Agent:** Accessibility-first `Observe → Plan → Act → Verify` loop with 5 autonomy levels (`L0 OBSERVE` through `L4 FULL AUTO`), emergency cancellation, and full session history.

### 2. Voice-First Interaction, Speaker Verification & Security
- **Configurable Wake Word & Voice (`core/wake_word.py`, `memory/config_manager.py`):** Preserves `hey_jarvis` as the default `openwakeword` model ID while keeping **AMATYA** as the user-facing identity; supports custom ONNX/TFLite models, speech speed, voice style, verbosity (`concise`/`normal`/`detailed`), and barge-in interruption.
- **Speaker Verification & Anti-Spoofing (`core/voice_auth.py`, `actions/voice_auth.py`):**
  - Multi-sample enrollment and 64-D acoustic speaker embeddings (MFCCs, Delta-MFCCs, autocorrelation F0 pitch stats, zero-meaned formant band ratios, spectral centroid/rolloff).
  - Replay-attack detection cache, playback spectral heuristics, and randomized challenge-response phrase generation.
- **6 Permission Tiers & 5 Autonomy Levels (`core/security.py`):**
  - Tiers `0` (`CONVERSATION`) through `5` (`CRITICAL_SECURITY`) with PBKDF2-HMAC-SHA256 PIN verification, automatic secret redaction, and structured JSONL audit logs (`memory/audit.log`).

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

---

## Operating System Setup Guides

### 1. Linux Setup (Ubuntu, Debian, Fedora, Arch, KDE Neon, openSUSE)

#### Step 1: Install System Dependencies
- **Ubuntu / Debian / KDE Neon:**
  ```bash
  sudo apt update
  sudo apt install -y python3-dev python3-venv git ffmpeg portaudio19-dev libasound2-dev wl-clipboard
  ```
- **Fedora / RHEL:**
  ```bash
  sudo dnf install -y python3-devel git ffmpeg-free portaudio-devel alsa-lib-devel wl-clipboard
  ```
- **Arch Linux:**
  ```bash
  sudo pacman -S --needed python git ffmpeg portaudio alsa-lib wl-clipboard
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

# Install Python 3.12, ffmpeg, and portaudio
brew install python@3.12 ffmpeg portaudio git
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

## Verification & Automated Test Suite

Run the full automated test suite (126 unit & acceptance tests):
```bash
PYTHONPATH=. ./AMATYA/bin/pytest tests/
```

To run individual test suites:
```bash
# Android TV automation & pairing tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_tv_automation.py

# Universal core acceptance tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_amatya_suite.py
```

---

## Built Upon Mark-LVII

AMATYA is a fork and evolution of **[Mark-LVII by FatihMakes](https://github.com/FatihMakes/Mark-LVII)**. All credit for the foundational architecture goes to FatihMakes. For upstream Mark-LVII documentation, original setup guides, provider configuration, and project background, see the **[Mark-LVII README](https://github.com/FatihMakes/Mark-LVII/blob/main/readme.md)**.

---

## License

Personal and non-commercial use only. Based on Mark-LVII by FatihMakes (CC BY-NC 4.0).
