# AMATYA Layered Memory Architecture

## Overview
AMATYA's memory architecture is organized into four distinct cognitive tiers designed for long-term consistency, high retrieval performance, and user privacy:

```
┌─────────────────────────────────────────────────────────────────┐
│                       WORKING MEMORY                            │
│  • Active task goal & current step index                        │
│  • Currently focused window (ID & title)                        │
│  • Most recently referenced files, projects, and devices        │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      EPISODIC MEMORY                            │
│  • Time-ordered logs of user requests & companion executions    │
│  • Outcome status (success / failure / blocked)                 │
│  • Failure diagnostics and replanning attempts                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                      SEMANTIC MEMORY                            │
│  • Long-term user preferences, hardware specs, relationships    │
│  • Confidence score (0.0 to 1.0) & Provenance tracking          │
│  • Contradiction detection preventing silent corruption         │
└────────────────────────────────┬────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                     PROCEDURAL MEMORY                           │
│  • Learned and approved multi-step automation routines          │
│  • Trigger conditions, action graphs, permission tiers          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Data Structures & Storage Format

### Semantic Fact Record
```json
{
  "fact_id": "preferences_favorite_editor",
  "category": "preferences",
  "subject": "user",
  "predicate": "favorite_editor",
  "object_value": "VS Code with Vim Keybindings",
  "classification": "user_preference",
  "provenance": "user_stated",
  "confidence": 1.0,
  "source_context": "User switched editors",
  "verified": true,
  "updated_at": 1793872200.0
}
```

### Provenance Classifications
- `user_stated`: Explicitly articulated by the user in natural language conversation. (Default confidence: 0.95–1.0).
- `observed`: Extracted from desktop behavior, shell history, or IDE activity. (Default confidence: 0.70–0.85).
- `inferred`: Deduced through LLM analysis or repeated interaction patterns. (Default confidence: 0.50–0.70).

---

## 2. Contradiction Detection Engine

When a new fact $(S, P, V_{\text{new}})$ is proposed:
1. The memory engine queries existing verified facts for $(S, P)$.
2. If an existing fact exists with value $V_{\text{old}} \neq V_{\text{new}}$:
   - If `allow_overwrite=False`, the transaction is aborted with a structured `ContradictionOutcome` and an explicit diagnostic error:
     *"Contradiction detected: 'user favorite_editor' is currently recorded as 'Neovim'. Overwrite requires explicit confirmation."*
   - If `allow_overwrite=True` or explicitly corrected via `correct_fact()`, the old fact is superseded, and a corresponding `user_correction` event is appended to episodic memory.

---

## 3. Privacy, Purge, and Disablement Controls

1. **Atomic Purge (`delete_memory`):**
   When `delete_memory(key)` is invoked:
   - The key is purged from `memory/semantic_memory.json`.
   - The key is mirrored out of legacy `memory/long_term.json`.
   - The purge event is logged to episodic audit records.
2. **Global Disablement (`set_memory_enabled`):**
   - When set to `False`, all storage calls immediately return `ok: False` with `"Memory system is currently disabled."`
   - No context extraction or facts are recorded to disk.
3. **Secret Redaction:**
   - Any string matching API keys, `.env` files, passwords, or session tokens is automatically redacted via `core.security.redact_secrets` before disk write.

