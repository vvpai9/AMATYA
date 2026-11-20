"""
Music Recognition & Audio Identification Action for JARVIS (Shazam / SoundHound Style).
Contributed by Aman Kumar (@iamTechieAman).

Identifies songs playing in the environment from the microphone or from local audio files.
Returns Title, Artist, Album, Genre, Release Date, and Lyrics.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

def _record_sample(seconds: int = 5, sample_rate: int = 44100) -> Optional[str]:
    try:
        import sounddevice as sd
        import numpy as np
        import scipy.io.wavfile as wav

        # Record mono or stereo audio
        audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()

        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        wav.write(temp_path, sample_rate, audio)
        return temp_path
    except Exception as e:
        print(f"[MusicRecognition] Audio recording error: {e}")
        return None


async def _async_recognize(audio_file: str) -> dict:
    from shazamio import Shazam
    shazam = Shazam()
    return await shazam.recognize(audio_file)


def music_recognition(parameters: dict, player=None) -> str:
    """
    Music and song recognition tool.
    parameters:
      audio_path: optional path to audio file (mp3, wav, mp4, etc.)
      duration: duration in seconds to record from mic if no audio_path provided (default: 5)
    """
    audio_path = parameters.get("audio_path") or ""
    duration = int(parameters.get("duration") or 5)
    duration = max(3, min(duration, 10))
    temp_wav = None

    if player and hasattr(player, "write_log"):
        player.write_log("SYS: Listening for music to identify...")

    if not audio_path or not Path(audio_path).is_file():
        temp_wav = _record_sample(seconds=duration)
        if not temp_wav:
            return "Unable to access microphone for music recognition."
        target_file = temp_wav
    else:
        target_file = str(Path(audio_path).expanduser().resolve())

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        out = loop.run_until_complete(_async_recognize(target_file))
        loop.close()

        track = out.get("track")
        if not track:
            if player and hasattr(player, "write_log"):
                player.write_log("SYS: Music recognition: No matching song found.")
            return "I listened carefully, sir, but could not identify any matching song in the database."

        title = track.get("title", "Unknown Title")
        artist = track.get("subtitle", "Unknown Artist")
        genres = track.get("genres", {}).get("primary", "Music")
        sections = track.get("sections", [])
        
        album = "Unknown Album"
        release_year = "Unknown"
        lyrics_lines = []

        for sec in sections:
            if sec.get("type") == "SONG":
                for meta in sec.get("metadata", []):
                    if meta.get("title") == "Album":
                        album = meta.get("text", album)
                    elif meta.get("title") == "Released":
                        release_year = meta.get("text", release_year)
            elif sec.get("type") == "LYRICS":
                lyrics_lines = sec.get("text", [])[:8]

        # Format markdown card for HUD
        card = [
            f"## 🎵 {title}",
            f"**Artist:** {artist}",
            f"**Album:** {album}",
            f"**Genre:** {genres} | **Released:** {release_year}",
            "",
        ]
        if lyrics_lines:
            card.extend(["### Lyrics Snippet:", "```", *lyrics_lines, "```"])

        card_md = "\n".join(card)

        if player and hasattr(player, "show_content"):
            player.show_content(f"Identified: {title}", card_md)

        if player and hasattr(player, "write_log"):
            player.write_log(f"MUSIC: Identified '{title}' by {artist}")

        return f"That song is '{title}' by {artist}, from the album '{album}'."

    except Exception as e:
        return f"Music identification failed: {e}"
    finally:
        if temp_wav and os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass


TOOL = {
    "name": "music_recognition",
    "description": (
        "Shazam-style music and song recognition for JARVIS. "
        "Identifies any song playing in the ambient environment using the microphone, "
        "or from an audio file. Returns track title, artist, album, genre, release year, and lyrics."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "audio_path": {
                "type": "STRING",
                "description": "Optional local file path to audio/video file to identify",
            },
            "duration": {
                "type": "INTEGER",
                "description": "Seconds to record from microphone if identifying live music (default: 5)",
            },
        },
    },
    "handler": music_recognition,
}
