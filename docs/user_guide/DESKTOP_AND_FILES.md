# Desktop Automation & Fast Frecency Navigation

AMATYA streamlines day-to-day desktop tasks with smart directory jumping, file operations, and application launching (`core/zoxide_nav.py`, `actions/desktop_nav.py`, `actions/file_controller.py`).

---

## 1. Frecency-Based Smart Navigation (Zoxide Engine)

AMATYA implements a **frecency** (frequency + recency) ranking engine powered by `zoxide` (with an internal pure-Python fallback):
- Automatically learns the directories you navigate to most frequently and recently.
- Allows you to jump to deeply nested folders using only partial keywords.
- Example: *"Jump to amatya"* resolves to `/home/user/Projects/AMATYA` immediately.

---

## 2. Desktop File Managers & Terminals

AMATYA launches native OS file managers and terminal emulators right where you need them:

### Supported File Managers
- **Linux:** Dolphin, Nautilus, Thunar, PCManFM, or `xdg-open`.
- **Windows:** Windows File Explorer.
- **macOS:** Finder (`open`).

### Supported Terminal Emulators
- **Linux:** Konsole, GNOME Terminal, Kitty, Alacritty, Tilix, xterm.
- **Windows:** Windows Terminal, PowerShell.
- **macOS:** Terminal.app, iTerm2.

### Voice & Tool Commands:
- *"Jump to projects folder"*
- *"Open downloads in file manager"*
- *"Launch a terminal in the current directory"*
- *"List my most frequent directories"*

---

## 3. Safe File Operations

AMATYA provides secure file management operations via `actions/file_controller.py`:
- **Read & Inspect:** View files, inspect source code, parse markdown and configs.
- **Search Files:** Find files by name, extension, or content regex.
- **Write & Edit:** Safe, line-targeted replacements with automated syntax validation.
- **Security Boundaries:** System-level paths (`/etc`, `/proc`, `/sys`, `/root`, `C:\Windows`) are strictly read-only or blocked to prevent unintended system modifications.
