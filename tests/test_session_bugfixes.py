"""
tests/test_session_bugfixes.py — Regression tests for AMATYA's 11 System Issue Fixes
===================================================================================
1. Local Time Reporting
2. VAD / Turn Latency defaults
3. Text-Only Interaction mode
4. Synthesized Audio Cues & Initialisation boot sound
5. Document Path Resolution & Comparison
6. Live Phone Battery Query via D-Bus / KDE Connect
7. Default File Manager Dynamic Resolution (Dolphin / Explorer / Finder)
8. Android TV Control & atvremote integration
9. KDE Connect Generic Target Resolution ('phone' -> Android Phone)
10. PPT Slide Density Formatting & Condensing (Rule of 4)
11. Table Export Resilience & User Directory Resolution
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["AMATYA_TEST_MODE"] = "1"

from actions import computer_settings, device_control, knowledge_base, creator
from core.appidentity import launcher_name
from core.audio_cues import (
    play_initialisation_sound,
    play_wake_chime,
    play_task_complete_chime,
    _synthesize_boot_chime,
)
from core.device_manager import get_device_manager, query_kdeconnect_battery
from core.doc_generator import _clean_and_condense_slide_lines, generate_document
from core.document_intelligence import (
    DocumentParser,
    DocumentTable,
    export_tables_xlsx,
    export_table_csv,
    resolve_user_path,
    resolve_user_output_path,
)
from core.phone_ring import kdeconnect_ring
from memory.config_manager import get_turn_tuning


class TestSessionBugfixes(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="amatya_bugfix_test_")
        self.addCleanup(lambda: shutil.rmtree(self.test_dir, ignore_errors=True))

    def test_01_local_time_reporting(self):
        """Issue 1: Verify computer_settings(action='get_time') returns local time with timezone."""
        mock_player = MagicMock()
        res = computer_settings.execute({"action": "get_time"}, player=mock_player)
        self.assertIn("status=done", res)
        self.assertIn("current local time is", res)
        mock_player.write_log.assert_called_once()
        log_arg = mock_player.write_log.call_args[0][0]
        self.assertIn("⏰", log_arg)

    def test_02_vad_turn_tuning_default(self):
        """Issue 2: Verify turn_tuning restores Mark-LVII defaults (enabled=False, silence_ms=550)."""
        tt = get_turn_tuning()
        self.assertFalse(tt["enabled"])
        self.assertEqual(tt["silence_ms"], 550)
        self.assertEqual(tt["prefix_ms"], 150)
        self.assertEqual(tt["end_sensitivity"], "high")

    def test_03_text_only_mode_toggle(self):
        """Issue 3: Verify computer_settings toggles text-only interaction on and off."""
        mock_player = MagicMock()
        mock_player.text_only = False

        res_on = computer_settings.execute({"action": "text_only_mode"}, player=mock_player)
        self.assertIn("status=done", res_on)
        self.assertIn("Text-only mode ENABLED", res_on)
        self.assertTrue(mock_player.text_only)

        res_off = computer_settings.execute({"action": "voice_mode"}, player=mock_player)
        self.assertIn("status=done", res_off)
        self.assertIn("Voice mode ENABLED", res_off)
        self.assertFalse(mock_player.text_only)

    def test_04_audio_cues_synthesize_and_execute(self):
        """Issue 4: Verify synthesized audio cues synthesize without OS/NameError."""
        data = _synthesize_boot_chime()
        self.assertGreater(len(data), 1000)
        # Verify play calls do not crash
        play_initialisation_sound(block=False)
        play_wake_chime()
        play_task_complete_chime()

    def test_05_resolve_user_path_knowledge_base(self):
        """Issue 5: Verify relative paths like Desktop/... resolve against user's home/Desktop."""
        home = Path.home()
        desktop = home / "Desktop"
        resolved = resolve_user_path("Desktop/Amatya_voice_test/alpha.txt")
        if (desktop / "Amatya_voice_test" / "alpha.txt").exists():
            self.assertEqual(resolved, desktop / "Amatya_voice_test" / "alpha.txt")
        else:
            self.assertEqual(resolved, (home / "Desktop/Amatya_voice_test/alpha.txt").resolve())

    def test_06_phone_battery_live_query(self):
        """Issue 6: Verify phone_status queries live battery and updates device status."""
        mgr = get_device_manager()
        res = mgr.phone_action("status", device_query="phone")
        self.assertTrue(res["ok"])
        self.assertIn("battery_pct", res["status"])
        self.assertIsInstance(res["status"]["battery_pct"], int)


    def test_10_ppt_slide_density_and_condense(self):
        """Issue 10: Verify PPT slide bullet condensing enforces executive brevity."""
        dense_input = [
            "**Key Finding One:** This is a very long, complex paragraph with multiple sentences. It contains far too much verbose information to display cleanly on a slide presentation.",
            "• Point Two: Accelerate adoption of distributed multi-agent systems and real-time reasoning tools.",
            "3. Operational latency must be kept under 350 milliseconds across all audio capture cycles.",
            "4. Resource allocation remains well within budget thresholds.",
            "5. Fifth point that should be capped under Rule of 4.",
            "6. Sixth point that should definitely not overflow the slide.",
        ]
        condensed = _clean_and_condense_slide_lines(dense_input, max_total=4)
        self.assertLessEqual(len(condensed), 4)
        for bullet in condensed:
            self.assertNotIn("**", bullet)
            self.assertNotIn("•", bullet)
            words = bullet.split()
            self.assertLessEqual(len(words), 16)

    def test_11_table_export_resilience_and_paths(self):
        """Issue 11: Verify export_tables_xlsx handles empty tables without openpyxl crash."""
        empty_xlsx = Path(self.test_dir) / "empty_tables.xlsx"
        p = export_tables_xlsx([], empty_xlsx)
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 0)

        out_resolved = resolve_user_output_path("Desktop/my_report.xlsx")
        self.assertTrue(str(out_resolved).startswith(str(Path.home())))

    def test_12_security_refusal_invariants(self):
        """Issue 12: Verify security protocols and voice authentication strictly refuse disablement."""
        from core.security import PermissionTier, check_permission
        from actions import voice_auth

        # 1. check_permission refusal
        perm = check_permission("disable_voice_auth", PermissionTier.SENSITIVE_SYSTEM)
        self.assertFalse(perm["allowed"])
        self.assertIn("REFUSAL", perm["reason"])

        perm_sec = check_permission("turn_off_security", PermissionTier.CRITICAL_SECURITY)
        self.assertFalse(perm_sec["allowed"])
        self.assertIn("REFUSAL", perm_sec["reason"])

        # 2. voice_auth action='disable' execution refusal
        res = voice_auth.execute({"action": "disable"})
        self.assertIn("status=failed", res)
        self.assertIn("Refusal", res)

    def test_13_terminal_to_konsole_mapping(self):
        """Issue 13: Verify 'terminal' resolves to 'konsole' on Linux desktop."""
        from core import appidentity
        term = appidentity.launcher_name("terminal")
        self.assertEqual(term, "konsole")
        variants = appidentity.spelling_variants("terminal")
        self.assertIn("konsole", variants)


if __name__ == "__main__":
    unittest.main()
