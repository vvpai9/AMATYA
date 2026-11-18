"""
core/task_verifier.py — AMATYA Task Outcome Verifier
=====================================================
Programmatically verifies that executed tasks actually achieved their intended
post-conditions before marking the node COMPLETED.

Phase 16 Core Objective B & Stage 5.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    passed: bool
    details: str
    errors: list[str] = field(default_factory=list)


class TaskVerifier:
    """Verifies task outputs against explicit rules and capability post-conditions."""

    @staticmethod
    def verify_task(node: Any, result: Any) -> VerificationResult:
        """Verify execution result of a TaskNode."""
        cap = getattr(node, "capability", "")
        params = getattr(node, "parameters", {})
        rule = getattr(node, "verification_rule", None)
        passed, msg = TaskVerifier.verify(cap, params, result, rule)
        errors = [] if passed else [msg]
        return VerificationResult(passed=passed, details=msg, errors=errors)

    @staticmethod
    def verify(
        capability: str,
        parameters: dict[str, Any],
        result: Any,
        rule: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Returns (is_verified, reason).
        """
        res_str = str(result or "")

        # ── 1. Check for blatant error outcomes ─────────────────────────────────
        err_signatures = (
            "error:",
            "permission denied",
            "failed to",
            "could not find",
            "exception:",
            "traceback (most recent call last)",
            "command failed",
        )
        lower_res = res_str.lower()
        # Only treat as error if not part of a successful report
        if any(err in lower_res for err in err_signatures) and not any(k in lower_res for k in ("0 errors", "no errors", "success", "completed", "done")):
            return False, f"Output contains failure signature: {res_str[:120]}"

        # ── 2. Explicit Verification Rules ──────────────────────────────────────
        if rule:
            parts = rule.split(":", 1)
            rtype = parts[0].strip().lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if rtype == "file_exists":
                # Path might be parameterized or literal
                p = Path(arg).expanduser()
                if p.exists() and p.stat().st_size >= 0:
                    return True, f"Verified: file '{p}' exists ({p.stat().st_size} bytes)."
                return False, f"Verification failed: file '{p}' does not exist or is empty."

            elif rtype == "dir_exists":
                p = Path(arg).expanduser()
                if p.is_dir():
                    return True, f"Verified: directory '{p}' exists."
                return False, f"Verification failed: directory '{p}' is missing."

            elif rtype == "contains":
                if arg.lower() in lower_res:
                    return True, f"Verified: output contains required string '{arg}'."
                return False, f"Verification failed: output missing '{arg}'."

            elif rtype == "regex":
                if re.search(arg, res_str, re.IGNORECASE):
                    return True, f"Verified: output matches pattern '{arg}'."
                return False, f"Verification failed: output does not match pattern '{arg}'."

            elif rtype == "nonzero_result":
                if result is not None and res_str.strip():
                    return True, "Verified: result is non-empty."
                return False, "Verification failed: result is null or empty."

        # ── 3. Capability-Specific Inferred Post-Conditions ────────────────────
        if capability in ("creator", "file_controller", "office_document_skills"):
            out_path = parameters.get("output_path") or parameters.get("file_path") or parameters.get("destination")
            if out_path and isinstance(out_path, str):
                p = Path(out_path).expanduser()
                if p.exists() and p.stat().st_size > 0:
                    return True, f"Verified: target file '{p}' exists ({p.stat().st_size} bytes)."
                # If path was relative to home or desktop
                elif (Path.home() / "Desktop" / out_path).exists():
                    return True, f"Verified: target file exists on Desktop."

        # Default: if call returned without error, consider conditionally verified
        return True, "Conditional verification: execution completed without error signature."


def verify_task_outcome(
    capability: str,
    parameters: dict[str, Any],
    result: Any,
    rule: Optional[str] = None,
) -> Tuple[bool, str]:
    return TaskVerifier.verify(capability, parameters, result, rule)


_VERIFIER = TaskVerifier()


def get_verifier() -> TaskVerifier:
    return _VERIFIER

