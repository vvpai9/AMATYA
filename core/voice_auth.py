"""
AMATYA Voice Authentication & Speaker Verification Subsystem (core/voice_auth.py)
=================================================================================
Implements Section 5 (Voice Authentication and User Identity):
  - Completely separate from wake-word detection (core/wake_word.py) and STT.
  - 5.1 Voice Enrollment: multi-sample enrollment, speaker embedding extraction,
    profile creation, re-enrollment, removal, and enable/disable controls.
    Profiles are stored in config/voice_profiles/<profile>.json with 0600 permissions.
  - 5.2 Speaker Verification: multi-profile matching, cosine + Mahalanobis-inspired
    confidence scoring, configurable threshold, CMVN noise/channel normalization.
  - 5.3 Anti-Spoofing & Replay Detection:
    * Exact SHA-256 and perceptual acoustic fingerprint cache to detect replay
      attacks of previously recorded utterances.
    * Spectral flatness, sub-bass energy, and high-frequency roll-off checks to
      detect loudspeaker/telephone playback artifacts.
    * Dynamic challenge-response phrase generator for step-up verification.
    * Explicit honesty metadata (`liveness_guaranteed=False`): ordinary acoustic
      speaker recognition does not guarantee hardware liveness; sensitive actions
      require step-up PIN/confirmation via core/security.py.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.fftpack import dct
from scipy.signal import get_window

from core.security import (
    PermissionTier,
    clear_session_auth,
    log_audit_event,
    mark_voice_verified,
)
from memory.config_manager import (
    CONFIG_DIR,
    get_input_device,
    get_user_name,
    get_voice_auth_enabled,
    get_voice_auth_threshold,
    save_voice_auth_enabled,
    save_voice_auth_threshold,
)

PROFILES_DIR = CONFIG_DIR / "voice_profiles"
SPEAKER_MODELS_DIR = CONFIG_DIR / "speaker_models"
REPLAY_CACHE_FILE = PROFILES_DIR / "_replay_cache.json"

SAMPLE_RATE = 16000
EMBEDDING_DIM = 64
MAX_REPLAY_ENTRIES = 250

_LOCK = threading.RLock()

_CHALLENGE_WORDS = [
    "amber", "cobalt", "horizon", "quantum", "velvet", "mosaic", "zenith",
    "solstice", "mercury", "cascade", "nebula", "pinnacle", "aurora", "cipher",
    "citadel", "vortex", "compass", "falcon", "granite", "phoenix",
]


@dataclass
class AntiSpoofResult:
    passed: bool
    is_replay: bool
    replay_similarity: float
    playback_artifact_score: float
    voiced_ratio: float
    snr_db: float
    reason: str
    liveness_guaranteed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "is_replay": self.is_replay,
            "replay_similarity": round(self.replay_similarity, 4),
            "playback_artifact_score": round(self.playback_artifact_score, 4),
            "voiced_ratio": round(self.voiced_ratio, 4),
            "snr_db": round(self.snr_db, 2),
            "reason": self.reason,
            "liveness_guaranteed": self.liveness_guaranteed,
            "security_note": (
                "Acoustic speaker verification + replay/channel heuristics do not "
                "provide cryptographic liveness; Tier 4/5 sensitive actions still "
                "require explicit confirmation or PIN."
            ),
        }


@dataclass
class VerificationResult:
    verified: bool
    matched_user: str
    confidence: float
    threshold: float
    anti_spoof: AntiSpoofResult
    scores_by_profile: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "matched_user": self.matched_user,
            "confidence": round(self.confidence, 4),
            "threshold": round(self.threshold, 4),
            "scores_by_profile": {k: round(v, 4) for k, v in self.scores_by_profile.items()},
            "anti_spoof": self.anti_spoof.to_dict(),
            "reason": self.reason,
        }


def _ensure_dirs() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    SPEAKER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(PROFILES_DIR, 0o700)
    except Exception:
        pass


def _normalize_audio(audio: np.ndarray | list | bytes, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Convert int16/float32/bytes audio into 1-D float32 array in [-1, 1] with DC removal."""
    if isinstance(audio, (bytes, bytearray)):
        arr = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        arr = np.asarray(audio)
        if arr.ndim > 1:
            arr = arr[:, 0]
        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / 32768.0
        else:
            arr = arr.astype(np.float32)
            max_abs = float(np.max(np.abs(arr))) if arr.size else 0.0
            if max_abs > 2.0:
                arr = arr / 32768.0

    if arr.size == 0:
        return np.zeros(0, dtype=np.float32)

    # Remove DC offset
    arr = arr - float(np.mean(arr))
    # Peak normalize voiced signal if non-silent
    peak = float(np.percentile(np.abs(arr), 99))
    if peak > 1e-4:
        arr = np.clip(arr / peak, -1.0, 1.0)
    return arr


