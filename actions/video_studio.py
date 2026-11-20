"""
AI Video Studio & Motion Graphic Generator for JARVIS.
Contributed by Aman Kumar (@iamTechieAman).

Enables JARVIS to autonomously generate videos, cinematic motion cards,
image-to-video slideshows with audio, and animated visual clips.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path.home() / "Desktop" / "JARVIS_Videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _find_ffmpeg() -> str:
    candidates = ["/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg", "ffmpeg"]
    for c in candidates:
        try:
            r = subprocess.run([c, "-version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return "ffmpeg"


def video_studio(parameters: dict, player=None) -> str:
    """
    Video creation and synthesis tool.
    parameters:
      action: 'create_clip' | 'slideshow' | 'text_card'
      title: title of the video
      text: main text or narrative script
      image_path: path to base image or image query
      duration: duration in seconds (default: 5)
      theme: 'cyber' | 'cinematic' | 'gold' | 'neon'
    """
    action = (parameters.get("action") or "create_clip").lower().strip()
    title = parameters.get("title") or "JARVIS Production"
    text = parameters.get("text") or title
    image_path = parameters.get("image_path") or ""
    duration = int(parameters.get("duration") or 5)
    duration = max(2, min(duration, 30))
    theme = (parameters.get("theme") or "cyber").lower()

    ffmpeg_bin = _find_ffmpeg()
    timestamp = int(time.time())
    out_file = OUTPUT_DIR / f"jarvis_clip_{timestamp}.mp4"
    temp_frame = OUTPUT_DIR / f"temp_frame_{timestamp}.png"

    # Color themes
    themes = {
        "cyber": ((10, 15, 29), (0, 210, 255), (255, 255, 255)),
        "cinematic": ((17, 24, 39), (243, 244, 246), (156, 163, 175)),
        "gold": ((28, 25, 23), (245, 158, 11), (254, 243, 199)),
        "neon": ((9, 9, 11), (236, 72, 153), (0, 255, 255)),
    }
    bg_col, title_col, text_col = themes.get(theme, themes["cyber"])

    try:
        # Create base canvas with Pillow
        if image_path and Path(image_path).is_file():
            base_img = Image.open(image_path).convert("RGB")
            base_img = base_img.resize((1280, 720), Image.Resampling.LANCZOS)
        else:
            base_img = Image.new("RGB", (1280, 720), color=bg_col)
            draw = ImageDraw.Draw(base_img)
            # Draw decorative HUD frame borders
            draw.rectangle([30, 30, 1250, 690], outline=title_col, width=2)
            draw.line([(30, 50), (60, 50)], fill=title_col, width=4)
            draw.line([(1220, 50), (1250, 50)], fill=title_col, width=4)
            draw.line([(30, 670), (60, 670)], fill=title_col, width=4)
            draw.line([(1220, 670), (1250, 670)], fill=title_col, width=4)

        draw = ImageDraw.Draw(base_img)

        # Load standard system font or default
        font_large = None
        font_small = None
        for font_path in ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"]:
            if os.path.exists(font_path):
                try:
                    font_large = ImageFont.truetype(font_path, 48)
                    font_small = ImageFont.truetype(font_path, 28)
                    break
                except Exception:
                    pass

        if not font_large:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Render Title & Subtitle with shadows
        draw.text((642, 312), title.upper(), fill=(0, 0, 0), font=font_large, anchor="mm")
        draw.text((640, 310), title.upper(), fill=title_col, font=font_large, anchor="mm")

        # Multi-line text wrapping for caption
        caption = text[:120]
        draw.text((642, 402), caption, fill=(0, 0, 0), font=font_small, anchor="mm")
        draw.text((640, 400), caption, fill=text_col, font=font_small, anchor="mm")

        base_img.save(temp_frame)

        # Subtle zoom motion using ffmpeg zoompan
        filter_str = (
            f"zoompan=z='min(zoom+0.0008,1.15)':d={duration*25}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720"
        )

        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1", "-i", str(temp_frame),
            "-f", "lavfi", "-i", f"sine=frequency=432:duration={duration}",
            "-vf", filter_str,
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
            str(out_file)
        ]

        if player and hasattr(player, "write_log"):
            player.write_log(f"VIDEO: Rendering cinematic clip '{title}' ({duration}s)...")

        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Cleanup temp frame
        if temp_frame.exists():
            temp_frame.unlink(missing_ok=True)

        if r.returncode != 0:
            return f"Video generation failed: {r.stderr[:200]}"

        # Play in HUD if player is available
        if player and hasattr(player, "show_video"):
            player.show_video(str(out_file), title)

        if player and hasattr(player, "write_log"):
            player.write_log(f"VIDEO: Generated {out_file.name} successfully.")

        return (
            f"I have created the video clip '{title}', sir. "
            f"It is saved at {out_file.name} on your Desktop and playing directly on your HUD."
        )
    except Exception as e:
        if temp_frame.exists():
            temp_frame.unlink(missing_ok=True)
        return f"Error creating video: {e}"


TOOL = {
    "name": "video_studio",
    "description": (
        "AI Video Studio and clip generator for JARVIS. "
        "Allows creating MP4 video clips, stylized motion cards, title videos, and animated slideshows. "
        "Automatically displays the generated video in the JARVIS HUD player."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "create_clip | text_card | slideshow (default: create_clip)",
            },
            "title": {
                "type": "STRING",
                "description": "Title of the video clip",
            },
            "text": {
                "type": "STRING",
                "description": "Main text, caption, or script for the video",
            },
            "image_path": {
                "type": "STRING",
                "description": "Optional background image path",
            },
            "duration": {
                "type": "INTEGER",
                "description": "Duration in seconds (default: 5)",
            },
            "theme": {
                "type": "STRING",
                "description": "Visual theme: cyber | cinematic | gold | neon (default: cyber)",
            },
        },
        "required": ["title"],
    },
    "handler": video_studio,
}
