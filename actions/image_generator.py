"""
AI Image Generation Action for JARVIS.
Generates images from natural language descriptions using modern diffusion models (FLUX / SDXL).
Downloads generated images directly to Desktop / Downloads and automatically previews them.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

DESKTOP = Path.home() / "Desktop"
DOWNLOADS = Path.home() / "Downloads"

def generate_image(prompt: str, width: int = 1024, height: int = 1024, filename: Optional[str] = None) -> str:
    """Generate an image using Pollinations AI FLUX engine."""
    clean_prompt = prompt.strip()
    if not clean_prompt:
        return "Please provide a prompt describing the image you want to generate."
    
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true&enhance=true"
    
    ts = int(time.time())
    if filename:
        clean_name = filename if filename.lower().endswith((".jpg", ".png", ".jpeg")) else f"{filename}.jpg"
        dest = DESKTOP / clean_name
    else:
        dest = DESKTOP / f"jarvis_gen_{ts}.jpg"

    dest.parent.mkdir(parents=True, exist_ok=True)
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
        
        # On macOS, open the image in Preview
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", str(dest)])
            except Exception:
                pass

        return f"🎨 Generated image for '{clean_prompt}' saved to `{dest}` and opened in preview."
    except Exception as e:
        return f"Image generation failed: {e}"

def image_generator(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for image_generator action."""
    prompt = parameters.get("prompt", "").strip()
    filename = parameters.get("filename")
    width = int(parameters.get("width", 1024))
    height = int(parameters.get("height", 1024))

    if not prompt:
        return "Please provide a prompt describing what image to generate."

    if player:
        try: player.write_log(f"IMAGE: Generating '{prompt[:40]}...'")
        except Exception: pass

    return generate_image(prompt, width, height, filename)

TOOL = {
    "name": "image_generator",
    "description": (
        "Generates images from text descriptions using AI (FLUX / SDXL). "
        "Creates artwork, logos, concept designs, diagrams, wallpapers, or photo-realistic visuals. "
        "Saves the image directly to Desktop or Downloads and opens it immediately on screen."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "Detailed description of the image to generate",
            },
            "filename": {
                "type": "STRING",
                "description": "Optional custom filename (saved to Desktop by default)",
            },
            "width": {
                "type": "INTEGER",
                "description": "Image width in pixels (default: 1024)",
            },
            "height": {
                "type": "INTEGER",
                "description": "Image height in pixels (default: 1024)",
            }
        },
        "required": ["prompt"],
    },
    "handler": image_generator,
}
