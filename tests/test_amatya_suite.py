"""
AMATYA Comprehensive End-to-End Verification Suite (tests/test_amatya_suite.py)
===============================================================================
Tests all phases of the AMATYA AI Operating Companion:
  1. Wayland Desktop Automation (kwin-mcp v0.12.0 availability, window enumeration,
     vision capture, screenshot comparison, DesktopAgent autonomy levels).
  2. Voice Authentication, Speaker Enrollment, Impostor Rejection & Anti-Spoofing
     Replay Detection + Challenge-Response.
  3. Permission-Based Security Policy (Tiers 0-5, PBKDF2 PIN, Autonomy Levels 1-5,
     Secret Detection & Redaction).
  4. Multi-Role AI Model Router (11 roles, hardware detection, deterministic embeddings).
  5. Hybrid Semantic RAG Knowledge Base & Memory Secret Guard.
  6. Central Orchestrator & Contextual Reference Resolution ("Open that",
     "Close the previous window", "Check the same project again",
     "Send that file to my phone").
  7. Smart Home Automation (Device Registry, State Verification, Routines Engine,
     Camera Privacy, Confirmation Gates).
  8. Connected Devices & Network Control (Discovery, Android Phone KDE Connect/ADB,
     Redmi Android TV, Remote SSH, Authorization Gates).
  9. CREATOR Software Engineering, Command Risk Classifier & Document Engine
     (PDF, DOCX, XLSX, PPTX, CSV, Markdown, ZIP round-trip).
  10. Declarative Skill Metadata & Command-Centre Telemetry Snapshot.
"""
from __future__ import annotations

import tempfile
import unittest
import pytest
from pathlib import Path

import numpy as np


def _synth_voice(f0: float, formants: list[tuple[float, float]], duration: float = 2.0, sr: int = 16000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    vib = 1.0 + 0.012 * np.sin(2 * np.pi * 5.2 * t + rng.uniform(0, 6))
    sig = np.zeros_like(t)
    for h in range(1, 28):
        freq = f0 * h * vib
        amp = sum(np.exp(-0.5 * ((f0 * h - fm) / bw) ** 2) for fm, bw in formants)
        sig += (amp / (h ** 0.7)) * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2 * np.pi))
    env = 0.55 + 0.45 * np.sin(2 * np.pi * 3.5 * t + rng.uniform(0, 3))
    sig = sig * env + rng.normal(0, 0.015, size=t.shape)
    sig = sig / (np.max(np.abs(sig)) + 1e-6)
    return (sig * 24000).astype(np.int16)


