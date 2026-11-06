"""
tests/test_phase13_acceptance.py
=================================
Acceptance Test Suite for AMATYA Phase 13.2: Universal Ingestion Framework.

Tests verify:
  1. Modality & MIME Detection (Magic bytes + Extension fallback).
  2. Document Extraction Pipeline (Text, Markdown, HTML, CSV).
  3. Code Extraction Pipeline (Symbols, structure, language tags).
  4. Media Extraction Pipeline (Image dimensions, Audio wave headers).
  5. Error Isolation (Malformed and corrupt files handled without crashing).
  6. Security Governance (Path restrictions, SSRF blocking, Secret redaction, Untrusted tagging).
  7. Incremental Indexing & Change Detection (New, Unchanged O(1) skip, Modified).
  8. Deletion Propagation (Atomic purging from registry and RAG).
  9. Interrupted Ingestion Recovery (Reset stuck processing state).
  10. Action & Tool Integration (actions/knowledge_base.py ingest, ingestion_status, sync_incremental).
"""
import json
import shutil
import tempfile
import time
import unittest
import wave
from pathlib import Path

from PIL import Image

from actions import knowledge_base
from core.creator_knowledge import CreatorKnowledgeManager, get_creator_knowledge_manager
from core.document_intelligence import (
    DocumentParser,
    DocumentReasoningEngine,
    DocumentTable,
    export_table_csv,
    export_tables_xlsx,
)
from core.ingestion import (
    IngestionRegistry,
    IngestionStatus,
    Modality,
    ModalityDetector,
    SecurityGovernance,
    SemanticChunker,
    SourceRecord,
    SourceType,
    UniversalIngestionEngine,
    get_ingestion_engine,
)
from core.knowledge_graph import (
    EntityType,
    PersonalKnowledgeGraph,
    RelationType,
    get_knowledge_graph,
)
from core.live_monitor import LiveInformationMonitor, get_live_monitor
from core.media_intelligence import MediaIntelligenceEngine
from core.rag import get_knowledge_base
from core.research_engine import ResearchIntelligenceEngine, get_research_engine
from core.universal_search import UniversalSearchEngine, get_search_engine
from core.visual_intelligence import VisualIntelligenceEngine


