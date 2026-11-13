"""
tests/test_tv_automation.py — Unit Tests for AMATYA Android TV Automation Subsystem.
===================================================================================
Tests cross-platform Android TV v2 remote controller, unconfigured TV prompts,
key aliases, and device manager integration.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from actions.device_control import execute
from core.device_manager import get_device_manager
from core.tv_control import (
    KEY_ALIASES,
    TV_APP_MAP,
    AndroidTVController,
    async_finish_pairing_flow,
    async_start_pairing_flow,
    is_tv_configured,
)


class TestTVAutomation(unittest.TestCase):
    def setUp(self):
        self.dm = get_device_manager()

    def test_key_aliases_and_apps(self):
        """Verify standard key aliases and app package mappings."""
        self.assertEqual(KEY_ALIASES["UP"], "DPAD_UP")
        self.assertEqual(KEY_ALIASES["DOWN"], "DPAD_DOWN")
        self.assertEqual(KEY_ALIASES["SELECT"], "DPAD_CENTER")
        self.assertEqual(KEY_ALIASES["ENTER"], "ENTER")
        self.assertEqual(KEY_ALIASES["POWER"], "POWER")
        self.assertEqual(KEY_ALIASES["MUTE"], "VOLUME_MUTE")

        self.assertEqual(TV_APP_MAP["vlc"], "org.videolan.vlc")
        self.assertEqual(TV_APP_MAP["youtube"], "com.google.android.youtube.tv")
        self.assertEqual(TV_APP_MAP["netflix"], "com.netflix.ninja")
        self.assertEqual(TV_APP_MAP["prime_video"], "com.amazon.amazonvideo.livingroom")

    def test_is_tv_configured(self):
        """Verify is_tv_configured returns False for unconfigured devices and True for valid setups."""
        self.assertFalse(is_tv_configured(None))
        self.assertFalse(is_tv_configured({}))
        self.assertFalse(is_tv_configured({"ip_address": "", "paired": False}))
        self.assertFalse(is_tv_configured({"ip_address": "192.168.1.200", "paired": True}))

        with tempfile.TemporaryDirectory() as tmp:
            cert_p = Path(tmp) / "cert.pem"
            key_p = Path(tmp) / "key.pem"
            cert_p.write_text("DUMMY_CERT")
            key_p.write_text("DUMMY_KEY")

            configured_dev = {
                "ip_address": "192.168.1.50",
                "paired": True,
                "cert_file": str(cert_p),
                "key_file": str(key_p),
            }
            self.assertTrue(is_tv_configured(configured_dev))

            unpaired_dev = dict(configured_dev, paired=False)
            self.assertFalse(is_tv_configured(unpaired_dev))

    def test_unconfigured_tv_prompt(self):
        """When TV is not yet configured, device_control must prompt the user with setup instructions."""
        test_id = "test_unconfigured_living_room_tv"
        self.dm._devices[test_id] = {
            "device_id": test_id,
            "name": "Unconfigured TV",
            "type": "android_tv",
            "configured": False,
            "paired": False,
            "ip_address": "",
        }
        try:
            res = execute({"action": "tv_power", "device": test_id})
            self.assertIn("No Android TV is configured yet", str(res))
            self.assertIn("action='setup_tv'", str(res))
        finally:
            self.dm._devices.pop(test_id, None)

    @patch("core.tv_control.AndroidTVRemote")
    def test_pairing_flows(self, mock_remote_cls):
        """Test start and finish pairing flows."""
        mock_instance = MagicMock()
        mock_instance.async_generate_cert_if_missing = AsyncMock(return_value=True)
        mock_instance.async_start_pairing = AsyncMock(return_value=None)
        mock_instance.async_finish_pairing = AsyncMock(return_value=None)
        mock_remote_cls.return_value = mock_instance

        # 1. Start pairing
        ok, msg = asyncio.run(async_start_pairing_flow(host="192.168.1.75"))
        self.assertTrue(ok)
        self.assertIn("Pairing initiated", msg)
        self.assertIn("192.168.1.75", msg)

        # 2. Finish pairing
        ok_fin, msg_fin, host = asyncio.run(async_finish_pairing_flow("ABC123"))
        self.assertTrue(ok_fin)
        self.assertIn("Successfully paired", msg_fin)
        self.assertEqual(host, "192.168.1.75")


if __name__ == "__main__":
    unittest.main()
