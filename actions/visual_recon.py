"""
Visual Recognition & Smart Lens Action for JARVIS.
Inspects camera frames, images, or screen captures to recognize objects, text, people,
equations, hardware components, and documents.
If an item is unrecognized or requires deeper web information (pricing, manuals, specs),
it automatically performs a live Google / Web search to provide a complete answer.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

from core import gemini
from actions.web_search import web_search
from actions.screen_processor import _capture_camera, _capture_screen

def analyze_visual(prompt: str = "Identify what you see", use_camera: bool = True, image_path: Optional[str] = None) -> str:
    """Analyze visual input from camera or image file and enrich with web search if needed."""
    img_bytes = None
    mime_type = "image/jpeg"

    if image_path:
        p = Path(image_path).expanduser().resolve()
        if p.is_file():
            try:
                img_bytes = p.read_bytes()
                mime_type = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            except Exception as e:
                return f"Could not read image file: {e}"
        else:
            return f"Image file not found: {image_path}"
    elif use_camera:
        try:
            img_bytes, mime_type = _capture_camera()
        except Exception as e:
            # Fallback to screen capture if webcam is unavailable
            try:
                img_bytes, mime_type = _capture_screen()
            except Exception as e2:
                return f"Camera capture failed ({e}) and screen capture fallback failed ({e2})."
    else:
        try:
            img_bytes, mime_type = _capture_screen()
        except Exception as e:
            return f"Screen capture failed: {e}"

    if not img_bytes:
        return "No image data could be captured."

    # Ask model to inspect image
    analysis_prompt = (
        f"You are the visual cortex of JARVIS. The user asks: '{prompt}'.\n"
        "Examine the image carefully. Identify objects, brand names, model numbers, text, or faces.\n"
        "State clearly what is visible. If you identify a specific product, gadget, error code, or unknown item "
        "that would benefit from live web lookup (such as price, specifications, or troubleshooting), "
        "end your response with 'SEARCH_QUERY: <search query>'."
    )

    try:
        from google.genai import types
        part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        contents = [part, analysis_prompt]
        response = gemini.call(contents, tier=gemini.SMART, timeout_ms=30000)
        result_text = response.text if response and hasattr(response, "text") and response.text else ""
    except Exception as e:
        result_text = f"Visual model inspection error: {e}"

    if not result_text:
        result_text = "I saw the image, but could not determine detailed features."

    # Check if a web search fallback/enrichment was requested
    if "SEARCH_QUERY:" in result_text:
        main_part, query_part = result_text.split("SEARCH_QUERY:", 1)
        search_query = query_part.strip().splitlines()[0].strip()
        if search_query:
            try:
                web_info = web_search({"query": search_query})
                return f"{main_part.strip()}\n\n🌐 Additional Web Search Results for '{search_query}':\n{web_info}"
            except Exception:
                pass

    return result_text.strip()

def visual_recon(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for visual_recon."""
    prompt = parameters.get("prompt", "Identify what you see and explain it in detail")
    source = parameters.get("source", "camera").lower().strip()
    image_path = parameters.get("image_path")

    if player:
        try: player.write_log("VISION: Analyzing camera view / visual input...")
        except Exception: pass

    use_camera = (source == "camera")
    return analyze_visual(prompt=prompt, use_camera=use_camera, image_path=image_path)


TOOL = {
    "name": "visual_recon",
    "description": (
        "Visual Recognition & Smart Camera Lens. Inspects what the user holds up to the camera or provides "
        "in an image. Identifies products, objects, text, equations, electronics, and documents. "
        "If an object needs more details (such as live pricing, technical specifications, or documentation), "
        "automatically triggers a Google web search to fetch comprehensive up-to-date data."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "Specific question about what to identify or look for in the camera frame",
            },
            "source": {
                "type": "STRING",
                "description": "camera | screen | file (default: camera)",
            },
            "image_path": {
                "type": "STRING",
                "description": "Optional file path to an image file instead of live camera",
            }
        },
        "required": [],
    },
    "handler": visual_recon,
}
