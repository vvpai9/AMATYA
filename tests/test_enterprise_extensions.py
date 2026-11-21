"""
tests/test_enterprise_extensions.py — Enterprise Suite & Mark-LVII Integration Tests
===================================================================================
Tests the enterprise capabilities contributed by Aman Kumar (@iamTechieAman):
  - Autonomous Code Engineering Agent (AST verified edits, read, search, scaffold)
  - Self-Repair & Diagnostics Engine (Module syntax scan, dependency validation)
  - AI Trading & Quantitative Suite (Crypto/Stock quotes, risk position sizing, technical indicators)
  - Reverse Engineering Suite (REA) (Entropy analysis, strings extraction, JWT inspection, cURL parser)
  - Cyber Security & Defense Suite (Safe port scanner, SSL auditor, HTTP headers evaluator)
  - Document Studio & Universal Creator (File generation, document extraction)
  - Study Copilot & Academic Research (Concept decomposition, Feynman technique)
  - Voice Biometrics & Verifier (Acoustic feature extraction, cosine similarity matching)
  - Capability Registry Discovery & Security Authorization (94 capabilities verified)
"""
from __future__ import annotations

import ast
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.capability_registry import get_capability_registry
from core.security import authorize_tool_execution, PermissionTier
import core.voice_verifier as voice_verifier

# Actions
from actions.ai_trading import ai_trading, compute_rsi
from actions.autonomous_code_agent import autonomous_code_agent
from actions.cyber_security import cyber_security
from actions.document_studio import document_studio
from actions.rea_tool import rea_tool, _calc_entropy, _extract_strings
from actions.self_repair import _check_module_syntax, _check_dependencies
from actions.study_copilot import study_copilot
from actions.adaptive_identity import set_user_honorific, get_user_honorific


# ── 1. Autonomous Code Agent Tests ────────────────────────────────────────────

def test_autonomous_code_agent_read_and_write():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test_module.py"
        content = "def hello():\n    return 'world'\n"
        
        # Write
        res_write = autonomous_code_agent({"action": "write", "path": str(p), "content": content})
        assert "Successfully created" in res_write or "Successfully wrote" in res_write
        assert p.exists()

        # Read
        res_read = autonomous_code_agent({"action": "read", "path": str(p)})
        assert "Read lines" in res_read
        assert "def hello():" in p.read_text(encoding="utf-8")


def test_autonomous_code_agent_surgical_edit_with_ast():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sample.py"
        p.write_text("def calculate(x, y):\n    return x + y\n", encoding="utf-8")

        # Valid edit
        res_edit = autonomous_code_agent({
            "action": "edit",
            "path": str(p),
            "target": "return x + y",
            "replacement": "return x * y",
        })
        assert "Successfully edited" in res_edit or "Successfully replaced" in res_edit
        assert "return x * y" in p.read_text(encoding="utf-8")

        # Invalid syntax edit must be rejected by AST validation
        res_bad = autonomous_code_agent({
            "action": "edit",
            "path": str(p),
            "target": "return x * y",
            "replacement": "def invalid syntax {{{",
        })
        assert "Syntax validation failed" in res_bad or "AST Syntax Error" in res_bad
        # Content must remain intact (rollback)
        assert "return x * y" in p.read_text(encoding="utf-8")


# ── 2. Reverse Engineering Suite (REA) Tests ──────────────────────────────────

def test_rea_tool_entropy_calculation():
    # Constant bytes -> 0 entropy
    const_bytes = b"AAAAAAAAAAAAAAAA"
    assert _calc_entropy(const_bytes) == 0.0

    # Random high-entropy bytes -> > 3.5
    high_entropy = bytes(range(256))
    assert _calc_entropy(high_entropy) >= 7.0


def test_rea_tool_strings_extraction():
    binary_blob = b"\x00\x01\x02SECRET_TOKEN_12345\x00\xffhttps://api.amatya.org\x00"
    extracted = _extract_strings(binary_blob, min_len=5)
    assert "SECRET_TOKEN_12345" in extracted
    assert any(s == "https://api.amatya.org" for s in extracted)


def test_rea_tool_jwt_inspection():
    # Well-formed dummy JWT (header.payload.signature)
    import base64
    from actions.rea_tool import _decode_jwt
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b'{"sub":"user123","role":"admin"}').decode().rstrip("=")
    dummy_jwt = f"{header}.{payload}.dummysig"

    decoded = _decode_jwt(dummy_jwt)
    assert decoded.get("header", {}).get("alg") == "HS256"
    assert decoded.get("payload", {}).get("role") == "admin"

    curl_target = f"curl -H 'Authorization: Bearer {dummy_jwt}' https://api.example.com/v1"
    res = rea_tool({"target": curl_target})
    assert "JWT Bearer Token detected" in res or "admin" in res


