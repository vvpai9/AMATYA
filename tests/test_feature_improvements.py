"""
Unit tests for the Feature Improvements branch:
1. Wireframe Holographic Orb HUD (core/orb_hud.py).
2. Universal Plugin HUD Host (gui/plugin_hud.py).
3. Camera index override & browser page reuse (screen_processor.py, browser_control.py).
4. Local Companion Control Server (core/local_control.py).
5. Storage Guardian, Network Intelligence, and Downloads Organizer plugins.
6. HUD style configuration & switching (config_manager.py, computer_settings.py).
"""

import os
import unittest
import urllib.request
import json
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QPixmap, QColor

# Headless Qt application
_app = QApplication.instance()
if _app is None:
    _app = QApplication(["amatya_test", "-platform", "offscreen"])


class TestFeatureImprovements(unittest.TestCase):
    def test_01_orb_hud_geometry_and_paint(self):
        """Verify Wireframe Orb HUD mesh generation, subdivision, stepping, and painting."""
        from core.orb_hud import OrbHud, _icosahedron, _build_mesh

        verts, edges = _icosahedron(radius=1.0)
        self.assertEqual(len(verts), 12)
        self.assertEqual(len(edges), 30)

        d1_verts, d1_edges = _build_mesh(detail=1, radius=1.0)
        self.assertGreater(len(d1_verts), 12)
        self.assertGreater(len(d1_edges), 30)

        orb = OrbHud()
        orb.step(dt=0.033, amp=0.45, speaking=True, muted=False, state="SPEAKING")

        # Paint onto offscreen QPixmap
        pix = QPixmap(400, 400)
        pix.fill(QColor(0, 0, 0))
        painter = QPainter(pix)
        orb.paint(
            painter,
            cx=200.0,
            cy=200.0,
            r=120.0,
            main=QColor(0, 229, 255),
            acc=QColor(255, 183, 3),
            bg=QColor(4, 10, 16),
            amp=0.45,
            state="SPEAKING",
            muted=False,
            W=400.0,
            H=400.0,
        )
        painter.end()
        self.assertFalse(pix.isNull())

    def test_02_hud_style_config_and_cycling(self):
        """Verify config manager and computer_settings support the 'orb' centrepiece style."""
        from memory.config_manager import HUD_STYLES, get_hud_style, save_hud_style
        from actions.computer_settings import execute

        self.assertIn("orb", HUD_STYLES)

        orig_style = get_hud_style()
        try:
            save_hud_style("orb")
            self.assertEqual(get_hud_style(), "orb")

            # Test switching via computer_settings tool
            res = execute({"action": "set_hud_style", "value": "orb"})
            self.assertIn("Wireframe Holographic Orb", str(res))

            res_gyro = execute({"action": "set_hud_style", "value": "3d"})
            self.assertIn("3-D Gyroscope Reactor Core", str(res_gyro))
        finally:
            save_hud_style(orig_style)

    def test_03_plugin_hud_host_spec_rendering(self):
        """Verify PluginHudHost renders native declarative specs and updates state."""
        from gui.plugin_hud import PluginHudHost

        host = PluginHudHost()
        spec = {
            "title": "System Storage",
            "subtitle": "Partition Overview",
            "metrics": [
                {"label": "ROOT", "value": "45%", "tone": "cyan"},
                {"label": "HOME", "value": "62%", "tone": "amber"},
            ],
            "table": {
                "headers": ["Drive", "Used", "Total"],
                "rows": [["/dev/sda1", "120 GB", "500 GB"]],
            },
            "footer": "All systems nominal",
        }

        ok = host.show_view(
            plugin_id="storage_guardian",
            title="STORAGE GUARDIAN",
            content=spec,
            content_type="spec",
            replace=True,
        )
        self.assertTrue(ok)
        self.assertTrue(host.is_active())

        snap = host.get_state_snapshot()
        self.assertTrue(snap["active"])
        self.assertEqual(snap["plugin_id"], "storage_guardian")
        self.assertEqual(snap["content_type"], "spec")

        # Close view
        host.close_view("storage_guardian")
        self.assertFalse(host.is_active())
        host.cleanup()

    def test_04_camera_index_and_browser_page_reuse(self):
        """Verify camera index environment override and Playwright page reuse."""
        from actions.screen_processor import _get_camera_index
        from actions.browser_control import _BrowserSession

        # Test AMATYA_CAMERA_INDEX env var
        with patch.dict(os.environ, {"AMATYA_CAMERA_INDEX": "3"}):
            self.assertEqual(_get_camera_index(), 3)

        # Test JARVIS_CAMERA_INDEX fallback env var
        with patch.dict(os.environ, {"JARVIS_CAMERA_INDEX": "5"}, clear=False):
            if "AMATYA_CAMERA_INDEX" in os.environ:
                del os.environ["AMATYA_CAMERA_INDEX"]
            self.assertEqual(_get_camera_index(), 5)

        # Test browser session instantiation
        session = _BrowserSession("chromium")
        self.assertIsNotNone(session)
        self.assertEqual(session.browser_name, "chromium")

    def test_05_local_control_loopback_server(self):
        """Verify LocalControlServer loopback HTTP endpoints on 127.0.0.1:8765."""
        from core.local_control import LocalControlServer, PORT

        state = {"muted": False, "speaking": False, "state": "IDLE"}
        muted_flag = [False]
        interrupted_flag = [False]

        def _toggle_mute():
            muted_flag[0] = not muted_flag[0]
            state["muted"] = muted_flag[0]

        def _interrupt():
            interrupted_flag[0] = True

        server = LocalControlServer(
            get_state=lambda: state,
            on_mute_toggle=_toggle_mute,
            on_interrupt=_interrupt,
        )

        started = server.start()
        if started:
            try:
                # GET /status
                req = urllib.request.Request(f"http://127.0.0.1:{PORT}/status")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                    self.assertEqual(data.get("state"), "IDLE")

                # POST /mute
                req_mute = urllib.request.Request(f"http://127.0.0.1:{PORT}/mute", data=b"{}", method="POST")
                with urllib.request.urlopen(req_mute, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                    self.assertTrue(data.get("muted"))
                self.assertTrue(muted_flag[0])

                # POST /interrupt
                req_int = urllib.request.Request(f"http://127.0.0.1:{PORT}/interrupt", data=b"{}", method="POST")
                with urllib.request.urlopen(req_int, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                    self.assertTrue(data.get("ok"))
                self.assertTrue(interrupted_flag[0])
            finally:
                server.stop()

    def test_06_storage_guardian_and_network_intelligence_plugins(self):
        """Verify storage_guardian and network_intelligence plugins execute without raising."""
        from plugins.storage_guardian import run as run_storage
        from plugins.network_intelligence import run as run_network
        from plugins.downloads_organizer import run as run_downloads

        # Storage Guardian
        res_storage = run_storage({"action": "status"})
        self.assertIsInstance(res_storage, str)
        self.assertTrue(len(res_storage) > 0)

        # Network Intelligence
        res_network = run_network({"action": "status"})
        self.assertIsInstance(res_network, str)
        self.assertTrue(len(res_network) > 0)

        # Downloads Organizer
        res_downloads = run_downloads({"action": "status"})
        self.assertIsInstance(res_downloads, str)
        self.assertTrue(len(res_downloads) > 0)

    def test_07_google_calendar_and_drive_plugins_safe_fallbacks(self):
        """Verify calendar and drive plugins return informative guidance when unauthenticated."""
        from plugins.google_calendar import run as run_calendar
        from plugins.drive_search import run as run_drive

        res_cal = run_calendar({"operation": "read"})
        self.assertIn("Google Calendar", res_cal)

        res_drive = run_drive({"query": "report"})
        self.assertIn("Drive", res_drive)


if __name__ == "__main__":
    unittest.main()
