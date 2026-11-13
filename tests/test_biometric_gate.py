"""
tests/test_biometric_gate.py — Comprehensive test suite for Biometric Voice
Authentication and Secure PIN Fallback Gate.
"""

import time
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

from core import confirm
from core import security
from core import voice_auth


class TestBiometricVoiceAndPinGate(unittest.TestCase):
    def setUp(self):
        self.spoken = []
        self.logs = []
        self.shown = []
        self.hidden = []

        confirm.bind(
            show=lambda t, d: self.shown.append((t, d)),
            hide=lambda: self.hidden.append(True),
            log=lambda m: self.logs.append(m),
            speak=lambda s: self.spoken.append(s),
        )

        # Clear any pending confirmation
        with confirm._lock:
            confirm._pending = None

        # Reset security policy PIN state for clean test isolation
        pol = security._load_policy()
        pol.pop("pin_salt", None)
        pol.pop("pin_hash", None)
        pol.pop("pin_iterations", None)
        security._save_policy(pol)
        with security._LOCK:
            security._PIN_ATTEMPTS.clear()
            security._PIN_LOCKOUT_UNTIL = 0.0
            security._SESSION_STATE.pin_verified_at = 0.0

    def tearDown(self):
        with confirm._lock:
            confirm._pending = None
        # Clean up PIN
        pol = security._load_policy()
        pol.pop("pin_salt", None)
        pol.pop("pin_hash", None)
        pol.pop("pin_iterations", None)
        security._save_policy(pol)

    def test_01_initial_blank_pin(self):
        """Initial state has no PIN configured; user is informed to set one."""
        self.assertFalse(security.has_pin())

        # Request confirmation
        executed = []
        confirm.request("act_1", "Format Disk", "danger", run=lambda: executed.append(1))
        self.assertTrue(confirm.has_pending())

        # Attempting PIN authorization when none is configured informs user
        ok, msg = confirm.pin_authorize("1234")
        self.assertFalse(ok)
        self.assertIn("No security PIN is configured", msg)
        self.assertTrue(any("set a pin" in s.lower() for s in self.spoken))
        self.assertEqual(len(executed), 0)

    def test_02_spoken_pin_guard_strictly_rejects_audio_pin(self):
        """User speaking their PIN aloud must be blocked to prevent acoustic leakage."""
        confirm.request("act_2", "Reboot Server", "reboot", run=lambda: None)
        self.assertTrue(confirm.has_pending())

        # Try to speak PIN
        res = confirm.voice_authorize("my pin is 5432")
        self.assertFalse(res)
        self.assertTrue(confirm.has_pending())
        self.assertTrue(confirm.is_awaiting_pin())
        self.assertTrue(any("do not speak your pin" in s.lower() for s in self.spoken))

        # Try speaking raw digits
        self.spoken.clear()
        res2 = confirm.voice_authorize("pin 123456")
        self.assertFalse(res2)
        self.assertTrue(any("do not speak your pin" in s.lower() for s in self.spoken))

    def test_03_biometric_voice_matched_authorizes(self):
        """When voice acoustics match enrolled profile, command is authorized immediately."""
        executed = []
        confirm.request("act_3", "Launch Rocket", "rocket", run=lambda: executed.append("BOOM"))

        # Synthetic PCM audio frame (0.2s of 16kHz 16-bit PCM = 6400 bytes)
        dummy_audio = (np.sin(np.linspace(0, 100, 3200)) * 10000).astype(np.int16).tobytes()

        # Mock VoiceAuthenticator to simulate verified speaker
        mock_vr = voice_auth.VerificationResult(
            verified=True,
            matched_user="Commander",
            confidence=0.92,
            threshold=0.72,
            anti_spoof=voice_auth.AntiSpoofResult(
                passed=True, is_replay=False, replay_similarity=0.1,
                playback_artifact_score=0.1, voiced_ratio=0.5, snr_db=25.0, reason="OK"
            ),
            reason="Verified speaker Commander (confidence=0.92)",
        )

        with patch("core.confirm.get_voice_auth_enabled", return_value=True), \
             patch("core.confirm.get_voice_authenticator") as mock_get_auth:
            mock_auth = MagicMock()
            mock_auth.list_profiles.return_value = [{"user_name": "Commander"}]
            mock_auth.verify_speaker.return_value = mock_vr
            mock_get_auth.return_value = mock_auth

            res = confirm.voice_authorize("yes proceed, confirm it", audio=dummy_audio)
            self.assertTrue(res)
            self.assertFalse(confirm.has_pending())
            self.assertTrue(any("speaker identity verified" in s.lower() for s in self.spoken))

        time.sleep(0.05)
        self.assertEqual(executed, ["BOOM"])

    def test_04_biometric_voice_mismatch_fails_to_pin_fallback(self):
        """Impostor or unverified voice fails closed and transitions to PIN entry."""
        executed = []
        confirm.request("act_4", "Erase Database", "wipe", run=lambda: executed.append("wiped"))

        dummy_audio = (np.sin(np.linspace(0, 100, 3200)) * 10000).astype(np.int16).tobytes()

        mock_vr = voice_auth.VerificationResult(
            verified=False,
            matched_user="",
            confidence=0.35,
            threshold=0.72,
            anti_spoof=voice_auth.AntiSpoofResult(
                passed=True, is_replay=False, replay_similarity=0.1,
                playback_artifact_score=0.1, voiced_ratio=0.5, snr_db=20.0, reason="OK"
            ),
            reason="Confidence 0.35 below threshold 0.72",
        )

        with patch("core.confirm.get_voice_auth_enabled", return_value=True), \
             patch("core.confirm.get_voice_authenticator") as mock_get_auth:
            mock_auth = MagicMock()
            mock_auth.list_profiles.return_value = [{"user_name": "Commander"}]
            mock_auth.verify_speaker.return_value = mock_vr
            mock_get_auth.return_value = mock_auth

            res = confirm.voice_authorize("confirm execution", audio=dummy_audio)
            self.assertFalse(res)
            # Confirmation must STILL be pending and awaiting PIN
            self.assertTrue(confirm.has_pending())
            self.assertTrue(confirm.is_awaiting_pin())
            self.assertTrue(any("voice verification uncertain" in s.lower() for s in self.spoken))

        # Command must NOT have executed
        time.sleep(0.05)
        self.assertEqual(executed, [])

    def test_05_set_pin_and_authorize_via_text_pin(self):
        """User sets PIN via input field, then authorizes pending confirmation using PIN."""
        executed = []
        confirm.request("act_5", "Update Kernel", "kernel", run=lambda: executed.append("updated"))

        # Transition to awaiting PIN
        confirm.set_awaiting_pin(True)
        self.assertTrue(confirm.is_awaiting_pin())

        # User sets PIN via text command
        ok, msg = security.set_pin("8899")
        self.assertTrue(ok)
        self.assertTrue(security.has_pin())

        # Trying text "confirm" while awaiting PIN is rejected
        res_text, msg_text = confirm.text_authorize("confirm")
        self.assertFalse(res_text)
        self.assertIn("PIN required", msg_text)
        self.assertEqual(executed, [])

        # User types their PIN in the input field
        res_pin, msg_pin = confirm.text_authorize("8899")
        self.assertTrue(res_pin)
        self.assertIn("Security PIN verified", msg_pin)
        self.assertFalse(confirm.has_pending())

        time.sleep(0.05)
        self.assertEqual(executed, ["updated"])

    def test_06_invalid_pin_rate_limiting(self):
        """Invalid PINs are rejected and trigger rate limiting protection."""
        security.set_pin("4321")
        confirm.request("act_6", "Open Vault", "vault", run=lambda: None)

        # 1st wrong attempt
        ok, msg = confirm.pin_authorize("0000")
        self.assertFalse(ok)
        self.assertIn("Invalid PIN", msg)

        # Trigger lockout with multiple failed attempts
        for _ in range(4):
            confirm.pin_authorize("9999")

        ok_locked, msg_locked = confirm.pin_authorize("4321")
        self.assertFalse(ok_locked)
        self.assertIn("locked out", msg_locked.lower())

    def test_07_negative_cancellation_clears_pending(self):
        """Spoken or text cancellation aborts the pending confirmation."""
        executed = []
        confirm.request("act_7", "Wipe Cache", "cache", run=lambda: executed.append("cleared"))
        self.assertTrue(confirm.has_pending())

        res = confirm.voice_authorize("no, cancel that please")
        self.assertFalse(res)
        self.assertFalse(confirm.has_pending())
        self.assertTrue(any("cancelled" in s.lower() for s in self.spoken))

        time.sleep(0.05)
        self.assertEqual(executed, [])


if __name__ == "__main__":
    unittest.main()

