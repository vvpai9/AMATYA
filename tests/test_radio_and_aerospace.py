"""
tests/test_radio_and_aerospace.py — Tests for Radio Discovery, Playback, and Orbital/Flight Tracking
"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core import radio_aerospace
from core.action_loader import discover_actions


class TestRadioAndAerospace(unittest.TestCase):
    def tearDown(self):
        radio_aerospace.stop_radio()

    def test_01_radio_discovery(self):
        """Verify discovery of online and curated radio stations."""
        stations = radio_aerospace.search_radio_stations("classical", limit=5)
        self.assertTrue(len(stations) > 0)
        first = stations[0]
        self.assertIn("name", first)
        self.assertIn("url", first)
        self.assertTrue(first["url"].startswith("http"))

    def test_02_radio_playback_lifecycle(self):
        """Test play, status inspection, and stopping of a radio stream."""
        ok, msg = radio_aerospace.play_radio("BBC World Service", volume=75)
        self.assertTrue(ok)
        self.assertIn("BBC World Service", msg)

        status = radio_aerospace.get_radio_status()
        self.assertIn("volume", status)
        self.assertEqual(status["volume"], 75)

        # Stop radio
        stop_msg = radio_aerospace.stop_radio()
        self.assertIn("Stopped", stop_msg)
        self.assertFalse(radio_aerospace.get_radio_status()["is_playing"])

    def test_03_iss_trajectory(self):
        """Verify live International Space Station telemetry."""
        iss = radio_aerospace.get_iss_trajectory(user_lat=40.71, user_lon=-74.00)
        self.assertEqual(iss["target"], "International Space Station (ISS)")
        self.assertEqual(iss["norad_id"], 25544)
        self.assertIn("latitude", iss)
        self.assertIn("longitude", iss)
        self.assertGreater(iss["altitude_km"], 350.0)
        self.assertGreater(iss["velocity_kmh"], 25000.0)

    def test_04_satellite_constellation_telemetry(self):
        """Verify orbital tracking of satellites and space stations."""
        sats = radio_aerospace.get_satellite_trajectories()
        self.assertGreaterEqual(len(sats), 3)
        targets = [s["target"] for s in sats]
        self.assertTrue(any("ISS" in t for t in targets))
        self.assertTrue(any("Tiangong" in t for t in targets))

    def test_05_flight_tracking(self):
        """Verify tracking of aircraft flight trajectory by callsign."""
        flight = radio_aerospace.track_flight("UAL100")
        self.assertTrue(flight["found"])
        self.assertIn("callsign", flight)
        self.assertIn("altitude_ft", flight)
        self.assertIn("velocity_kmh", flight)
        self.assertIn("latitude", flight)

    def test_06_overhead_airspace(self):
        """Verify scanning of local airspace for overhead aircraft."""
        flights = radio_aerospace.get_overhead_flights(user_lat=37.77, user_lon=-122.41)
        self.assertTrue(isinstance(flights, list))
        self.assertTrue(len(flights) > 0)
        f = flights[0]
        self.assertIn("callsign", f)
        self.assertIn("altitude_ft", f)

    def test_07_action_dispatch_and_hud(self):
        """Verify action dispatch through ActionRegistry and HUD presentation."""
        registry = discover_actions(Path("actions"))
        self.assertTrue(registry.has("radio_and_aerospace"))

        mock_player = MagicMock()

        # Test Radio Discovery Mode
        res_radio = registry.run(
            "radio_and_aerospace",
            {"mode": "radio", "radio_action": "search", "station": "jazz"},
            ctx={"player": mock_player},
        )
        self.assertIn("radio stations", res_radio.lower())
        mock_player.show_content.assert_called()
        self.assertIn("Radio Stations", mock_player.show_content.call_args[0][0])

        # Test Aerospace Trajectory Mode
        mock_player.reset_mock()
        res_aero = registry.run(
            "radio_and_aerospace",
            {"mode": "aerospace", "aerospace_target": "iss"},
            ctx={"player": mock_player},
        )
        self.assertIn("space station", res_aero.lower())
        mock_player.show_content.assert_called()
        self.assertIn("ISS", mock_player.show_content.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
