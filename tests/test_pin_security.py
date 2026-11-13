import os
import unittest
from unittest.mock import MagicMock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PyQt6.QtWidgets import QApplication, QLineEdit
    from gui.overlays import SecurityPinOverlay
    from gui.widgets import LogWidget
    HAS_QT_GUI = True
except (ImportError, Exception):
    HAS_QT_GUI = False

from core.security import (
    PermissionTier,
    check_permission,
    clear_pin,
    has_pin,
    redact_secrets,
    set_pin,
    verify_pin,
)
from core.confirm import bind, has_pending, pin_authorize, request, resolve, text_authorize


class TestPinSecurityAndMasking(unittest.TestCase):
    def setUp(self):
        self.mock_show = MagicMock()
        self.mock_hide = MagicMock()
        self.mock_log = MagicMock()
        self.mock_speak = MagicMock()
        self.mock_pin_mode = MagicMock()
        bind(
            show=self.mock_show,
            hide=self.mock_hide,
            log=self.mock_log,
            speak=self.mock_speak,
            pin_mode=self.mock_pin_mode,
        )
        set_pin("4321")

    def tearDown(self):
        resolve(False)

    def test_01_redact_secrets_masks_pin_variations(self):
        """PINs must never appear in logs or text outputs."""
        samples = [
            ("Authorise with PIN 4321", "Authorise with PIN **** (REDACTED)"),
            ("authorize with pin 9876", "authorize with pin **** (REDACTED)"),
            ("set_pin 1234", "set_pin **** (REDACTED)"),
            ("clear_pin 4321", "clear_pin **** (REDACTED)"),
            ("pin: 9999", "pin: **** (REDACTED)"),
            ("my pin is 5555", "my pin is **** (REDACTED)"),
            ("PIN 8888", "PIN **** (REDACTED)"),
        ]
        for raw, expected in samples:
            redacted = redact_secrets(raw)
            self.assertEqual(redacted, expected)
            self.assertNotIn("4321", redact_secrets("Authorise with PIN 4321"))
            self.assertNotIn("9876", redact_secrets("authorize with pin 9876"))

    def test_02_communication_log_sanitizes_pin(self):
        """LogWidget (append_log) and redact_secrets must automatically sanitize any incoming PIN."""
        raw_msg = "You: Authorise with PIN 4321"
        sanitized = redact_secrets(raw_msg)
        self.assertNotIn("4321", sanitized)
        self.assertIn("****", sanitized)

        if HAS_QT_GUI:
            app = QApplication.instance() or QApplication([])
            log_widget = LogWidget()
            log_widget.append_log(raw_msg)

            # Check queue
            queued = log_widget._queue
            self.assertTrue(len(queued) > 0 or log_widget._text != "")
            all_text = " ".join(queued) + " " + log_widget._text
            self.assertNotIn("4321", all_text)
            self.assertIn("****", all_text)

    def test_03_pin_authorization_handles_authorise_phrase(self):
        """'Authorise with PIN <digits>' must be recognized and authorized."""
        request("test_operation", "Test Operation", "Detail", lambda: "success")
        self.assertTrue(has_pending())

        ok, msg = pin_authorize("Authorise with PIN 4321")
        self.assertTrue(ok)
        self.assertIn("Security PIN verified", msg)
        self.assertFalse(has_pending())

    def test_04_text_authorize_handles_authorise_phrase(self):
        """text_authorize from input field processes 'Authorise with PIN <digits>'."""
        request("test_operation", "Test Operation", "Detail", lambda: "success")
        self.assertTrue(has_pending())

        res, msg = text_authorize("Authorise with PIN 4321")
        self.assertTrue(res)
        self.assertIn("Security PIN verified", msg)

    def test_05_initial_pin_bootstrap_avoids_deadlock(self):
        """When no PIN is configured, setting the initial PIN must not require an unconfigured PIN."""
        from core.security import _load_policy, _save_policy

        pol = _load_policy()
        salt = pol.pop("pin_salt", None)
        hsh = pol.pop("pin_hash", None)
        _save_policy(pol)
        try:
            self.assertFalse(has_pin())
            perm = check_permission("voice_auth:set_pin", PermissionTier.CRITICAL_SECURITY)
            self.assertTrue(perm["allowed"])
            self.assertFalse(perm["requires_pin"])
        finally:
            if salt and hsh:
                pol["pin_salt"] = salt
                pol["pin_hash"] = hsh
                _save_policy(pol)

    @unittest.skipUnless(HAS_QT_GUI, "PyQt6 / libEGL display runtime not installed in headless environment")
    def test_06_security_pin_overlay_masking(self):
        """SecurityPinOverlay masks all inputs with QLineEdit.EchoMode.Password."""
        app = QApplication.instance() or QApplication([])
        overlay = SecurityPinOverlay()

        self.assertTrue(overlay._masked)
        if overlay._cur_edit:
            self.assertEqual(overlay._cur_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(overlay._new_edit.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(overlay._confirm_edit.echoMode(), QLineEdit.EchoMode.Password)

        # Toggle mask
        overlay._toggle_mask()
        self.assertFalse(overlay._masked)
        self.assertEqual(overlay._new_edit.echoMode(), QLineEdit.EchoMode.Normal)

        overlay._toggle_mask()
        self.assertTrue(overlay._masked)
        self.assertEqual(overlay._new_edit.echoMode(), QLineEdit.EchoMode.Password)
        overlay.deleteLater()


if __name__ == "__main__":
    unittest.main()
