"""
tests/test_geolocation.py — Unit tests for AMATYA Device Geolocation Subsystem
"""
import unittest
from unittest.mock import patch

from core import geolocation


class TestGeolocation(unittest.TestCase):
    def test_01_get_device_location_structure(self):
        """Verify device location structure contains required keys."""
        loc = geolocation.get_device_location()
        self.assertIsInstance(loc, dict)
        self.assertIn("latitude", loc)
        self.assertIn("longitude", loc)
        self.assertIn("display_name", loc)
        self.assertIsInstance(loc["latitude"], float)
        self.assertIsInstance(loc["longitude"], float)

    def test_02_get_device_coordinates(self):
        """Verify coordinate tuple extraction."""
        lat, lon = geolocation.get_device_coordinates()
        self.assertIsInstance(lat, float)
        self.assertIsInstance(lon, float)
        self.assertGreaterEqual(lat, -90.0)
        self.assertLessEqual(lat, 90.0)
        self.assertGreaterEqual(lon, -180.0)
        self.assertLessEqual(lon, 180.0)

    def test_03_get_device_location_name(self):
        """Verify location name string."""
        name = geolocation.get_device_location_name()
        self.assertIsInstance(name, str)
        self.assertTrue(len(name) > 0)

    def test_04_manual_location_override(self):
        """Verify user can manually set and override device location."""
        custom = geolocation.set_device_location(
            city="Dharwad",
            region="Karnataka",
            country="India",
            latitude=15.4589,
            longitude=75.0078,
        )
        self.assertEqual(custom["city"], "Dharwad")
        self.assertEqual(custom["latitude"], 15.4589)
        self.assertEqual(custom["longitude"], 75.0078)
        self.assertIn("Dharwad", geolocation.get_device_location_name())

        # Cleanup/restore auto-detected location
        geolocation.get_device_location(force_refresh=True)

    def test_05_encrypted_storage_at_rest(self):
        """Verify that location cache on disk is encrypted and not clear-text JSON."""
        loc = geolocation.get_device_location()
        geolocation._save_location(loc)
        raw_text = geolocation.LOCATION_CACHE_FILE.read_text(encoding="utf-8").strip()
        # Must not start with cleartext JSON '{'
        self.assertFalse(raw_text.startswith("{"))
        # Must decrypt back to original location dictionary
        from core.security import decrypt_sensitive_data
        dec = decrypt_sensitive_data(raw_text)
        self.assertEqual(dec.get("display_name"), loc.get("display_name"))


if __name__ == "__main__":
    unittest.main()
