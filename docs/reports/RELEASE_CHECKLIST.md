# AMATYA Public Release Checklist (Phase 15)

## 1. Secrets & Credentials Scan
- [x] No plaintext API keys or tokens in code files.
- [x] `config/api_keys.json` untracked and covered in `.gitignore`.
- [x] Sanitized `config/api_keys.example.json` created.
- [x] Sensitive device/network configuration untracked (`connected_devices.json`, `home_devices.json`).
- [x] PBKDF2-HMAC-SHA256 PIN hashing enforced with rate-limiting.

## 2. Security Gateway & Input Validation
- [x] Centralized authorization gateway active on all action, plugin, and orchestrator execution paths.
- [x] Unclassified or unregistered tools fail closed.
- [x] Prompt injection vectors blocked on tool parameters.
- [x] Restricted AST parser (`safe_sympify`) eliminates arbitrary code execution in symbolic math.
- [x] SSRF validation verifies IPv4 and IPv6 addresses against private and loopback networks.
- [x] Dashboard endpoints secured with Bearer tokens, CSRF protection, and local interface binding.

## 3. Portability & Hygiene
- [x] No hardcoded user paths (`/home/username`) in active code.
- [x] Clean, deduplicated `requirements.txt`.
- [x] `.gitignore` comprehensive across virtual environments, cache files, memory databases, and personal configs.
- [x] Python 3.12 compatibility verified.

## 4. Test Verification
- [x] 127 / 127 unit, security, and acceptance tests passing (100% pass rate).
- [x] Zero regressions across Phases 11–15.
- [x] Git history fully preserved across all 76 commits.

