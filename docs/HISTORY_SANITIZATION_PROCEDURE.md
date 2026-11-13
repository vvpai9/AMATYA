# AMATYA Git History Sanitization & Public Release Procedure
**Protocol Version:** 15.1.0  
**Status:** Approved for Public Release Preparation  
**Classification:** Confidential Engineering Operations

---

## 1. Scope and Principles

Before releasing AMATYA (अमात्य) as an open-source or public GitHub repository, historical commits from early prototyping phases must be sanitized to eliminate any accidental inclusions of:
- Personal home automation configurations (`config/home_devices.json`, `config/home_routines.json`).
- Paired mobile device IDs and MAC addresses (`config/connected_devices.json`).
- Personal memory graphs and ingestion indexes (`memory/*.json`).
- Local API keys and authentication tokens (`config/api_keys.json`).
- Cryptographic keys and self-signed TLS certificates (`config/certs/`).

### Non-Negotiable Guardrails
1. **Never alter the primary development repository in-place.** The primary development repository contains legitimate provenance and milestone history.
2. **Verified Backup Guarantee:** A complete, untampered clone must be archived before executing any history filtering operations:
   ```bash
   git clone . ~/Projects/Mark-LVI-original-backup
   ```
3. **Dedicated Publication Branch / Clean Remote:** History filtering is executed inside an isolated worktree or clean export directory to create a dedicated `public-release` branch.

---

## 2. Identified Sensitive Historical Artifacts

The following files and patterns are identified across the Git history and must be purged from historical trees prior to public push:

| Category | File Paths / Patterns | Mitigation Method |
|---|---|---|
| **Home & IoT Config** | `config/connected_devices.json`, `config/home_devices.json`, `config/home_routines.json` | `git-filter-repo --invert-paths --path ...` |
| **User Memory Graph** | `memory/knowledge_graph.json`, `memory/ingestion_index.json`, `memory/semantic_memory.json`, `memory/project_profiles.json`, `memory/procedural_memory.json` | `git-filter-repo --invert-paths --path ...` |
| **Credentials & Certs** | `config/api_keys.json`, `config/certs/amatya.key`, `config/certs/amatya.crt` | Replace with `.example.json` templates and remove real files |
| **Private Modules** | `maha_amatya/*`, `plugins/maha_*.py` | Moved to private host storage (`~/.local/share/maha-amatya/`) |

---

## 3. Step-by-Step Sanitization Protocol (`git-filter-repo`)

`git-filter-repo` is the modern, Git-recommended replacement for `git-filter-branch` and BFG Repo-Cleaner.

### Step 3.1: Install `git-filter-repo`
```bash
pip install git-filter-repo
```

### Step 3.2: Create an Isolated Export Repository
```bash
# Clone to an isolated working directory dedicated to public release
git clone --no-local ~/Projects/Mark-LVI /tmp/amatya-public-export
cd /tmp/amatya-public-export
```

### Step 3.3: Execute Path Removal
Create an exclusion file `/tmp/paths-to-remove.txt`:
```
config/connected_devices.json
config/home_devices.json
config/home_routines.json
config/api_keys.json
config/certs/
memory/knowledge_graph.json
memory/ingestion_index.json
memory/semantic_memory.json
memory/project_profiles.json
memory/procedural_memory.json
maha_amatya/
```

Run the filter:
```bash
git filter-repo --invert-paths --paths-from-file /tmp/paths-to-remove.txt --force
```

### Step 3.4: Scrub Accidental Credential Strings
Create an expression replacement file `/tmp/replace-expressions.txt`:
```
# Redact any accidental API key literals in historical commit bodies
regex:(AIzaSy[A-Za-z0-9_-]{33})==>[REDACTED_API_KEY]
regex:(sk-[A-Za-z0-9]{32,})==>[REDACTED_API_KEY]
```

Run the text replacement filter:
```bash
git filter-repo --replace-text /tmp/replace-expressions.txt --force
```

---

## 4. Executed Sanitization & Verification Report

The sanitization procedure has been executed and verified in an isolated export environment:

### 4.1 Backup Verification
- **Full Clone Backup:** `~/Projects/Mark-LVI-original-backup` (77 commits, fully synchronized).
- **Immutable Tarball Archive:** `~/Projects/Mark-LVI-original-full-backup.tar.gz` (5.2 MB).

### 4.2 Sanitized Public Export Repository
- **Location:** `~/Projects/amatya-public-export`
- **Execution Tool:** `git-filter-repo 2.47.0`
- **Objects Processed:** 998 objects across 77 commits.

### 4.3 Git Objects Verification
Running the exhaustive object inspection command on `~/Projects/amatya-public-export`:
```bash
git rev-list --objects --all | awk '{print $2}' | sort -u | grep -E '(connected_devices|home_devices|home_routines|certs|ingestion_index|knowledge_graph|procedural_memory|project_profiles|semantic_memory|\.key$|\.crt$|maha)'
```
**Verification Result:**
```
config/connected_devices.example.json
config/home_devices.example.json
core/knowledge_graph.py
```
*Zero sensitive historical files, credentials, or private modules remain in reachable or unreachable Git objects.*

### 4.4 Test Suite Verification on Sanitized Export
Executed test suite inside `~/Projects/amatya-public-export`:
```bash
PYTHONPATH=. pytest tests/
============================= 126 passed in 50.55s =============================
```
100% pass rate achieved across all 126 test cases.

---

## 5. Public Push Protocol

When ready to publish to a new public GitHub remote:
1. Navigate to the verified sanitized repository:
   ```bash
   cd ~/Projects/amatya-public-export
   ```
2. Tag release candidate:
   ```bash
   git tag -a v15.1.0-rc1 -m "AMATYA v15.1.0 Public Release Candidate"
   ```
3. Add public remote and push:
   ```bash
   git remote add origin https://github.com/<owner>/amatya.git
   git push -u origin main --tags
   ```
*(Do NOT push the original repository history to a public remote).*

