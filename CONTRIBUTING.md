# Contributing to AMATYA

Thank you for your interest in contributing to **AMATYA (अमात्य)**!

AMATYA is an open-source, local-first autonomous desktop AI assistant and reasoning system.

---

## 1. Development Principles

1. **Threading Integrity:**
   - PyQt6 widgets must **only** be created and modified on the Qt main thread (`ui.py`).
   - Actions (`actions/*.py`) and plugins (`plugins/*.py`) run on worker threads and must **never** touch Qt widgets directly. Use thread-safe methods on `player` (`player.write_log`, `player.show_content`, `player.show_quiz`, etc.).

2. **Security Gateway Compliance:**
   - Every new action or plugin must register its permission requirements in `TOOL_PERMISSION_MATRIX` (`core/security.py`).
   - Untrusted inputs must be parsed safely using restricted parsers (such as `safe_sympify` for math).

3. **Portability:**
   - Never hardcode personal paths (such as `/home/username`). Always use dynamic `Path.home()` or XDG standard directory lookups.

4. **Testing:**
   - Run the complete test suite before submitting pull requests:
     ```bash
     PYTHONPATH=. pytest tests/
     ```
   - Ensure all acceptance suites (`test_amatya_suite.py`, `test_phase11_acceptance.py` through `test_phase15_security.py`) pass without failure.

---

## 2. Setting Up Local Environment

```bash
git clone https://github.com/vvpai9/AMATYA.git
cd AMATYA
python3 -m venv AMATYA
source AMATYA/bin/activate
pip install -r requirements.txt
cp config/api_keys.example.json config/api_keys.json
```
Edit `config/api_keys.json` with your Gemini API key and launch:
```bash
python main.py
```

