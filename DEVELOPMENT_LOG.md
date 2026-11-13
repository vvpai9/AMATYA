# AMATYA (अमात्य) — Engineering Audit, Implementation & Verification Log

**Repository:** `~/Projects/Mark-LVI` (evolved from `FatihMakes/Mark-LVII`)  
**Environment:** KDE Neon / KDE Plasma 6.8.x on Wayland, PipeWire 1.6.x, Python 3.12 (`./AMATYA/bin/python`)  
**Hardware:** Intel Core i5-11300H, 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile / Max-Q (4096 MiB VRAM)

---

## 1. Initial Repository Audit Findings

Before modifying any files, a full audit of the repository, git log, and runtime environment was performed:

1. **Preserved Prior Work:**
   - OpenCode's Phase 1–3 files (`core/vision.py`, `core/screen_automation.py`, `core/desktop_agent.py`, `core/kwin_mcp_client.py`, `actions/kwin_desktop.py`, `actions/desktop_agent.py`, `core/model_router.py`) were inspected and preserved.
   - User memory (`memory/long_term.json`), credentials (`config/api_keys.json`), and upstream attribution (`FatihMakes/Mark-LVII`) were preserved intact.
2. **Identified Bugs & Gaps Fixed During Implementation:**
   - **`kwin-mcp` v0.12.0 Schema Mismatches:** `core/kwin_mcp_client.py` and `actions/kwin_desktop.py` were passing outdated parameter names (`button="left"` instead of `action="click", button="left"`, `x1/y1/x2/y2` instead of `from_x/from_y/to_x/to_y`, `dy/dx` instead of `vertical/horizontal`, `clipboard_read`/`clipboard_write` instead of `wayland_clipboard` with `action="get"/"set"`). Furthermore, `kwin-mcp` defaulted to launching an isolated `dbus-run-session`, preventing it from seeing the user's real KDE Plasma windows.
   - **Capture Modes:** `core/vision.py` only supported full-desktop capture; per-monitor (`eDP-1`, `HDMI-A-1`), active-window, and rectangular region capture modes were missing.
   - **Legacy X11 Assumptions:** `actions/computer_control.py`, `actions/computer_settings.py`, `actions/code_helper.py`, and `actions/reminder.py` relied on `pyperclip`, `pyautogui`, or Windows PowerShell toasts without Wayland-native fallbacks (`wl-copy`/`wl-paste`, `kwin-mcp`, `notify-send`).
   - **GPU Detection in `core/model_router.py`:** Only checked `torch.cuda`, missing `nvidia-smi` detection when PyTorch CUDA was not loaded, so the NVIDIA GTX 1650 Mobile (4 GB VRAM) was reported as `0 GB VRAM`.
   - **Memory Search Underscore Splitting (`memory/memory_manager.py`):** `search_memory()` split query tokens with `r"[^\w]+"` (which keeps underscores intact) while `_pretty(key)` replaced underscores with spaces, causing snake_case key searches to miss.

---

## 2. Milestones Implemented & Verified

### Milestone 1 — Wayland-Native Desktop Automation (Verified Live on KDE Plasma 6)
- Fixed all `kwin-mcp` v0.12.0 tool schemas in [`core/kwin_mcp_client.py`](./core/kwin_mcp_client.py) and [`actions/kwin_desktop.py`](./actions/kwin_desktop.py) and enabled live KDE session attachment (`isolate_dbus=False`).
- Added `capture_monitor()`, `capture_active_window()`, and `capture_region()` to [`core/vision.py`](./core/vision.py) and `kscreen-doctor -j` JSON parsing to [`core/screen_automation.py`](./core/screen_automation.py).
- Enhanced [`core/desktop_agent.py`](./core/desktop_agent.py) with an accessibility-first (`find_ui_elements` + `read_screen_text`) `Observe → Plan → Act → Verify` loop, 5 autonomy levels, task cancellation, and execution history.
- **Live Verification:** Captured real Wayland desktop screenshots (`3286x1080`), single-monitor (`eDP-1` `1920x1080`), active window, and custom regions; listed 6 live KDE Plasma windows (`Antigravity`, `Gmail`, `Google Chrome`, `YouTube`, `WhatsApp`); queried live AT-SPI2 UI elements (`50 elements found`).

### Milestone 2 — Voice Intelligence, Speaker Verification & Permission Security
- Added configurable wake-word & voice preferences (`wake_word_model`, `wake_word_phrase`, `wake_word_threshold`, `voice_name`, `speech_speed`, `voice_style`, `verbosity`, `barge_in_enabled`) to [`memory/config_manager.py`](./memory/config_manager.py) and [`core/wake_word.py`](./core/wake_word.py).
- Built [`core/voice_auth.py`](./core/voice_auth.py) and [`actions/voice_auth.py`](./actions/voice_auth.py) with 64-D acoustic speaker embeddings, multi-sample enrollment, impostor rejection (`0.9831` legitimate vs. `0.4913` impostor), replay-attack cache detection (`is_replay=True`), spectral playback heuristics, and challenge-response verification.
- Built [`core/security.py`](./core/security.py) enforcing 6 Permission Tiers (`TIER_0_CONVERSATION` to `TIER_5_CRITICAL_SECURITY`), 5 Autonomy Levels, PBKDF2-HMAC-SHA256 PIN verification, secret redaction, and structured audit logging (`memory/audit.log`).

