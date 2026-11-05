"""
actions/voice_auth.py — Voice Authentication, Speaker Identity & Security Policy for AMATYA.

Exposes speaker enrollment, speaker verification, anti-spoofing challenge-response,
wake-word & voice style configuration, PIN management, autonomy level configuration,
and security audit log inspection.
"""
from __future__ import annotations

from typing import Any

from core import outcome
from core.security import (
    PermissionTier,
    check_permission,
    clear_pin,
    clear_session_auth,
    get_session_auth_status,
    has_pin,
    read_audit_log,
    set_pin,
    verify_pin,
)
from core.voice_auth import get_voice_authenticator
from core.wake_word import list_available_models
from memory.config_manager import (
     AUTONOMY_LEVELS,
    AVAILABLE_VOICES,
    SPEECH_STYLES,
    SPEECH_VERBOSITIES,
    get_autonomy_level,
    get_speech_speed,
    get_speech_style,
    get_speech_verbosity,
    get_voice,
    get_voice_auth_enabled,
    get_voice_auth_threshold,
    get_wake_word_enabled,
    get_wake_word_model,
    get_wake_word_threshold,
    save_autonomy_level,
    save_speech_speed,
    save_speech_style,
    save_speech_verbosity,
    save_voice,
    save_voice_auth_enabled,
    save_voice_auth_threshold,
    save_wake_word_enabled,
    save_wake_word_model,
    save_wake_word_threshold,
)

SKILL_METADATA = {
    "name": "voice_auth",
    "version": "1.0.0",
    "description": "Voice authentication, speaker enrollment, anti-spoofing, PIN security, and voice settings.",
    "capabilities": [
        "speaker_enrollment",
        "speaker_verification",
        "anti_spoofing",
        "pin_authentication",
        "voice_configuration",
        "security_audit",
    ],
    "permissions": ["microphone", "security_policy", "config_write"],
    "dependencies": ["numpy", "scipy", "sounddevice"],
    "supported_actions": [
        "status",
        "enroll",
        "re_enroll",
        "verify",
        "list_profiles",
        "delete_profile",
        "enable",
        "disable",
        "set_threshold",
        "generate_challenge",
        "verify_challenge",
        "set_pin",
        "verify_pin",
        "clear_pin",
        "set_autonomy",
        "configure_voice",
        "audit_log",
    ],
    "security_level": "high",
}

