# AMATYA (अमात्य) — Personal AI Operating Companion

**Built upon [FatihMakes's Mark-LVI](https://github.com/FatihMakes/Mark-LVI)** — AMATYA evolves Mark-LVI into a local-first, autonomous personal AI operating companion for **KDE Neon / KDE Plasma 6 Wayland**, combining Wayland-native desktop automation, biometric speaker verification, permission-tiered security, a hardware-aware local AI model router, smart home orchestration, connected device control (Android phone, Redmi Android TV, SSH computers), and **CREATOR** (an autonomous software engineering and multi-format document engine).

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

### 7. Futuristic Command-Centre HUD (`ui.py`, `dashboard/server.py`)
- Holographic rotating globe with real-time audio-reactive lip-sync, plus:
  - **`⊞ COMMAND CENTRE`:** Live telemetry overlay displaying security tier, voice auth status, GPU/RAM model router status, connected devices, smart home summary, and active tasks.
  - **`🛡 AUTONOMY`:** One-click cycling across all 5 autonomy levels (`L0 OBSERVE` → `L4 FULL AUTO`).
  - **`🛑 EMERGENCY STOP`:** Immediately halts all running desktop agents, background tasks, and speech output.

---

## Built Upon Mark-LVI

AMATYA is a fork and evolution of **[Mark-LVI by FatihMakes](https://github.com/FatihMakes/Mark-LVI)**. All credit for the foundational architecture goes to FatihMakes:

| Capability | Status in AMATYA |
|---|---|
| Gemini Live voice conversation & local STT/LLM/TTS | ✅ Preserved + expanded |
| Auto-discovered actions & plugins + `SKILL_METADATA` | ✅ 27 bundled actions verified |
| Verified outcomes (`done`/`unverified`/`failed`) & Undo stack | ✅ Preserved |
| Wayland-native desktop automation (`kwin-mcp` v0.12.0 + AT-SPI2) | ✅ Complete & verified live |
| Biometric speaker verification & 6-tier security policy | ✅ Complete & verified |
| 11-role GPU-aware Local AI Model Router + Hybrid RAG | ✅ Complete & verified |
| AI Privacy Modes (`strict_local`, `hybrid`, `cloud_enabled`) | ✅ Phase 12 verified |
| Persistent Layered Memory (Working, Episodic, Semantic, Procedural) | ✅ Phase 12 verified |
| Adaptive Workflow Engine & Routine Approval Gates | ✅ Phase 12 verified |
| Proactive Intelligence (5 Priority Tiers + Quiet Hours Policy) | ✅ Phase 12 verified |
| CentralOrchestrator & contextual reference resolution | ✅ Complete & verified |
| Smart Home Automation (HA + MQTT + Simulator + Routines) | ✅ Complete & verified |
| Connected Devices (KDE Connect, ADB, Redmi TV, SSH, LAN) | ✅ Complete & verified live |
| CREATOR Coding Agent + Project Profile Manager (`memory/project_profiles.json`) | ✅ Phase 12 verified |
| Command-Centre HUD + Subsystem Self-Diagnostics | ✅ Phase 12 verified |

---

## Quick Start & Verification

```bash
# Run AMATYA
./AMATYA/bin/python main.py

# Run the complete automated test suite (30 unit & acceptance tests across Phase 10, 11, and 12)
./AMATYA/bin/python -m unittest discover -s tests -v
```

---

## License

Personal and non-commercial use only. Based on Mark-LVI by FatihMakes (CC BY-NC 4.0).