### Milestone 3 — Central Intelligence, Local AI Model Router & Hybrid RAG
- Upgraded [`core/model_router.py`](./core/model_router.py) and [`actions/model_router.py`](./actions/model_router.py) with `nvidia-smi` GPU detection (detecting `NVIDIA GeForce GTX 1650 with Max-Q Design`, `4.0 GB VRAM`) and 11 specialized model roles.
- Built [`core/rag.py`](./core/rag.py) and [`actions/knowledge_base.py`](./actions/knowledge_base.py) for local hybrid semantic + lexical BM25 document indexing and retrieval.
- Built [`core/orchestrator.py`](./core/orchestrator.py) and [`actions/orchestrator.py`](./actions/orchestrator.py) and hooked `CentralOrchestrator` into [`main.py`](./main.py) `_execute_tool` for contextual pronoun/reference resolution and emergency-stop coordination.

### Milestone 4 — Smart Home Automation
- Built [`core/home_automation.py`](./core/home_automation.py), [`actions/home_automation.py`](./actions/home_automation.py), [`config/home_devices.json`](./config/home_devices.json), and [`config/home_routines.json`](./config/home_routines.json) supporting Home Assistant REST/WS, MQTT, post-command state verification, camera privacy gate, routines (`morning`, `evening`, `leaving_home`, `returning_home`, `sleep`), and a clearly labeled Simulated Home Environment.

### Milestone 5 — Connected Devices & Network Control (Verified Live)
- Built [`core/device_manager.py`](./core/device_manager.py), [`actions/device_control.py`](./actions/device_control.py), and [`config/connected_devices.json`](./config/connected_devices.json) supporting live KDE Connect discovery (detected the user's primary Android phone via `kdeconnect-cli` plus 12 LAN neighbors via `ip neigh`), Android file transfer & ring alert, Redmi Android TV ADB control, and remote computer SSH/SCP execution.

### Milestone 6 — CREATOR Software Engineering & Document Engine
- Built [`core/creator.py`](./core/creator.py), [`core/doc_generator.py`](./core/doc_generator.py), and [`actions/creator.py`](./actions/creator.py) supporting repository architecture inspection, symbol search, safe file edits with AST syntax validation and backup rollback, Command Risk Classification, and local generation/inspection across **PDF, DOCX, XLSX, PPTX, CSV, Markdown, and ZIP**.

### Milestone 7 — Skills Metadata, Command-Centre HUD & Automated Test Suite
- Added `SKILL_METADATA` schema validation to [`core/action_loader.py`](./core/action_loader.py) and [`core/plugin_loader.py`](./core/plugin_loader.py) (all 26 bundled actions load cleanly with 0 rejections).
- Added `/api/command-centre`, `/api/emergency-stop`, and `/api/autonomy` to [`dashboard/server.py`](./dashboard/server.py) and added `⊞ COMMAND CENTRE`, `🛡 AUTONOMY`, and `🛑 EMERGENCY STOP` controls to [`ui.py`](./ui.py).
- Created [`tests/test_amatya_suite.py`](./tests/test_amatya_suite.py) (`Ran 8 tests in 4.5s — OK`).

---

## 3. Post-Implementation Diagnostics: Resolving "Invalid API Key" Loop

### Root Cause
When testing valid newly-created Gemini API keys (including modern Google AI Studio keys starting with `AQ.`), entering the key repeatedly triggered:
`ERR: API key invalid — please re-enter your key.`
Investigation revealed a dual root cause:
1. **Tool Schema Validation Rejection in [`actions/creator.py`](./actions/creator.py):**
   The OpenAPI schema for the `creator` tool declared nested arrays without items (`"rows": {"type": "ARRAY", "items": {"type": "ARRAY"}}`) and bare objects. Gemini's Live Bidi WebSocket rejected this during session setup:
   `APIError('1007 None. * BidiGenerateContentRequest.setup.tools[0].function_declarations[12].parameters.properties[rows].items.items: missing field')`.
2. **WebSocket 1007 Close Code Misclassification in [`main.py`](./main.py):**
   RFC 6455 code 1007 is returned by Gemini Live whenever any setup or payload error occurs. `main.py` contained `if "API key not valid" in err_str or "1007" in err_str:`, which caused ANY schema or setup error to be falsely reported as an invalid API key, opening the setup overlay in an infinite loop.

### Fix
1. Updated `actions/creator.py` schema with full nested `items` definitions (`"rows": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "STRING"}}}`) and concrete `properties` for `edits` and `sections`.
2. Updated `main.py` to only classify actual authentication failures (`"api key not valid"`, `"api_key_invalid"`, `"invalid api key"`, `"pass a valid api key"`) as API key errors, while treating non-auth 1007 codes as setup/payload rejection errors with backoff.
3. Updated `ui.py` `_on_setup_done()` to preserve existing configuration in `config/api_keys.json` when saving new keys.
4. Updated `core/security.py` credential regex to match modern `AQ.` format Gemini API keys for automatic secret redaction.
5. **Live Verification:** Verified with `client.aio.live.connect(model=live_model, config=cfg)` — successfully connected to live Gemini session (`<class 'google.genai.live.AsyncSession'>`).

