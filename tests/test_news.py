"""
tests/test_news.py — Comprehensive tests for AMATYA World News & Outage Subsystem
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core import news_service
from core.action_loader import discover_actions


class TestNewsAndOutages(unittest.TestCase):
    def setUp(self):
        # Reset preferences
        self.prefs = news_service.get_news_preferences()

    def test_01_preferences_customization(self):
        """Verify user can customize preferred news topics."""
        custom_topics = ["politics", "tech", "sports"]
        updated = news_service.set_user_topics(custom_topics)
        self.assertTrue(updated["initialized"])
        self.assertEqual(updated["topics"], custom_topics)

        # Retrieve again
        loaded = news_service.get_news_preferences()
        self.assertEqual(loaded["topics"], custom_topics)

    def test_02_topic_news_fetching(self):
        """Verify news fetching for global and specific topics."""
        politics = news_service.fetch_topic_news("politics")
        self.assertTrue(isinstance(politics, list))
        if politics:
            first = politics[0]
            self.assertIn("title", first)
            self.assertIn("link", first)

        tech = news_service.fetch_topic_news("tech")
        self.assertTrue(isinstance(tech, list))

    def test_03_duration_formatter(self):
        """Verify human-readable duration calculations for outages."""
        self.assertEqual(news_service._format_duration(45), "45s")
        self.assertEqual(news_service._format_duration(150), "2m 30s")
        self.assertEqual(news_service._format_duration(3700), "1h 1m")

    def test_04_outage_monitoring(self):
        """Verify service status checking and outage telemetry."""
        # Check a known reliable domain
        status = news_service.check_service_status("Google", "google.com")
        self.assertEqual(status["service"], "Google")
        self.assertIn("is_up", status)
        self.assertIn("latency_ms", status)

    def test_05_news_briefing_generation(self):
        """Verify compilation of news briefing, HUD formatting, and spoken output."""
        mock_player = MagicMock()
        briefing = news_service.generate_news_briefing(
            period="morning",
            topics=["politics", "tech"],
            player=mock_player,
        )

        self.assertEqual(briefing["period"], "morning")
        self.assertIn("spoken", briefing)
        self.assertIn("markdown", briefing)
        self.assertIn("AMATYA Morning Intelligence Briefing", briefing["markdown"])
        # Verify HUD presentation
        mock_player.show_content.assert_called_once()
        title_arg, md_arg = mock_player.show_content.call_args[0]
        self.assertIn("News Briefing", title_arg)
        self.assertIn("AMATYA Morning Intelligence Briefing", md_arg)

    def test_06_action_tool_dispatch(self):
        """Test action dispatch through ActionRegistry."""
        registry = discover_actions(Path("actions"))
        self.assertTrue(registry.has("news_briefing"))

        # Test configure topics
        res_cfg = registry.run("news_briefing", {"configure_topics": ["geopolitics", "science"]})
        self.assertIn("geopolitics", res_cfg)

        # Test outage-only check
        res_outage = registry.run("news_briefing", {"check_outages_only": True})
        self.assertTrue("operational" in res_outage.lower() or "alert" in res_outage.lower())

    def test_07_downdetector_outage_fetch(self):
        """Verify Downdetector incident fetching and correlation."""
        incidents = news_service.fetch_downdetector_outages()
        self.assertIsInstance(incidents, list)
        if incidents:
            first = incidents[0]
            self.assertIn("title", first)
            self.assertIn("source", first)

    def test_08_flightradar24_integration(self):
        """Verify Flightradar24 overhead airspace and flight trajectory tracking."""
        from core import radio_aerospace
        # Overhead flights
        overhead = radio_aerospace.get_overhead_flights(user_lat=12.9187, user_lon=74.8598, radius_deg=2.0)
        self.assertIsInstance(overhead, list)
        self.assertGreater(len(overhead), 0)
        self.assertIn("callsign", overhead[0])

        # Track flight query
        tr = radio_aerospace.track_flight("AI101")
        self.assertTrue(tr.get("found"))
        self.assertIn("callsign", tr)
        self.assertIn(tr.get("source"), ("Flightradar24", "OpenSky Network", "Estimated Trajectory"))


if __name__ == "__main__":
    unittest.main()
