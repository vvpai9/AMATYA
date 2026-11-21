"""
core/paths.py — Central path management for AMATYA generated assets and runtime locations.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_amatya_generated_dir(ensure_dir: bool = True) -> Path:
    """Return the root path for the AMATYA_Generated folder.

    Defaults:
      - Linux & POSIX: Path.home() / "AMATYA_Generated"
      - Windows: Path.home() / "Desktop" / "AMATYA_Generated"

    Can be customized via the AMATYA_GENERATED_DIR environment variable.
    """
    custom = os.environ.get("AMATYA_GENERATED_DIR")
    if custom:
        root = Path(custom).expanduser().resolve()
    elif sys.platform.startswith("win"):
        root = Path.home() / "Desktop" / "AMATYA_Generated"
    else:
        root = Path.home() / "AMATYA_Generated"

    if ensure_dir:
        root.mkdir(parents=True, exist_ok=True)
    return root


def get_generated_subfolder(name: str) -> Path:
    """Return and create a specific subfolder inside AMATYA_Generated.

    Standard subfolders:
      - 'artifacts': Claude-style HTML5/Mermaid/SVG interactive artifacts
      - 'charts': Matplotlib plots and data visualizations
      - 'downloads': Downloaded media and YouTube audio/video files
      - 'videos': Synthesized cinematic video clips and HUD motion cards
    """
    root = get_amatya_generated_dir()
    sub = root / name
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def ensure_generated_folders() -> dict[str, Path]:
    """Ensure all primary generated folders exist and return their paths."""
    return {
        "root": get_amatya_generated_dir(),
        "artifacts": get_generated_subfolder("artifacts"),
        "charts": get_generated_subfolder("charts"),
        "downloads": get_generated_subfolder("downloads"),
        "videos": get_generated_subfolder("videos"),
    }
