"""
tests/test_jarvis_skills.py — Rigorous Test Suite for Integrated JARVIS Skills
=============================================================================
Tests action loading, security authorization, and execution across:
  - cyber_sentry (tactical perimeter scan, port audit, firewall)
  - stark_lab (symbolic math, ballistic kinematics, orbital mechanics)
  - armor_diagnostics (hardware telemetry, thermal zones, battery health)
  - satellite_tracker (live ISS tracking, orbital parameters, space weather)
  - skill_runner & skills_registry (progressive disclosure and skills discovery)
"""
import unittest
from pathlib import Path

from core.action_loader import discover_actions
from core.skills_registry import discover_skills, get_skill, search_skills
from actions.cyber_sentry import execute as exec_cyber
from actions.stark_lab import execute as exec_stark
from actions.armor_diagnostics import execute as exec_armor
from actions.satellite_tracker import execute as exec_satellite
from actions.skill_runner import execute as exec_skills


class TestJarvisSkills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = discover_actions(Path("actions"))

    def test_01_action_loader_discovery_and_registration(self):
        """Verify all 5 JARVIS actions are auto-discovered and registered."""
        for name in ("cyber_sentry", "stark_lab", "armor_diagnostics", "satellite_tracker", "skill_runner"):
            self.assertTrue(self.registry.has(name), f"Action '{name}' failed auto-discovery")

    def test_02_cyber_sentry_perimeter_scan(self):
        """Test cyber_sentry perimeter scan, port audit, and threat scoring."""
        res = exec_cyber({"action": "perimeter_scan"})
        self.assertIn("status=done", res)
        self.assertIn("cyber_sentry", res)
        self.assertIn("Defense posture is", res)

        # Test port audit
        res_ports = exec_cyber({"action": "scan_ports"})
        self.assertIn("status=done", res_ports)

        # Test firewall audit
        res_fw = exec_cyber({"action": "audit_firewall"})
        self.assertIn("status=done", res_fw)

    def test_03_stark_lab_symbolic_math_and_physics(self):
        """Test stark_lab calculus, equations, projectile trajectory, and orbital mechanics."""
        # 1. Solve quadratic equation x^2 - 16 = 0
        res_solve = exec_stark({"action": "symbolic_math", "expression": "x**2 - 16", "operation": "solve", "variable": "x"})
        self.assertIn("status=done", res_solve)
        self.assertIn("-4", res_solve)
        self.assertIn("4", res_solve)

        # 2. Derivative of sin(x)*x
        res_diff = exec_stark({"action": "symbolic_math", "expression": "x*sin(x)", "operation": "diff", "variable": "x"})
        self.assertIn("status=done", res_diff)

        # 3. Integration of 2*x
        res_int = exec_stark({"action": "symbolic_math", "expression": "2*x", "operation": "integrate", "variable": "x"})
        self.assertIn("status=done", res_int)

        # 4. Ballistic Trajectory
        res_traj = exec_stark({"action": "trajectory", "velocity": 100.0, "angle": 45.0, "mass": 5.0})
        self.assertIn("status=done", res_traj)
        self.assertIn("Trajectory simulated", res_traj)

        # 5. Orbital Mechanics (Earth at 400km)
        res_orb = exec_stark({"action": "orbital", "altitude_km": 400.0, "body": "earth"})
        self.assertIn("status=done", res_orb)
        self.assertIn("Orbital velocity", res_orb)

    def test_04_armor_diagnostics_telemetry(self):
        """Test armor_diagnostics hardware metrics, thermal zones, and battery state."""
        res_armor = exec_armor({"action": "armor_status"})
        self.assertIn("status=done", res_armor)
        self.assertIn("Armor status:", res_armor)

        res_therm = exec_armor({"action": "thermal_map"})
        self.assertIn("status=done", res_therm)

        res_bat = exec_armor({"action": "battery_health"})
        self.assertIn("status=done", res_bat)

    def test_05_satellite_tracker_and_space_weather(self):
        """Test satellite_tracker live ISS telemetry and NOAA space weather."""
        res_iss = exec_satellite({"action": "track_satellite", "satellite": "iss"})
        self.assertIn("status=done", res_iss)
        self.assertIn("International Space Station", res_iss)

        res_sw = exec_satellite({"action": "space_weather"})
        self.assertIn("status=done", res_sw)
        self.assertIn("Space weather status:", res_sw)

    def test_06_skills_registry_and_runner(self):
        """Test skills discovery, progressive disclosure, and skill_runner actions."""
        skills = discover_skills()
        self.assertGreaterEqual(len(skills), 20, "Should have discovered at least 20 skills")

        # Verify new skills exist in registry
        for name in ("cyber-defense", "stark-calculator", "armor-diagnostics", "orbital-mechanics"):
            s = get_skill(name)
            self.assertIsNotNone(s, f"Skill '{name}' should be indexed")
            self.assertTrue(s.skill_file.exists())

        # Test search
        matches = search_skills("orbital")
        self.assertGreater(len(matches), 0)

        # Test skill_runner action execution
        res_list = exec_skills({"action": "list_skills"})
        self.assertIn("status=done", res_list)

        res_info = exec_skills({"action": "skill_info", "skill_name": "stark-calculator"})
        self.assertIn("status=done", res_info)

    def test_07_action_gateway_authorization(self):
        """Verify registry dispatch runs through core.security gateway without permission block."""
        res = self.registry.run("stark_lab", {"action": "orbital", "altitude_km": 500.0})
        self.assertNotIn("Permission Denied", res)
        self.assertIn("status=done", res)


if __name__ == "__main__":
    unittest.main()
