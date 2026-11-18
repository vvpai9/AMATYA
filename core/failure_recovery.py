"""
core/failure_recovery.py — AMATYA Failure Recovery & Adaptive Replanning Engine
==============================================================================
Diagnoses errors, distinguishes transient vs. permanent faults, enforces safety
guards against retrying destructive operations, and generates recovery strategies.

Phase 16 Core Objective B.3 (Failure Recovery).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    TRANSIENT = "TRANSIENT"                    # Network glitch, rate limit, busy socket -> safe retry with backoff
    PERMANENT = "PERMANENT"                    # Missing file, invalid parameter -> requires replanning or user fix
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"  # Rejected by security gateway or user -> do NOT retry
    UNSUPPORTED = "UNSUPPORTED"                # Missing binary, missing capability -> suggest fallback


@dataclass
class RecoveryPlan:
    category: ErrorCategory
    can_retry: bool
    backoff_seconds: float
    recommended_strategy: str
    suggested_alternative: Optional[Dict[str, Any]] = None


class FailureRecoveryEngine:
    """Diagnoses task execution failures and determines safe recovery actions."""

    @staticmethod
    def diagnose(
        capability: str,
        parameters: Dict[str, Any],
        error_msg: str,
        retry_count: int = 0,
        max_retries: int = 2,
        is_reversible: bool = True,
    ) -> RecoveryPlan:
        err_lower = (error_msg or "").lower()

        # ── 1. Security or Authorization Denial ────────────────────────────────
        if "permission denied" in err_lower or "security gateway denied" in err_lower or "unapproved" in err_lower:
            return RecoveryPlan(
                category=ErrorCategory.AUTHORIZATION_DENIED,
                can_retry=False,
                backoff_seconds=0.0,
                recommended_strategy="Escalate to user for explicit authorization; do not retry automatically.",
            )

        # ── 2. Irreversible Operation Safety Guard ────────────────────────────
        # Never automatically retry destructive operations
        if not is_reversible or any(k in capability.lower() for k in ("delete", "rm", "kill", "format", "reboot")):
            return RecoveryPlan(
                category=ErrorCategory.PERMANENT,
                can_retry=False,
                backoff_seconds=0.0,
                recommended_strategy="Operation is non-reversible. Automatic retry prohibited to prevent data loss.",
            )

        # ── 3. Transient Errors (Network, Rate Limit, Socket Busy) ─────────────
        transient_signatures = (
            "timeout",
            "timed out",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "rate limit",
            "429",
            "503",
            "resource temporarily unavailable",
            "socket busy",
        )
        if any(sig in err_lower for sig in transient_signatures):
            if retry_count < max_retries:
                backoff = (2 ** retry_count) * 0.75
                return RecoveryPlan(
                    category=ErrorCategory.TRANSIENT,
                    can_retry=True,
                    backoff_seconds=backoff,
                    recommended_strategy=f"Transient failure detected. Retry attempt {retry_count + 1}/{max_retries} with {backoff:.1f}s backoff.",
                )
            else:
                return RecoveryPlan(
                    category=ErrorCategory.TRANSIENT,
                    can_retry=False,
                    backoff_seconds=0.0,
                    recommended_strategy=f"Transient failure exceeded max retries ({max_retries}). Escalating to user.",
                )

        # ── 4. Missing Dependencies or Binaries ───────────────────────────────
        if "not installed" in err_lower or "command not found" in err_lower or "no such file or directory: '" in err_lower:
            return RecoveryPlan(
                category=ErrorCategory.UNSUPPORTED,
                can_retry=False,
                backoff_seconds=0.0,
                recommended_strategy="Required system dependency or file is missing. Check prerequisites.",
            )

        # ── 5. Default Permanent Failure ──────────────────────────────────────
        return RecoveryPlan(
            category=ErrorCategory.PERMANENT,
            can_retry=False,
            backoff_seconds=0.0,
            recommended_strategy="Permanent execution failure. Replanning or user clarification required.",
        )


def diagnose_failure(
    capability: str,
    parameters: Dict[str, Any],
    error_msg: str,
    retry_count: int = 0,
    max_retries: int = 2,
    is_reversible: bool = True,
) -> RecoveryPlan:
    return FailureRecoveryEngine.diagnose(capability, parameters, error_msg, retry_count, max_retries, is_reversible)


_RECOVERY_ENGINE = FailureRecoveryEngine()


def get_recovery_engine() -> FailureRecoveryEngine:
    return _RECOVERY_ENGINE

