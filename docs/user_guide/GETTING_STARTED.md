# Getting Started with AMATYA (अमात्य)

Welcome to **AMATYA** — an autonomous AI companion, tactical desktop assistant, and command-centre HUD engineered for Linux (KDE Plasma 6 / Wayland / X11), macOS, and Windows.

---

## 1. System Requirements

### Recommended Hardware Profile
- **CPU:** 4+ physical cores (Intel Core i5/i7/i9 or AMD Ryzen 5/7/9).
- **RAM:** 16 GB recommended (minimum 8 GB).
- **GPU:** Optional NVIDIA GPU with CUDA for local acceleration; full cloud model routing supported.
- **Audio:** Microphone and speakers/headphones configured via PipeWire, PulseAudio, ALSA, or OS audio stack.

### Supported Operating Systems
- **Linux:** Ubuntu 22.04+, Fedora 39+, Arch Linux, Debian 12+, KDE Neon 6.
- **macOS:** macOS 13+ (Ventura, Sonoma, Sequoia).
- **Windows:** Windows 10/11 (64-bit) with PowerShell 7+.

---

## 2. Installation & Setup

### Step 2.1: Clone the Repository
```bash
git clone git@github.com:vvpai9/AMATYA.git
cd AMATYA
```

### Step 2.2: Set Up Virtual Environment & Dependencies

#### On Linux:
```bash
# Install system packages (Ubuntu/Debian/KDE Neon)
sudo apt update
sudo apt install -y python3-dev python3-venv git ffmpeg portaudio19-dev libasound2-dev wl-clipboard zoxide

# Create virtual environment
python3 -m venv AMATYA
source AMATYA/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

#### On Fedora / RHEL:
```bash
sudo dnf install -y python3-devel git ffmpeg-free portaudio-devel alsa-lib-devel wl-clipboard zoxide
python3 -m venv AMATYA
source AMATYA/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## 3. Configuration

AMATYA stores user credentials and settings in `config/api_keys.json`.

Copy the provided example template:
```bash
cp config/api_keys.example.json config/api_keys.json
```

Edit `config/api_keys.json` with your preferred AI provider API key:
```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "autonomy_level": "confirm",
  "hud_style": "reactor_3d",
  "voice_enabled": true,
  "clock_format": "24h"
}
```

Supported LLM providers include Google Gemini (`gemini-2.5-flash`, `gemini-2.5-pro`), Anthropic Claude, OpenAI, and local Ollama models.

---

## 4. Launching AMATYA

### Start the GUI HUD & Voice Engine:
```bash
./AMATYA/bin/python main.py
```

### Headless / Web Dashboard Mode:
If you want to run AMATYA as a background companion or access the web interface from another device:
```bash
./AMATYA/bin/python dashboard/server.py
```
Open your browser to:
- **Local Dashboard:** `http://127.0.0.1:8000`
- **Companion Loopback Control Channel:** `http://127.0.0.1:8765/status`

---

## 5. Verification

Run the verification test suite:
```bash
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_feature_improvements.py
PYTHONPATH=. ./AMATYA/bin/pytest tests/test_zoxide_nav.py
```
*(Note: To avoid disturbing local connected screens, do not run TV automation tests while your TV is active).*
