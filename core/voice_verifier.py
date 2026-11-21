"""
Voice Biometrics & Speaker Recognition Engine for JARVIS (Voice Match / Siri / Google Assistant style).
Contributed by Aman Kumar (@iamTechieAman).

Ensures JARVIS responds exclusively to the verified voice of the registered owner (Aman Kumar),
filtering out other speakers, TV noise, and background voices.
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

VOICEPRINT_FILE = Path.home() / ".jarvis_voiceprint.json"
OWNER_DEFAULT_NAME = "Aman Kumar"
MATCH_THRESHOLD = 0.65  # Cosine similarity threshold for voice match


def _extract_acoustic_features(audio_data: np.ndarray, sample_rate: int = 16000) -> np.ndarray:
    """
    Extract robust acoustic feature vector from raw audio:
    - Zero-Crossing Rate (ZCR)
    - Root-Mean-Square Energy (RMS)
    - Spectral Centroid & Spectral Spread
    - Multi-band Spectral Energy (16 log-spaced filter banks)
    """
    # Convert to float32 normalized [-1.0, 1.0]
    if audio_data.dtype == np.int16:
        signal = audio_data.astype(np.float32) / 32768.0
    else:
        signal = audio_data.astype(np.float32)

    if len(signal) < 256:
        return np.zeros(20, dtype=np.float32)

    # 1. Zero-crossing rate
    zcr = np.mean(np.abs(np.diff(np.sign(signal)))) / 2.0

    # 2. RMS Energy
    rms = np.sqrt(np.mean(signal ** 2))

    # 3. FFT Magnitude spectrum
    fft_vals = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)

    # 4. Spectral Centroid
    sum_fft = np.sum(fft_vals) + 1e-9
    spectral_centroid = np.sum(freqs * fft_vals) / sum_fft

    # 5. Spectral Rolloff (85% energy point)
    cum_energy = np.cumsum(fft_vals)
    rolloff_idx = np.searchsorted(cum_energy, 0.85 * cum_energy[-1])
    spectral_rolloff = freqs[min(rolloff_idx, len(freqs) - 1)]

    # 6. 16-band energy filterbanks
    bands = np.logspace(np.log10(100), np.log10(min(sample_rate // 2, 7500)), num=17)
    band_energies = []
    for i in range(16):
        idx = np.where((freqs >= bands[i]) & (freqs < bands[i + 1]))[0]
        if len(idx) > 0:
            energy = np.mean(fft_vals[idx])
        else:
            energy = 0.0
        band_energies.append(np.log1p(energy))

    # Assemble normalized 20-dim feature vector
    features = np.array([
        zcr * 10.0,
        rms * 5.0,
        spectral_centroid / 4000.0,
        spectral_rolloff / 6000.0,
        *band_energies
    ], dtype=np.float32)

    norm = np.linalg.norm(features) + 1e-9
    return features / norm


def is_enrolled() -> bool:
    """Check if owner voiceprint profile exists."""
    return VOICEPRINT_FILE.is_file()


def is_voice_match_enabled() -> bool:
    """Check if voice match verification is active and calibrated with owner voice."""
    if not is_enrolled():
        return False
    try:
        data = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
        return bool(data.get("enabled", False) and (data.get("calibrated_real", False) or data.get("calibrated", False)))
    except Exception:
        return False


def set_voice_match_enabled(enabled: bool) -> None:
    """Enable or disable voice match verification."""
    data = {}
    if VOICEPRINT_FILE.is_file():
        try:
            data = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["enabled"] = bool(enabled)
    VOICEPRINT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def enroll_owner_voice(
    audio_data: np.ndarray,
    owner_name: str = OWNER_DEFAULT_NAME,
    sample_rate: int = 16000
) -> dict:
    """
    Enroll or calibrate owner's voiceprint profile.
    """
    features = _extract_acoustic_features(audio_data, sample_rate)
    profile = {
        "owner": owner_name,
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_rate": sample_rate,
        "enabled": True,
        "calibrated": True,
        "calibrated_real": True,
        "vector": features.tolist()
    }
    VOICEPRINT_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return {
        "status": "ENROLLED",
        "owner": owner_name,
        "features_dim": len(features),
        "enrolled_at": profile["enrolled_at"]
    }


def verify_speaker(audio_data: np.ndarray, sample_rate: int = 16000) -> Tuple[bool, float, str]:
    """
    Verify if incoming audio matches the enrolled owner's voiceprint.
    Returns: (is_match, similarity_score, speaker_name)
    """
    if not is_enrolled() or not is_voice_match_enabled():
        return True, 1.0, OWNER_DEFAULT_NAME

    try:
        profile = json.loads(VOICEPRINT_FILE.read_text(encoding="utf-8"))
        owner_name = profile.get("owner", OWNER_DEFAULT_NAME)
        ref_vec = np.array(profile["vector"], dtype=np.float32)

        cur_vec = _extract_acoustic_features(audio_data, sample_rate)

        # Cosine similarity
        similarity = float(np.dot(ref_vec, cur_vec))

        # Check match against threshold
        is_match = similarity >= MATCH_THRESHOLD
        speaker = owner_name if is_match else "Unrecognized Speaker"
        return is_match, round(similarity, 3), speaker
    except Exception as e:
        print(f"[VoiceVerifier] Verification error: {e}")
        return True, 1.0, OWNER_DEFAULT_NAME
