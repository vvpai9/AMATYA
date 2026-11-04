"""
Local wake-word detection for AMATYA.

Design goals:
  • ZERO cost when the feature is off — openwakeword is imported ONLY inside
    start()/install helpers, never at module load. If the user never enables
    wake word, none of this touches the app.
  • ZERO latency on the audio path — the microphone callback only ever does a
    cheap, non-blocking queue push (feed()); the actual model inference runs in
    this module's own background thread, so the real-time audio thread and the
    Gemini stream are never slowed.
  • Fully local & offline — audio fed here never leaves the machine; there is no
    network call except the one-time model download the user triggers from the UI.
  • Configurable wake models — supports built-in openwakeword models (default
    'hey_jarvis') as well as custom .onnx/.tflite models placed in
    config/wake_models/ (e.g. hey_amatya.onnx), while maintaining AMATYA as the
    user-facing identity. Note: wake-word detection only wakes the microphone
    gate; speaker identity verification is handled separately by core/voice_auth.py.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

# Default pretrained openwakeword model identifier.
WAKE_MODEL = "hey_jarvis"
BUILTIN_WAKE_MODELS = ("hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy")
# Score in [0,1]; above this counts as a detection. Tunable per environment.
DEFAULT_THRESHOLD = 0.5
# Mic frames arrive at 16 kHz int16; this is just the detector's input rate.
SAMPLE_RATE = 16000
CUSTOM_MODELS_DIR = Path(__file__).resolve().parent.parent / "config" / "wake_models"


def _get_configured_model(model_override: str | None = None) -> str:
    if model_override and str(model_override).strip():
        return str(model_override).strip()
    try:
        from memory.config_manager import get_wake_word_model
        return get_wake_word_model()
    except Exception:
        return WAKE_MODEL


def _get_configured_threshold(threshold_override: float | None = None) -> float:
    if threshold_override is not None:
        return float(threshold_override)
    try:
        from memory.config_manager import get_wake_word_threshold
        return get_wake_word_threshold()
    except Exception:
        return DEFAULT_THRESHOLD


def _resolve_model_target(model_name: str) -> str:
    """Resolve model_name to a custom file path if found in config/wake_models/,
    otherwise return model_name as an openwakeword model identifier."""
    p = Path(model_name)
    if p.is_file():
        return str(p.resolve())
    CUSTOM_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("", ".onnx", ".tflite"):
        cand = CUSTOM_MODELS_DIR / f"{model_name}{ext}"
        if cand.is_file():
            return str(cand.resolve())
    return model_name


def list_available_models() -> dict:
    """Return available built-in and custom wake-word models."""
    CUSTOM_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    custom = sorted(
        p.name for p in CUSTOM_MODELS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".onnx", ".tflite")
    )
    return {
        "configured_model": _get_configured_model(),
        "configured_threshold": _get_configured_threshold(),
        "builtin_models": list(BUILTIN_WAKE_MODELS),
        "custom_models": custom,
        "custom_models_dir": str(CUSTOM_MODELS_DIR),
    }


def is_installed() -> bool:
    """True if the openwakeword package is importable (no model check)."""
    try:
        import importlib.util
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready(model_name: str | None = None) -> bool:
    """True if openwakeword is installed AND its model files are present on disk.

    This is a cheap, DETERMINISTIC file-existence check. It deliberately does NOT
    construct a Model to probe readiness — doing that is slow and, worse, can clash
    with the detector's own Model when it's already running, which intermittently
    returned False and made the UI flicker to 'not downloaded'. Never raises.
    """
    if not is_installed():
        return False
    try:
        import openwakeword
        models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        if not models_dir.is_dir():
            return False
        target = _resolve_model_target(_get_configured_model(model_name))
        if Path(target).is_file():
            has_wake = True
        else:
            stem = Path(target).stem
            has_wake = (any(models_dir.glob(f"{stem}*.onnx"))
                        or any(models_dir.glob(f"{stem}*.tflite"))
                        or any(models_dir.glob(f"{WAKE_MODEL}*.onnx"))
                        or any(models_dir.glob(f"{WAKE_MODEL}*.tflite")))
        has_mel = (any(models_dir.glob("melspectrogram*.onnx"))
                   or any(models_dir.glob("melspectrogram*.tflite")))
        has_emb = (any(models_dir.glob("embedding_model*.onnx"))
                   or any(models_dir.glob("embedding_model*.tflite")))
        return bool(has_wake and has_mel and has_emb)
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None,
                         model_name: str | None = None) -> tuple[bool, str]:
    """
    One-click setup for the UI button: pip-install openwakeword if missing, then
    download the wake model. Returns (ok, message). Never raises — every failure
    is reported through the returned message and the logger.
    """
    _tell = notify or (lambda _msg: None)
    target_model = _get_configured_model(model_name)
    resolved_target = _resolve_model_target(target_model)
    is_custom_file = Path(resolved_target).is_file()
    dl_model = WAKE_MODEL if is_custom_file else target_model
    try:
        if not is_installed():
            logger("Wake word: installing openwakeword (one-time)…")
            _tell("Wake word: installing openwakeword (one-time)…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openwakeword==0.6.0"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"
        # Download the pretrained melspectrogram/embedding + wake models.
        logger("Wake word: downloading models…")
        _tell("Wake word: downloading models…")
        try:
            import openwakeword.utils as _u
            try:
                _u.download_models([dl_model])
            except TypeError:
                _u.download_models()   # older signature downloads the default set
        except Exception as e:
            return False, f"model download failed: {e}"

        if not is_ready(target_model):
            return False, "installed, but the wake model files are incomplete."

        # Validate the Python API, not just the presence of model files. A
        # partially upgraded openwakeword install can mix model.py and utils.py
        # from different releases and fail with AudioFeatures(... wakeword_models).
        model_to_load = resolved_target if is_custom_file else dl_model
        try:
            from openwakeword.model import Model
            _test_model = Model(
                wakeword_models=[model_to_load], inference_framework="onnx"
            )
            del _test_model
        except TypeError as e:
            if "AudioFeatures" not in str(e) or "wakeword_models" not in str(e):
                raise
            logger("Wake word: repairing mixed openwakeword installation…")
            repaired = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install",
                    "--force-reinstall", "--no-deps", "openwakeword==0.6.0",
                ],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120,
            )
            if repaired.returncode != 0:
                detail = (repaired.stderr or repaired.stdout or "").strip()
                return False, (
                    "openwakeword repair failed. Run: "
                    "python -m pip install --force-reinstall --no-deps "
                    "openwakeword==0.6.0"
                    + (f" ({detail.splitlines()[-1][:160]})" if detail else "")
                )
            # pip replaced the package files; discard stale imported modules.
            import importlib
            for _name in tuple(sys.modules):
                if _name == "openwakeword" or _name.startswith("openwakeword."):
                    sys.modules.pop(_name, None)
            importlib.invalidate_caches()
            from openwakeword.model import Model
            _test_model = Model(
                wakeword_models=[model_to_load], inference_framework="onnx"
            )
            del _test_model
        logger("Wake word: ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs the wake model in a dedicated thread. The mic thread calls feed() with
    raw int16 frames; detections invoke on_detect() (called from this thread —
    the callback must marshal to whatever loop/UI it needs).
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float | None = None,
                 model_name: str | None = None,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = _get_configured_threshold(threshold)
        self._model_name = _get_configured_model(model_name)
        self._logger    = logger
        # See PluginRegistry: `logger` is the console and gets everything,
        # `notify` is the activity log and gets only what the user must act on.
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._ready = False

    def start(self) -> bool:
        """Load the model and spawn the inference thread. Returns True on success.
        Safe to call again — a no-op if already running. Never raises."""
        if self._running:
            return True
        self._threshold = _get_configured_threshold(self._threshold)
        self._model_name = _get_configured_model(self._model_name)
        resolved_target = _resolve_model_target(self._model_name)
        try:
            from openwakeword.model import Model
            try:
                self._model = Model(wakeword_models=[resolved_target], inference_framework="onnx")
            except Exception:
                # Fallback to default hey_jarvis if a custom model fails to load
                if resolved_target != WAKE_MODEL:
                    self._logger(
                        f"Wake word: custom model '{resolved_target}' failed, falling back to '{WAKE_MODEL}'."
                    )
                    self._model = Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")
                else:
                    raise
        except Exception as e:
            detail = str(e)
            if ("AudioFeatures" in detail and "wakeword_models" in detail):
                self._logger(
                    "Wake word: incompatible/mixed openwakeword installation. "
                    "Repair with: python -m pip install --force-reinstall "
                    "--no-deps openwakeword==0.6.0"
                )
                self._notify(
                    "Wake word library needs repair; run the displayed pip command. "
                    "Voice assistant remains available."
                )
            else:
                self._logger(f"Wake word: could not load model — {detail}")
                self._notify("Wake word unavailable — use the WAKE NOW button.")
            self._model = None
            return False
        self._running = True
        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeWordThread")
        self._thread.start()
        self._logger(
            f"Wake word: listening for AMATYA wake phrase "
            f"(model='{self._model_name}', threshold={self._threshold:.2f})."
        )
        return True

    def stop(self) -> None:
        self._running = False
        # unblock the thread if it's waiting on the queue
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Must stay cheap and
        never block — the frame is copied and dropped if the queue is backed up."""
        if not self._running:
            return
        try:
            # frame_int16 is a numpy int16 array (possibly 2-D mono) — flatten to 1-D
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            pass

    def _loop(self) -> None:
        import numpy as np
        target_key = Path(self._model_name).stem.lower()
        while self._running:
            try:
                frame = self._queue.get()
                if frame is None or not self._running:
                    break
                scores = self._model.predict(np.asarray(frame, dtype=np.int16))
                score = 0.0
                if isinstance(scores, dict):
                    for k, v in scores.items():
                        kl = k.lower()
                        if target_key in kl or "jarvis" in kl or "amatya" in kl:
                            score = max(score, float(v))
                    if score == 0.0 and scores:
                        score = max(float(v) for v in scores.values())
                if score >= self._threshold:
                    # drain any backlog so we don't double-fire on the same utterance
                    self._drain()
                    try:
                        self._on_detect()
                    except Exception as e:
                        self._logger(f"Wake word: on_detect error — {e}")
            except Exception as e:
                self._logger(f"Wake word: inference error — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