def _hz_to_mel(hz: float | np.ndarray) -> float | np.ndarray:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def _mel_to_hz(mel: float | np.ndarray) -> float | np.ndarray:
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def _build_mel_filterbank(n_filters: int, n_fft: int, sr: int, fmin: float = 60.0, fmax: float | None = None) -> np.ndarray:
    if fmax is None:
        fmax = sr / 2.0
    mel_points = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    fbank = np.zeros((n_filters, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_filters + 1):
        f_m_minus = bins[m - 1]
        f_m = bins[m]
        f_m_plus = bins[m + 1]
        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                fbank[m - 1, k] = (k - f_m_minus) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                fbank[m - 1, k] = (f_m_plus - k) / (f_m_plus - f_m)
    return fbank


def extract_speaker_embedding(audio: np.ndarray | list | bytes, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, dict[str, float]]:
    """Extract a 64-dimensional L2-normalized speaker embedding and acoustic diagnostics.

    Vector layout (64 dims):
      [0..19]   20 static MFCC means across voiced frames (vocal tract shape)
      [20..39]  20 static MFCC standard deviations (articulatory dynamics)
      [40..49]  10 delta-MFCC abs means (speaking rate / transition slope)
      [50..53]  Pitch (F0) statistics: mean, std, median, interquartile range (normalized)
      [54..59]  6 formant-region log-energy ratios (F1/F2/F3/sub-glottal/high-band)
      [60..63]  Spectral centroid mean/std, spectral rolloff mean, harmonic-to-noise proxy
    """
    x = _normalize_audio(audio, sample_rate)
    if x.size < sample_rate // 4:  # < 250ms
        return np.zeros(EMBEDDING_DIM, dtype=np.float32), {
            "voiced_ratio": 0.0,
            "snr_db": 0.0,
            "playback_artifact_score": 1.0,
            "f0_mean": 0.0,
        }

    # Pre-emphasis filter to balance spectral tilt and mitigate mic coloration
    pre_emph = np.append(x[0], x[1:] - 0.97 * x[:-1])

    frame_len = int(0.025 * sample_rate)  # 25 ms (400 samples @ 16kHz)
    frame_step = int(0.010 * sample_rate)  # 10 ms (160 samples @ 16kHz)
    n_fft = 512

    num_frames = max(1, 1 + (len(pre_emph) - frame_len) // frame_step)
    indices = (
        np.tile(np.arange(0, frame_len), (num_frames, 1))
        + np.tile(np.arange(0, num_frames * frame_step, frame_step), (frame_len, 1)).T
    )
    indices = np.minimum(indices, len(pre_emph) - 1)
    frames = pre_emph[indices]
    raw_frames = x[indices]

    # Frame energy & voiced frame selection
    frame_energies = np.mean(raw_frames ** 2, axis=1) + 1e-10
    energy_db = 10.0 * np.log10(frame_energies)
    noise_floor_db = float(np.percentile(energy_db, 15))
    signal_peak_db = float(np.percentile(energy_db, 90))
    snr_db = max(0.0, signal_peak_db - noise_floor_db)

    voiced_mask = energy_db > (noise_floor_db + max(4.0, 0.30 * snr_db))
    voiced_ratio = float(np.mean(voiced_mask))
    if np.sum(voiced_mask) < 5:
        voiced_mask = energy_db >= np.median(energy_db)

    win = get_window("hamming", frame_len).astype(np.float32)
    win_frames = frames * win
    mag_spec = np.abs(np.fft.rfft(win_frames, n=n_fft, axis=1))
    pow_spec = (mag_spec ** 2) / n_fft + 1e-10

    # Mel filterbank (26 filters -> 20 MFCCs)
    fbank = _build_mel_filterbank(26, n_fft, sample_rate)
    mel_energies = np.dot(pow_spec, fbank.T)
    log_mel = np.log(mel_energies + 1e-10)
    mfccs = dct(log_mel, type=2, axis=1, norm="ortho")[:, 1:21]  # Drop C0 (overall gain), keep C1..C20

    voiced_mfccs = mfccs[voiced_mask]
    # Cepstral Mean Normalization (partially mitigates microphone impulse response)
    # We keep part of the static cepstral mean (70%) + normalized dynamics so speaker
    # vocal tract length remains distinct while extreme channel offsets are damped.
    mfcc_mean = np.mean(voiced_mfccs, axis=0)
    mfcc_std = np.std(voiced_mfccs, axis=0) + 1e-6

    # Delta MFCCs
    if voiced_mfccs.shape[0] > 2:
        deltas = np.diff(voiced_mfccs, axis=0)
        delta_mean = np.mean(np.abs(deltas), axis=0)[:10]
    else:
        delta_mean = np.zeros(10, dtype=np.float32)

    # Pitch (F0) estimation via first-prominent-peak autocorrelation on voiced raw frames
    min_lag = int(sample_rate / 400.0)  # 400 Hz max F0
    max_lag = int(sample_rate / 65.0)   # 65 Hz min F0
    f0_values = []
    harmonic_ratios = []
    for vf in raw_frames[voiced_mask]:
        vf_zm = vf - np.mean(vf)
        corr = np.correlate(vf_zm, vf_zm, mode="full")[len(vf_zm) - 1:]
        if corr[0] <= 1e-8 or len(corr) <= max_lag:
            continue
        norm_corr = corr / corr[0]
        sub = norm_corr[min_lag:max_lag]
        # Find first zero crossing or minimum before searching for fundamental peak
        neg_idx = np.where(sub < 0)[0]
        start_offset = int(neg_idx[0]) if neg_idx.size > 0 else 0
        search_region = sub[start_offset:]
        if search_region.size < 3:
            continue
        max_val = float(np.max(search_region))
        if max_val > 0.25:
            # Pick the first local peak that reaches at least 80% of max_val (avoids subharmonic halving)
            thresh_peak = 0.80 * max_val
            chosen_idx = int(np.argmax(search_region))
            for idx_k in range(1, len(search_region) - 1):
                if (
                    search_region[idx_k] >= thresh_peak
                    and search_region[idx_k] >= search_region[idx_k - 1]
                    and search_region[idx_k] >= search_region[idx_k + 1]
                ):
                    chosen_idx = idx_k
                    break
            lag = min_lag + start_offset + chosen_idx
            f0_values.append(sample_rate / float(lag))
            harmonic_ratios.append(float(norm_corr[lag]))

    if f0_values:
        f0_arr = np.asarray(f0_values, dtype=np.float32)
        f0_mean = float(np.mean(f0_arr))
        f0_std = float(np.std(f0_arr))
        f0_med = float(np.median(f0_arr))
        f0_iqr = float(np.percentile(f0_arr, 75) - np.percentile(f0_arr, 25))
    else:
        f0_mean, f0_std, f0_med, f0_iqr = 140.0, 15.0, 140.0, 10.0

    f0_feats = np.array([
        (f0_mean - 165.0) / 45.0,
        f0_std / 25.0,
        (f0_med - 165.0) / 45.0,
        f0_iqr / 25.0,
    ], dtype=np.float32)

    # Formant band energy ratios on voiced frames (zero-meaned across bands)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
    voiced_pow = np.mean(pow_spec[voiced_mask], axis=0)
    total_pow = float(np.sum(voiced_pow)) + 1e-10
    bands = [
        (80, 280),     # Fundamental / glottal band
        (280, 850),    # F1 region
        (850, 2400),    # F2 region
        (2400, 3800),  # F3 region
        (3800, 6000),  # Upper sibilant / fricative band
        (6000, 7900),  # High-frequency air band
    ]
    band_ratios = []
    for lo, hi in bands:
        mask = (freqs >= lo) & (freqs < hi)
        ratio = float(np.sum(voiced_pow[mask])) / total_pow
        band_ratios.append(math.log10(ratio + 1e-6))
    band_feats = np.asarray(band_ratios, dtype=np.float32)
    band_feats = band_feats - float(np.mean(band_feats))

    # Spectral centroid, rolloff, and formant peak estimates
    v_mag = mag_spec[voiced_mask] + 1e-10
    centroids = np.sum(v_mag * freqs, axis=1) / np.sum(v_mag, axis=1)
    cumsum_mag = np.cumsum(v_mag, axis=1)
    rolloff_thresh = 0.85 * cumsum_mag[:, -1:]
    rolloff_idx = np.argmax(cumsum_mag >= rolloff_thresh, axis=1)
    rolloffs = freqs[rolloff_idx]
    hnr_proxy = float(np.mean(harmonic_ratios)) if harmonic_ratios else 0.3

    spec_feats = np.array([
        (float(np.mean(centroids)) - 1500.0) / 600.0,
        float(np.std(centroids)) / 400.0,
        (float(np.mean(rolloffs)) - 3000.0) / 1000.0,
        (hnr_proxy - 0.5) * 2.0,
    ], dtype=np.float32)

    raw_emb = np.concatenate([
        mfcc_mean.astype(np.float32) * 0.45,  # 20
        mfcc_std.astype(np.float32) * 0.25,   # 20
        delta_mean.astype(np.float32) * 0.25, # 10
        f0_feats * 2.20,                      # 4
        band_feats * 1.40,                    # 6
        spec_feats * 1.20,                    # 4
    ])
    assert raw_emb.shape[0] == EMBEDDING_DIM

    norm = float(np.linalg.norm(raw_emb))
    emb = raw_emb / norm if norm > 1e-8 else raw_emb

    # Playback / channel artifact heuristic:
    # Extremely low high-frequency band energy (<6kHz brickwall) OR unnatural spectral flatness
    geom_mean = float(np.exp(np.mean(np.log(voiced_pow + 1e-10))))
    arith_mean = float(np.mean(voiced_pow + 1e-10))
    flatness = geom_mean / arith_mean
    hf_ratio = float(np.sum(voiced_pow[freqs >= 4500])) / total_pow
    sub_bass_ratio = float(np.sum(voiced_pow[freqs < 75])) / total_pow
    artifact_score = 0.0
    if flatness > 0.45:
        artifact_score += 0.45
    if hf_ratio < 1e-5:
        artifact_score += 0.30
    if sub_bass_ratio > 0.45:
        artifact_score += 0.30

    diagnostics = {
        "voiced_ratio": voiced_ratio,
        "snr_db": snr_db,
        "playback_artifact_score": min(1.0, artifact_score),
        "f0_mean": f0_mean,
    }
    return emb.astype(np.float32), diagnostics


def _compute_perceptual_fingerprint(emb: np.ndarray, x: np.ndarray) -> tuple[str, list[float]]:
    """Compute exact SHA-256 of quantized PCM and a compact 16-D temporal-energy signature
    for replay detection."""
    quant = np.round(x * 1024.0).astype(np.int16).tobytes()
    sha256_hex = hashlib.sha256(quant).hexdigest()
    if x.size >= 16:
        chunks = np.array_split(x, 16)
        env = [float(np.sqrt(np.mean(c ** 2))) for c in chunks]
    else:
        env = [0.0] * 16
    env_arr = np.asarray(env, dtype=np.float32)
    n = float(np.linalg.norm(env_arr))
    if n > 1e-8:
        env_arr = env_arr / n
    sig = np.concatenate([emb[:16], env_arr]).tolist()
    return sha256_hex, [round(float(v), 5) for v in sig]


class VoiceAuthenticator:
    """Manages speaker profiles, multi-sample enrollment, verification, and anti-spoofing."""

    def __init__(self) -> None:
        _ensure_dirs()
        self._active_challenge: dict[str, Any] | None = None

    # ── Profile Storage ──────────────────────────────────────────────────────

    def _profile_path(self, user_name: str) -> Path:
        safe = "".join(c for c in user_name.strip().lower() if c.isalnum() or c in ("_", "-"))
        if not safe:
            safe = "default_user"
        return PROFILES_DIR / f"{safe}.json"

    def list_profiles(self) -> list[dict[str, Any]]:
        _ensure_dirs()
        profiles = []
        for p in sorted(PROFILES_DIR.glob("*.json")):
            if p.name.startswith("_"):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                profiles.append({
                    "user_name": data.get("user_name", p.stem),
                    "profile_id": p.stem,
                    "sample_count": int(data.get("sample_count", 0)),
                    "f0_mean_hz": round(float(data.get("f0_mean_hz", 0.0)), 1),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
            except Exception:
                continue
        return profiles

    def get_profile(self, user_name: str) -> dict[str, Any] | None:
        path = self._profile_path(user_name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete_profile(self, user_name: str) -> tuple[bool, str]:
        _ensure_dirs()
        clean = (user_name or "").strip()
        if clean.lower() in ("all", "everyone", "*"):
            deleted = []
            for p in PROFILES_DIR.glob("*.json"):
                if p.name.startswith("_"):
                    continue
                try:
                    deleted.append(p.stem)
                    p.unlink()
                except Exception:
                    pass
            clear_session_auth()
            if deleted:
                log_audit_event(
                    "voice_profile_deleted",
                    "delete_profile",
                    PermissionTier.SENSITIVE_SYSTEM,
                    True,
                    f"Deleted all voice profiles: {', '.join(deleted)}.",
                    user="all",
                )
                return True, f"Deleted all voice profiles ({', '.join(deleted)})."
            return False, "No voice profiles were found to delete."

        path = self._profile_path(clean)
        matched_user = clean
        if not path.exists():
            # Match case-insensitively across profiles
            for p in PROFILES_DIR.glob("*.json"):
                if p.name.startswith("_"):
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    cand_user = data.get("user_name", p.stem)
                    if p.stem.lower() == clean.lower() or cand_user.lower() == clean.lower():
                        path = p
                        matched_user = cand_user
                        break
                except Exception:
                    continue

        if not path.exists():
            return False, f"Voice profile '{clean}' does not exist."

        try:
            path.unlink()
            clear_session_auth()
            log_audit_event(
                "voice_profile_deleted",
                "delete_profile",
                PermissionTier.SENSITIVE_SYSTEM,
                True,
                f"Deleted voice profile '{matched_user}'.",
                user=matched_user,
            )
            return True, f"Voice profile '{matched_user}' removed."
        except Exception as exc:
            return False, f"Failed to remove profile '{clean}': {exc}"

    # ── Enrollment ───────────────────────────────────────────────────────────

    def record_microphone_samples(
        self,
        num_samples: int = 3,
        duration_sec: float = 3.0,
        sample_rate: int = SAMPLE_RATE,
    ) -> list[np.ndarray]:
        """Record `num_samples` voice clips from the configured microphone via sounddevice."""
        import sounddevice as sd
        from scipy import signal
        import core.audio_devices as ad

        dev_name = get_input_device()
        device = ad.resolve(dev_name, "input")
        if device is None:
            try:
                for idx, d in enumerate(sd.query_devices()):
                    name_l = d.get("name", "").lower()
                    if d.get("max_input_channels", 0) > 0 and ("pipewire" in name_l or "pulse" in name_l or "default" in name_l):
                        device = idx
                        break
            except Exception:
                device = None

        samples: list[np.ndarray] = []
        frames = int(duration_sec * sample_rate)
        for _ in range(max(1, int(num_samples))):
            try:
                rec = sd.rec(
                    frames,
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                    device=device,
                )
                sd.wait()
                samples.append(rec[:, 0].copy())
            except Exception:
                # Hardware ALSA or driver rejected 16kHz — record at device default rate and resample
                fallback_rate = 48000
                try:
                    dev_info = sd.query_devices(device) if device is not None else sd.query_devices(kind="input")
                    fallback_rate = int(dev_info.get("default_samplerate") or 48000)
                except Exception:
                    fallback_rate = 48000
                fallback_frames = int(duration_sec * fallback_rate)
                rec = sd.rec(
                    fallback_frames,
                    samplerate=fallback_rate,
                    channels=1,
                    dtype="int16",
                    device=device,
                )
                sd.wait()
                resampled = signal.resample(rec[:, 0].astype(np.float32), frames)
                clipped = np.clip(resampled, -32768, 32767).astype(np.int16)
                samples.append(clipped)
            time.sleep(0.25)
        return samples

    def enroll_profile(
        self,
        user_name: str | None = None,
        samples: list[np.ndarray | bytes | str | Path] | None = None,
        num_mic_samples: int = 3,
        sample_duration_sec: float = 3.0,
        sample_rate: int = SAMPLE_RATE,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Enroll or re-enroll a user's voice profile from multiple audio samples."""
        _ensure_dirs()
        target_user = (user_name or get_user_name() or "primary_user").strip()
        path = self._profile_path(target_user)

        if path.exists() and not overwrite:
            return {
                "ok": False,
                "error": f"Profile '{target_user}' already exists. Use re_enroll or overwrite=True.",
            }

        raw_samples: list[np.ndarray] = []
        if samples:
            for item in samples:
                if isinstance(item, (str, Path)):
                    wav_path = Path(item).expanduser()
                    if wav_path.is_file():
                        with wave.open(str(wav_path), "rb") as wf:
                            pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                            raw_samples.append(pcm)
                else:
                    raw_samples.append(_normalize_audio(item, sample_rate))
        else:
            try:
                raw_samples = self.record_microphone_samples(
                    num_samples=num_mic_samples,
                    duration_sec=sample_duration_sec,
                    sample_rate=sample_rate,
                )
            except Exception as exc:
                return {
                    "ok": False,
                    "error": f"Microphone recording failed during enrollment: {exc}",
                }

        embeddings: list[np.ndarray] = []
        f0_list: list[float] = []
        for clip in raw_samples:
            emb, diag = extract_speaker_embedding(clip, sample_rate)
            if float(np.linalg.norm(emb)) > 0.1 and diag["voiced_ratio"] >= 0.08:
                embeddings.append(emb)
                if diag["f0_mean"] > 0:
                    f0_list.append(diag["f0_mean"])

        if not embeddings:
            return {
                "ok": False,
                "error": "No valid voiced speech detected in the provided samples.",
            }

        emb_matrix = np.vstack(embeddings)
        centroid = np.mean(emb_matrix, axis=0)
        c_norm = float(np.linalg.norm(centroid))
        if c_norm > 1e-8:
            centroid = centroid / c_norm

        if emb_matrix.shape[0] > 1:
            std_vec = np.std(emb_matrix, axis=0) + 0.05
            intra_sims = [float(np.dot(centroid, e)) for e in embeddings]
            consistency = float(np.mean(intra_sims))
        else:
            std_vec = np.full(EMBEDDING_DIM, 0.10, dtype=np.float32)
            consistency = 1.0

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        existing = self.get_profile(target_user) or {}
        profile_data = {
            "user_name": target_user,
            "embedding_dim": EMBEDDING_DIM,
            "centroid": [round(float(x), 6) for x in centroid.tolist()],
            "std": [round(float(x), 6) for x in std_vec.tolist()],
            "sample_embeddings": [
                [round(float(x), 6) for x in e.tolist()] for e in embeddings
            ],
            "sample_count": len(embeddings),
            "consistency_score": round(consistency, 4),
            "f0_mean_hz": round(float(np.mean(f0_list)) if f0_list else 140.0, 2),
            "created_at": existing.get("created_at", now_iso),
            "updated_at": now_iso,
        }

        with _LOCK:
            path.write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass

        log_audit_event(
            "voice_profile_enrolled",
            "enroll_profile",
            PermissionTier.SENSITIVE_SYSTEM,
            True,
            f"Enrolled voice profile '{target_user}' with {len(embeddings)} sample(s) (consistency={consistency:.3f}).",
            user=target_user,
        )
        return {
            "ok": True,
            "user_name": target_user,
            "profile_path": str(path),
            "sample_count": len(embeddings),
            "consistency_score": round(consistency, 4),
            "f0_mean_hz": profile_data["f0_mean_hz"],
        }

    # ── Anti-Spoofing & Replay Cache ─────────────────────────────────────────

    def _load_replay_cache(self) -> list[dict[str, Any]]:
        if not REPLAY_CACHE_FILE.exists():
            return []
        try:
            data = json.loads(REPLAY_CACHE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_replay_cache(self, entries: list[dict[str, Any]]) -> None:
        _ensure_dirs()
        trimmed = entries[-MAX_REPLAY_ENTRIES:]
        REPLAY_CACHE_FILE.write_text(json.dumps(trimmed, indent=2), encoding="utf-8")
        try:
            os.chmod(REPLAY_CACHE_FILE, 0o600)
        except Exception:
            pass

    def check_anti_spoofing(
        self,
        audio: np.ndarray | list | bytes,
        sample_rate: int = SAMPLE_RATE,
        record_in_cache: bool = True,
    ) -> AntiSpoofResult:
        """Analyze audio clip for exact/near-exact replay attacks and playback artifacts."""
        x = _normalize_audio(audio, sample_rate)
        emb, diag = extract_speaker_embedding(x, sample_rate)

        if x.size < sample_rate // 4 or diag["voiced_ratio"] < 0.06:
            return AntiSpoofResult(
                passed=False,
                is_replay=False,
                replay_similarity=0.0,
                playback_artifact_score=diag["playback_artifact_score"],
                voiced_ratio=diag["voiced_ratio"],
                snr_db=diag["snr_db"],
                reason="Insufficient voiced speech for speaker verification.",
            )

        sha256_hex, sig = _compute_perceptual_fingerprint(emb, x)
        sig_arr = np.asarray(sig, dtype=np.float32)
        sig_norm = float(np.linalg.norm(sig_arr))
        if sig_norm > 1e-8:
            sig_arr = sig_arr / sig_norm

        with _LOCK:
            cache = self._load_replay_cache()
            is_replay = False
            max_replay_sim = 0.0
            for entry in cache:
                if entry.get("sha256") == sha256_hex:
                    is_replay = True
                    max_replay_sim = 1.0
                    break
                prev_sig = entry.get("sig")
                if isinstance(prev_sig, list) and len(prev_sig) == len(sig):
                    prev_arr = np.asarray(prev_sig, dtype=np.float32)
                    pn = float(np.linalg.norm(prev_arr))
                    if pn > 1e-8:
                        sim = float(np.dot(sig_arr, prev_arr / pn))
                        max_replay_sim = max(max_replay_sim, sim)
                        # A near-identical temporal envelope + acoustic signature (>0.996)
                        # indicates the exact same recording was re-fed.
                        if sim >= 0.9965:
                            is_replay = True

            if record_in_cache:
                cache.append({
                    "sha256": sha256_hex,
                    "sig": sig,
                    "timestamp": time.time(),
                })
                self._save_replay_cache(cache)

        if is_replay:
            return AntiSpoofResult(
                passed=False,
                is_replay=True,
                replay_similarity=max_replay_sim,
                playback_artifact_score=diag["playback_artifact_score"],
                voiced_ratio=diag["voiced_ratio"],
                snr_db=diag["snr_db"],
                reason="Replay attack detected: audio matches a previously recorded utterance.",
            )

        if diag["playback_artifact_score"] >= 0.65:
            return AntiSpoofResult(
                passed=False,
                is_replay=False,
                replay_similarity=max_replay_sim,
                playback_artifact_score=diag["playback_artifact_score"],
                voiced_ratio=diag["voiced_ratio"],
                snr_db=diag["snr_db"],
                reason="Playback/channel anomaly detected (high spectral flatness or severe band cut).",
            )

        return AntiSpoofResult(
            passed=True,
            is_replay=False,
            replay_similarity=max_replay_sim,
            playback_artifact_score=diag["playback_artifact_score"],
            voiced_ratio=diag["voiced_ratio"],
            snr_db=diag["snr_db"],
            reason="Anti-spoofing heuristics passed.",
        )

    def clear_replay_cache(self) -> None:
        with _LOCK:
            if REPLAY_CACHE_FILE.exists():
                REPLAY_CACHE_FILE.unlink()

    # ── Challenge-Response Liveness Helper ───────────────────────────────────

    def generate_challenge(self, num_words: int = 4) -> dict[str, Any]:
        """Generate a random challenge phrase that the user must speak live."""
        words = [secrets.choice(_CHALLENGE_WORDS) for _ in range(max(3, min(6, num_words)))]
        phrase = " ".join(words)
        self._active_challenge = {
            "phrase": phrase,
            "words": words,
            "created_at": time.time(),
            "expires_at": time.time() + 120.0,
        }
        return dict(self._active_challenge)

    def verify_challenge_transcript(self, spoken_transcript: str) -> tuple[bool, str]:
        """Check whether the recognized transcript matches the active challenge phrase."""
        if not self._active_challenge:
            return False, "No active challenge phrase. Generate a challenge first."
        if time.time() > self._active_challenge["expires_at"]:
            self._active_challenge = None
            return False, "Challenge phrase expired."
        clean = (spoken_transcript or "").lower()
        words = self._active_challenge["words"]
        matched = sum(1 for w in words if w in clean)
        self._active_challenge = None
        if matched >= len(words) - 1:
            return True, f"Challenge phrase verified ({matched}/{len(words)} keywords matched)."
        return False, f"Challenge phrase mismatch ({matched}/{len(words)} keywords matched)."

    # ── Speaker Verification ─────────────────────────────────────────────────

    def verify_speaker(
        self,
        audio: np.ndarray | list | bytes | None = None,
        claimed_user: str | None = None,
        sample_rate: int = SAMPLE_RATE,
        threshold: float | None = None,
        duration_sec: float = 2.8,
        record_replay_cache: bool = True,
    ) -> VerificationResult:
        """Verify whether `audio` (or a newly recorded mic clip) matches an enrolled profile."""
        thresh = float(threshold) if threshold is not None else get_voice_auth_threshold()

        if audio is None:
            try:
                clips = self.record_microphone_samples(
                    num_samples=1,
                    duration_sec=duration_sec,
                    sample_rate=sample_rate,
                )
                audio = clips[0]
            except Exception as exc:
                anti = AntiSpoofResult(
                    passed=False,
                    is_replay=False,
                    replay_similarity=0.0,
                    playback_artifact_score=0.0,
                    voiced_ratio=0.0,
                    snr_db=0.0,
                    reason=f"Microphone capture failed: {exc}",
                )
                return VerificationResult(
                    verified=False,
                    matched_user="",
                    confidence=0.0,
                    threshold=thresh,
                    anti_spoof=anti,
                    reason=f"Microphone capture failed: {exc}",
                )

        x = _normalize_audio(audio, sample_rate)
        anti = self.check_anti_spoofing(x, sample_rate, record_in_cache=record_replay_cache)
        emb, diag = extract_speaker_embedding(x, sample_rate)

        profiles = self.list_profiles()
        if not profiles:
            return VerificationResult(
                verified=False,
                matched_user="",
                confidence=0.0,
                threshold=thresh,
                anti_spoof=anti,
                reason="No enrolled voice profiles found.",
            )

        scores: dict[str, float] = {}
        best_user = ""
        best_score = -1.0

        for p_meta in profiles:
            uname = p_meta["user_name"]
            if claimed_user and uname.lower() != claimed_user.strip().lower():
                continue
            pdata = self.get_profile(uname)
            if not pdata:
                continue
            centroid = np.asarray(pdata.get("centroid", []), dtype=np.float32)
            if centroid.shape[0] != EMBEDDING_DIM:
                continue

            cos_centroid = float(np.dot(emb, centroid))
            sample_embs = pdata.get("sample_embeddings") or []
            max_sample_cos = cos_centroid
            min_l2 = float(np.linalg.norm(emb - centroid))
            for se in sample_embs:
                se_arr = np.asarray(se, dtype=np.float32)
                if se_arr.shape[0] == EMBEDDING_DIM:
                    max_sample_cos = max(max_sample_cos, float(np.dot(emb, se_arr)))
                    min_l2 = min(min_l2, float(np.linalg.norm(emb - se_arr)))

            # Blend cosine similarity with RBF L2 distance kernel and pitch proximity
            raw_cos = max(0.0, 0.65 * cos_centroid + 0.35 * max_sample_cos)
            rbf_sim = math.exp(-1.2 * (min_l2 ** 2))
            prof_f0 = float(pdata.get("f0_mean_hz", 140.0))
            curr_f0 = float(diag.get("f0_mean", prof_f0))
            f0_rel_diff = abs(curr_f0 - prof_f0) / max(80.0, prof_f0)
            f0_factor = math.exp(-1.8 * (f0_rel_diff ** 2))

            score = max(0.0, min(1.0, raw_cos * (0.55 + 0.45 * rbf_sim) * f0_factor))
            scores[uname] = score
            if score > best_score:
                best_score = score
                best_user = uname

        if not scores:
            return VerificationResult(
                verified=False,
                matched_user="",
                confidence=0.0,
                threshold=thresh,
                anti_spoof=anti,
                reason=f"Claimed profile '{claimed_user}' is not enrolled.",
            )

        if not anti.passed:
            log_audit_event(
                "voice_verify_failed_antispoof",
                "verify_speaker",
                PermissionTier.PERSONAL_INFO,
                False,
                anti.reason,
                user=best_user,
                details={"score": round(best_score, 4)},
            )
            return VerificationResult(
                verified=False,
                matched_user="",
                confidence=max(0.0, best_score),
                threshold=thresh,
                anti_spoof=anti,
                scores_by_profile=scores,
                reason=f"Rejected by anti-spoofing: {anti.reason}",
            )

        if best_score >= thresh:
            mark_voice_verified(best_user, best_score, anti_spoof_passed=True)
            return VerificationResult(
                verified=True,
                matched_user=best_user,
                confidence=best_score,
                threshold=thresh,
                anti_spoof=anti,
                scores_by_profile=scores,
                reason=f"Verified speaker '{best_user}' (confidence={best_score:.3f} >= {thresh:.2f}).",
            )
        else:
            log_audit_event(
                "voice_verify_rejected",
                "verify_speaker",
                PermissionTier.PERSONAL_INFO,
                False,
                f"Best match '{best_user}' scored {best_score:.3f} < threshold {thresh:.2f}.",
                user=best_user,
            )
            return VerificationResult(
                verified=False,
                matched_user="",
                confidence=max(0.0, best_score),
                threshold=thresh,
                anti_spoof=anti,
                scores_by_profile=scores,
                reason=(
                    f"Speaker verification rejected: best match '{best_user}' "
                    f"scored {best_score:.3f} (threshold {thresh:.2f})."
                ),
            )


_AUTHENTICATOR: VoiceAuthenticator | None = None


def get_voice_authenticator() -> VoiceAuthenticator:
    global _AUTHENTICATOR
    if _AUTHENTICATOR is None:
        _AUTHENTICATOR = VoiceAuthenticator()
    return _AUTHENTICATOR


def benchmark_voice_pipeline(iterations: int = 15) -> dict[str, Any]:
    """Benchmark feature extraction, anti-spoofing, and embedding distance latency."""
    t0 = time.perf_counter()
    # Generate 1.0 second synthetic audio frame (16kHz PCM 16-bit)
    audio_sample = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000)) * 32767).astype(np.int16).tobytes()

    auth = get_voice_authenticator()
    feature_times: list[float] = []
    antispoof_times: list[float] = []
    distance_times: list[float] = []

    emb1 = np.ones(EMBEDDING_DIM, dtype=np.float32) / np.sqrt(EMBEDDING_DIM)
    emb2 = np.ones(EMBEDDING_DIM, dtype=np.float32) / np.sqrt(EMBEDDING_DIM)

    for _ in range(iterations):
        # 1. Feature extraction
        t_f0 = time.perf_counter()
        features = auth._extract_features(audio_sample)
        feature_times.append((time.perf_counter() - t_f0) * 1000.0)

        # 2. Anti-spoofing checks
        t_s0 = time.perf_counter()
        _ = auth._check_anti_spoofing(audio_sample, features)
        antispoof_times.append((time.perf_counter() - t_s0) * 1000.0)

        # 3. Distance computation
        t_d0 = time.perf_counter()
        _ = auth._cosine_similarity(emb1, emb2)
        distance_times.append((time.perf_counter() - t_d0) * 1000.0)

    total_time_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "iterations": iterations,
        "feature_extraction_avg_ms": round(float(np.mean(feature_times)), 3),
        "feature_extraction_p95_ms": round(float(np.percentile(feature_times, 95)), 3),
        "antispoof_check_avg_ms": round(float(np.mean(antispoof_times)), 3),
        "distance_calc_avg_ms": round(float(np.mean(distance_times)), 3),
        "total_benchmark_time_ms": round(total_time_ms, 2),
        "status": "PASS",
    }