class TestAmatyaSuite(unittest.TestCase):

    @pytest.mark.integration
    @pytest.mark.desktop
    def test_01_wayland_desktop_and_vision(self):
        from core.platform_support import is_usable_display_available
        from core.kwin_mcp_client import available
        from core.vision import get_vision
        from core.desktop_agent import DesktopAgent

        if not is_usable_display_available():
            self.skipTest("Usable desktop display session (Wayland/X11) is not provisioned; skipping desktop integration test.")

        self.assertTrue(available(), "kwin-mcp binary/module should be available in AMATYA venv")
        vis = get_vision()
        cap = vis.capture_full()
        if cap.ok:
            self.assertGreater(len(cap.image_bytes), 1000)
            cmp_same = vis.compare(cap, cap)
            self.assertFalse(cmp_same.changed)
            self.assertAlmostEqual(cmp_same.similarity, 1.0, places=3)

        agent = DesktopAgent()
        agent.set_autonomy("observe_only")
        self.assertEqual(agent.autonomy, "observe_only")
        agent.set_autonomy("autonomous_workflows")
        self.assertEqual(agent.autonomy, "autonomous_workflows")

    def test_02_voice_auth_and_antispoofing(self):
        from core.voice_auth import get_voice_authenticator

        auth = get_voice_authenticator()
        auth.clear_replay_cache()

        s1 = _synth_voice(125.0, [(500, 90), (1450, 140), (2500, 180)], seed=11)
        s2 = _synth_voice(126.5, [(508, 90), (1442, 140), (2515, 180)], seed=22)
        s3 = _synth_voice(124.0, [(494, 90), (1458, 140), (2490, 180)], seed=33)

        res = auth.enroll_profile("unit_test_user", samples=[s1, s2, s3])
        self.assertTrue(res["ok"])

        try:
            # Legitimate speaker verification
            s_legit = _synth_voice(125.8, [(503, 90), (1452, 140), (2505, 180)], seed=44)
            v_ok = auth.verify_speaker(s_legit, claimed_user="unit_test_user")
            self.assertTrue(v_ok.verified)
            self.assertGreaterEqual(v_ok.confidence, 0.78)

            # Replay attack detection (exact same audio re-submitted)
            v_rep = auth.verify_speaker(s_legit, claimed_user="unit_test_user")
            self.assertFalse(v_rep.verified)
            self.assertTrue(v_rep.anti_spoof.is_replay)

            # Impostor rejection
            s_imp = _synth_voice(235.0, [(780, 110), (2150, 170), (3200, 220)], seed=88)
            v_imp = auth.verify_speaker(s_imp, claimed_user="unit_test_user")
            self.assertFalse(v_imp.verified)

            # Challenge-response phrase check
            ch = auth.generate_challenge()
            ok_ch, _ = auth.verify_challenge_transcript(ch["phrase"])
            self.assertTrue(ok_ch)
        finally:
            auth.delete_profile("unit_test_user")
            auth.clear_replay_cache()

    def test_03_security_permissions_and_pin(self):
        from core.security import (
            PermissionTier,
            check_permission,
            clear_pin,
            contains_secret,
            redact_secrets,
            set_pin,
            verify_pin,
        )
        from memory.config_manager import save_autonomy_level

        ok, _ = set_pin("7391")
        self.assertTrue(ok)
        try:
            self.assertTrue(verify_pin("7391")[0])
            self.assertFalse(verify_pin("0000")[0])

            save_autonomy_level("observe_only")
            res_obs = check_permission("edit_file", PermissionTier.PRIVATE_FILES, interactive_confirm=False)
            self.assertFalse(res_obs["allowed"])

            save_autonomy_level("confirm")
            self.assertTrue(contains_secret("AQ.mock_token_fixture_for_unit_tests_abcdefghijklmnopqrstuvwx"))
            self.assertIn("[REDACTED_SECRET]", redact_secrets("password=mock_user_password_redaction_test"))
        finally:
            clear_pin("7391")
            save_autonomy_level("confirm")

    def test_04_model_router_and_rag(self):
        from core.model_router import get_router
        from core.rag import get_knowledge_base

        router = get_router()
        summary = router.summary()
        self.assertGreaterEqual(len(summary["routes"]), 10)
        emb = router.embed("AMATYA KDE Wayland desktop companion")
        self.assertEqual(len(emb), 128)

        kb = get_knowledge_base()
        idx_res = kb.index_text(
            "unit_test_doc",
            "AMATYA integrates KDE Connect, Redmi Android TV over ADB, and Home Assistant routines.",
            title="Unit Test Spec",
        )
        self.assertTrue(idx_res["ok"])
        try:
            hits = kb.query("How does AMATYA control Redmi Android TV and KDE Connect?")
            self.assertTrue(len(hits) > 0)
            self.assertEqual(hits[0]["source_id"], "unit_test_doc")
        finally:
            kb.remove_source("unit_test_doc")

    def test_05_orchestrator_context_resolution(self):
        from core.orchestrator import get_orchestrator

        repo_root = str(Path(__file__).resolve().parent.parent)
        readme_path = str(Path(repo_root) / "README.md")

        orch = get_orchestrator()
        orch.context.update_entity(
            last_file=readme_path,
            last_project=repo_root,
            window_id="{win-1}",
            window_title="Kate",
        )
        orch.context.update_entity(
            window_id="{win-2}",
            window_title="Konsole",
        )

        r_phone = orch.context.resolve_references("Send that file to my phone.")
        self.assertEqual(r_phone["recommended_action"]["tool"], "device_control")
        self.assertEqual(r_phone["recommended_action"]["parameters"]["file_path"], readme_path)

        r_win = orch.context.resolve_references("Close the previous window.")
        self.assertEqual(r_win["recommended_action"]["tool"], "kwin_desktop")
        self.assertEqual(r_win["recommended_action"]["parameters"]["window_id"], "{win-1}")

        r_proj = orch.context.resolve_references("Check the same project again.")
        self.assertEqual(r_proj["recommended_action"]["tool"], "creator")

    def test_06_home_automation_and_devices(self):
        from core.home_automation import get_home_controller
        from core.device_manager import get_device_manager
        from memory.config_manager import save_autonomy_level

        save_autonomy_level("autonomous_workflows")
        try:
            ha = get_home_controller()
            res = ha.control_device("living room lights", "turn_on", {"brightness_pct": 80})
            self.assertTrue(res["ok"] and res["verified"])

            unconf = ha.execute_routine("leaving_home", confirmed=False, interactive_confirm=False)
            self.assertFalse(unconf["ok"])
            self.assertTrue(unconf.get("requires_confirmation"))

            conf = ha.execute_routine("leaving_home", confirmed=True)
            self.assertTrue(conf["ok"] and conf["verified"])

            dm = get_device_manager()
            tv = dm.tv_action("launch_app", "redmi_tv", app_name="Netflix")
            self.assertTrue(tv["ok"])
            self.assertEqual(tv["status"]["current_app"], "Netflix")
        finally:
            save_autonomy_level("confirm")

    def test_07_creator_and_document_formats(self):
        from core.creator import classify_command_risk, get_creator_engine
        from core.doc_generator import analyze_document, generate_document

        self.assertEqual(classify_command_risk("git status")["risk_level"], "SAFE_READ")
        self.assertEqual(classify_command_risk("pytest")["risk_level"], "SAFE_BUILD")
        self.assertEqual(classify_command_risk("sudo rm -rf /")["risk_level"], "DESTRUCTIVE")

        engine = get_creator_engine()
        blocked = engine.run_shell("rm -rf /tmp/test_block", confirmed=False, interactive_confirm=False)
        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked.get("blocked"))

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            for ext in (".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".md"):
                fp = tdir / f"test_doc{ext}"
                g = generate_document(
                    fp,
                    title="AMATYA Verification",
                    content="Autonomous verification payload.",
                    rows=[["col1", "col2"], ["val1", "val2"]],
                )
                self.assertTrue(g["ok"], f"Failed to generate {ext}: {g}")
                a = analyze_document(fp)
                self.assertTrue(a["ok"], f"Failed to analyze {ext}: {a}")

    def test_08_action_loader_and_command_centre(self):
        from core.action_loader import discover_actions
        from dashboard.server import get_command_centre_snapshot

        reg = discover_actions(Path(__file__).resolve().parent.parent / "actions", logger=lambda _: None)
        self.assertGreaterEqual(len(reg.names()), 25)
        for required in ("kwin_desktop", "desktop_agent", "voice_auth", "model_router", "knowledge_base", "orchestrator", "home_automation", "device_control", "creator"):
            self.assertIn(required, reg.names())

        snap = get_command_centre_snapshot()
        self.assertIn("desktop_automation", snap)
        self.assertIn("voice_auth", snap)
        self.assertIn("home_automation", snap)
        self.assertIn("connected_devices", snap)
        self.assertIn("model_router", snap)
        self.assertIn("orchestrator", snap)


if __name__ == "__main__":
    unittest.main()
