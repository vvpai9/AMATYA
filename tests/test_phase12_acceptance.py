"""
tests/test_phase12_acceptance.py — Comprehensive Acceptance Test Suite for AMATYA Phase 12.
=============================================================================================
Validates all Phase 12 objectives:
  - Objective A: Persistent Layered Personal Memory (Episodic, Semantic, Contradiction Detection, Purge, Disablement)
  - Objective B: Continuous Contextual Intelligence & Ambiguity Resolution
  - Objective C & D: Adaptive Workflow Engine, Routine Approval Gates & Sequence Learning
  - Objective E: Proactive Intelligence, 5 Notification Tiers & Quiet Hours Policy
  - Objective H: Device UUIDs, Dynamic IP Resolution & Real Device Integration
  - Objective I: Resource-Aware Privacy Modes ('strict_local' blocking cloud leakage)
  - Objective J: Memory-Aware CREATOR & Project Profiles (memory/project_profiles.json)
  - Objective K & L: System Reliability Diagnostics & Holographic Telemetry HUD
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.context_manager import ContextManager, get_context_manager
from core.creator import ProjectProfileManager, get_creator_engine
from core.device_manager import get_device_manager
from core.diagnostics import diagnose_all_subsystems, format_command_centre_hud, gather_system_telemetry
from core.memory_engine import MemoryEngine, SemanticFact, get_memory_engine
from core.model_router import get_router
from core.proactive_engine import (
    NotificationPriority,
    ProactiveAlert,
    ProactiveIntelligenceEngine,
    get_proactive_engine,
)
from core.workflow_engine import WorkflowEngine, WorkflowRoutine, get_workflow_engine


class TestPhase12Acceptance(unittest.TestCase):
    """Rigorous Phase 12 acceptance testing verifying persistent intelligence and autonomy."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="amatya_phase12_test_")
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── Test 1: Layered Memory, Contradictions, and Deletion Purge ───────────

    def test_01_layered_memory_contradictions_and_purge(self):
        """Verify Objective A: Layered memory, contradiction detection, and permanent purge."""
        mem_file = self.temp_path / "semantic_memory.json"
        engine = MemoryEngine(storage_path=mem_file)

        # 1. Store a confirmed user fact
        res1 = engine.store_fact(
            key="favorite_editor",
            value="Neovim",
            category="preferences",
            provenance="user_stated",
            confidence=0.95,
        )
        self.assertTrue(res1["ok"])
        self.assertEqual(res1["action"], "stored")

        # 2. Contradiction detection: inferring conflicting fact with lower confidence
        contra = engine.detect_contradiction("favorite_editor", "VS Code")
        self.assertTrue(contra["contradiction"])
        self.assertEqual(contra["existing_value"], "Neovim")

        # 3. Correct fact explicitly
        res2 = engine.correct_fact(
            key="favorite_editor",
            new_value="VS Code with Vim Keybindings",
            reason="User switched editors",
        )
        self.assertTrue(res2["ok"])
        fact = engine.get_fact("favorite_editor")
        self.assertIsNotNone(fact)
        self.assertEqual(fact.value, "VS Code with Vim Keybindings")

        # 4. Search memory
        hits = engine.search_memories("editor")
        self.assertTrue(len(hits) >= 1)
        self.assertEqual(hits[0].key, "favorite_editor")

        # 5. Delete and purge memory
        del_res = engine.delete_memory("favorite_editor")
        self.assertTrue(del_res)
        self.assertIsNone(engine.get_fact("favorite_editor"))

        # 6. Memory disablement toggle
        engine.set_memory_enabled(False)
        self.assertFalse(engine.is_memory_enabled())
        res_disabled = engine.store_fact(key="temp_note", value="secret info")
        self.assertFalse(res_disabled["ok"])
        self.assertIn("disabled", res_disabled["message"])

    # ── Test 2: Continuous Contextual Intelligence & Ambiguity ───────────────

    def test_02_contextual_intelligence_and_ambiguity(self):
        """Verify Objective B: Pronoun resolution, previous task references, and ambiguity questions."""
        cm = ContextManager()

        # Record turns and task outcomes
        cm.record_turn("user", "Generate the annual revenue summary presentation.")
        cm.record_turn("assistant", "Generated presentation at /home/user/annual_revenue.pptx")
        cm.record_active_task(
            task_id="task-99",
            goal="Generate annual revenue summary",
            artifacts=["/home/user/annual_revenue.pptx"],
        )

        # Test reference resolution for previous file
        resolved_file = cm.resolve_references("Send that document to my phone")
        self.assertIn("annual_revenue.pptx", resolved_file.get("resolved_text", ""))

        # Test reference resolution for previous task continuation
        resolved_cont = cm.resolve_references("Continue what you were doing")
        self.assertIn("Generate annual revenue summary", resolved_cont.get("resolved_text", ""))

        # Ambiguity detection when an action lacks mandatory entity
        clarification = cm.detect_ambiguity("Do the same thing for the other project")
        self.assertTrue(clarification["is_ambiguous"])
        self.assertIn("clarification_question", clarification)
        self.assertTrue(len(clarification["clarification_question"]) > 5)

    # ── Test 3: Adaptive Workflow Engine, Learning & Approval Gates ─────────

    def test_03_workflow_engine_learning_and_approval_gates(self):
        """Verify Objective C & D: Workflow routines, repetition learning, and approval gates."""
        wf_file = self.temp_path / "workflows.json"
        engine = WorkflowEngine(storage_path=wf_file)

        # 1. Register a high-privilege routine requiring approval
        routine = WorkflowRoutine(
            id="routine_deploy_app",
            name="Deploy Production App",
            description="Builds container and pushes to production server",
            trigger_type="manual",
            actions=[
                {"tool": "creator", "parameters": {"action": "run_tests"}},
                {"tool": "creator", "parameters": {"action": "run_shell", "command": "docker build -t app:v1 ."}},
            ],
            requires_approval=True,
            approved_by_user=False,
        )
        engine.register_routine(routine)

        # 2. Execution must fail/block if not approved
        res_blocked = engine.execute_workflow("routine_deploy_app")
        self.assertFalse(res_blocked["ok"])
        self.assertIn("requires explicit user approval", res_blocked["error"])

        # 3. Approve routine and re-execute
        appr_ok, appr_msg = engine.approve_routine("routine_deploy_app")
        self.assertTrue(appr_ok)

        with patch("core.orchestrator.get_orchestrator") as mock_orch:
            mock_task = MagicMock()
            mock_task.status = "completed"
            mock_task.result_summary = "All steps completed"
            mock_task.to_dict.return_value = {"status": "completed"}
            mock_orch.return_value.execute_task.return_value = mock_task
            res_approved = engine.execute_workflow("routine_deploy_app")
            self.assertTrue(res_approved["ok"])
            self.assertEqual(res_approved["status"], "completed")

        # 4. Workflow learning from repeated tool sequences
        seq = [("desktop_control", {"action": "kwin_list"}), ("kwin_desktop", {"action": "snapshot"})]
        engine.record_action_invocation(seq[0][0], seq[0][1])
        engine.record_action_invocation(seq[1][0], seq[1][1])
        engine.record_action_invocation(seq[0][0], seq[0][1])
        engine.record_action_invocation(seq[1][0], seq[1][1])
        engine.record_action_invocation(seq[0][0], seq[0][1])
        candidate = engine.record_action_invocation(seq[1][0], seq[1][1])
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["occurrences"], 3)

    # ── Test 4: Proactive Intelligence, Notification Tiers & Quiet Hours ───

    def test_04_proactive_intelligence_and_quiet_hours(self):
        """Verify Objective E: 5 notification priority tiers, quiet hours suppression, and phrasing."""
        state_file = self.temp_path / "proactive_state.json"
        pro = ProactiveIntelligenceEngine(storage_path=state_file)

        # Verify 5 notification priorities exist
        self.assertEqual(int(NotificationPriority.INFORMATIONAL), 1)
        self.assertEqual(int(NotificationPriority.USEFUL_SUGGESTION), 2)
        self.assertEqual(int(NotificationPriority.WARNING), 3)
        self.assertEqual(int(NotificationPriority.URGENT), 4)
        self.assertEqual(int(NotificationPriority.CRITICAL), 5)

        # Speech formatting respects distinguished kinds
        obs_alert = ProactiveAlert(
            alert_id="obs_1",
            priority=int(NotificationPriority.INFORMATIONAL),
            category="system",
            kind="observation",
            title="System Memory",
            message="RAM utilization dropped below 40%.",
        )
        spoken_obs = pro.format_proactive_speech(obs_alert)
        self.assertIn("observation", spoken_obs.lower())

        appr_alert = ProactiveAlert(
            alert_id="appr_1",
            priority=int(NotificationPriority.URGENT),
            category="workflow",
            kind="awaiting_approval",
            title="Deploy Routine",
            message="Production deployment is ready for execution.",
        )
        spoken_appr = pro.format_proactive_speech(appr_alert)
        self.assertIn("authorization is requested", spoken_appr.lower())

        # Test quiet hours suppression: mock quiet hours
        with patch.object(pro, "is_quiet_hours", return_value=True):
            # During quiet hours, low priority alerts should be suppressed
            with patch("core.orchestrator.get_orchestrator") as mock_orch:
                mock_orch.return_value.list_tasks.return_value = [
                    {"task_id": "paused_1", "status": "paused", "goal": "Sample"}
                ]
                deliverable = pro.evaluate_environment()
                # Paused task is priority USEFUL_SUGGESTION (2), suppressed during quiet hours
                self.assertEqual(len(deliverable), 0)

    # ── Test 5: Model Router Privacy Modes & Zero Leakage ───────────────────

    def test_05_privacy_modes_and_strict_local_enforcement(self):
        """Verify Objective I: 'strict_local' completely blocks external Gemini calls."""
        router = get_router()
        orig_mode = router.get_privacy_mode()
        try:
            # Set to strict_local
            ok, msg = router.set_privacy_mode("strict_local")
            self.assertTrue(ok)
            self.assertEqual(router.get_privacy_mode(), "strict_local")

            # A task routed to gemini or when local fails must be blocked
            with patch.dict(router._overrides, {"general": "gemini:gemini-2.5-flash"}):
                res = router.generate("general", "Hello world")
                self.assertIn("[ModelRouter Error] Generation blocked", res)
                self.assertIn("Strict Local Mode is active", res)

            # Set back to hybrid
            router.set_privacy_mode("hybrid")
            self.assertEqual(router.get_privacy_mode(), "hybrid")
        finally:
            router.set_privacy_mode(orig_mode)

    # ── Test 6: CREATOR Project Profile Management & AST Validation ─────────

    def test_06_creator_project_profiles_and_ast(self):
        """Verify Objective J: ProjectProfileManager auto-profiling, persistence, and syntax checks."""
        profiles_file = self.temp_path / "project_profiles.json"
        pm = ProjectProfileManager(storage_path=profiles_file)

        # Create a mock project repository
        repo_dir = self.temp_path / "mock_project"
        repo_dir.mkdir()
        (repo_dir / "package.json").write_text('{"name": "mock-app"}', encoding="utf-8")
        (repo_dir / "README.md").write_text("# Mock Web App\nA Node.js web application.", encoding="utf-8")

        # Auto-profile
        prof = pm.auto_profile(repo_dir)
        self.assertEqual(prof.name, "mock_project")
        self.assertIn("Node.js/JavaScript", prof.tech_stack)
        self.assertIn("npm test", prof.test_commands)
        self.assertIn("npm install", prof.build_commands)
        self.assertIn("Mock Web App", prof.purpose)

        # Retrieve profile
        fetched = pm.get_profile("mock_project")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "mock_project")

        # Creator engine integration
        engine = get_creator_engine()
        engine.profiles = pm
        profs_list = engine.list_profiles()
        self.assertTrue(len(profs_list) >= 1)

    # ── Test 7: Connected Device Persistent UUIDs & IP Resolution ───────────

    def test_07_device_uuids_and_dynamic_ip(self):
        """Verify Objective H: Every registered device maintains a persistent UUID and IP resolution."""
        dm = get_device_manager()
        devices = dm.list_registered_devices()
        self.assertTrue(len(devices) >= 2)

        for d in devices:
            self.assertIn("uuid", d)
            self.assertTrue(len(d["uuid"]) >= 32)

        # Test IP resolution
        tv = dm.resolve_device("redmi_tv") or dm.resolve_device("10.0.0.3")
        self.assertIsNotNone(tv)
        ip = dm.resolve_device_ip("redmi_tv")
        self.assertEqual(ip, "10.0.0.3")

    # ── Test 8: Subsystems Self-Diagnostics & Holographic Telemetry HUD ─────

    def test_08_subsystems_diagnostics_and_telemetry_hud(self):
        """Verify Objective K & L: Subsystem health assessment and holographic command centre HUD."""
        diag = diagnose_all_subsystems()
        expected_subs = {"audio", "models", "memory", "desktop", "devices", "security"}
        for s in expected_subs:
            self.assertIn(s, diag)
            self.assertIn(diag[s]["status"], ("Healthy", "Degraded", "Unavailable", "Simulated", "Not Configured"))
            self.assertIn("details", diag[s])

        # Telemetry snapshot
        telemetry = gather_system_telemetry()
        self.assertIn("hardware", telemetry)
        self.assertIn("subsystems", telemetry)
        self.assertIn("model_router", telemetry)
        self.assertIn("memory", telemetry)
        self.assertIn("workflows", telemetry)

        # Format HUD
        hud = format_command_centre_hud(telemetry)
        self.assertIn("AMATYA COMMAND CENTRE HUD", hud)
        self.assertIn("PRIVACY:", hud)
        self.assertIn("HEALTH :", hud)
        self.assertIn("CONNECTED DEVICES:", hud)


if __name__ == "__main__":
    unittest.main()
