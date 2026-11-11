# AMATYA Release Candidate 15.1.0 (अमात्य)
**Release Version:** v15.1.0-rc1  
**Test Suite Status:** 122 passed / 122 total (100% pass rate)  
**Verification Date:** 2026-11-10

---

## 1. Executive Summary

AMATYA Phase 15.1 establishes complete security hardening, centralized authorization governance, pre-import plugin trust verification via AST parsing, genuine OS process isolation for scientific simulations, DNS-rebinding proof IP-pinned HTTP/HTTPS transport and mandatory TLS for remote operations.

---

## 2. Key Remediation Deliverables & Hardening

### 1. Fail-Closed Authorization Gateway (`core/security.py`, `core/action_loader.py`, `core/plugin_loader.py`, `main.py`)
- **Remediation:** Removed fail-open `except Exception:` blocks across all dispatch pipelines.
- **Fail-Closed Guarantee:** Any unexpected exception or crash in the security gateway immediately denies execution with `Permission Denied: Security Gateway error ... Denied by default (fail-closed)`.
- **Verification:** Unit tests with failure injection (`test_fail_open_authorization_protection_action_registry`, `test_fail_open_authorization_protection_plugin_registry`) verify execution refusal.

### 2. Mandatory TLS for LAN Operations (`dashboard/server.py`)
- **Remediation:** Serving cleartext HTTP across local networks is strictly disallowed.
- **Enforcement:** `DashboardServer._ssl_enabled()` enforces TLS certificates (`amatya.crt`, `amatya.key`) whenever `dashboard_lan` is active. Attempting to bind cleartext sets `_bind_error` and halts startup.
- **Verification:** `test_mandatory_tls_for_lan_mode` verifies refusal to serve cleartext.

### 3. Pre-Import Plugin Trust Approval & Static AST Manifest Inspection (`core/plugin_loader.py`)
- **Remediation (Issue 2.1):** Unapproved plugins previously executed module-level code during discovery import. Now plugins are inspected strictly via Python AST analysis (`ast.parse`) without executing any code.
- **Pre-Import Trust Gate:** `spec.loader.exec_module()` is never called for unapproved plugins. Code import is suppressed until explicit trust approval is granted.
- **Verification:** `test_unapproved_plugin_code_never_executed_during_discovery` confirms that plugins with top-level exceptions/payloads are safely inspected without executing code.

### 4. Genuine OS Process Isolation for Simulation Engine (`core/simulation_engine.py`)
- **Process Isolation (Issue 2.2):** Replaced thread-based execution with isolated OS processes (`multiprocessing.Process` via `spawn` context).
- **Hard Timeout Force-Kill:** On timeout, the child process is terminated via `SIGTERM` and `SIGKILL`, completely terminating runaway computations without blocking caller threads.
- **Resource Limits:** OS-level CPU execution time limits (`RLIMIT_CPU`) and virtual memory limits (`RLIMIT_AS`) are enforced on worker processes.

### 5. Hardened SSRF & DNS-Rebinding Proof IP Pinning (`core/ingestion.py`, `core/security.py`)
- **Anti-DNS Rebinding (Issue 2.4):** To eliminate the TOCTOU DNS rebinding gap where `urllib.request` re-resolves domain names during socket connection, `SecurityGovernance.validate_and_resolve_url()` pre-resolves and validates the destination IP.
- **Pinned IP Transport:** `PinnedIPHTTPConnection` and `PinnedIPHTTPSConnection` bind TCP sockets strictly to the pre-validated IP address, while passing the original hostname for HTTP `Host` headers, TLS SNI, and certificate validation.
- **Biometric Redaction:** Audit logs mask high-dimensional biometric embedding float vectors (`[REDACTED_BIOMETRIC_VECTOR]`), raw audio bytes (`[REDACTED_AUDIO_BYTES]`), and sensitive authentication keys.

### 6. Reproducible Release Verification (`.github/workflows/ci.yml`, `tests/`)
- Complete GitHub Actions automated workflow for matrix Python 3.12 testing.
- Full test suite passes 127 out of 127 tests across all milestones (Phases 11–15).

---

## 3. Test Suite Pass Matrix

| Test Suite | Focus Area | Result |
|---|---|---|
| `test_phase11_acceptance.py` | Central Intelligence, Model Collaboration, Audio Cues | **14 / 14 Passed** |
| `test_phase12_acceptance.py` | Contextual Memory, Workflows, Procedural Engine | **8 / 8 Passed** |
| `test_phase13_acceptance.py` | Multimodal Ingestion, Knowledge Graph, SSRF & Governance | **25 / 25 Passed** |
| `test_phase14_acceptance.py` | Deterministic Math, Process-Isolated Simulation, Decision Intelligence | **13 / 13 Passed** |
| `test_phase15_security.py` | Central Security Gateway, CSRF, PIN Lockout, AST Plugin Trust, IP Pinning | **22 / 22 Passed** |
| `test_amatya_suite.py` | Wayland Desktop, Multi-modal Vision, Audio Synthesis | **8 / 8 Passed** |
| `test_session_bugfixes.py` | Local Timezone, Voice Auth Strictness, Document Comparison | **10 / 10 Passed** |
| `test_user_enhancements.py` | Spectacle Wayland Screenshot, Computer Control, Vision Fallback | **22 / 22 Passed** |
| **Total** | **Full Milestone Regression Suite** | **122 / 122 Passed (100%)** |