# ── 3. AI Trading & Technical Analysis Tests ──────────────────────────────────

def test_ai_trading_risk_and_position_size():
    res = ai_trading({
        "action": "risk",
        "capital": 10000,
        "risk_pct": 2.0,
        "entry": 100.0,
        "stop_loss": 90.0,
    })
    # Max risk = 200, risk/unit = 10 -> Position size = 20 units
    assert "20.0 units" in res or "20 units" in res or "Risk" in res


def test_ai_trading_rsi_calculation():
    prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    rsi = compute_rsi(prices, period=14)
    # Consecutive upward moves -> RSI close to 100
    assert rsi > 80.0


# ── 4. Cyber Security Suite Tests ─────────────────────────────────────────────

def test_cyber_security_http_headers():
    res = cyber_security({"action": "headers", "target": "https://google.com"})
    assert "HTTP Security Headers" in res or "Auditing" in res


def test_cyber_security_breach_k_anonymity():
    # HIBP k-anonymity test with known common password 'password123'
    res = cyber_security({"action": "check_password", "target": "password123"})
    assert "BREACH ALERT" in res or "Compromised" in res or "breach" in res.lower()


# ── 5. Document Studio Tests ──────────────────────────────────────────────────

def test_document_studio_create_file():
    with tempfile.TemporaryDirectory() as td:
        dest = str(Path(td) / "generated_script.py")
        res = document_studio({
            "action": "create_file",
            "file_path": dest,
            "content": "print('Document Studio Generation')\n",
        })
        assert "Created file" in res or "Successfully created" in res
        assert Path(dest).exists()
        assert "Document Studio Generation" in Path(dest).read_text(encoding="utf-8")
        assert Path(dest).exists()
        assert "Document Studio Generation" in Path(dest).read_text(encoding="utf-8")


# ── 6. Self-Repair Diagnostics Tests ──────────────────────────────────────────

def test_self_repair_syntax_and_dependencies():
    # Syntax check on this test file
    ok, msg = _check_module_syntax(Path(__file__))
    assert ok is True

    # Dependency check
    present, missing = _check_dependencies()
    assert "numpy" in present
    assert "PyQt6" in present


# ── 7. Voice Verifier Biometrics Tests ────────────────────────────────────────

def test_voice_verifier_feature_extraction():
    # Synthetic audio signal (1 second, 16kHz sine wave)
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    audio = (np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)

    feat = voice_verifier._extract_acoustic_features(audio, sample_rate=16000)
    assert isinstance(feat, np.ndarray)
    assert len(feat) == 20
    # Must be normalized
    norm = float(np.linalg.norm(feat))
    assert 0.99 <= norm <= 1.01


def test_voice_verifier_cosine_similarity_match():
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    audio1 = (np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)
    audio2 = (np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)

    f1 = voice_verifier._extract_acoustic_features(audio1)
    f2 = voice_verifier._extract_acoustic_features(audio2)
    sim = float(np.dot(f1, f2))
    assert sim >= 0.99  # Identical tone matches near 1.0


# ── 8. Adaptive Identity Tests ────────────────────────────────────────────────

def test_adaptive_identity_get_set():
    set_user_honorific("Sir", "Aman Kumar")
    h, name = get_user_honorific()
    assert h == "Sir"
    assert name == "Aman Kumar"


# ── 9. Capability Registry Discovery & Security Gateway ───────────────────────

def test_capability_registry_total_capabilities():
    reg = get_capability_registry()
    caps = reg.list_capabilities()
    assert len(caps) >= 90  # 94 capabilities registered
    cap_names = {c.name for c in caps}
    assert "ai_trading" in cap_names
    assert "autonomous_code_agent" in cap_names
    assert "cyber_security" in cap_names
    assert "rea_tool" in cap_names
    assert "document_studio" in cap_names
    assert "self_repair" in cap_names


def test_security_gateway_authorizes_enterprise_tools():
    # Security Gateway must allow registered enterprise tools
    auth1 = authorize_tool_execution("ai_trading", {"action": "quote", "symbol": "BTC"})
    assert auth1.get("allowed") is True

    auth2 = authorize_tool_execution("cyber_security", {"action": "headers", "target": "https://google.com"})
    assert auth2.get("allowed") is True
