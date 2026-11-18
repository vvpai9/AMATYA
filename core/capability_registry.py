"""
core/capability_registry.py — AMATYA Unified Capability Registry & Standardized Contract
========================================================================================
Unifies discovery, inspection, risk classification, and secure dispatch across:
  1. Built-in Actions (`actions/*.py`)
  2. Drop-in Plugins (`plugins/*.py`)
  3. Progressive-Disclosure Agent Skills (`skills/*/SKILL.md`)

Non-Negotiable Architecture Rules:
  - Discovery must NEVER imply execution permission.
  - Unapproved plugins remain blocked from execution (zero-import trust gate).
  - All capability execution MUST pass through Central Authorization Gateway (`core.security`).
  - Fail-closed security: any unauthorized or unregistered tool is denied.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core.action_loader import ActionRecord, discover_actions
from core.plugin_loader import PluginRecord, discover_plugins
from core.security import (
    PermissionTier,
    TOOL_PERMISSION_MATRIX,
    authorize_tool_execution,
    log_audit_event,
)
from core.skills_registry import SkillInfo, discover_skills
from memory.config_manager import BASE_DIR, get_plugin_approved, get_plugin_enabled

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def tier_to_risk(tier: int) -> RiskLevel:
    if tier <= 1:
        return RiskLevel.LOW
    elif tier == 2:
        return RiskLevel.MEDIUM
    elif tier in (3, 4):
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


@dataclass
class Capability:
    name: str
    kind: str  # "action" | "plugin" | "skill"
    category: str
    description: str
    parameters_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "OBJECT", "properties": {}})
    output_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "OBJECT", "properties": {}})
    permission_tier: int = 0
    risk_level: RiskLevel = RiskLevel.LOW
    is_reversible: bool = True
    timeout_seconds: float = 60.0
    health_status: str = "healthy"  # "healthy" | "degraded" | "unapproved" | "unavailable"
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)
    executor: Optional[Callable[..., Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        d.pop("executor", None)
        return d


class UnifiedCapabilityRegistry:
    """Central registry exposing all AMATYA tools, plugins, and skills under a uniform contract."""

    def __init__(self) -> None:
        self._capabilities: Dict[str, Capability] = {}
        self._initialized = False

    def initialize(self, force_reload: bool = False) -> None:
        with _LOCK:
            if self._initialized and not force_reload:
                return

            self._capabilities.clear()
            self._load_actions()
            self._load_plugins()
            self._load_skills()
            self._initialized = True
            logger.info("UnifiedCapabilityRegistry initialized with %d capabilities.", len(self._capabilities))

    def _determine_category(self, name: str, desc: str) -> str:
        name_lower = name.lower()
        desc_lower = desc.lower()
        if any(k in name_lower for k in ("file", "dir", "zoxide", "download")):
            return "filesystem"
        if any(k in name_lower for k in ("desktop", "kwin", "window", "screen", "mouse")):
            return "desktop"
        if any(k in name_lower for k in ("cyber", "security", "auth", "pin", "firewall")):
            return "security"
        if any(k in name_lower for k in ("stark", "math", "calc", "orbit", "trajectory", "science")):
            return "science"
        if any(k in name_lower for k in ("system", "monitor", "armor", "battery", "storage", "network")):
            return "telemetry"
        if any(k in name_lower for k in ("radio", "news", "weather", "flight", "satellite", "aerospace")):
            return "intelligence"
        if any(k in name_lower for k in ("tv", "device", "phone", "ring", "home", "whatsapp")):
            return "devices"
        if any(k in name_lower for k in ("browser", "search", "web", "scrape")):
            return "browser"
        if any(k in name_lower for k in ("doc", "pdf", "xlsx", "pptx", "creator", "report")):
            return "documents"
        return "general"

    def _load_actions(self) -> None:
        actions_dir = BASE_DIR / "actions"
        if not actions_dir.exists():
            return

        try:
            reg = discover_actions(actions_dir=actions_dir, reserved_names=set(), logger=logger.debug)
            for name, act in reg._actions.items():
                if not act.valid:
                    continue
                desc = act.description or act.brief or ""
                params = act.parameters or {"type": "OBJECT", "properties": {}}

                # Security Tier from MATRIX
                meta = TOOL_PERMISSION_MATRIX.get(name, {})
                ptier = int(meta.get("default_tier", PermissionTier.GENERAL_CONVERSATION))
                risk = tier_to_risk(ptier)
                cat = self._determine_category(name, desc)

                # Reversibility heuristic
                irreversible = any(k in name.lower() or k in desc.lower() for k in ("delete", "kill", "remove", "reboot", "shutdown", "format"))

                self._capabilities[name] = Capability(
                    name=name,
                    kind="action",
                    category=cat,
                    description=desc,
                    parameters_schema=params,
                    permission_tier=ptier,
                    risk_level=risk,
                    is_reversible=not irreversible,
                    health_status="healthy",
                    dependencies=list(act.dependencies or []),
                    executor=act.handler,
                )
        except Exception as exc:
            logger.error("Failed loading actions into capability registry: %s", exc)

    def _load_plugins(self) -> None:
        plugins_dir = BASE_DIR / "plugins"
        if not plugins_dir.exists():
            return

        try:
            # We preserve plugin AST safety: unapproved plugins are not executed
            reg = discover_plugins(plugins_dir=plugins_dir, core_tool_names=set(self._capabilities.keys()), logger=logger.debug)
            for plug in reg._all_records:
                name = plug.name
                desc = plug.description or plug.brief or ""
                params = plug.parameters or {"type": "OBJECT", "properties": {}}

                meta = TOOL_PERMISSION_MATRIX.get(name, {})
                ptier = int(meta.get("default_tier", PermissionTier.GENERAL_CONVERSATION))
                risk = tier_to_risk(ptier)
                cat = self._determine_category(name, desc)

                is_approved = get_plugin_approved(name)
                is_enabled = get_plugin_enabled(name)
                health = "healthy" if (is_approved and is_enabled) else ("unapproved" if not is_approved else "unavailable")

                # The executor wraps plugin.run with approval checks
                def make_executor(p_info: PluginRecord):
                    def _exec(params_dict: dict, player=None, session_memory=None, **kw):
                        if not get_plugin_approved(p_info.name):
                            raise PermissionError(f"Plugin '{p_info.name}' is unapproved. User must approve it before execution.")
                        return p_info.run(params_dict, player=player, session_memory=session_memory)
                    return _exec

                self._capabilities[name] = Capability(
                    name=name,
                    kind="plugin",
                    category=cat,
                    description=desc,
                    parameters_schema=params,
                    permission_tier=ptier,
                    risk_level=risk,
                    health_status=health,
                    dependencies=list(plug.dependencies or []),
                    executor=make_executor(plug),
                )
        except Exception as exc:
            logger.error("Failed loading plugins into capability registry: %s", exc)

    def _load_skills(self) -> None:
        try:
            skills = discover_skills()
            for name, s_info in skills.items():
                cap_name = f"skill:{name}"
                desc = s_info.description or f"Skill: {name}"
                cat = s_info.category or self._determine_category(name, desc)

                # Skills execute via skill_runner.py
                def make_skill_executor(skill_name: str):
                    def _exec(params_dict: dict, player=None, session_memory=None, **kw):
                        from actions.skill_runner import execute as run_skill
                        return run_skill({"action": "run_skill", "skill": skill_name, "parameters": params_dict}, player=player, session_memory=session_memory)
                    return _exec

                self._capabilities[cap_name] = Capability(
                    name=cap_name,
                    kind="skill",
                    category=cat,
                    description=desc,
                    parameters_schema={"type": "OBJECT", "properties": {"instruction": {"type": "STRING", "description": "Goal or parameters for this skill"}}},
                    permission_tier=int(PermissionTier.GENERAL_CONVERSATION),
                    risk_level=RiskLevel.LOW,
                    health_status="healthy",
                    dependencies=s_info.scripts,
                    executor=make_skill_executor(name),
                )
        except Exception as exc:
            logger.error("Failed loading skills into capability registry: %s", exc)

    def get_capability(self, name: str) -> Optional[Capability]:
        with _LOCK:
            if not self._initialized:
                self.initialize()
            return self._capabilities.get(name)

    def list_capabilities(
        self,
        category: Optional[str] = None,
        risk_level: Optional[RiskLevel] = None,
        kind: Optional[str] = None,
        healthy_only: bool = False,
    ) -> List[Capability]:
        with _LOCK:
            if not self._initialized:
                self.initialize()

            results = list(self._capabilities.values())
            if category:
                results = [c for c in results if c.category.lower() == category.lower()]
            if risk_level:
                results = [c for c in results if c.risk_level == risk_level]
            if kind:
                results = [c for c in results if c.kind.lower() == kind.lower()]
            if healthy_only:
                results = [c for c in results if c.health_status == "healthy"]
            return results

    def search(self, query: str) -> List[Capability]:
        with _LOCK:
            if not self._initialized:
                self.initialize()

            q = query.lower().strip()
            scored = []
            for c in self._capabilities.values():
                score = 0
                if q == c.name.lower():
                    score += 100
                elif q in c.name.lower():
                    score += 50
                if q in c.description.lower():
                    score += 20
                if q in c.category.lower():
                    score += 10
                if score > 0:
                    scored.append((score, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [c for _, c in scored]

    def execute_capability(
        self,
        name: str,
        parameters: Dict[str, Any],
        actor: str = "orchestrator",
        player: Any = None,
        session_memory: Any = None,
        interactive_confirm: bool = True,
    ) -> Any:
        """
        Securely executes a capability through the mandatory Central Authorization Gateway.
        FAILS CLOSED if capability is unregistered, unapproved, or unauthorized.
        """
        with _LOCK:
            if not self._initialized:
                self.initialize()

            cap = self._capabilities.get(name)
            if not cap:
                reason = f"Capability '{name}' is not registered in AMATYA."
                log_audit_event("permission_denied", name, int(PermissionTier.CRITICAL_SECURITY), False, reason)
                raise PermissionError(reason)

            # Strip 'skill:' prefix for security matrix lookup if present
            matrix_tool_name = name[6:] if name.startswith("skill:") else name

            # ── 1. Mandatory Central Authorization Gateway Check ───────────────
            auth = authorize_tool_execution(
                matrix_tool_name,
                parameters,
                execution_context={"interactive_confirm": interactive_confirm},
                actor=actor,
            )
            if not auth.get("allowed", False):
                reason = auth.get("reason", "Denied by Central Authorization Gateway.")
                log_audit_event("permission_denied", name, cap.permission_tier, False, reason)
                raise PermissionError(f"Security Gateway Denied '{name}': {reason}")

            # ── 2. Health and Approval Check ──────────────────────────────────
            if cap.health_status == "unapproved":
                raise PermissionError(f"Capability '{name}' is unapproved. User trust approval required.")

            if not cap.executor:
                raise RuntimeError(f"Capability '{name}' has no registered executor.")

            # ── 3. Execute with Safe Invocation ────────────────────────────────
            log_audit_event("execution_started", name, cap.permission_tier, True, f"Executing via {actor}")
            start_t = time.time()
            try:
                # Inspect executor signature to pass only supported kwargs
                import inspect
                sig = inspect.signature(cap.executor)
                kwargs = {}
                if "player" in sig.parameters:
                    kwargs["player"] = player
                if "session_memory" in sig.parameters:
                    kwargs["session_memory"] = session_memory

                res = cap.executor(parameters, **kwargs)
                elapsed = time.time() - start_t
                log_audit_event("execution_completed", name, cap.permission_tier, True, f"Completed in {elapsed:.3f}s")
                return res
            except Exception as exc:
                elapsed = time.time() - start_t
                log_audit_event("execution_failed", name, cap.permission_tier, False, f"Failed in {elapsed:.3f}s: {exc}")
                raise


_REGISTRY: Optional[UnifiedCapabilityRegistry] = None


def get_capability_registry() -> UnifiedCapabilityRegistry:
    global _REGISTRY
    with _LOCK:
        if _REGISTRY is None:
            _REGISTRY = UnifiedCapabilityRegistry()
            _REGISTRY.initialize()
        return _REGISTRY
