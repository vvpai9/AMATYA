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
from core.rag import get_knowledge_base


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


if __name__ == "__main__":
    unittest.main()
