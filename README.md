# AMATYA (अमात्य) — Universal Personal AI Operating Companion

**Built upon [FatihMakes's Mark-LVII](https://github.com/FatihMakes/Mark-LVII)** — AMATYA evolves Mark-LVII into a local-first, universal autonomous personal AI operating companion designed for **all Linux distributions** (Ubuntu, Debian, Fedora, Arch, KDE Neon, openSUSE, GNOME, KDE Plasma, X11, Wayland), **Windows 10/11**, and **macOS** (Apple Silicon & Intel). AMATYA provides identical core functionality across operating systems, combining universal desktop automation, biometric speaker verification, permission-tiered security, a hardware-aware local AI model router, smart home orchestration, connected device control (Android phone, Android TV, SSH hosts), the **Enterprise & Autonomous Intelligence Suite** (contributed by Aman Kumar), and **CREATOR** (an autonomous software engineering, self-repair and multi-format document engine).

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
- **Autonomous Desktop Agent:** Accessibility-first `Observe → Plan → Act → Verify` loop with 5 autonomy levels (`L1: OBSERVE` through `L5: FULL AUTO`), emergency cancellation, and full session history:
  - **Level 1 (`observe_only`):** Watch and report, never act.
  - **Level 2 (`recommend`):** Propose actions and wait for user approval.
  - **Level 3 (`confirm`):** Execute standard actions, require confirmation for sensitive/destructive operations.
  - **Level 4 (`autonomous_low_risk`):** Execute low-risk actions automatically, confirm destructive operations.
  - **Level 5 (`autonomous_workflows`):** Fully autonomous execution of approved multi-step workflows.

### 2. Voice-First Interaction, Speaker Verification & Security
- **Configurable Wake Word & Voice (`core/wake_word.py`, `memory/config_manager.py`):** Preserves `hey_jarvis` as the default `openwakeword` model ID while keeping **AMATYA** as the user-facing identity; supports custom ONNX/TFLite models, speech speed, voice style, verbosity (`concise`/`normal`/`detailed`), and barge-in interruption.
- **Hardware-Level Sleep Muting & Stage Direction Suppression (`main.py`, `core/tts.py`):**
  - When sleeping, the microphone audio path is completely gated and muted so no mic audio is transmitted. Audio queues are instantly drained.
  - Strict suppression of synthetic LLM stage directions (e.g. `(remains silent)`, `(silence)`, `*remains silent*`), preventing unwanted speech output or visual chatter when AMATYA remains quiet.
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

### 6. CREATOR — Unified Autonomous Software Engineering, Self-Repair & Multi-Modal Generation Suite (`core/creator.py`, `actions/creator.py`)

> **Major Feature Upgrade:** The **CREATOR** suite unifies AMATYA's core software engineering engine with the advanced autonomous software engineering, self-repair, and generation tools contributed by **Aman Kumar ([@iamTechieAman](https://github.com/iamTechieAman))** from Mark-LVII PR #182 and his fork.

- **Autonomous Software Engineering & AST-Verified Surgical Editing:**
  - **Surgical AST Code Editing (`edit_code`):** Precise find-and-replace code modification verified against Python's Abstract Syntax Tree (`ast.parse`) before persisting, with automatic rollback on syntax errors.
  - **Bounded Code Reading (`read_code`):** Line-bounded inspection with offset ranges and byte-size truncation protection.
  - **Universal File Writing (`write_code` / `create_file`):** Create and overwrite code or config files with automatic parent directory scaffolding and AST syntax verification.
  - **Project Scaffolding (`scaffold` / `create_project`):** Generate complete project boilerplate for FastAPI, Python, React/Web, or custom structures with automatic Git repository initialization and profiling.
  - **Multi-File Atomic Edits (`apply_edits` / `apply_edits_and_verify`):** Multi-file search-and-replace with in-memory backups and automatic rollback if post-edit tests fail.
  - **Code Search & Intelligence (`search_code`, `code_assist`):** Regex/symbol search across workspaces and AI architectural guidance via the hardware-aware ModelRouter.
- **Autonomous Self-Repair, Diagnostics & Auto-Healing (`self_repair`, `audit_system`):**
  - **Codebase Integrity Audit:** Automatically parses every module across `actions/`, `core/`, `gui/`, `memory/`, and `providers/` using AST to flag syntax anomalies.
  - **Dependency Verification & Auto-Healing:** Audits critical packages (`PyQt6`, `sounddevice`, `numpy`, `google-genai`, `requests`, `ddgs`, `playwright`, `openwakeword`, `faster_whisper`, `psutil`, `pillow`) and performs pip self-healing on demand.
  - **Voice Turn Latency Tuning:** Ensures rapid response mode (`silence_ms: 450`, `prefix_ms: 100`) for seamless natural voice interaction.
  - **Visual HUD Presentation:** Summarizes health audits into rich Markdown reports on the HUD (`player.show_content`).
- **Coding Pipeline & Risk-Gated Terminal Execution:**
  - **Command Risk Classification:** Categorizes every terminal command into `SAFE_READ`, `SAFE_BUILD`, `MODIFY`, or `DESTRUCTIVE`.
  - **Git Automation (`git_status`, `git_diff`, `git_log`, `git_commit`, `git_branch`, `git_push`, `git_pull`):** Full version control pipeline management.
  - **Automated Test Runner (`run_tests`, `check_project`):** Runs pytest, unittest, npm test, or compilation checks with elapsed time reporting.
- **Document Studio & Universal File Creator (`generate_doc`, `analyze_doc`, `merge_pdf`, `extract_pdf_pages`):**
  - High-fidelity generation and analysis of **PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP** files.
  - Multi-file PDF merging (`merge_pdf`) and page extraction (`extract_pdf_pages`).
  - Natively integrates the Anthropic Skills ecosystem (`docx`, `xlsx`, `pptx`, `pdf`).
- **Multi-Modal Media Generation (`generate_image`, `create_video`):**
  - **AI Image Generation:** Synthesize artwork, concept art, wallpapers, and diagrams using FLUX/SDXL via Pollinations AI with automatic desktop saving and preview.
  - **AI Video Studio:** Synthesize cinematic HUD motion cards, visual titles, and video clips (MP4) styled in `cyber`, `cinematic`, `gold`, or `neon` themes using FFmpeg and Pillow.

### 7. Vedic Jyotisha & Astrological Intelligence (`core/jyotisha.py`, `actions/jyotisha.py`)
- **Vedic Sidereal Calculations (Lahiri / Chitrapaksha Ayanamsha):** High-precision planetary longitudes, Lagna, and Bhavas computed using Swiss Ephemeris (`pyswisseph`).
- **All 16 Shodashavarga Divisional Charts:** Full computation and interpretation of D1 (Rashi), D2 (Hora), D3 (Drekkana), D4 (Chaturthamsa), D7 (Saptamsha), D9 (Navamsha), D10 (Dashamsha), D12, D16, D20, D24, D27, D30, D40, D45, and D60 (Shashtiamsha).
- **Planetary Strengths & Karakas:** Six-fold **Shadbala** (Sthana, Dig, Kala, Cheshta, Naisargika, Drik) in Virupas/Rupas and Jaimini **Chara Karakas** (Atmakaraka..Darakaraka).
- **Vimsottari Dasha Engine:** Computes birth dasha balance, the complete 120-year cycle of Mahadashas and Antardashas, and active transit periods.

### 8. Mobile Calling, Phone Ringing & AgentRing VoIP (`core/phone_ring.py`, `actions/phone_ring.py`)
- **AgentRing VoIP Integration:** Lets AMATYA call your mobile phone over self-hosted VoIP when tasks complete or critical input is needed, with real-time AI voice bridging and zero carrier/Twilio fees.
- **Cross-Platform Fallbacks:** Direct local Wi-Fi / LAN ringing via KDE Connect, ADB audio boost, and Ntfy.sh HTTP push.

### 9. Futuristic Command-Centre HUD & 4 Visualisation Modes (`ui.py`, `gui/hud.py`, `core/orb_hud.py`, `gui/plugin_hud.py`, `dashboard/server.py`)
- **Four Selectable Centrepiece Visualisation Modes:**
  1. **⚙️ Classic Mark-LVI Flat Reactor Core:** The original Mark-LVI reactor visualization featuring multi-layer sweeping arcs, 72-point graduations, an atmosphere glow body, and an audio amplitude-reactive frequency spike ring.
  2. **◉ 3-D Gyroscope Reactor Core:** Foreshortened 3D holographic core with dual gyroscope rings turning across different axes and equatorial orbital tracers.
  3. **🌐 Wireframe Holographic Orb:** 3D holographic wireframe icosahedron with Loop subdivision, rotating orbital rings, reactive particle cloud, and dynamic audio-reactive amplitude deformation.
  4. **🧑 Animated Face Avatar:** Expressive software-rendered holographic head with audio-reactive mouth visemes and gaze tracking.
  - Cycle seamlessly between modes via voice command (`"switch hud"`, `"orb"`, `"wireframe"`, `"classic reactor"`, `"3d reactor"`, `"avatar"`) or by tapping the HUD style button.
- **Universal Plugin HUD Host (`gui/plugin_hud.py`):**
  - Thread-safe embedded HUD display engine enabling plugins to render rich declarative native HUD cards, telemetry tables, stat tiles, HTML, or web views directly inside the central HUD canvas (`player.show_hud_view()`).
- **Local Companion Loopback Control Channel (`core/local_control.py`):**
  - Lightweight loopback HTTP micro-service (`127.0.0.1:8765`) enabling external scripts, companion devices, or desktop hotkeys to query live status (`/status`), toggle mute (`/mute`), or trigger voice interrupts (`/interrupt`).
- **Enhanced Typography & Clean Card Outages:**
  - Improved readability with balanced typography across HUD labels, metric bars, and status strips.
  - Structured card-based outage tables and Downdetector incident alerts eliminating dense paragraph text.
- **HUD Command Centre Overlays & Controls:**
  - **`🛡 AUTONOMY`:** Dedicated one-click cycling button in the **CONTROLS** drawer (top-bar sliders icon) across all 5 autonomy levels (`L1: OBSERVE` → `L2: RECOMMEND` → `L3: CONFIRM` → `L4: LOW-RISK` → `L5: FULL AUTO`). Also displayed in real-time in the left **STATUS** column, the bottom **Status Strip**, the web dashboard header pill, and controllable via voice (`"Set autonomy level to 4"` / `"Change autonomy to recommend"`).
  - **`⊞ COMMAND CENTRE`:** Live telemetry overlay displaying security tier, voice auth status, GPU/RAM model router status, connected devices, smart home summary, and active tasks.
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
- **Flightradar24 Commercial Airspace Tracking:** Real-time local airspace scanning via live Flightradar24 radar feeds displaying commercial flight numbers, operating carriers, aircraft types (e.g. `A320`, `B738`), routes (`Origin → Destination`), true barometric altitude (accurately distinguishing airborne cruise vs. 0 ft on-ground / scheduled status), speed, and heading. Includes individual flight tracking by callsign with resilient fallback to OpenSky Network.
- **Orbital Trajectory & Aerospace Tracking:** Real-time telemetry, latitude/longitude/altitude calculations, and flyover pass predictions for the International Space Station (ISS) and space stations.

### 14. JARVIS-Class Tactical Skills & Stark Diagnostics Suite (`core/skills_registry.py`, `actions/skill_runner.py`, `actions/cyber_sentry.py`, `actions/stark_lab.py`, `actions/armor_diagnostics.py`, `actions/satellite_tracker.py`, `skills/`)
- **Universal Agent Skills Ecosystem (`core/skills_registry.py`, `actions/skill_runner.py`):**
  - Universal discovery and progressive-disclosure runtime engine indexing 23 specialized agent skills across 7 domains (`skills/*/SKILL.md`).
  - Includes full native bindings to Anthropic's official skills ecosystem (`docx`, `xlsx`, `pptx`, `pdf`, `frontend-design`, `mcp-builder`, `webapp-testing`, etc.) plus custom Iron Man JARVIS tactical and scientific skills.
  - Spoken/text queries: *"What skills do you have?"*, *"List tactical security skills"*, *"Show info on stark-calculator"*.
- **Stark Tactical Cyber Defense Matrix (`actions/cyber_sentry.py`, `skills/cyber-defense/SKILL.md`):**
  - Comprehensive perimeter inspection (`perimeter_scan`), local/LAN open port auditing (`scan_ports`), native firewall status check (`audit_firewall` across `ufw`/`nftables`/`iptables`/`pfctl`/Windows Firewall), authentication log intrusion scanning (`auth_audit`), and SUID/world-writable file permission auditing (`file_permissions`).
  - Spoken/text commands: *"Run a perimeter scan"*, *"Audit firewall status"*, *"Check auth logs for intrusion attempts"*, *"Scan open ports"*.
- **Stark Laboratory Scientific Computing & Physics Simulation (`actions/stark_lab.py`, `skills/stark-calculator/SKILL.md`):**
  - High-precision symbolic calculus, derivatives, integrals, matrix equations, and algebraic simplification via SymPy (`symbolic_math`).
  - Kinematic 2D projectile trajectory simulation with real-world aerodynamic drag and numerical integration (`trajectory`).
  - Orbital mechanics: orbital velocity, Kepler periods, escape velocities, and altitude profiles (`orbital`).
  - Spoken/text commands: *"Calculate orbital velocity at 400 km"*, *"Solve symbolic integral of x*sin(x)"*, *"Simulate projectile trajectory at 45 degrees with 120 m/s velocity"*.
- **Stark Armor Telemetry & Hardware Health Diagnostics (`actions/armor_diagnostics.py`, `skills/armor-diagnostics/SKILL.md`):**
  - Mark suit & system telemetry (`armor_status`), CPU core thermal mapping and sensor readouts (`thermal_map`), battery health and power supply diagnostics (`battery_health`), and GPU power/VRAM diagnostics (`gpu_telemetry`).
  - Spoken/text commands: *"JARVIS, suit diagnostics"*, *"Check core thermals"*, *"Report battery and power status"*, *"Run armor health status"*.
- **Global Aerospace & Orbital Satellite Tracker (`actions/satellite_tracker.py`, `skills/orbital-mechanics/SKILL.md`):**
  - Real-time satellite positioning and orbital velocity for the International Space Station (ISS), Tiangong Space Station (CSS), Hubble Space Telescope, and Starlink constellations (`track_satellite`).
  - Space station flyover pass predictions (`passes`).
  - NOAA Space Weather Prediction Center solar geomagnetic storm telemetry and solar flux alerts (`space_weather`).
  - Spoken/text commands: *"Where is the space station right now?"*, *"Track Hubble Space Telescope"*, *"Check space weather and solar storms"*.

### 15. Smart Desktop Utilities & Workspace Plugins (`plugins/`)
- **Storage Guardian (`plugins/storage_guardian.py`):** Real-time disk telemetry, mount point capacities, large file discovery, and cleanup suggestions rendered dynamically on the Universal Plugin HUD.
- **Network Intelligence (`plugins/network_intelligence.py`):** Active network interface metrics, gateway latencies, DNS resolution timings, and interface state monitoring.
- **Downloads Folder Organizer (`plugins/downloads_organizer.py`):** Categorizes clutter in user downloads directory into logical bins (documents, images, videos, archives, installers) with preview and safe dry-run modes.
- **Google Calendar & Google Drive Integration (`plugins/google_calendar.py`, `plugins/drive_search.py`):** Calendar schedule queries, event creation, and Google Drive file search with helpful guided authorization flows.

### 16. Enterprise & Autonomous Intelligence Suite — Major Upgrade (`actions/`, `core/`)

> **Major System Upgrade:** Natively integrates the comprehensive suite of autonomous intelligence, cybersecurity, quantitative trading, reverse engineering, and personal automation capabilities contributed by **Aman Kumar ([@iamTechieAman](https://github.com/iamTechieAman))** from Mark-LVII PR #182 and his fork:

- **ChatGPT Code Interpreter & Claude Artifacts Canvas Engine (`actions/code_interpreter.py`):** Subprocess Python code execution with automatic Matplotlib plot interception and saving (`AMATYA_Generated/charts/`), SymPy symbolic mathematics & calculus solver (derivatives, integrals, equations, LaTeX formulas), Claude-style interactive artifact generation (HTML5 webapps, Mermaid architecture diagrams, SVG graphics saved to `AMATYA_Generated/artifacts/`), and automated CSV/Excel exploratory data analysis.
- **Claude-Grade Document Studio Upgrades (`actions/document_studio.py`):** Convert any PDF to editable Word document (`pdf2docx`), convert Word documents to formatted PDFs (`reportlab`), and direct in-place PDF text search-and-replace (`pymupdf`) without breaking page layout.
- **Deep Cyber Defense Scan & System Temp Cleaner (`actions/cyber_security.py`):** Deep system security & hardening audit (SIP, FileVault, Firewall, Gatekeeper, attack surface, open sockets), safe cross-platform temp and cache cleaner (Homebrew, pip, npm, Chrome, /tmp), multi-threaded TCP port scanning, SSL/TLS certificate chain auditing (TLS 1.2+ enforced), HTTP security headers, and zero-knowledge HaveIBeenPwned breach verification.
- **Gemini Multi-Key Auto-Rotation Pool (`core/gemini.py`, `memory/config_manager.py`, `gui/overlays.py`, `main.py`):** Configurable pool of multiple Gemini API keys with automatic failover and rotation upon HTTP 429 rate limit or quota exhaustion, supported via comma-separated entry in the UI setup overlay.
- **Universal Top-Bar Upload & Drag-and-Drop Context Injection (`gui/window.py`):** Top-bar `📎 UPLOAD` button and multi-modal drag-and-drop file and folder handler that parses, previews, and indexes uploaded codebases, documents, and images directly into AMATYA's active conversation context.
- **Native Email & Messaging Automation (`actions/send_message.py`):** Compose and send emails via default mail client (`mailto:`) or webmail Gmail composer, alongside verified WhatsApp, Telegram, Signal, Discord, and Messenger automation.
- **Quantitative AI Trading & Risk Management (`actions/ai_trading.py`):** Real-time asset pricing, technical momentum indicators (14-period RSI, SMA, EMA), Kelly Criterion and fixed-fractional risk position sizing, portfolio tracking, and paper trading simulation.
- **Reverse Engineering & Binary Analysis Suite (`actions/rea_tool.py`):** Shannon entropy analysis for packed or encrypted payloads, ASCII/Unicode string extraction, JWT bearer token decoding and claims analysis, curl-to-python translation, ELF/PE binary header inspection, and Android APK manifest extraction.
- **Voice Biometrics & Neural Speaker Verification (`actions/voice_biometrics.py`, `core/voice_verifier.py`):** Continuous acoustic feature extraction, enrolled voice profile calibration with live microphone RMS verification, and cosine similarity matching to enforce hardware-level owner authentication.
- **Adaptive Identity & Protocol Engine (`actions/adaptive_identity.py`):** Dynamically customizes honorifics (Sir, Boss, Captain, Doctor), formality levels, and interaction tones to match user preference.
- **Autonomous Job Hunter & Career Copilot (`actions/job_hunter.py`, `actions/resume_studio.py`):** ATS resume analysis and scoring, Google XYZ-formula bullet transformation, bespoke cover letter drafting, interview preparation, and multi-company job application package generation (`~/Desktop/AMATYA_Company_Applications/`).
- **Academic Study Copilot & Tutor (`actions/study_copilot.py`):** Feynman-technique concept explanations, interactive active-recall quizzes, step-by-step problem solving, and high-yield study cheat sheets.
- **Multi-Modal Generation Studio (`actions/image_generator.py`, `actions/video_studio.py`, `actions/media_downloader.py`, `actions/music_recognition.py`):** AI artwork synthesis via FLUX, cinematic HUD motion clips (`AMATYA_Generated/videos/`), YouTube/web media downloads (`AMATYA_Generated/downloads/`), and ambient music recognition.
- **Personal Concierge & Self-Learning Butler (`actions/concierge_service.py`, `actions/self_learning.py`):** Multi-day travel itineraries, flight/hotel logistics, dining recommendations, and autonomous skill acquisition that creates persistent user-defined rules and custom actions.

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
- Install the required **[Microsoft Visual C++ Redistributable (2015–2022)](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)** ([Direct download: vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe)) or via winget:
  ```powershell
  winget install Microsoft.VCRedist.2015+.x64
  ```
- Install **Zoxide** for lightning-fast directory navigation via winget:
  ```powershell
  winget install ajeetdsouza.zoxide
  ```
- Ensure microphone permissions are enabled under: `Settings → Privacy & security → Microphone → Let desktop apps access your microphone`.
- 📖 **Detailed Documentation:** For more detailed setup guides, architecture breakdowns, and feature walkthroughs, refer to the **[`docs/`](./docs)** folder (including the [User Guide](./docs/user_guide/) and [Getting Started](./docs/user_guide/GETTING_STARTED.md)).

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

# JARVIS tactical skills, Stark diagnostics & lab tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_jarvis_skills.py

# Universal core acceptance tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_amatya_suite.py

# Feature improvements & Mark-LVII integration tests
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_feature_improvements.py
```

---

## Built Upon Mark-LVII & Contributor Acknowledgements

AMATYA is a fork and evolution of **[Mark-LVII by FatihMakes](https://github.com/FatihMakes/Mark-LVII)**. All credit for the foundational architecture goes to FatihMakes. For upstream Mark-LVII documentation, original setup guides, provider configuration, and project background, see the **[Mark-LVII README](https://github.com/FatihMakes/Mark-LVII/blob/main/readme.md)**.

### Contributors

- **Varun Vivek Pai ([@vvpai9](https://github.com/vvpai9)):** Creator & Lead Architect of AMATYA.
- **FatihMakes ([@FatihMakes](https://github.com/FatihMakes)):** Original creator and lead architect of Mark-LVII.
- **Aman Kumar ([@iamTechieAman](https://github.com/iamTechieAman)):** Major contributor of the Enterprise & Autonomous Intelligence Suite, Perplexity-inspired UI redesign (3D celestial particle orb, 3-mode workspace, context drawer), Godmode Assistant, ChatGPT Code Interpreter & Claude Artifacts Canvas engine, Document Studio converters & solvers, Cyber Security audits, multi-key rotation pool, and unified CREATOR capabilities.
- **AMATYA Community:** Cross-platform Linux (Wayland/X11), Windows, and macOS enhancements, cognitive orchestration, biometric voice authentication, and hardware-aware local AI routing.

---

## License

Personal and non-commercial use only. Based on Mark-LVII by FatihMakes (CC BY-NC 4.0).
