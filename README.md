# AMATYA (अमात्य) — Personal AI Operating Companion

**Built upon [FatihMakes's Mark-LVII](https://github.com/FatihMakes/Mark-LVII)** — AMATYA evolves Mark-LVII into a local-first, autonomous personal AI operating companion for **KDE Neon / KDE Plasma 6 Wayland**, combining Wayland-native desktop automation, biometric speaker verification, permission-tiered security, a hardware-aware local AI model router, smart home orchestration, connected device control (Android phone, Redmi Android TV, SSH computers), and **CREATOR** (an autonomous software engineering and multi-format document engine).

---

## Core Capabilities

### 1. Wayland-Native Desktop Automation (`kwin-mcp` v0.12.0 + AT-SPI2)
AMATYA controls KDE Plasma 6 Wayland natively through `kwin-mcp` (KWin EIS libei input + KWin ScreenShot2 + AT-SPI2 accessibility tree) with Wayland-native fallbacks (`wl-clipboard`, `spectacle`, `grim`, `notify-send`).

| Capability | Implementation |
|---|---|
| **Capture Modes** | Full desktop, individual monitor (`eDP-1`, `HDMI-A-1`, etc.), active window, rectangular region |
| **Screen Understanding** | AT-SPI2 accessibility tree (`find_ui_elements`), Tesseract OCR (`read_screen_text`), VLM analysis, pixel diffing |
| **Wayland Input** | Keyboard typing, key combinations, mouse move/click/double-click/right-click/drag/scroll via libei |
| **Autonomous Desktop Agent** | Accessibility-first `Observe → Plan → Act → Verify` loop (`core/desktop_agent.py`) with 5 autonomy levels, cancellation, and history |

### 2. Voice-First Interaction, Speaker Verification & Security
- **Configurable Wake Word & Voice (`core/wake_word.py`, `memory/config_manager.py`):** Preserves `hey_jarvis` as the default `openwakeword` model ID while keeping **AMATYA** as the user-facing identity; supports custom ONNX/TFLite models, speech speed, voice style, verbosity (`concise`/`normal`/`detailed`), and barge-in interruption.
- **Speaker Verification & Anti-Spoofing (`core/voice_auth.py`, `actions/voice_auth.py`):**
  - Multi-sample enrollment and 64-D acoustic speaker embeddings (MFCCs, Delta-MFCCs, autocorrelation F0 pitch stats, zero-meaned formant band ratios, spectral centroid/rolloff).
  - Replay-attack detection cache, playback spectral heuristics, and randomized challenge-response phrase generation.
- **6 Permission Tiers & 5 Autonomy Levels (`core/security.py`):**
  - Tiers `0` (`CONVERSATION`) through `5` (`CRITICAL_SECURITY`) with PBKDF2-HMAC-SHA256 PIN verification, automatic secret redaction, and structured JSONL audit logs (`memory/audit.log`).

### 3. Central Intelligence, Local AI Router & Hybrid RAG
- **11-Role Hardware-Aware Model Router (`core/model_router.py`, `actions/model_router.py`):**
  - Detects CPU, RAM (16 GB), and GPU VRAM via `nvidia-smi` (GTX 1650 Mobile ~4 GB VRAM) and routes across `conversation`, `reasoning`, `coding`, `desktop_understanding`, `ocr`, `stt`, `tts`, `wake_word`, `speaker_verification`, `embeddings`, and `summarization`.
- **Contextual Reference Resolution (`core/orchestrator.py`, `actions/orchestrator.py`):**
  - Resolves contextual references such as *"Open that"*, *"Close the previous window"*, *"Continue what you were doing"*, *"Check the same project again"*, and *"Send that file to my phone"*.
- **Hybrid RAG Knowledge Base (`core/rag.py`, `actions/knowledge_base.py`):**
  - Indexes project files, notes, and directories into a local hybrid semantic + lexical BM25 knowledge store.

### 4. Smart Home Automation (`core/home_automation.py`, `actions/home_automation.py`)
- Supports **Home Assistant REST/WebSocket API**, **MQTT**, and a clearly labeled **Simulated Home Environment** (`[SIMULATED HOME ENVIRONMENT]`) when no live broker is reachable.
- Post-command state verification, camera privacy gate (`TIER_3_SENSITIVE`), and multi-step routines (`morning`, `evening`, `leaving_home`, `returning_home`, `sleep`) with confirmation gates for locks, alarms, and cameras.

### 5. Connected Devices & Network Ecosystem (`core/device_manager.py`, `actions/device_control.py`)
- **Discovery:** Live discovery via **KDE Connect** (`kdeconnect-cli`), **ADB**, **LAN ARP (`ip neigh`)**, **mDNS**, and **Tailscale**.
- **Android Phone:** File sharing (`--share` / `adb push`), Find-My-Phone ring alert (`--ring`), clipboard sync, battery check, and app launch.
- **Redmi Android TV:** Power toggle, volume/mute, D-Pad navigation, app launch (YouTube, Netflix, Prime Video, Hotstar, VLC, Kodi), and media URL casting via ADB over LAN.
- **Remote Computers:** Non-interactive SSH command execution, system status check, and SCP file transfer.

### 6. CREATOR — Software Engineering & Document Engine (`core/creator.py`, `core/doc_generator.py`)
- **Software Engineering:** Repository architecture summary, symbol search, safe file editing with automatic Python AST syntax validation and backup rollback, git status/diff, and test execution with **Command Risk Classification** (`SAFE_READ`, `SAFE_BUILD`, `MODIFY`, `DESTRUCTIVE`).
- **Multi-Format Documents:** Generate and inspect **PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP** files locally.
- **Dynamic Content & Summary Bridging:** Auto-bridges summarized text directly from generated files (`.txt`, `.md`, `.pdf`, `.docx`) into multi-slide presentations without falling back to stale or generic placeholder content.
- **Strict File Deletion Protection:** Deletion of any file or directory requires mandatory confirmation and supports spoken voice authorization (`confirm.voice_authorize`).

### 7. Vedic Jyotisha & Astrological Intelligence (`core/jyotisha.py`, `actions/jyotisha.py`)
- **Vedic Sidereal Calculations (Lahiri / Chitrapaksha Ayanamsha):** High-precision planetary longitudes, Lagna, and Bhavas computed using Swiss Ephemeris (`pyswisseph`).
- **Classical Indian Nomenclature:** Uses classical terms throughout (Mesha..Meena for Rashis; Surya, Chandra, Mangala, Budha, Guru, Shukra, Shani, Rahu, Ketu for Grahas).
- **All 16 Shodashavarga Divisional Charts:** Full computation and interpretation of D1 (Rashi), D2 (Hora), D3 (Drekkana), D4 (Chaturthamsa), D7 (Saptamsha), D9 (Navamsha for marriage/dharma), D10 (Dashamsha for career), D12 (Dwadashamsha), D16, D20, D24, D27, D30, D40, D45, and D60 (Shashtiamsha).
- **Planetary Strengths & Karakas:** Six-fold **Shadbala** (Sthana, Dig, Kala, Cheshta, Naisargika, Drik) in Virupas and Rupas, and Jaimini **Chara Karakas** (Atmakaraka, Amatyakaraka, Bhratrikaraka, Matrikaraka, Putrakaraka, Gnatikaraka, Darakaraka).
- **Upagraha Maandi & Outer Planets:** Precise calculation of Maandi and Gulika based on diurnal/nocturnal Saturnian Khandas, plus modern outer planets Harshal (Uranus), Varun (Neptune), and Yama (Pluto).
- **Vimsottari Dasha Engine:** Computes birth dasha balance, the complete 120-year cycle of Mahadashas and Antardashas, and identifies the currently active period and transition dates.
- **Synthesized Readings & Upayas:** Generates structured analyses covering personality, career (D10), marriage (D9), wealth (D2), Maandi harmonization, and classical Vedic remedies.
- **Western Astrology Mode:** Seamlessly switches to Western Tropical astrology (Sayana coordinates, Placidus houses, Big Three, and major aspects) ONLY when explicitly requested.

### 8. Mobile Calling, Phone Ringing & Cross-Platform Parity (`core/phone_ring.py`, `actions/phone_ring.py`)
- **AgentRing VoIP Integration ([mutonby/agentring](https://github.com/mutonby/agentring)):**
  - Lets AMATYA call your phone over self-hosted VoIP when tasks complete or urgent input is needed, with real-time AI voice bridging and zero carrier/Twilio fees.
  - Supports `--urgent` calling to wake phones from Doze mode and bypass Do Not Disturb, plus interactive messaging (`agentring msg`) and QR pairing (`agentring pair`).
- **Free Open-Source Alternatives:**
  - **KDE Connect:** Direct local Wi-Fi / LAN phone ringing at maximum volume across Linux, Windows, and macOS without cloud dependency.
  - **ADB over Wi-Fi / USB:** Direct Android audio stream boosting and native alarm/ringtone intent execution.
  - **Ntfy.sh (Open-Source HTTP Push):** Zero-dependency pure Python push notifications with priority=urgent and telephone/alarm tags to ring devices even when muted.
- **Windows & macOS Parity:**
  - Native clipboard fallbacks (`pbcopy`/`pbpaste` on macOS; PowerShell `Get-Clipboard`/`Set-Clipboard` on Windows).
  - Native screen capture backends (`screencapture -x` on macOS; `ImageGrab`/`mss` on Windows).
  - Executable path resolution for `kdeconnect-cli` (`.exe` on Windows, `.app` bundle on macOS) and `adb`.

### 9. Futuristic Command-Centre HUD (`ui.py`, `dashboard/server.py`)
- Holographic rotating globe with real-time audio-reactive lip-sync, plus:
  - **`⊞ COMMAND CENTRE`:** Live telemetry overlay displaying security tier, voice auth status, GPU/RAM model router status, connected devices, smart home summary, and active tasks.
  - **`🛡 AUTONOMY`:** One-click cycling across all 5 autonomy levels (`L0 OBSERVE` → `L4 FULL AUTO`).
  - **`🛑 EMERGENCY STOP`:** Immediately halts all running desktop agents, background tasks, and speech output.

---

### 10. Scientific Computation, Simulation & Quantitative Reasoning (Phase 14)
- **Deterministic Mathematics (`core/scientific_computation.py`):**
  - Safe symbolic algebra, analytical calculus, limits, and ordinary differential equations.
  - High-precision numerical root-finding, optimization, and dual-method finite-difference verification.
  - Dimensional analysis with strict unit validation (`UnitQuantity`) and rejection of incompatible quantities.
- **Physical Domain Simulations (`core/simulation_engine.py`):**
  - Transient thermal junction heating with accurate settling times ($4\tau$ seconds).
  - RLC circuit analog response modeling.
  - Two-body Keplerian orbital mechanics with energy conservation audits.
  - True stochastic Monte Carlo uncertainty analysis with seed reproducibility and distribution preview.

### 11. Centralized Security Gateway & Release Engineering (Phase 15)
- **Unified Authorization Gateway (`core/security.py`):**
  - Mandatory pre-execution gateway for all tools, actions, and plugins (`authorize_tool_execution`).
  - Strict fail-closed policy on unclassified tools.
  - Active scanning and blocking of adversarial prompt injections across parameters.
  - Rate-limited PBKDF2-HMAC-SHA256 PIN authentication with exponential backoff and lockouts.
  - Deep recursive audit log redaction.
- **Hardened Remote Dashboard (`dashboard/server.py`):**
  - Default binding to `127.0.0.1` unless LAN mode is explicitly enabled.
  - CSRF Origin/Referer header verification on state-changing endpoints.
  - Bearer token authentication required on telemetry and emergency-stop endpoints.
- **SSRF & Ingestion Defense (`core/ingestion.py`):**
  - Dual IPv4 / IPv6 DNS resolution preventing access to loopback and private networks.
  - Redirect interception re-evaluating each hop against SSRF policies.
  - Cryptographic SHA-256 incremental content hashing.

### 12. Maha-AMATYA (महामात्य) Private Edition
- **Private Plugin Architecture:** Dynamic extension discovery from `$XDG_DATA_HOME/maha-amatya/plugins/` keeps confidential domain modules separate from the public repository.
- **Maha Orbit Lab (`maha_orbit_lab.py`):** Astrodynamics, Keplerian elements, propagation, and Hohmann transfer delta-v.
- **Maha Analog Lab (`maha_analog_lab.py`):** Cadence Spectre log parsing, PVT corner sensitivity matrix, and feedback amplifier loop stability analysis.

---

## Built Upon Mark-LVII

AMATYA is a fork and evolution of **[Mark-LVII by FatihMakes](https://github.com/FatihMakes/Mark-LVII)**. All credit for the foundational architecture goes to FatihMakes. For the upstream Mark-LVII documentation, original setup guides, provider configuration, and project background, see the **[Mark-LVII README](https://github.com/FatihMakes/Mark-LVII/blob/main/readme.md)**.

| Capability | Status in AMATYA |
|---|---|
| Gemini Live voice conversation & local STT/LLM/TTS | ✅ Preserved + expanded |
| Auto-discovered actions & plugins + `SKILL_METADATA` | ✅ 26 bundled actions verified |
| Verified outcomes (`done`/`unverified`/`failed`) & Undo stack | ✅ Preserved |
| Wayland-native desktop automation (`kwin-mcp` v0.12.0 + AT-SPI2) | ✅ Complete & verified live |
| Biometric speaker verification & 6-tier security policy | ✅ Complete & verified |
| 11-role GPU-aware Local AI Model Router + Hybrid RAG | ✅ Complete & verified |
| CentralOrchestrator & contextual reference resolution | ✅ Complete & verified |
| Smart Home Automation (HA + MQTT + Simulator + Routines) | ✅ Complete & verified |
| Connected Devices (KDE Connect, ADB, Redmi TV, SSH, LAN) | ✅ Complete & verified live |
| CREATOR Coding Agent + PDF/DOCX/XLSX/PPTX/CSV/MD/ZIP Engine | ✅ Complete & verified |
| Vedic Jyotisha Engine (Shodashavarga D1..D60, Shadbala, Dashas) | ✅ Complete & verified |
| Phone Ring & AgentRing VoIP (Linux, Windows, macOS) | ✅ Complete & verified |
| Command-Centre HUD + Emergency Stop | ✅ Complete & verified |

---

## Quick Start & Verification

```bash
# Run AMATYA
./AMATYA/bin/python main.py

# Run the full automated test suite (127 tests across Phases 11–15)
PYTHONPATH=. ./AMATYA/bin/pytest tests/
```

---

## License

Personal and non-commercial use only. Based on Mark-LVII by FatihMakes (CC BY-NC 4.0).
