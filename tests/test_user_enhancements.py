"""
tests/test_user_enhancements.py — Verification of Phase 12 User Directives

Directives Verified:
1. Professional Multi-slide Presentations with transitions, cards, metrics & styling
2. CREATOR Voice Confirmation & Spoken Authorization
3. Concurrent Multitasking with Continuous Voice Status Updates
4. Wayland Spectacle Desktop Screen Capture Subsystem
5. File Controller Path Resolution & _BASE_DIR Integrity
6. Strict Confirmation Gate for AMATYA Shutdown
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["AMATYA_TEST_MODE"] = "1"

from actions import computer_control, creator, file_controller, orchestrator
from core import confirm
from core.doc_generator import analyze_document, generate_document
from core.orchestrator import CentralOrchestrator, TaskRecord, get_orchestrator
from core.vision import Vision, get_vision


class TestUserEnhancements(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="amatya_enhancements_")
        self.addCleanup(lambda: shutil.rmtree(self.test_dir, ignore_errors=True))

    # ── 1. Professional Multi-Slide PPTX Generation ───────────────────────────

    def test_01_professional_multislide_pptx(self):
        """Directive 1: Verify multi-slide PPTX with cards, metrics, transitions, and theme."""
        out_file = Path(self.test_dir) / "quarterly_review.pptx"
        data = {
            "title": "Quarterly Performance & Growth Strategy",
            "subtitle": "AMATYA Executive Intelligence Briefing",
            "metadata": {"date": "November 2026", "author": "AMATYA AI"},
            "theme": "corporate",
            "slides": [
                {
                    "title": "Executive Summary",
                    "content": "Strong quarterly performance driven by automated operations and multi-agent coordination.",
                    "cards": [
                        {"title": "Core Objective", "content": "Deliver reliable desktop autonomy and context-aware assistance."},
                        {"title": "Strategic Focus", "content": "Enterprise stability, local privacy enforcement, and voice biometrics."},
                    ],
                },
                {
                    "title": "Key Metrics & KPIs",
                    "content": "Operational indicators across core capabilities.",
                    "metrics": [
                        {"value": "99.8%", "label": "Task Success Rate"},
                        {"value": "<250ms", "label": "Voice Auth Latency"},
                        {"value": "100%", "label": "Local Privacy Conformance"},
                    ],
                },
                {
                    "title": "Architecture Overview",
                    "content": "Three-tier distributed intelligence structure.",
                    "cards": [
                        {"title": "Tier 1: Fast Reflex", "content": "Instant local intents and hotword recognition."},
                        {"title": "Tier 2: Reasoning", "content": "Task planning, DAG workflows, and state transitions."},
                        {"title": "Tier 3: Execution", "content": "Wayland automation, IoT coordination, and creator engine."},
                    ],
                },
                {
                    "title": "Next Milestones",
                    "content": "Long-term engineering roadmap milestones and autonomous monitoring routines.",
                },
            ],
        }

        res = generate_document(
            doc_type="pptx",
            title=data["title"],
            content=data,
            output_path=str(out_file),
            theme="corporate",
        )
        self.assertTrue(res["ok"], f"Presentation generation failed: {res}")
        self.assertTrue(out_file.exists())
        self.assertGreater(out_file.stat().st_size, 15000)

        # Inspect generated presentation
        analysis = analyze_document(str(out_file))
        self.assertTrue(analysis["ok"])
        self.assertEqual(analysis["format"], "pptx")
        self.assertGreaterEqual(analysis["slide_count"], 4)
        self.assertIn("Quarterly Performance", analysis["text"])

    # ── 2. CREATOR Voice Confirmation & Spoken Authorization ──────────────────

    def test_02_voice_confirmation_and_authorization(self):
        """Directive 2: Voice announcements and voice authorization of destructive actions."""
        spoken_messages = []
        logged_messages = []
        shown_dialogs = []

        def mock_speak(msg: str):
            spoken_messages.append(msg)

        def mock_log(msg: str):
            logged_messages.append(msg)

        def mock_show(title: str, detail: str):
            shown_dialogs.append((title, detail))

        def mock_hide():
            pass

        confirm.bind(show=mock_show, hide=mock_hide, log=mock_log, speak=mock_speak)

        # Step A: Request confirmation
        executed_work = []
        token = confirm.request(
            key="test_rm_command",
            title="Delete Temporary Files",
            detail="rm -rf /tmp/test_dir",
            run=lambda: (executed_work.append(True) or "Cleaned files."),
        )

        self.assertIn("[CONFIRMATION_PENDING]", token)
        self.assertTrue(confirm.has_pending())
        info = confirm.get_pending_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["key"], "test_rm_command")

        # Verify spoken announcement was triggered
        self.assertTrue(any("authorization is required" in s.lower() for s in spoken_messages))

        # Step B: Spoken voice authorization ("yes proceed")
        spoken_messages.clear()
        auth_res = confirm.voice_authorize("yes proceed, please execute it")
        self.assertTrue(auth_res)
        self.assertFalse(confirm.has_pending())
        self.assertTrue(any("authorized" in s.lower() for s in spoken_messages))

        time.sleep(0.1)  # worker thread run
        self.assertEqual(len(executed_work), 1)

        # Step C: Negative authorization ("no abort")
        confirm.request(
            key="test_cancel_command",
            title="Dangerous Command",
            detail="format /dev/null",
            run=lambda: executed_work.append("should_not_run"),
        )
        self.assertTrue(confirm.has_pending())
        neg_res = confirm.voice_authorize("no, cancel that immediately")
        self.assertFalse(neg_res)
        self.assertFalse(confirm.has_pending())
        self.assertNotIn("should_not_run", executed_work)

    # ── 3. Concurrent Multitasking with Continuous Voice Updates ──────────────

    def test_03_concurrent_multitasking_with_voice_updates(self):
        """Directive 3: Work on multiple tasks simultaneously with continuous voice updates."""
        orch = CentralOrchestrator()
        spoken_updates = []

        def mock_speak(msg: str):
            spoken_updates.append(msg)

        # Provide a mock action runner simulating two simultaneous tasks
        def mock_runner(action_name: str, params: dict):
            time.sleep(0.05)  # simulate async work
            return f"Processed {action_name} successfully."

        tasks = [
            "Inspect git status and check workspace changes",
            "Audit project dependencies and compile report",
        ]

        result = orch.run_multitask(
            tasks,
            action_runner=mock_runner,
            speak=mock_speak,
            status_interval_sec=0.1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tasks_count"], 2)
        self.assertTrue(len(spoken_updates) >= 2)
        # Verify initial announcement, step updates, and final completion
        self.assertTrue(any("concurrent multitasking" in s.lower() for s in spoken_updates))
        self.assertTrue(any("completed successfully" in s.lower() for s in spoken_updates))

        # Test tool execute interface for orchestrator multitask
        tool_res = orchestrator.execute(
            {"action": "multitask", "tasks": ["Task A", "Task B"]},
            speak=mock_speak,
        )
        self.assertIn("completed successfully", str(tool_res))

    # ── 4. Wayland Spectacle Screenshot Subsystem ─────────────────────────────

    def test_04_wayland_spectacle_screenshot(self):
        """Directive 4: Vision subsystem captures desktop screen cleanly using Spectacle."""
        v = get_vision()
        cap = v.capture_full()
        self.assertTrue(cap.ok, f"Capture failed: {cap.error}")
        self.assertGreater(len(cap.image_bytes), 1000, "Screenshot data is suspiciously small")
        self.assertEqual(cap.mime_type, "image/png")

        # Test computer_control action screenshot
        res_ctrl = computer_control.execute({"action": "screenshot"})
        self.assertTrue("Screenshot captured" in res_ctrl or "Saved to" in res_ctrl or "Screenshot" in res_ctrl)

    # ── 5. File Controller Path Resolution & _BASE_DIR Integrity ──────────────

    def test_05_file_controller_base_dir_resolution(self):
        """Directive 5: Verify file_controller handles non-project and media paths without _BASE_DIR NameError."""
        # Test directory listing on a safe system path
        res = file_controller.execute({
            "action": "list",
            "path": "/tmp",
        })
        self.assertNotIn("name '_BASE_DIR' is not defined", res)
        self.assertFalse(res.startswith("Error listing files: name '_BASE_DIR' is not defined"))

    # ── 6. Strict Confirmation Gate for AMATYA Shutdown ───────────────────────

    def test_06_shutdown_strictly_requires_confirmation(self):
        """Directive 6: AMATYA shutdown cannot execute unconfirmed on turn 1."""
        shown = []
        spoken = []

        def mock_show(t, d):
            shown.append((t, d))

        def mock_speak(m):
            spoken.append(m)

        confirm.bind(show=mock_show, hide=lambda: None, log=lambda m: None, speak=mock_speak)

        # Calling shutdown via confirm.request must gate it
        executed = []
        token = confirm.request(
            key="shutdown_amatya",
            title="Shut Down AMATYA",
            detail="Terminate AMATYA completely.",
            run=lambda: executed.append("SHUTDOWN_EXECUTED"),
        )

        self.assertIn("[CONFIRMATION_PENDING]", token)
        # Should NOT have executed yet
        self.assertEqual(len(executed), 0)
        self.assertTrue(confirm.has_pending())
        self.assertTrue(any("authorization is required for shut down amatya" in s.lower() for s in spoken))

        # Only upon explicit confirmation does it run
        confirm.voice_authorize("confirm shutdown")
        time.sleep(0.1)
        self.assertEqual(len(executed), 1)

    # ── 7. ContextManager Alternative Project Ambiguity Detection ─────────────

    def test_07_context_manager_other_project_ambiguity(self):
        """Verify ContextManager correctly flags ambiguity for 'other project' when no alternative exists."""
        from core.context_manager import ContextManager
        ctx_file = Path(self.test_dir) / "test_ambiguity_ctx.json"
        cm = ContextManager(state_path=ctx_file)

        # 1. State with only 1 project and dot
        cm.update_entity(last_project="/home/user/Projects/Mark-LVI")
        cm.update_entity(last_project=".")  # should canonicalize to the same project
        self.assertEqual(len(cm.get_state().get("recent_projects", [])), 1)

        # 2. Assert ambiguity on alternative project queries
        res1 = cm.detect_ambiguity("Do the same thing for the other project")
        self.assertTrue(res1["is_ambiguous"])
        self.assertIn("Which other project", res1["clarification_question"])

        res2 = cm.detect_ambiguity("Do the same for the other project")
        self.assertTrue(res2["is_ambiguous"])
        self.assertIn("Which other project", res2["clarification_question"])

        res3 = cm.detect_ambiguity("Switch to another project")
        self.assertTrue(res3["is_ambiguous"])

        # 3. Add a truly distinct second project
        cm.update_entity(last_project="/home/user/Projects/AlternativeApp")
        res_distinct = cm.detect_ambiguity("Do the same thing for the other project")
        self.assertFalse(res_distinct["is_ambiguous"])
        self.assertEqual(
            res_distinct["resolutions"].get("project_path"),
            str(Path("/home/user/Projects/Mark-LVI").resolve()),
        )

    # ── 8. Knowledge Base search_memories top_k keyword compatibility ──────────

    def test_08_knowledge_base_search_memories_top_k(self):
        """Verify knowledge_base search_memories handles top_k without TypeError."""
        from actions import knowledge_base
        from core.memory_engine import get_memory_engine

        mem = get_memory_engine(storage_dir=Path(self.test_dir) / "test_mem")
        mem.set_enabled(True)
        mem.store_fact(predicate="preferred_shell", object_value="zsh", category="environment")
        mem.store_fact(predicate="primary_monitor", object_value="DP-1", category="hardware")

        with patch("actions.knowledge_base.get_memory_engine", return_value=mem):
            res = knowledge_base.execute({"action": "search_memories", "query": "shell", "top_k": 3})
            self.assertIn("status=done", str(res))
            self.assertIn("preferred_shell", str(res))

            # Test MemoryEngine directly with both limit and top_k
            direct_top_k = mem.search_memories("monitor", top_k=1)
            self.assertEqual(len(direct_top_k), 1)
            self.assertEqual(direct_top_k[0].predicate, "primary_monitor")

            direct_limit = mem.search_memories("shell", limit=1)
            self.assertEqual(len(direct_limit), 1)
            self.assertEqual(direct_limit[0].predicate, "preferred_shell")

    # ── 9. PPTX Dynamic Content Without Template Repetition ───────────────────

    def test_09_pptx_dynamic_content_no_repetition(self):
        """Verify PPT generation reflects custom content dynamically without static hardcoded templates."""
        from actions import creator
        from core.doc_generator import analyze_document

        # Deck 1: Placement report in markdown format
        deck1_path = Path(self.test_dir) / "placement_report.pptx"
        deck1_content = (
            "# Placement Statistics 2024\n"
            "ECE placement rate reached 94% across core semiconductor firms.\n\n"
            "# Leading Industry Partners\n"
            "Texas Instruments, Qualcomm, Intel, and Synopsys conducted campus visits.\n\n"
            "# Academic Performance\n"
            "Over 120 students secured Tier-1 research and development roles."
        )
        res1 = creator.execute({
            "action": "generate_doc",
            "output_path": str(deck1_path),
            "title": "KLE Placement Summary 2024",
            "content": deck1_content,
        })
        self.assertIn("status=done", str(res1))

        analysis1 = analyze_document(deck1_path)
        self.assertTrue(analysis1["ok"])
        deck1_text = analysis1["text"]

        # Ensure Deck 1 contains its own dynamic content and no hardcoded AMATYA test metrics
        self.assertIn("Placement Statistics 2024", deck1_text)
        self.assertIn("Texas Instruments", deck1_text)
        self.assertNotIn("Executive Overview & Context", deck1_text)
        self.assertNotIn("100% Test Suite Pass Rate", deck1_text)

        # Deck 2: Low-Dropout Regulator report with structured slides parameter
        deck2_path = Path(self.test_dir) / "ldo_report.pptx"
        deck2_slides = [
            {
                "title": "Bandgap Reference Subsystem",
                "content": "Curvature-compensated 1.2V reference operating down to 1.8V VDD.",
            },
            {
                "title": "Folded Cascode Error Amplifier",
                "content": "Delivers 78dB DC gain and 65-degree phase margin with 10pF load.",
            },
            {
                "title": "Transient Response & Dropout",
                "content": "Dropout voltage measured at 180mV under maximum 250mA output current.",
            },
        ]
        res2 = creator.execute({
            "action": "generate_doc",
            "output_path": str(deck2_path),
            "title": "LDO IC Final Verification",
            "slides": deck2_slides,
        })
        self.assertIn("status=done", str(res2))

        analysis2 = analyze_document(deck2_path)
        self.assertTrue(analysis2["ok"])
        deck2_text = analysis2["text"]

        # Ensure Deck 2 contains its own technical content and doesn't repeat Deck 1
        self.assertIn("Bandgap Reference Subsystem", deck2_text)
        self.assertIn("Folded Cascode Error Amplifier", deck2_text)
        self.assertNotIn("Placement Statistics 2024", deck2_text)
        self.assertNotIn("Texas Instruments", deck2_text)
        self.assertNotIn("Executive Overview & Context", deck2_text)


if __name__ == "__main__":
    unittest.main()
