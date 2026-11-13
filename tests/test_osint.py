"""
tests/test_osint.py — Comprehensive tests for AMATYA OSINT & Reconnaissance Subsystem
"""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions import osint_tools
from core.action_loader import discover_actions
from core.tasks.agents import load as load_agents


class TestOSINTSubsystem(unittest.TestCase):
    def test_01_agent_profile_loading(self):
        """Verify the OSINT Investigator agent profile loads cleanly."""
        agents = load_agents([Path("agents")])
        self.assertIn("osint_investigator", agents)
        prof = agents["osint_investigator"]
        self.assertEqual(prof.name, "osint_investigator")
        self.assertEqual(prof.mode, "research")
        self.assertIn("osint_investigate", prof.tools)
        self.assertTrue(len(prof.instructions) > 50)

    def test_02_domain_analysis(self):
        """Test domain intelligence extraction."""
        res = osint_tools.analyze_domain("example.com")
        self.assertEqual(res["domain"], "example.com")
        self.assertIn("dns", res)
        self.assertIn("security_headers", res)
        # Should resolve A records or have dns dict
        self.assertTrue(isinstance(res["dns"], dict))

    def test_03_ip_telemetry(self):
        """Test IP intelligence and geolocation structure."""
        res = osint_tools.analyze_ip("8.8.8.8")
        self.assertEqual(res["ip"], "8.8.8.8")
        self.assertIn("geolocation", res)
        self.assertIn("network", res)
        # 8.8.8.8 should have Google or DNS in network or reverse DNS
        self.assertTrue(isinstance(res["network"], dict))

    def test_04_email_intelligence(self):
        """Test email syntax validation and disposable detection."""
        # Valid email
        good = osint_tools.analyze_email("user@gmail.com")
        self.assertTrue(good["valid_syntax"])
        self.assertEqual(good["domain"], "gmail.com")
        self.assertFalse(good["is_disposable"])

        # Disposable email
        trash = osint_tools.analyze_email("temp@mailinator.com")
        self.assertTrue(trash["valid_syntax"])
        self.assertTrue(trash["is_disposable"])

        # Invalid syntax
        bad = osint_tools.analyze_email("not-an-email")
        self.assertFalse(bad["valid_syntax"])

    def test_05_phone_intelligence(self):
        """Test phone number parsing and carrier metadata."""
        # Standard US number
        res = osint_tools.analyze_phone("+12024561111")
        self.assertTrue(res["valid"])
        self.assertEqual(res["e164_format"], "+12024561111")
        self.assertIn("country_code", res)
        self.assertIn("timezones", res)

    def test_06_file_metadata_and_hashes(self):
        """Test file hash generation and forensic metadata extraction."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"TOP SECRET OSINT DOSSIER")
            f_path = f.name

        try:
            res = osint_tools.analyze_file_metadata(f_path)
            self.assertEqual(res["file_name"], Path(f_path).name)
            self.assertIn("hashes", res)
            self.assertEqual(len(res["hashes"]["sha256"]), 64)
            self.assertEqual(len(res["hashes"]["md5"]), 32)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_07_action_registry_dispatch(self):
        """Test action dispatch through ActionRegistry and HUD presentation."""
        registry = discover_actions(Path("actions"))
        self.assertTrue(registry.has("osint_investigate"))

        mock_player = MagicMock()
        summary = registry.run(
            "osint_investigate",
            {"target": "example.com", "category": "domain"},
            ctx={"player": mock_player},
        )
        self.assertIn("example.com", summary.lower())
        # Verify player.show_content was invoked with HUD report
        mock_player.show_content.assert_called_once()
        call_args = mock_player.show_content.call_args[0]
        self.assertIn("OSINT", call_args[0])
        self.assertIn("DNS Resolution", call_args[1])


if __name__ == "__main__":
    unittest.main()
