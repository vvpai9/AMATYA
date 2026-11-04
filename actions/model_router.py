"""
actions/model_router.py — Model Router & Local AI Inference Configuration for AMATYA.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.model_router import DEFAULT_MODELS, get_router

SKILL_METADATA = {
    "name": "model_router",
    "version": "1.0.0",
    "description": "Inspect hardware capabilities, model routing table, local Ollama/llama.cpp status, and switch models per task role.",
    "capabilities": ["model_routing", "hardware_detection", "local_inference_probe"],
    "permissions": ["config_write"],
    "dependencies": ["psutil", "numpy"],
    "supported_actions": ["status", "probe", "set_route", "set_provider_url", "recommend"],
    "security_level": "normal",
}

TOOL = {
    "name": "model_router",
    "description": (
        "Inspect and configure AMATYA's multi-role AI Model Router (reasoning, "
        "planning, coding, vision, image_analysis, document_analysis, ocr, stt, "
        "tts, embeddings, tool_orchestration). Actions: 'status', 'probe', "
        "'set_route', 'set_provider_url', 'recommend'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'status', 'probe', 'set_route', 'set_provider_url', or 'recommend'.",
            },
            "role": {
                "type": "STRING",
                "description": f"Task role ({', '.join(DEFAULT_MODELS.keys())}).",
            },
            "model_spec": {
                "type": "STRING",
                "description": "Model specification 'provider:model' (e.g. 'ollama:qwen2.5-coder:7b').",
            },
            "provider": {
                "type": "STRING",
                "description": "Provider name ('ollama', 'llamacpp', 'lmstudio', 'remote').",
            },
            "base_url": {
                "type": "STRING",
                "description": "Endpoint URL for the provider (e.g. 'http://192.168.1.200:11434').",
            },
        },
        "required": ["action"],
    },
}


def execute(
    parameters: dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
) -> Any:
    action = str(parameters.get("action", "status") or "status").strip().lower()
    router = get_router()

    if action == "status":
        info = router.summary()
        hw = info["hardware"]
        routes_str = ", ".join(f"{k}→{v}" for k, v in info["routes"].items())
        return outcome.done(
            f"Hardware: {hw['cpu_cores']} cores, {hw['ram_gb']} GB RAM, "
            f"GPU: {hw['gpu_name'] or 'None'} ({hw['gpu_vram_gb'] or 0} GB VRAM). "
            f"Routes: {routes_str}.",
            data=info,
        )

    if action == "probe":
        probed = router.probe_providers()
        ol = probed.get("ollama", {})
        ol_msg = (
            f"Ollama ONLINE ({len(ol.get('models', []))} models: {', '.join(ol.get('models', [])[:6])})"
            if ol.get("online")
            else f"Ollama offline at {ol.get('url')}"
        )
        return outcome.done(f"Provider probe: {ol_msg}.", data=probed)

    if action == "set_route":
        role = str(parameters.get("role", "") or "").strip()
        spec = str(parameters.get("model_spec", "") or "").strip()
        ok, msg = router.set_route(role, spec)
        return outcome.done(msg) if ok else outcome.failed(msg)

    if action == "set_provider_url":
        prov = str(parameters.get("provider", "") or "").strip()
        url = str(parameters.get("base_url", "") or "").strip()
        if not prov or not url:
            return outcome.failed("Both 'provider' and 'base_url' are required.")
        ok, msg = router.set_provider_url(prov, url)
        return outcome.done(msg) if ok else outcome.failed(msg)

    if action == "recommend":
        role = str(parameters.get("role", "reasoning") or "reasoning").strip()
        rec = router.recommend_size(role)
        return outcome.done(
            f"Recommended model size for '{role}' on this hardware: {rec} (currently routed to {router.route(role)})."
        )

    return outcome.failed(f"Unknown model_router action '{action}'.")
