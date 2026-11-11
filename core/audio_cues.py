"""
AMATYA Audio Cues & JARVIS Acoustic Signatures (core/audio_cues.py)
===================================================================
Provides high-fidelity synthesized acoustic signatures for AMATYA:
  - Initialisation boot chime (arc-reactor harmonic sweep & crystal chord)
  - Wake chime
  - Task completion chime
  - Warning/confirmation chime

All audio cues are synthesized programmatically with pure sinusoidal harmonics,
anti-click cosine ramps, and exponential decays. No external asset files are required.
Playback routes non-blockingly via sounddevice and PipeWire.
"""
from __future__ import annotations

import io
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from typing import Any

import numpy as np

SAMPLE_RATE = 48000


def _synthesize_boot_chime(sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Synthesize the signature JARVIS initialisation sound:
    Resonant sub-bass sweep + dual crystal chords (C5, E5, G5, C6) + high harmonic shimmer.
    """
    duration = 1.35
    total_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, total_samples, False)

    # 1. Warm sub-bass harmonic sweep (110 Hz -> 220 Hz)
    f0_sweep = 110.0 + 110.0 * (1.0 - np.exp(-t * 7.0))
    sub_bass = 0.28 * np.sin(2.0 * np.pi * f0_sweep * t) * np.exp(-t * 3.2)

    # 2. Resonant major crystal chord with progressive exponential decay
    c5 = 0.35 * np.sin(2.0 * np.pi * 523.25 * t) * np.exp(-t * 2.6)
    e5 = 0.30 * np.sin(2.0 * np.pi * 659.25 * t) * np.exp(-t * 2.3)
    g5 = 0.25 * np.sin(2.0 * np.pi * 783.99 * t) * np.exp(-t * 2.0)
    c6 = 0.20 * np.sin(2.0 * np.pi * 1046.50 * t) * np.exp(-t * 1.8)

    # 3. Metallic/crystal overtones for futuristic acoustic sheen
    shimmer1 = 0.08 * np.sin(2.0 * np.pi * 2093.0 * t) * np.exp(-t * 3.8)
    shimmer2 = 0.05 * np.sin(2.0 * np.pi * 3135.96 * t) * np.exp(-t * 4.5)

    waveform = sub_bass + c5 + e5 + g5 + c6 + shimmer1 + shimmer2

    # 4. Anti-click cosine fade-in and smooth exponential fade-out
    fade_in_len = int(sample_rate * 0.015)
    waveform[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
    fade_out_len = int(sample_rate * 0.05)
    waveform[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len)

    waveform = np.clip(waveform, -1.0, 1.0)
    return (waveform * 32767).astype(np.int16)


def _synthesize_wake_chime(sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Synthesize a light, rapid dual-tone chime when awakened by wake word."""
    duration = 0.35
    total_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, total_samples, False)

    t1 = 0.25 * np.sin(2.0 * np.pi * 880.0 * t) * np.exp(-t * 12.0)
    t2 = 0.28 * np.sin(2.0 * np.pi * 1318.5 * t) * np.exp(-t * 10.0)
    waveform = t1 + t2
    fade = int(sample_rate * 0.01)
    waveform[:fade] *= np.linspace(0.0, 1.0, fade)
    waveform[-fade:] *= np.linspace(1.0, 0.0, fade)
    return (np.clip(waveform, -1.0, 1.0) * 32767).astype(np.int16)


def _synthesize_task_complete_chime(sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Synthesize a subtle ascending tri-tone confirming a completed task."""
    duration = 0.65
    total_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, total_samples, False)

    step1 = np.where(t < 0.15, 0.25 * np.sin(2.0 * np.pi * 587.33 * t) * np.exp(-t * 6.0), 0.0)
    t_mid = np.maximum(0.0, t - 0.15)
    step2 = np.where((t >= 0.15) & (t < 0.35), 0.28 * np.sin(2.0 * np.pi * 783.99 * t_mid) * np.exp(-t_mid * 6.0), 0.0)
    t_end = np.maximum(0.0, t - 0.35)
    step3 = np.where(t >= 0.35, 0.32 * np.sin(2.0 * np.pi * 1174.66 * t_end) * np.exp(-t_end * 4.0), 0.0)

    waveform = step1 + step2 + step3
    fade = int(sample_rate * 0.01)
    waveform[:fade] *= np.linspace(0.0, 1.0, fade)
    waveform[-fade:] *= np.linspace(1.0, 0.0, fade)
    return (np.clip(waveform, -1.0, 1.0) * 32767).astype(np.int16)


def play_audio_data(pcm_data: np.ndarray, sample_rate: int = SAMPLE_RATE, block: bool = False) -> None:
    """Play raw int16 PCM audio non-blockingly via sounddevice and PipeWire."""
    if os.environ.get("AMATYA_TEST_MODE") == "1":
        return

    def _play_fallback_cli(wav_bytes: bytes) -> bool:
        """Fallback to pw-play, paplay, or aplay if PortAudio / sounddevice fails."""
        for player_cmd in ("pw-play", "paplay", "aplay"):
            try:
                subprocess.run([player_cmd, "-"], input=wav_bytes, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
        return False

    def _worker():
        try:
            import sounddevice as sd
            import core.audio_devices as ad
            from memory.config_manager import get_output_device

            dev_name = get_output_device()
            dev_idx = ad.resolve(dev_name, "output")
            sd.play(pcm_data, samplerate=sample_rate, device=dev_idx, blocking=True)
            return
        except Exception:
            pass  # Fall through to system audio CLI player

        try:
            with io.BytesIO() as bio:
                with wave.open(bio, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(pcm_data.tobytes())
                _play_fallback_cli(bio.getvalue())
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True, name="amatya-audio-cue")
    t.start()
    if block:
        t.join()


def play_initialisation_sound(block: bool = False) -> None:
    """Play the signature AMATYA / JARVIS initialisation boot chime."""
    data = _synthesize_boot_chime(SAMPLE_RATE)
    play_audio_data(data, SAMPLE_RATE, block=block)


def play_wake_chime() -> None:
    """Play the wake acknowledgement cue."""
    data = _synthesize_wake_chime(SAMPLE_RATE)
    play_audio_data(data, SAMPLE_RATE, block=False)


def play_task_complete_chime() -> None:
    """Play the task completion chime."""
    data = _synthesize_task_complete_chime(SAMPLE_RATE)
    play_audio_data(data, SAMPLE_RATE, block=False)


def get_startup_speech(user_name: str = "sir") -> str:
    """Generate the crisp, dignified JARVIS startup speech based on local time."""
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        salutation = "Good morning"
    elif hour < 17:
        salutation = "Good afternoon"
    else:
        salutation = "Good evening"

    # Dignified and authoritative JARVIS tone
    return (
        f"{salutation}, {user_name}. AMATYA online. "
        "All core subsystems nominal. Desktop control and connected devices synchronized. "
        "Standing by for instructions."
    )