class TestPhase13Acceptance(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="amatya_phase13_test_"))
        self.registry_file = self.test_dir / "test_ingestion_index.json"
        self.engine = UniversalIngestionEngine(registry_path=self.registry_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_modality_detection(self):
        """Verifies modality detection across documents, code, images, audio, video, web, data."""
        # 1. Plaintext and Markdown
        txt_file = self.test_dir / "notes.txt"
        txt_file.write_text("AMATYA research notes", encoding="utf-8")
        mod, mime = ModalityDetector.detect(txt_file)
        self.assertEqual(mod, Modality.DOCUMENT)
        self.assertEqual(mime, "text/plain")

        md_file = self.test_dir / "readme.md"
        md_file.write_text("# Documentation", encoding="utf-8")
        mod, mime = ModalityDetector.detect(md_file)
        self.assertEqual(mod, Modality.DOCUMENT)

        # 2. Python Code
        py_file = self.test_dir / "script.py"
        py_file.write_text("def hello(): pass\n", encoding="utf-8")
        mod, mime = ModalityDetector.detect(py_file)
        self.assertEqual(mod, Modality.CODE)

        # 3. CSV Data
        csv_file = self.test_dir / "data.csv"
        csv_file.write_text("id,name,value\n1,alpha,100\n", encoding="utf-8")
        mod, mime = ModalityDetector.detect(csv_file)
        self.assertEqual(mod, Modality.DATA)

        # 4. Web URL
        mod, mime = ModalityDetector.detect("https://google.com/search")
        self.assertEqual(mod, Modality.WEB)

        # 5. PNG Magic Bytes
        png_file = self.test_dir / "image.png"
        img = Image.new("RGB", (64, 64), color="red")
        img.save(png_file, format="PNG")
        mod, mime = ModalityDetector.detect(png_file)
        self.assertEqual(mod, Modality.IMAGE)
        self.assertEqual(mime, "image/png")

        # 6. WAV Magic Bytes
        wav_file = self.test_dir / "audio.wav"
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 1600)  # 0.1 sec silence
        mod, mime = ModalityDetector.detect(wav_file)
        self.assertEqual(mod, Modality.AUDIO)
        self.assertEqual(mime, "audio/wav")

    def test_02_document_extraction_pipeline(self):
        """Verifies text, markdown, HTML, and CSV structured extraction."""
        # Markdown extraction
        md_file = self.test_dir / "spec.md"
        md_file.write_text(
            "# Phase 13 Architecture\n\nAMATYA introduces a multimodal knowledge graph.\n\n## Section 2\n\nDetails on ingestion.",
            encoding="utf-8",
        )
        res = self.engine.ingest_file(md_file)
        self.assertTrue(res.is_success)
        self.assertEqual(res.modality, Modality.DOCUMENT)
        self.assertGreater(len(res.chunks), 0)
        self.assertIn("Phase 13", res.raw_text)

        # CSV extraction
        csv_file = self.test_dir / "telemetry.csv"
        csv_file.write_text("timestamp,metric,reading\n1001,cpu_temp,48.5\n1002,cpu_temp,49.2\n", encoding="utf-8")
        res_csv = self.engine.ingest_file(csv_file)
        self.assertTrue(res_csv.is_success)
        self.assertEqual(res_csv.modality, Modality.DATA)
        self.assertEqual(len(res_csv.tables), 1)
        self.assertEqual(res_csv.tables[0]["headers"], ["timestamp", "metric", "reading"])

    def test_03_code_extraction_pipeline(self):
        """Verifies code parsing, symbol detection, and structural chunking."""
        code_file = self.test_dir / "agent.py"
        code_content = (
            "import os\n\n"
            "class AutonomousAgent:\n"
            "    def __init__(self):\n"
            "        self.active = True\n\n"
            "    def execute_plan(self):\n"
            "        return 'executed'\n"
        )
        code_file.write_text(code_content, encoding="utf-8")
        res = self.engine.ingest_file(code_file)
        self.assertTrue(res.is_success)
        self.assertEqual(res.modality, Modality.CODE)
        self.assertIn("class AutonomousAgent", res.metadata.get("symbols", []))
        self.assertIn("def execute_plan", res.metadata.get("symbols", []))

    def test_04_media_extraction_pipeline(self):
        """Verifies image and audio metadata extraction."""
        # 1. Image
        img_path = self.test_dir / "test_visual.png"
        img = Image.new("RGB", (320, 240), color="blue")
        img.save(img_path, format="PNG")
        res_img = self.engine.ingest_file(img_path)
        self.assertTrue(res_img.is_success)
        self.assertEqual(res_img.modality, Modality.IMAGE)
        self.assertEqual(res_img.metadata.get("width"), 320)
        self.assertEqual(res_img.metadata.get("height"), 240)

        # 2. Audio
        wav_path = self.test_dir / "test_audio.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * 44100)  # 0.5s stereo
        res_audio = self.engine.ingest_file(wav_path)
        self.assertTrue(res_audio.is_success)
        self.assertEqual(res_audio.modality, Modality.AUDIO)
        self.assertEqual(res_audio.metadata.get("channels"), 2)
        self.assertEqual(res_audio.metadata.get("sample_rate"), 44100)

    def test_05_error_isolation_and_malformed_files(self):
        """Verifies that corrupted files are isolated gracefully without throwing exceptions."""
        corrupt_pdf = self.test_dir / "corrupted.pdf"
        corrupt_pdf.write_bytes(b"%PDF-1.4 [NOT A VALID PDF TRUNCATED DATA]")
        res = self.engine.ingest_file(corrupt_pdf)
        self.assertFalse(res.is_success)
        self.assertIsNotNone(res.error)
        self.assertIn("PDF extraction failure", res.error)

    def test_06_security_governance_and_redaction(self):
        """Verifies path restriction, SSRF guard, secret redaction, and untrusted tagging."""
        # 1. Path restriction
        forbidden = Path("/etc/shadow")
        valid, msg = SecurityGovernance.validate_path(forbidden)
        self.assertFalse(valid)
        self.assertIn("protected system directory", msg)

        # 2. SSRF Protection
        ssrf_valid, ssrf_msg = SecurityGovernance.validate_url("http://127.0.0.1:8080/admin")
        self.assertFalse(ssrf_valid)
        self.assertIn("restricted private or loopback IP", ssrf_msg)

        ssrf_valid2, _ = SecurityGovernance.validate_url("http://localhost:3000")
        self.assertFalse(ssrf_valid2)

        # 3. Secret Redaction
        secret_file = self.test_dir / "creds.txt"
        secret_file.write_text("My Google API key is AQ.mock_token_fixture_for_unit_tests_abcdefghijklmnopqrstuvwx in production.", encoding="utf-8")
        res = self.engine.ingest_file(secret_file)
        self.assertTrue(res.is_success)
        for chunk in res.chunks:
            self.assertTrue(chunk.untrusted)
            self.assertNotIn("AQ.mock_token_fixture_for_unit_tests_abcdefghijklmnopqrstuvwx", chunk.text)
            self.assertIn("[REDACTED", chunk.text)

    def test_07_incremental_indexing_and_change_detection(self):
        """Verifies that unchanged files are skipped in O(1) and modified files are re-indexed."""
        doc = self.test_dir / "change_test.txt"
        doc.write_text("Initial version of project requirements.", encoding="utf-8")

        # First ingestion -> NEW
        res1 = self.engine.ingest_file(doc)
        self.assertTrue(res1.is_success)
        self.assertFalse(res1.metadata.get("skipped", False))
        stats1 = self.engine.get_stats()
        self.assertEqual(stats1["total_sources"], 1)

        # Second ingestion without modification -> UNCHANGED (skipped)
        res2 = self.engine.ingest_file(doc)
        self.assertTrue(res2.metadata.get("skipped", False))

        # Check incremental preview
        preview = self.engine.check_incremental([doc])
        self.assertEqual(len(preview["unchanged"]), 1)
        self.assertEqual(len(preview["new"]), 0)
        self.assertEqual(len(preview["modified"]), 0)

        # Modify document -> MODIFIED
        time.sleep(0.05)
        doc.write_text("Updated version with revised phase goals.", encoding="utf-8")
        res3 = self.engine.ingest_file(doc)
        self.assertTrue(res3.is_success)
        self.assertFalse(res3.metadata.get("skipped", False))

    def test_08_deletion_propagation(self):
        """Verifies deletion from ingestion registry and RAG knowledge store."""
        note_res = self.engine.ingest_text("Unique AMATYA Phase 13 knowledge statement.", title="Deletion Note")
        self.assertTrue(note_res.is_success)
        sid = note_res.source_id

        # Verify present in registry
        rec = self.engine.registry.get(sid)
        self.assertIsNotNone(rec)

        # Propagate deletion
        deleted = self.engine.propagate_deletion(sid)
        self.assertTrue(deleted)
        self.assertIsNone(self.engine.registry.get(sid))

    def test_09_interrupted_recovery(self):
        """Verifies interrupted ingestion state is auto-recovered from PROCESSING to PENDING."""
        # Create a registry with an item stuck in PROCESSING
        stuck_rec = SourceRecord(
            source_id="stuck_file_123",
            uri="/path/to/stuck.pdf",
            source_type=SourceType.FILE.value,
            modality=Modality.DOCUMENT.value,
            mime_type="application/pdf",
            size_bytes=1024,
            content_hash="",
            mtime=time.time(),
            status=IngestionStatus.PROCESSING.value,
        )
        self.engine.registry.set(stuck_rec)

        # Re-initialize registry (simulating app restart after unexpected shutdown)
        new_registry = IngestionRegistry(index_path=self.registry_file)
        recovered = new_registry.get("stuck_file_123")
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.status, IngestionStatus.PENDING.value)

    def test_10_actions_integration(self):
        """Verifies actions/knowledge_base.py integration with ingest, ingestion_status, sync_incremental."""
        test_file = self.test_dir / "action_test.md"
        test_file.write_text("# Knowledge Base Action Integration\n\nTesting Phase 13 tool integration.", encoding="utf-8")

        # 1. Action: ingest file
        res = knowledge_base.execute({"action": "ingest", "path": str(test_file)})
        self.assertIn("status=done", res)
        self.assertIn("action=knowledge_base", res)
        self.assertIn("Successfully ingested file", res)

        # 2. Action: ingestion_status
        status_res = knowledge_base.execute({"action": "ingestion_status"})
        self.assertIn("status=done", status_res)
        self.assertIn("Ingestion Registry:", status_res)

        # 3. Action: sync_incremental preview
        sync_prev = knowledge_base.execute({"action": "sync_incremental", "path": str(self.test_dir), "preview": True})
        self.assertIn("status=done", sync_prev)
        self.assertIn("Incremental preview", sync_prev)

    def test_11_structural_document_parsing(self):
        """Verifies hierarchical heading recognition, breadcrumbs, figures, and footnotes."""
        doc_path = self.test_dir / "architecture_report.md"
        content = (
            "# 1. System Overview\n\n"
            "This report outlines the hardware topology.\n\n"
            "## 1.1 Compute Subsystem\n\n"
            "Intel i5 processor with 16GB memory.\n\n"
            "![System Block Diagram](block_diagram.png)\n\n"
            "### 1.1.1 Memory Controller\n\n"
            "DDR4 3200MHz bus architecture.\n\n"
            "[^1]: Memory timings verified at 1.2V.\n"
        )
        doc_path.write_text(content, encoding="utf-8")
        parsed = DocumentParser.parse(doc_path)
        self.assertIsNone(parsed.error)
        self.assertEqual(len(parsed.headings), 3)

        # Check levels and breadcrumbs
        self.assertEqual(parsed.headings[0].level, 1)
        self.assertEqual(parsed.headings[0].text, "1. System Overview")

        self.assertEqual(parsed.headings[1].level, 2)
        self.assertEqual(parsed.headings[1].breadcrumb, "1. System Overview > 1.1 Compute Subsystem")

        self.assertEqual(parsed.headings[2].level, 3)
        self.assertEqual(parsed.headings[2].breadcrumb, "1. System Overview > 1.1 Compute Subsystem > 1.1.1 Memory Controller")

        # Check figures and footnotes
        self.assertEqual(len(parsed.figures), 1)
        self.assertIn("System Block Diagram", parsed.figures[0].caption)
        self.assertEqual(len(parsed.references), 1)
        self.assertIn("Memory timings verified", parsed.references[0].text)

    def test_12_table_extraction_and_missing_values(self):
        """Verifies table parsing without silent zero-coercion, CSV/Markdown export, and Excel generation."""
        md_table_path = self.test_dir / "specs_table.md"
        content = (
            "# Hardware Specifications\n\n"
            "| Component | Operating Voltage | Current | Status |\n"
            "|---|---|---|---|\n"
            "| CPU Core | 1.2 V | 15.0 A | Active |\n"
            "| GPU Core | 0.95 V |  | Standby |\n"
            "| DRAM Bus | 1.2 V | 2.5 A |  |\n"
        )
        md_table_path.write_text(content, encoding="utf-8")
        parsed = DocumentParser.parse(md_table_path)
        self.assertEqual(len(parsed.tables), 1)

        tbl = parsed.tables[0]
        self.assertEqual(tbl.row_count, 3)
        self.assertEqual(tbl.col_count, 4)

        # Verify missing values are None (NOT converted to 0)
        self.assertIsNone(tbl.rows[1][2])  # GPU Current is missing
        self.assertIsNone(tbl.rows[2][3])  # DRAM Status is missing

        # Verify CSV export
        csv_str = tbl.to_csv()
        self.assertIn("CPU Core,1.2 V,15.0 A,Active", csv_str)
        self.assertIn("GPU Core,0.95 V,,Standby", csv_str)

        # Verify Excel multi-sheet export
        xlsx_path = self.test_dir / "exported_tables.xlsx"
        export_tables_xlsx(parsed.tables, xlsx_path)
        self.assertTrue(xlsx_path.exists())
        self.assertGreater(xlsx_path.stat().st_size, 100)

    def test_13_cross_reference_resolution(self):
        """Verifies in-text cross-reference linking to figures, tables, and sections."""
        doc_path = self.test_dir / "cross_ref_test.md"
        content = (
            "# Power Analysis\n\n"
            "The regulator parameters are defined as shown in Table 1 below.\n\n"
            "| Rail | Voltage |\n"
            "|---|---|\n"
            "| VCC | 3.3 V |\n\n"
            "For routing topologies, see Figure 2 on layout.\n"
        )
        doc_path.write_text(content, encoding="utf-8")
        parsed = DocumentParser.parse(doc_path)
        self.assertGreaterEqual(len(parsed.cross_references), 2)
        ref_types = [cr["type"] for cr in parsed.cross_references]
        self.assertIn("Table", ref_types)
        self.assertIn("Figure", ref_types)

    def test_14_document_reasoning_and_conclusions(self):
        """Verifies structural summarization, conclusion identification, and section finding."""
        doc_path = self.test_dir / "research_paper.md"
        content = (
            "# 1. Background\n\n"
            "Initial research into low-power IoT architectures.\n\n"
            "# 2. Power Consumption\n\n"
            "Under full load, power consumption peaks at 4.2 W.\n\n"
            "# 3. Conclusions\n\n"
            "The proposed regulator reduces static leakage by 35%.\n"
            "Thermal margins remain acceptable across ambient conditions.\n"
        )
        doc_path.write_text(content, encoding="utf-8")
        parsed = DocumentParser.parse(doc_path)

        # 1. Summarize
        summary = DocumentReasoningEngine.summarize(parsed)
        self.assertEqual(summary["total_headings"], 3)
        self.assertGreaterEqual(len(summary["conclusions"]), 1)
        self.assertIn("reduces static leakage", summary["conclusions"][0]["point"])
        self.assertIn("Conclusions", summary["conclusions"][0]["source_section"])

        # 2. Find Section
        matches = DocumentReasoningEngine.find_section(parsed, "power consumption")
        self.assertGreaterEqual(len(matches), 1)
        self.assertIn("Power Consumption", matches[0]["section_title"])

    def test_15_cross_document_comparison_and_discrepancies(self):
        """Verifies multi-document comparison detecting common parameters, agreements, and discrepancies."""
        doc_a_path = self.test_dir / "spec_revision_a.md"
        doc_a_path.write_text(
            "# Revision A Specifications\n\n"
            "Peak Power: 12.0 W\n"
            "Supply Voltage: 3.3 V\n"
            "Operating Temp: 70 C\n",
            encoding="utf-8",
        )

        doc_b_path = self.test_dir / "spec_revision_b.md"
        doc_b_path.write_text(
            "# Revision B Specifications\n\n"
            "Peak Power: 15.5 W\n"
            "Supply Voltage: 3.3 V\n"
            "Clock Rate: 4.0 GHz\n",
            encoding="utf-8",
        )

        doc_a = DocumentParser.parse(doc_a_path)
        doc_b = DocumentParser.parse(doc_b_path)

        comp = DocumentReasoningEngine.compare_documents(doc_a, doc_b)
        self.assertEqual(comp["common_parameters_count"], 2)

        # Agreement: Supply Voltage = 3.3 V
        self.assertEqual(len(comp["agreements"]), 1)
        self.assertEqual(comp["agreements"][0]["parameter"], "Supply Voltage")

        # Discrepancy: Peak Power = 12.0 W vs 15.5 W
        self.assertEqual(len(comp["discrepancies"]), 1)
        self.assertEqual(comp["discrepancies"][0]["parameter"], "Peak Power")

        # Unique parameters
        self.assertIn("Operating Temp", comp["unique_to_a"])
        self.assertIn("Clock Rate", comp["unique_to_b"])

    def test_16_document_intelligence_actions(self):
        """Verifies tool actions for parse_document, extract_tables, compare_documents, document_summary, find_section."""
        doc_path = self.test_dir / "system_guide.md"
        doc_path.write_text(
            "# System Operating Guide\n\n"
            "## 1. Power Guidelines\n\n"
            "System voltage must remain between 3.1 V and 3.5 V.\n\n"
            "| Rail | Nominal |\n"
            "|---|---|\n"
            "| VDD | 3.3 V |\n\n"
            "## 2. Conclusions\n\n"
            "All power rails operate within safety limits.\n",
            encoding="utf-8",
        )

        # 1. Action: parse_document
        res_parse = knowledge_base.execute({"action": "parse_document", "path": str(doc_path)})
        self.assertIn("status=done", res_parse)
        self.assertIn("Parsed 'system_guide.md'", res_parse)

        # 2. Action: extract_tables with CSV export
        csv_out = self.test_dir / "table_out.csv"
        res_tables = knowledge_base.execute({
            "action": "extract_tables",
            "path": str(doc_path),
            "output_path": str(csv_out),
        })
        self.assertIn("status=done", res_tables)
        self.assertIn("Extracted 1 table(s)", res_tables)
        self.assertTrue(csv_out.exists())

        # 3. Action: document_summary
        res_summary = knowledge_base.execute({"action": "document_summary", "path": str(doc_path)})
        self.assertIn("status=done", res_summary)
        self.assertIn("Document Summary", res_summary)
        self.assertIn("safety limits", res_summary)

        # 4. Action: find_section
        res_find = knowledge_base.execute({
            "action": "find_section",
            "path": str(doc_path),
            "query": "power guidelines",
        })
        self.assertIn("status=done", res_find)
        self.assertIn("Found 1 section match(es)", res_find)

    def test_17_visual_intelligence_analysis(self):
        """Verifies visual image analysis, classification, and element detection."""
        img_path = self.test_dir / "schematic_diagram.png"
        img = Image.new("RGB", (800, 600), color=(250, 250, 250))
        img.save(img_path, format="PNG")

        res = VisualIntelligenceEngine.analyze_image(img_path)
        self.assertEqual(res.image_type, "schematic")
        self.assertEqual(res.dimensions, (800, 600))
        self.assertGreaterEqual(res.confidence, 0.7)
        self.assertGreaterEqual(len(res.elements), 1)

    def test_18_visual_verification_of_desktop_action(self):
        """Verifies pre- and post-action visual change detection and bounding box isolation."""
        before_path = self.test_dir / "screen_before.png"
        after_path = self.test_dir / "screen_after.png"

        img_before = Image.new("RGB", (400, 300), color="white")
        img_before.save(before_path, format="PNG")

        img_after = Image.new("RGB", (400, 300), color="white")
        # Draw a small blue box simulating a clicked button state change
        for x in range(50, 150):
            for y in range(50, 100):
                img_after.putpixel((x, y), (0, 0, 255))
        img_after.save(after_path, format="PNG")

        # 1. Action with changes -> verified True
        verif = VisualIntelligenceEngine.verify_action(
            before_path,
            after_path,
            expected_change_region=(40, 40, 160, 110),
        )
        self.assertTrue(verif.verified)
        self.assertGreater(verif.change_ratio, 0.0)
        self.assertGreaterEqual(len(verif.changed_boxes), 1)

        # 2. Identical images -> verified False
        verif_same = VisualIntelligenceEngine.verify_action(before_path, before_path)
        self.assertFalse(verif_same.verified)
        self.assertEqual(verif_same.change_ratio, 0.0)

    def test_19_media_intelligence_audio_and_action_items(self):
        """Verifies timestamped audio transcription, speaker turns, and action item detection."""
        audio_path = self.test_dir / "standup_meeting.wav"
        with wave.open(str(audio_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 32000)  # 2.0s audio

        transcript = (
            "Good morning team. We need to deploy the new voltage regulator module by Friday. "
            "Please ensure the tests are passing. I will check the telemetry graphs."
        )
        res = MediaIntelligenceEngine.analyze_audio(audio_path, simulated_transcript=transcript)
        self.assertEqual(len(res.transcript_chunks), 4)
        self.assertGreaterEqual(len(res.action_items), 2)
        self.assertIn("Speaker 1", res.speakers_detected)
        self.assertGreater(res.duration_seconds, 0)

    def test_20_knowledge_graph_multi_hop_and_contradictions(self):
        """Verifies entity creation, 2-hop graph traversal, contradiction detection, and deletion cascading."""
        kg_file = self.test_dir / "test_kg.json"
        kg = PersonalKnowledgeGraph(storage_path=kg_file)

        # Add nodes
        p_node = kg.add_entity("Mark-LVI", EntityType.PROJECT)
        c_node = kg.add_entity("Phase 13", EntityType.CONCEPT)
        d_node = kg.add_entity("Android Phone", EntityType.DEVICE)

        # Add edges: Mark-LVI -> Phase 13 -> Android Phone
        kg.add_relationship(p_node.entity_id, RelationType.IMPLEMENTS, c_node.entity_id)
        kg.add_relationship(c_node.entity_id, RelationType.CONNECTED_TO, d_node.entity_id)

        # Multi-hop traversal: 2 hops from Mark-LVI should reach Android Phone
        hops = kg.traverse_multi_hop(p_node.entity_id, max_hops=2)
        target_names = [h["target_name"] for h in hops]
        self.assertIn("Phase 13", target_names)
        self.assertIn("Android Phone", target_names)

        # Contradiction detection
        node_a = kg.add_entity("Spec Alpha", EntityType.DOCUMENT)
        node_b = kg.add_entity("Spec Beta", EntityType.DOCUMENT)
        kg.add_relationship(node_a.entity_id, RelationType.CONTRADICTS, node_b.entity_id, source_context="Voltage conflict")
        contra = kg.detect_contradictions()
        self.assertEqual(len(contra), 1)
        self.assertEqual(contra[0]["source"], "Spec Alpha")

        # Deletion cascading
        del_count = kg.propagate_deletion(p_node.entity_id)
        self.assertGreater(del_count, 0)
        self.assertIsNone(kg.get_entity(p_node.entity_id))

    def test_21_universal_semantic_search(self):
        """Verifies hybrid search over RAG text chunks and knowledge graph entities."""
        searcher = UniversalSearchEngine()
        # Seed an entity in the graph
        kg = get_knowledge_graph()
        kg.add_entity("SearchTestEntity", EntityType.PROJECT, properties={"focus": "Multimodal"})

        hits = searcher.search("SearchTestEntity", top_k=5)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].retrieval_method, "knowledge_graph")

    def test_22_source_grounded_research_engine(self):
        """Verifies multi-step research workflow, evidence collection, and citation formatting."""
        researcher = ResearchIntelligenceEngine()
        report = researcher.conduct_research("Universal Ingestion architecture", max_sources=3)
        self.assertGreaterEqual(len(report.plan_steps), 5)
        self.assertEqual(report.topic, "Universal Ingestion architecture")
        md = report.to_markdown()
        self.assertIn("# Research Report:", md)
        self.assertIn("Executive Summary", md)

    def test_23_creator_knowledge_spaces(self):
        """Verifies isolated project knowledge spaces and context assembly."""
        spaces_file = self.test_dir / "test_spaces.json"
        km = CreatorKnowledgeManager(storage_path=spaces_file)

        space = km.create_space("iot_space", "IoT Project Space", description="Embedded IoT telemetry")
        self.assertEqual(space.space_id, "iot_space")

        switched = km.set_active_space("iot_space")
        self.assertTrue(switched)
        self.assertEqual(km.get_active_space().space_id, "iot_space")

        ctx = km.assemble_creator_context("Power regulation schematic")
        self.assertEqual(ctx["active_space"]["space_id"], "iot_space")
        self.assertIn("grounding_confidence", ctx)

    def test_24_live_information_monitor(self):
        """Verifies file change detection and baseline tracking."""
        mon_file = self.test_dir / "test_monitors.json"
        mon = LiveInformationMonitor(config_path=mon_file)

        watched_file = self.test_dir / "watched_log.txt"
        watched_file.write_text("Log line 1\n", encoding="utf-8")

        target = mon.register_monitor("log_target", "file", str(watched_file))
        self.assertEqual(target.target_id, "log_target")

        # Baseline check -> No change
        changed_1, _ = mon.check_target("log_target")
        self.assertFalse(changed_1)

        # Modify file -> Change detected
        time.sleep(0.05)
        watched_file.write_text("Log line 1\nLog line 2\n", encoding="utf-8")
        changed_2, explanation = mon.check_target("log_target")
        self.assertTrue(changed_2)
        self.assertIn("State change detected", explanation)

    def test_25_extended_knowledge_base_actions(self):
        """Verifies tool actions for graph_stats, graph_query, conduct_research, manage_space, live_monitor."""
        # 1. Action: graph_stats
        res_stats = knowledge_base.execute({"action": "graph_stats"})
        self.assertIn("status=done", res_stats)
        self.assertIn("Knowledge Graph:", res_stats)

        # 2. Action: conduct_research
        res_research = knowledge_base.execute({"action": "conduct_research", "topic": "AMATYA Architecture"})
        self.assertIn("status=done", res_research)

        # 3. Action: manage_space
        res_space = knowledge_base.execute({"action": "manage_space", "sub_action": "get_active"})
        self.assertIn("status=done", res_space)
        self.assertIn("Active Knowledge Space", res_space)


if __name__ == "__main__":
    unittest.main()
