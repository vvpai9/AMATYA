# AMATYA Security Policy & Governance

This document describes the security model, vulnerability reporting procedures, and architectural defense-in-depth principles implemented in **AMATYA (अमात्य)**.

---

## 1. Security Architecture & Threat Model

AMATYA operates as an autonomous, multi-modal personal assistant with direct desktop, local file system, network, and device control capabilities. To protect against malicious prompt injections, arbitrary code execution, lateral privilege escalation, and data exfiltration, AMATYA enforces a **zero-trust defense-in-depth model**:

### 1.1 Centralized Authorization Gateway (`core/security.py`)
All tool executions—whether initiated via voice, chat, background automation, or external triggers—must pass through `core.security.authorize_tool_execution`:
- **Fail-Closed Policy:** Any unregistered or unclassified tool is immediately blocked.
- **Prompt Injection Defense:** Every tool parameter is scanned for adversarial prompt injection patterns (`ignore previous instructions`, jailbreak tokens, etc.) and blocked prior to dispatch.
- **Biometric & PIN Step-Up Verification:** Sensitive operations (shell execution, code modifications, system configuration, shutdown) require active speaker verification and progressive PBKDF2-HMAC-SHA256 PIN authentication.
- **Rate-Limiting & Lockout:** 5 consecutive failed PIN attempts trigger exponential backoff and a mandatory 60-second lockout.

### 1.2 Restricted Symbolic AST Parser (`core/scientific_computation.py`)
Deterministic mathematical evaluation uses a restricted Abstract Syntax Tree (AST) validator (`safe_sympify`) that forbids attribute traversal (`.__class__`, `.__globals__`), arbitrary module imports (`__import__`), lambda definitions, and system executions.

### 1.3 Strict SSRF & Content-Addressable Ingestion (`core/ingestion.py`)
- **SSRF Defense:** URL validation resolves both IPv4 (`AF_INET`) and IPv6 (`AF_INET6`) addresses against private, loopback, link-local, and multicast ranges before initiating network requests.
- **Safe HTTP Redirects:** `SafeRedirectHandler` intercepts all HTTP/HTTPS redirects and re-validates each intermediate target.
- **Cryptographic Content Integrity:** File synchronization compares SHA-256 content hashes in addition to file modification times.

### 1.4 Dashboard Security (`dashboard/server.py`)
- **Bearer Token Authentication:** Mandated on all sensitive control endpoints (`/api/command-centre`, `/api/emergency-stop`, `/api/autonomy`, `/api/command`).
- **CSRF & Origin Header Checking:** Rejects cross-origin state-changing requests.
- **Localhost Default:** Binds to `127.0.0.1` by default unless LAN mode is explicitly enabled by the user.

---

## 2. Reporting a Security Vulnerability

If you discover a security vulnerability in AMATYA:
1. **Do not create a public issue or disclosure.**
2. Send detailed disclosure information, including reproduction steps, affected versions, and proof of concept to the project maintainers.
3. Vulnerabilities will be triaged and addressed with high priority.

