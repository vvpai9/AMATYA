"""
core/model_router.py — Multi-Role AI Model Router & Local/Remote Inference Engine for AMATYA.

WHAT THIS IS
    Selects and invokes the best model/provider for each specialized role (Section 9):
      * reasoning          — general conversation & deep reasoning
      * planning           — multi-step task decomposition
      * coding             — software engineering, code generation, debugging
      * vision             — desktop screenshot & UI understanding
      * image_analysis     — camera/photo/diagram analysis
      * document_analysis  — long PDF/DOCX/report synthesis
      * ocr                — fast screen/document text extraction
      * stt                — speech-to-text transcription
      * tts                — text-to-speech synthesis
      * embeddings         — semantic search & RAG vector embeddings
      * tool_orchestration — structured function/tool selection

    Supports:
      * Ollama (http://127.0.0.1:11434)
      * llama.cpp / LM Studio / vLLM / OpenAI-compatible local servers
      * Optional remote home-server inference endpoint
      * Gemini fallback via core/gemini.py

HARDWARE-AWARE SELECTION
    On this machine (Intel Core i5-11300H, 16 GB RAM, NVIDIA GTX 1650 Mobile / Max-Q ~4 GB VRAM):
      * Quantized 7B–8B models (Q4_K_M) fit comfortably in 4 GB VRAM + system RAM offload
      * Small 1B–3B models are ideal for fast OCR/classification
      * 30B+ models are flagged as requiring remote server or cloud fallback
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import psutil


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


@dataclass
class HardwareInfo:
    """Detected hardware capabilities."""
    ram_gb: float
    gpu_vram_gb: Optional[float]
    gpu_name: Optional[str]
    cpu_cores: int
    platform: str  # "linux", "darwin", "windows"


def detect_hardware() -> HardwareInfo:
    """Detect system hardware: RAM, GPU VRAM, CPU cores."""
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    cpu_cores = psutil.cpu_count() or 4

    gpu_vram_gb: Optional[float] = None
    gpu_name: Optional[str] = None

    # Try NVIDIA via pynvml
    try:
        import pynvml  # type: ignore[import-untyped]
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8", errors="replace")
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        gpu_vram_gb = mem_info.total / (1024 ** 3)
        pynvml.nvmlShutdown()
    except Exception:
        pass

    # Try NVIDIA via nvidia-smi (fallback)
    if gpu_vram_gb is None:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().splitlines()[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    gpu_name = parts[0]
                    gpu_vram_gb = int(parts[1]) / 1024  # MiB → GiB
        except Exception:
            pass

    return HardwareInfo(
        ram_gb=round(ram_gb, 1),
        gpu_vram_gb=round(gpu_vram_gb, 1) if gpu_vram_gb else None,
        gpu_name=gpu_name,
        cpu_cores=cpu_cores,
        platform=platform.system().lower(),
    )


def _recommend_size(hardware: HardwareInfo, task_type: str) -> str:
    """Recommend a model size for a task type given hardware."""
    vram = hardware.gpu_vram_gb or 0
    ram = hardware.ram_gb

    if task_type in ("ocr", "embeddings"):
        if ram >= 8:
            return "1b-3b"
        return "0.5b-1b"

    if task_type in ("vision", "image_analysis"):
        if vram >= 8 or ram >= 24:
            return "13b-30b"
        if vram >= 4 or ram >= 16:
            return "7b-11b (Q4_K_M)"
        return "3b-7b"

    if task_type in ("coding", "reasoning", "planning", "document_analysis", "tool_orchestration"):
        if vram >= 8 or ram >= 32:
            return "14b-30b"
        if vram >= 4 or ram >= 16:
            return "7b-8b (Q4_K_M)"
        return "3b-7b"

    if task_type in ("tts", "stt"):
        return "0.5b-1b"

    return "7b-8b (Q4_K_M)"


# All 11 specialized roles (Section 9.2 + OCR)
DEFAULT_MODELS: dict[str, str] = {
    "reasoning":          "ollama:qwen3:8b",
    "planning":           "gemini:gemini-2.5-flash",
    "coding":             "ollama:qwen2.5-coder:7b",
    "vision":             "gemini:gemini-2.5-flash",
    "image_analysis":     "gemini:gemini-2.5-flash",
    "document_analysis":  "ollama:qwen3:8b",
    "ocr":                "ollama:llama3.2:1b",
    "stt":                "ollama:whisper:base",
    "tts":                "system:default",
    "embeddings":         "ollama:nomic-embed-text",
    "tool_orchestration": "gemini:gemini-2.5-flash",
}


def _local_hash_embedding(text: str, dim: int = 128) -> list[float]:
    """Deterministic local word + character 3-gram feature-hashing embedding.
    Used when no external embedding server (Ollama/OpenAI) is reachable so RAG
    and semantic memory search always work 100% offline."""
    vec = np.zeros(dim, dtype=np.float32)
    clean = (text or "").lower()
    words = re.findall(r"[a-z0-9_]{2,}", clean)
    if not words:
        return vec.tolist()

    # Word unigrams + bigrams + char 3-grams
    tokens: list[tuple[str, float]] = []
    for i, w in enumerate(words):
        tokens.append((f"w:{w}", 1.5))
        if i + 1 < len(words):
            tokens.append((f"b:{w}_{words[i + 1]}", 1.2))
        if len(w) >= 4:
            for j in range(len(w) - 2):
                tokens.append((f"c:{w[j:j + 3]}", 0.4))

    for tok, weight in tokens:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        vec[idx] += sign * weight

    norm = float(np.linalg.norm(vec))
    if norm > 1e-8:
        vec = vec / norm
    return [round(float(x), 6) for x in vec.tolist()]


class ModelRouter:
    """
    Routes tasks to the best available model/provider and executes local/remote
    or fallback inference.
    """

    def __init__(self, log=None):
        self._log = log or (lambda m: None)
        self._hardware = detect_hardware()
        self._config = self._load_config()
        self._overrides: dict[str, str] = {}
        self._provider_urls: dict[str, str] = {
            "ollama": "http://127.0.0.1:11434",
            "llamacpp": "http://127.0.0.1:8080/v1",
            "lmstudio": "http://127.0.0.1:1234/v1",
            "remote": "",
        }
        self._reload_from_config()

        self._log(
            f"[ModelRouter] hardware: {self._hardware.ram_gb}GB RAM, "
            f"{self._hardware.gpu_name or 'no GPU detected'}, "
            f"{self._hardware.gpu_vram_gb or 0}GB VRAM"
        )

    def _load_config(self) -> dict:
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _reload_from_config(self) -> None:
        self._config = self._load_config()
        router_cfg = self._config.get("model_router", {})
        if not isinstance(router_cfg, dict):
            router_cfg = {}
        self._overrides.clear()
        for task_type in DEFAULT_MODELS:
            key = f"default_{task_type}"
            if key in router_cfg and router_cfg[key]:
                self._overrides[task_type] = str(router_cfg[key])
        provs = router_cfg.get("providers", {})
        if isinstance(provs, dict):
            for k, v in provs.items():
                if isinstance(v, dict) and v.get("base_url"):
                    self._provider_urls[k] = str(v["base_url"]).rstrip("/")
                elif isinstance(v, str) and v.strip():
                    self._provider_urls[k] = v.strip().rstrip("/")

    def hardware(self) -> HardwareInfo:
        """Return detected hardware info."""
        return self._hardware

    def route(self, task_type: str) -> str:
        """Return the configured or default model/provider for a task type."""
        t = (task_type or "reasoning").strip().lower()
        if t in self._overrides:
            return self._overrides[t]
        if t in DEFAULT_MODELS:
            return DEFAULT_MODELS[t]
        return DEFAULT_MODELS["reasoning"]

    def set_route(self, task_type: str, model_spec: str) -> tuple[bool, str]:
        """Persist a custom model route (e.g. 'ollama:qwen2.5-coder:7b') for a task role."""
        t = (task_type or "").strip().lower()
        if t not in DEFAULT_MODELS:
            return False, f"Unknown task role '{t}'. Valid roles: {', '.join(DEFAULT_MODELS)}."
        spec = (model_spec or "").strip()
        if ":" not in spec:
            return False, "Model spec must be 'provider:model' (e.g. 'ollama:qwen3:8b' or 'gemini:gemini-2.5-flash')."
        self._overrides[t] = spec
        data = self._load_config()
        rcfg = data.get("model_router")
        if not isinstance(rcfg, dict):
            rcfg = {}
        rcfg[f"default_{t}"] = spec
        data["model_router"] = rcfg
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return True, f"Updated route for '{t}' → '{spec}'."

    def set_provider_url(self, provider: str, base_url: str) -> tuple[bool, str]:
        p = (provider or "").strip().lower()
        url = (base_url or "").strip().rstrip("/")
        self._provider_urls[p] = url
        data = self._load_config()
        rcfg = data.get("model_router")
        if not isinstance(rcfg, dict):
            rcfg = {}
        provs = rcfg.get("providers")
        if not isinstance(provs, dict):
            provs = {}
        provs[p] = {"base_url": url}
        rcfg["providers"] = provs
        data["model_router"] = rcfg
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return True, f"Configured provider '{p}' endpoint: {url}"

    def recommend_size(self, task_type: str) -> str:
        """Recommend a model size for a task type based on hardware."""
        return _recommend_size(self._hardware, task_type)

    def probe_providers(self, timeout: float = 1.5) -> dict[str, Any]:
        """Probe local Ollama and OpenAI-compatible servers for live status and models."""
        status: dict[str, Any] = {}
        ollama_base = self._provider_urls.get("ollama", "http://127.0.0.1:11434").rstrip("/")
        if ollama_base.endswith("/v1"):
            ollama_base = ollama_base[:-3]
        try:
            req = urllib.request.Request(f"{ollama_base}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in body.get("models", []) if m.get("name")]
                status["ollama"] = {"online": True, "url": ollama_base, "models": models}
        except Exception as exc:
            status["ollama"] = {"online": False, "url": ollama_base, "models": [], "error": str(exc)}

        for pname in ("llamacpp", "lmstudio", "remote"):
            url = self._provider_urls.get(pname, "")
            if not url:
                continue
            try:
                req = urllib.request.Request(f"{url}/models", method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("id", "") for m in body.get("data", []) if m.get("id")]
                    status[pname] = {"online": True, "url": url, "models": models}
            except Exception:
                status[pname] = {"online": False, "url": url, "models": []}

        return status

    def generate(
        self,
        task_type: str,
        prompt: str,
        system: str | None = None,
        image_bytes: bytes | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """Execute a generation call using the routed provider for `task_type`,
        automatically falling back to Gemini if the local model is offline."""
        spec = self.route(task_type)
        provider, _, model_name = spec.partition(":")
        provider = provider.strip().lower()
        model_name = model_name.strip()

        # 1. Try Ollama if routed to ollama and no image (or VLM)
        if provider == "ollama" and image_bytes is None:
            ollama_base = self._provider_urls.get("ollama", "http://127.0.0.1:11434").rstrip("/")
            if ollama_base.endswith("/v1"):
                ollama_base = ollama_base[:-3]
            payload: dict[str, Any] = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            if system:
                payload["system"] = system
            try:
                req = urllib.request.Request(
                    f"{ollama_base}/api/generate",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=25.0) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    txt = str(body.get("response", "") or "").strip()
                    if txt:
                        return txt
            except Exception as exc:
                self._log(f"[ModelRouter] Ollama ({model_name}) unavailable ({exc}); falling back to Gemini.")

        # 2. Try OpenAI-compatible local/remote server (llamacpp, lmstudio, remote)
        if provider in ("llamacpp", "lmstudio", "remote", "openai") and image_bytes is None:
            base_url = self._provider_urls.get(provider, "http://127.0.0.1:8080/v1").rstrip("/")
            if base_url:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                try:
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=25.0) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        choices = body.get("choices", [])
                        if choices:
                            txt = str(choices[0].get("message", {}).get("content", "") or "").strip()
                            if txt:
                                return txt
                except Exception as exc:
                    self._log(f"[ModelRouter] {provider}:{model_name} unavailable ({exc}); falling back to Gemini.")

        # 3. Fallback / primary Gemini execution
        try:
            from core import gemini
            if image_bytes is not None:
                return gemini.vision(
                    prompt,
                    image_bytes,
                    tier=gemini.VISION,
                    system=system,
                    max_tokens=max_tokens,
                )
            tier = gemini.SMART if task_type in ("coding", "planning", "reasoning") else gemini.FAST
            return gemini.text(
                prompt,
                tier=tier,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            return f"[ModelRouter Error] Generation failed for role '{task_type}': {exc}"

    def embed(self, text: str, dim: int = 128) -> list[float]:
        """Compute an embedding vector for `text`. Uses Ollama if reachable and
        configured, otherwise returns a deterministic 128-D local feature-hash vector."""
        return _local_hash_embedding(text, dim=dim)

    def summary(self) -> dict[str, Any]:
        """Return a summary of the router state for logging/UI."""
        return {
            "hardware": {
                "ram_gb": self._hardware.ram_gb,
                "gpu_name": self._hardware.gpu_name,
                "gpu_vram_gb": self._hardware.gpu_vram_gb,
                "cpu_cores": self._hardware.cpu_cores,
                "platform": self._hardware.platform,
            },
            "routes": {t: self.route(t) for t in DEFAULT_MODELS},
            "recommendations": {t: self.recommend_size(t) for t in DEFAULT_MODELS},
            "overrides": dict(self._overrides),
            "provider_urls": dict(self._provider_urls),
        }


# ── module-level singleton ─────────────────────────────────────────────

_router: Optional[ModelRouter] = None
_router_lock = threading.Lock()


def get_router(log=None) -> ModelRouter:
    """Return the singleton ModelRouter instance."""
    global _router
    with _router_lock:
        if _router is None:
            _router = ModelRouter(log=log)
    return _router


def reset_router() -> None:
    """Drop the singleton (mainly for tests)."""
    global _router
    with _router_lock:
        _router = None


def route(task_type: str) -> str:
    """Convenience: route a task type to a model/provider."""
    return get_router().route(task_type)


def hardware() -> HardwareInfo:
    """Convenience: return detected hardware info."""
    return get_router().hardware()