TOOL = {
    "name": "voice_auth",
    "description": (
        "Manage AMATYA voice authentication, speaker verification profiles, "
        "anti-spoofing challenges, security PIN, autonomy levels (1-5), and "
        "voice/wake-word settings. Actions: 'status', 'enroll', 're_enroll', "
        "'verify', 'list_profiles', 'delete_profile', 'enable', 'disable', "
        "'set_threshold', 'generate_challenge', 'verify_challenge', 'set_pin', "
        "'verify_pin', 'clear_pin', 'set_autonomy', 'configure_voice', 'audit_log'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to perform: 'status', 'enroll', 're_enroll', 'verify', "
                    "'list_profiles', 'delete_profile', 'enable', 'disable', "
                    "'set_threshold', 'generate_challenge', 'verify_challenge', "
                    "'set_pin', 'verify_pin', 'clear_pin', 'set_autonomy', "
                    "'configure_voice', 'audit_log'."
                ),
            },
            "user_name": {
                "type": "STRING",
                "description": "User profile name for enroll/verify/delete_profile.",
            },
            "num_samples": {
                "type": "INTEGER",
                "description": "Number of voice samples to record during enrollment (default 3).",
            },
            "sample_duration_sec": {
                "type": "NUMBER",
                "description": "Duration in seconds per sample recording (default 3.0).",
            },
            "sample_files": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Optional list of WAV file paths for enrollment.",
            },
            "threshold": {
                "type": "NUMBER",
                "description": "Confidence threshold in [0.5, 0.95] for speaker verification or wake word.",
            },
            "pin": {
                "type": "STRING",
                "description": "Security PIN for set_pin, verify_pin, or clear_pin.",
            },
            "challenge_transcript": {
                "type": "STRING",
                "description": "Spoken phrase to verify against an active anti-spoofing challenge.",
            },
            "autonomy_level": {
                "type": "STRING",
                "description": (
                    "Autonomy level: 'observe_only', 'recommend', 'confirm', "
                    "'autonomous_low_risk', or 'autonomous_workflows'."
                ),
            },
            "voice_name": {
                "type": "STRING",
                "description": f"Assistant voice ({', '.join(AVAILABLE_VOICES)}).",
            },
            "speech_speed": {
                "type": "NUMBER",
                "description": "Speech speed multiplier (0.5 to 2.0).",
            },
            "confirmed": {
                "type": "BOOLEAN",
                "description": "Set True if user explicitly confirmed deleting a profile, disabling voice auth, or sensitive action.",
            },
            "speech_verbosity": {
                "type": "STRING",
                "description": "Verbosity level: 'concise', 'normal', or 'detailed'.",
            },
            "speech_style": {
                "type": "STRING",
                "description": "Speech style: 'natural', 'formal', 'technical', or 'tactical'.",
            },
            "wake_word_model": {
                "type": "STRING",
                "description": "Wake word model name or custom .onnx filename.",
            },
            "wake_word_enabled": {
                "type": "BOOLEAN",
                "description": "Enable or disable wake-word listening.",
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
    confirmed = bool(
        parameters.get("confirmed", False)
        or parameters.get("confirm", False)
        or str(parameters.get("confirmed", "")).lower() in ("yes", "true", "1", "confirm")
    )
    auth = get_voice_authenticator()

    if action == "status":
        status = get_session_auth_status()
        profiles = auth.list_profiles()
        wake_info = list_available_models()
        summary = (
            f"Voice Auth: {'ENABLED' if status['voice_auth_enabled'] else 'DISABLED'} "
            f"(threshold={get_voice_auth_threshold():.2f}, enrolled_profiles={len(profiles)}, "
            f"verified_user={status['verified_user'] or 'none'}, "
            f"PIN={'configured' if status['pin_configured'] else 'not set'}, "
            f"autonomy={status['autonomy_level']}). "
            f"Voice: {get_voice()} (speed={get_speech_speed():.2f}x, "
            f"verbosity={get_speech_verbosity()}, style={get_speech_style()}). "
            f"Wake Word: {'ON' if get_wake_word_enabled() else 'OFF'} "
            f"(model={wake_info['configured_model']}, threshold={wake_info['configured_threshold']:.2f})."
        )
        return outcome.done(
            "voice_auth",
            result=summary,
            data={
                "auth_status": status,
                "profiles": profiles,
                "voice_settings": {
                    "voice_name": get_voice(),
                    "available_voices": AVAILABLE_VOICES,
                    "speech_speed": get_speech_speed(),
                    "speech_verbosity": get_speech_verbosity(),
                    "speech_style": get_speech_style(),
                },
                "wake_word": wake_info,
            },
        )

    if action == "list_profiles":
        profiles = auth.list_profiles()
        if not profiles:
            return outcome.done("voice_auth", result="No voice profiles are currently enrolled.", data={"profiles": []})
        names = ", ".join(f"{p['user_name']} ({p['sample_count']} samples)" for p in profiles)
        return outcome.done("voice_auth", result=f"Enrolled voice profiles: {names}.", data={"profiles": profiles})

    if action in ("enroll", "re_enroll"):
        user_name = parameters.get("user_name")
        num_samples = int(parameters.get("num_samples", 3) or 3)
        duration = float(parameters.get("sample_duration_sec", 3.0) or 3.0)
        sample_files = parameters.get("sample_files")
        if player:
            player.write_log(f"AMATYA: Enrolling voice profile for '{user_name or 'user'}'...")
        res = auth.enroll_profile(
            user_name=user_name,
            samples=sample_files if isinstance(sample_files, list) else None,
            num_mic_samples=num_samples,
            sample_duration_sec=duration,
            overwrite=True,
        )
        if not res.get("ok"):
            return outcome.failed("voice_auth", res.get("error", "Voice enrollment failed."), data=res)
        return outcome.done(
            "voice_auth",
            result=f"Enrolled voice profile '{res['user_name']}' with {res['sample_count']} sample(s) "
                   f"(consistency={res['consistency_score']:.2f}, mean pitch={res['f0_mean_hz']} Hz).",
            data=res,
        )

    if action == "verify":
        user_name = parameters.get("user_name")
        threshold = parameters.get("threshold")
        duration = float(parameters.get("sample_duration_sec", 2.8) or 2.8)
        sample_files = parameters.get("sample_files")
        audio_input = None
        if isinstance(sample_files, list) and sample_files:
            import wave
            import numpy as np
            with wave.open(str(sample_files[0]), "rb") as wf:
                audio_input = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        res = auth.verify_speaker(
            audio=audio_input,
            claimed_user=user_name,
            threshold=float(threshold) if threshold is not None else None,
            duration_sec=duration,
        )
        if res.verified:
            return outcome.done("voice_auth", result=res.reason, data=res.to_dict())
        return outcome.failed("voice_auth", res.reason, data=res.to_dict())

    if action == "delete_profile":
        user_name = str(parameters.get("user_name", "") or "").strip()
        profiles = auth.list_profiles()
        if not user_name:
            from memory.memory_manager import load_memory
            mem_identity = load_memory().get("identity", {})
            rem_name = (
                mem_identity.get("name", {}).get("value")
                if isinstance(mem_identity.get("name"), dict)
                else str(mem_identity.get("name", ""))
            ).strip()

            matching = [p["user_name"] for p in profiles if rem_name and p["user_name"].lower() == rem_name.lower()]
            if matching:
                user_name = matching[0]
            elif len(profiles) == 1:
                user_name = profiles[0]["user_name"]
            elif len(profiles) == 0:
                return outcome.failed("voice_auth", "No voice profiles are currently enrolled.")
            elif confirmed:
                # If confirmed without specific name, delete primary or latest profile
                user_name = profiles[-1]["user_name"]
            else:
                names = [p["user_name"] for p in profiles]
                return outcome.ask(
                    "voice_auth",
                    f"Multiple voice profiles exist ({', '.join(names)}). Which profile should I delete?",
                    profiles=names,
                )

        if not confirmed:
            return outcome.ask(
                "voice_auth",
                f"Deleting voice profile '{user_name}' cannot be undone. Please confirm to delete.",
                user_name=user_name,
                requires_confirmation=True,
            )

        perm = check_permission(
            "delete_voice_profile",
            PermissionTier.SENSITIVE_SYSTEM,
            description=f"Delete enrolled voice profile '{user_name}'",
            pin=parameters.get("pin"),
            confirmed=True,
        )
        if not perm["allowed"]:
            return outcome.failed("voice_auth", perm["reason"], data=perm)

        ok, msg = auth.delete_profile(user_name)
        return outcome.done("voice_auth", result=msg) if ok else outcome.failed("voice_auth", msg)

    if action == "enable":
        save_voice_auth_enabled(True)
        return outcome.done(
            "voice_auth",
            result=f"Voice authentication enabled (threshold={get_voice_auth_threshold():.2f})."
        )

    if action == "disable":
        perm = check_permission(
            "disable_voice_auth",
            PermissionTier.SENSITIVE_SYSTEM,
            description="Disable speaker voice authentication requirement",
            pin=parameters.get("pin"),
            confirmed=confirmed,
        )
        if not perm["allowed"]:
            return outcome.failed("voice_auth", perm["reason"], data=perm)
        save_voice_auth_enabled(False)
        clear_session_auth()
        return outcome.done("voice_auth", result="Voice authentication disabled.")

    if action == "set_threshold":
        t = parameters.get("threshold")
        if t is None:
            return outcome.failed("voice_auth", "Please provide 'threshold' between 0.50 and 0.95.")
        save_voice_auth_threshold(float(t))
        return outcome.done("voice_auth", result=f"Speaker verification threshold set to {get_voice_auth_threshold():.2f}.")

    if action == "generate_challenge":
        ch = auth.generate_challenge()
        return outcome.done(
            "voice_auth",
            result=f"Anti-spoofing liveness challenge phrase: '{ch['phrase']}'. Please speak this phrase aloud.",
            data=ch,
        )

    if action == "verify_challenge":
        spoken = str(parameters.get("challenge_transcript", "") or "")
        ok, msg = auth.verify_challenge_transcript(spoken)
        return outcome.done("voice_auth", result=msg) if ok else outcome.failed("voice_auth", msg)

    if action == "set_pin":
        pin = str(parameters.get("pin", "") or "")
        ok, msg = set_pin(pin)
        return outcome.done("voice_auth", result=msg) if ok else outcome.failed("voice_auth", msg)

    if action == "verify_pin":
        pin = str(parameters.get("pin", "") or "")
        ok, msg = verify_pin(pin)
        return outcome.done("voice_auth", result=msg) if ok else outcome.failed("voice_auth", msg)

    if action == "clear_pin":
        pin = str(parameters.get("pin", "") or "")
        ok, msg = clear_pin(pin)
        return outcome.done("voice_auth", result=msg) if ok else outcome.failed("voice_auth", msg)

    if action == "set_autonomy":
        lvl = str(parameters.get("autonomy_level", "") or "").strip().lower()
        if lvl not in AUTONOMY_LEVELS:
            return outcome.failed(
                "voice_auth",
                f"Invalid autonomy_level '{lvl}'. Valid levels: {', '.join(AUTONOMY_LEVELS)}."
            )
        save_autonomy_level(lvl)
        try:
            from core.desktop_agent import get_desktop_agent
            agent = get_desktop_agent()
            if agent is not None:
                agent.set_autonomy(lvl)
        except Exception:
            pass
        return outcome.done("voice_auth", result=f"AMATYA autonomy level set to '{get_autonomy_level()}'.")

    if action == "configure_voice":
        changes = []
        if parameters.get("voice_name"):
            save_voice(str(parameters["voice_name"]))
            changes.append(f"voice={get_voice()}")
        if parameters.get("speech_speed") is not None:
            save_speech_speed(float(parameters["speech_speed"]))
            changes.append(f"speed={get_speech_speed():.2f}x")
        if parameters.get("speech_verbosity"):
            save_speech_verbosity(str(parameters["speech_verbosity"]))
            changes.append(f"verbosity={get_speech_verbosity()}")
        if parameters.get("speech_style"):
            save_speech_style(str(parameters["speech_style"]))
            changes.append(f"style={get_speech_style()}")
        if parameters.get("wake_word_model"):
            save_wake_word_model(str(parameters["wake_word_model"]))
            changes.append(f"wake_model={get_wake_word_model()}")
        if parameters.get("threshold") is not None:
            save_wake_word_threshold(float(parameters["threshold"]))
            changes.append(f"wake_threshold={get_wake_word_threshold():.2f}")
        if parameters.get("wake_word_enabled") is not None:
            save_wake_word_enabled(bool(parameters["wake_word_enabled"]))
            changes.append(f"wake_enabled={get_wake_word_enabled()}")
        if not changes:
            return outcome.failed("voice_auth", "No voice configuration parameters provided.")
        return outcome.done("voice_auth", result=f"Updated voice configuration: {', '.join(changes)}.")

    if action == "audit_log":
        entries = read_audit_log(limit=25)
        return outcome.done(
            "voice_auth",
            result=f"Retrieved {len(entries)} recent security audit log entries.",
            data={"entries": entries},
        )

    return outcome.failed("voice_auth", f"Unknown voice_auth action: '{action}'.")

