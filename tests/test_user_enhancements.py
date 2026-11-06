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

from actions import computer_control, creator, file_controller, jyotisha, orchestrator
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

    # ── 10. File Deletion Strict Confirmation ─────────────────────────────────

    def test_10_file_deletion_requires_confirmation(self):
        """Verify file_controller strictly requires confirmation before deleting any file."""
        from actions import file_controller
        from core import confirm

        test_file = Path(self.test_dir) / "critical_document.txt"
        test_file.write_text("Confidential project data", encoding="utf-8")
        self.assertTrue(test_file.exists())

        # Bind mock HUD interface
        shown = []
        spoken = []
        confirm.bind(
            show=lambda t, d: shown.append((t, d)),
            hide=lambda: None,
            log=lambda m: None,
            speak=lambda s: spoken.append(s),
        )

        # 1. Unconfirmed delete call MUST NOT delete the file
        res = file_controller.execute({
            "action": "delete",
            "path": str(test_file),
            "confirmed": False,
        })
        self.assertIn("[CONFIRMATION_PENDING]", res)
        self.assertTrue(test_file.exists(), "File was deleted without confirmation!")
        self.assertTrue(confirm.has_pending())
        self.assertTrue(any("delete" in s.lower() for s in spoken))

        # 2. Authorizing via voice executes the deletion
        confirm.voice_authorize("confirm delete")
        time.sleep(0.1)
        self.assertFalse(test_file.exists(), "File should be moved to trash after confirmation")

        # 3. Direct confirmed=True parameter also allows confirmed execution
        test_file2 = Path(self.test_dir) / "another_file.txt"
        test_file2.write_text("Temporary file", encoding="utf-8")
        res2 = file_controller.execute({
            "action": "delete",
            "path": str(test_file2),
            "confirmed": True,
        })
        self.assertTrue(res2.startswith("Moved to Trash") or "Trash" in res2)
        self.assertFalse(test_file2.exists())

    # ── 11. Wayland Clipboard Plasma / wl-paste Fallback ───────────────────────

    def test_11_wayland_clipboard_plasma_fallback(self):
        """Verify clipboard_get and clipboard_paste operate cleanly without crashing on missing wl-paste."""
        from actions import computer_control

        # 1. Real end-to-end clipboard write and read via computer_control
        test_val = "AMATYA_CLIPBOARD_TEST_VERIFICATION_889"
        pasted = computer_control.computer_control({"action": "paste", "text": test_val})
        self.assertIn("Pasted", pasted)

        copied = computer_control.computer_control({"action": "copy"})
        self.assertEqual(copied, test_val)

        # 2. Verify fallback when client.clipboard_get raises RuntimeError (simulating missing binary)
        mock_client = MagicMock()
        mock_client.clipboard_get.side_effect = RuntimeError("wl-paste not found. Install wl-clipboard")
        mock_client.clipboard_set.side_effect = RuntimeError("wl-copy not found. Install wl-clipboard")

        with patch("actions.computer_control.get_client", return_value=mock_client), \
             patch("actions.computer_control._get_plasma_clipboard", return_value="fallback_clipboard_value"), \
             patch("actions.computer_control._set_plasma_clipboard", return_value=True):
            fallback_copy = computer_control._computer_control_via_kwin("copy", {})
            self.assertEqual(fallback_copy, "fallback_clipboard_value")

            fallback_paste = computer_control._computer_control_via_kwin("paste", {"text": "hello"})
            self.assertIn("Pasted", fallback_paste)

        # 3. Verify user-space wl-paste / wl-copy wrapper presence
        wl_paste = shutil.which("wl-paste")
        self.assertIsNotNone(wl_paste, "wl-paste wrapper should be found in PATH")

    # ── 12. PPT Generation Bridges Summary File Content (No Stale/Vague Data) ───

    def test_12_ppt_generation_bridges_file_summary_content(self):
        """Verify PPT creation resolves file paths and bridges summary text instead of vague placeholders."""
        from actions import creator
        from core.orchestrator import CentralOrchestrator

        # Create a realistic project summary text file
        summary_file = Path(self.test_dir) / "ldo_summary.txt"
        summary_content = (
            "# Low Dropout Voltage Regulator (LDO)\n\n"
            "## Executive Summary\n"
            "The LDO circuit delivers stable 1.8V output across 2.7V to 5.0V supply fluctuations.\n"
            "Achieves ultra-low quiescent current and fast transient recovery under step loads.\n\n"
            "## Technical Specifications\n"
            "- Dropout Voltage: 140mV at 200mA load current\n"
            "- Power Supply Rejection Ratio: 72dB at 1kHz\n"
            "- Quiescent Current: 28uA under no-load standby\n"
            "- Output Capacitor: 1.0uF ceramic ESR stable\n\n"
            "## Subsystem Architecture\n"
            "- Sub-bandgap reference generator with curvature compensation\n"
            "- Folded cascode error amplifier with high gain-bandwidth product\n"
            "- PMOS pass element with thermal shutdown protection\n"
        )
        summary_file.write_text(summary_content, encoding="utf-8")

        # 1. Direct Orchestrator summary extractor resolves file path
        orch = CentralOrchestrator()
        extracted = orch._extract_summary_text(f"File created: {summary_file}")
        self.assertIn("Dropout Voltage: 140mV", extracted)
        self.assertIn("Folded cascode error amplifier", extracted)

        # 2. Creator generate_doc with content as filepath
        ppt_file1 = Path(self.test_dir) / "ldo_deck1.pptx"
        res1 = creator.execute({
            "action": "generate_doc",
            "doc_type": "pptx",
            "title": "LDO Engineering Review",
            "content": str(summary_file),
            "output_path": str(ppt_file1),
        })
        self.assertIn("status=done", str(res1))
        self.assertTrue(ppt_file1.exists())

        analysis1 = analyze_document(str(ppt_file1))
        self.assertTrue(analysis1["ok"])
        self.assertIn("140mV", analysis1["text"])
        self.assertIn("Power Supply Rejection", analysis1["text"])
        self.assertNotIn("Architecture Focus: Comprehensive evaluation", analysis1["text"])

        # 3. Creator generate_doc with source_paths parameter
        ppt_file2 = Path(self.test_dir) / "ldo_deck2.pptx"
        res2 = creator.execute({
            "action": "generate_doc",
            "doc_type": "pptx",
            "title": "LDO Architecture Brief",
            "source_paths": [str(summary_file)],
            "output_path": str(ppt_file2),
        })
        self.assertIn("status=done", str(res2))
        analysis2 = analyze_document(str(ppt_file2))
        self.assertTrue(analysis2["ok"])
        self.assertIn("Folded cascode", analysis2["text"])

    # ── 13. Vedic Jyotisha Birth Chart Calculation & Comprehensive Analysis ─────

    def test_13_vedic_jyotisha_birth_chart_and_analysis(self):
        """Verify Vedic Jyotisha calculation: Sidereal Lahiri, Shodashavarga (D1..D60), Maandi, Shadbala, Dashas."""
        import actions.jyotisha
        from core.jyotisha import calculate_vedic_chart, resolve_location

        # Test location resolution
        lat, lon, tz, cname = resolve_location("Bengaluru")
        self.assertAlmostEqual(lat, 12.9716, places=2)
        self.assertAlmostEqual(lon, 77.5946, places=2)
        self.assertEqual(tz, 5.5)

        # 1. Action calculate_chart
        res = jyotisha.execute({
            "action": "calculate_chart",
            "name": "Varun",
            "date": "1995-05-15",
            "time": "14:30:00",
            "place": "Bengaluru",
        })
        self.assertIn("status=done", res)
        self.assertIn("VEDIC KUNDALI", res)
        self.assertIn("Lagna: Kanya", res)
        self.assertIn("Chandra Rashi: Vrishchika", res)
        self.assertIn("Maandi", res)
        self.assertIn("Harshal (Uranus)", res)
        self.assertIn("Varun (Neptune)", res)
        self.assertIn("Yama (Pluto)", res)

        # 2. All 16 Divisional Charts (Shodashavargas)
        chart = calculate_vedic_chart(name="Varun", date_str="1995-05-15", time_str="14:30:00", place="Bengaluru")
        vargas = chart.divisional_charts
        expected_vargas = ["D1", "D2", "D3", "D4", "D7", "D9", "D10", "D12", "D16", "D20", "D24", "D27", "D30", "D40", "D45", "D60"]
        for ev in expected_vargas:
            self.assertIn(ev, vargas, f"Missing divisional chart {ev}")
            self.assertIn("Lagna", vargas[ev])
            self.assertIn("Surya", vargas[ev])
            self.assertIn("Chandra", vargas[ev])

        # 3. Shadbala & Chara Karakas
        res_sb = jyotisha.execute({
            "action": "shadbala",
            "name": "Varun",
            "date": "1995-05-15",
            "time": "14:30:00",
            "place": "Bengaluru",
        })
        self.assertIn("status=done", res_sb)
        self.assertIn("Atmakaraka (AK)", res_sb)
        self.assertIn("Amatyakaraka (AmK)", res_sb)
        self.assertIn("Darakaraka (DK)", res_sb)
        self.assertIn("Shadbala", res_sb)

        # 4. Vimsottari Dasha Timeline
        res_dasha = jyotisha.execute({
            "action": "dasha_timeline",
            "name": "Varun",
            "date": "1995-05-15",
            "time": "14:30:00",
            "place": "Bengaluru",
        })
        self.assertIn("status=done", res_dasha)
        self.assertIn("VIMSOTTARI DASHA TIMELINE", res_dasha)
        self.assertIn("CURRENT ACTIVE PERIOD", res_dasha)
        self.assertIn("Mahadasha", res_dasha)

        # 5. Full Synthesized Reading
        res_read = jyotisha.execute({
            "action": "read_chart",
            "name": "Varun",
            "date": "1995-05-15",
            "time": "14:30:00",
            "place": "Bengaluru",
        })
        self.assertIn("status=done", res_read)
        self.assertIn("Core Triad", res_read)
        self.assertIn("Jaimini Chara Karakas", res_read)
        self.assertIn("D10 Dashamsha", res_read)
        self.assertIn("D9 Navamsha", res_read)
        self.assertIn("Classical Upayas", res_read)

    # ── 14. Western Tropical Astrology Mode ───────────────────────────────────

    def test_14_western_astrology_tropical_mode(self):
        """Verify Western astrology mode operates accurately with Tropical zodiac and Placidus houses."""
        res_w = jyotisha.execute({
            "action": "western_chart",
            "name": "Varun",
            "date": "1995-05-15",
            "time": "14:30:00",
            "place": "Bengaluru",
        })
        self.assertIn("status=done", res_w)
        self.assertIn("WESTERN TROPICAL HOROSCOPE", res_w)
        self.assertIn("Sun Sign: Taurus", res_w)
        self.assertIn("Moon Sign: Sagittarius", res_w)
        self.assertIn("Rising Sign (Ascendant): Virgo", res_w)
        self.assertIn("Placidus Houses", res_w)
        self.assertIn("Major Aspects", res_w)


if __name__ == "__main__":
    unittest.main()
