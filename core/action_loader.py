"""
Action discovery, validation, skill metadata registry, and dispatch.

Every actions/*.py that exposes a module-level ``TOOL`` dict is auto-discovered
here, exactly like a drop-in plugin, so main.py never has to hardcode a tool
declaration or a dispatch branch for it.

Supports Section 11 (Skills and Plugin Architecture):
Each action/skill module may also declare ``SKILL_METADATA`` (or embed metadata
fields inside ``TOOL``) describing:
  - capabilities: list[str]
  - permissions: list[str]
  - dependencies: list[str]
  - supported_actions: list[str]
  - security_level: "low" | "normal" | "high" | "critical"
"""
from __future__ import annotations

import importlib.util
import inspect
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}
_CTX_KEYS = ("player", "speak", "response", "session_memory")

_BEHAVIORS = ("BLOCKING", "NON_BLOCKING")
_SCHEDULING = ("WHEN_IDLE", "SILENT", "INTERRUPT")

META_KEYS = (
    "tier",
    "brief",
    "capabilities",
    "permissions",
    "dependencies",
    "supported_actions",
    "security_level",
)


def strip_meta(decls):
    """Declarations without META_KEYS. Non-dict entries pass through untouched;
    a declaration carrying none is returned as the same object, so what an API
    receives is byte-for-byte what it received before these keys existed."""
    out = []
    for decl in decls:
        if isinstance(decl, dict) and any(k in decl for k in META_KEYS):
            out.append({k: v for k, v in decl.items() if k not in META_KEYS})
        else:
            out.append(decl)
    return out


def _opt_upper(value, allowed: tuple[str, ...]) -> Optional[str]:
    v = str(value or "").strip().upper()
    return v if v in allowed else None


def _opt_tier(value) -> Optional[str]:
    text = str(value or "").strip().lower()
    return text if text in ("core", "extra") else None


def _opt_text(value) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


@dataclass
class ActionRecord:
    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    handler: Optional[Callable] = None
    file: str = ""
    valid: bool = False
    error: str = ""
    behavior: Optional[str] = None
    scheduling: Optional[str] = None
    tier: Optional[str] = None
    brief: Optional[str] = None
    # Section 11: Declarative Skill Metadata
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    supported_actions: list[str] = field(default_factory=list)
    security_level: str = "normal"


class ActionRegistry:
    def __init__(self, actions: dict[str, ActionRecord], logger: Callable[[str], None]):
        self._actions = actions
        self._all_records: list[ActionRecord] = []
        self._logger = logger

    def get_tool_declarations(self) -> list[dict]:
        out = []
        for rec in self._actions.values():
            decl = {
                "name": rec.name,
                "description": rec.description,
                "parameters": rec.parameters,
            }
            if rec.behavior:
                decl["behavior"] = rec.behavior
            if rec.tier:
                decl["tier"] = rec.tier
            if rec.brief:
                decl["brief"] = rec.brief
            out.append(decl)
        return out

    def has(self, name: str) -> bool:
        return name in self._actions

    def scheduling(self, name: str) -> Optional[str]:
        rec = self._actions.get(name)
        return rec.scheduling if rec else None

    def names(self) -> set[str]:
        return set(self._actions.keys())

    def list_skills(self) -> list[dict[str, Any]]:
        """Return declarative metadata for all loaded actions/skills (Section 11)."""
        out = []
        for rec in self._actions.values():
            out.append({
                "name": rec.name,
                "file": rec.file,
                "description": rec.brief or rec.description[:140],
                "capabilities": rec.capabilities,
                "permissions": rec.permissions,
                "dependencies": rec.dependencies,
                "supported_actions": rec.supported_actions,
                "security_level": rec.security_level,
                "valid": rec.valid,
            })
        return out

    def run(self, name: str, parameters: dict, ctx: dict | None = None) -> str:
        rec = self._actions.get(name)
        if rec is None or not rec.valid:
            return f"Action '{name}' is not available."
        try:
            return _call_handler(rec.handler, parameters, ctx or {}) or "Done."
        except Exception as e:
            self._logger(f"Action '{name}' crashed during run(): {e}")
            traceback.print_exc()
            return f"Tool '{name}' failed: {e}"


def _call_handler(fn: Callable, parameters: dict, ctx: dict) -> str:
    sig = inspect.signature(fn)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    kwargs = {}
    for key in _CTX_KEYS:
        if has_var_kw or key in sig.parameters:
            kwargs[key] = ctx.get(key)
    return fn(parameters=parameters, **kwargs)


def _extract_skill_meta(module, tool: dict, parameters: dict) -> dict[str, Any]:
    meta = getattr(module, "SKILL_METADATA", None)
    if not isinstance(meta, dict):
        meta = {}

    def _list_field(key: str) -> list[str]:
        val = meta.get(key) or tool.get(key) or []
        return [str(x) for x in val] if isinstance(val, (list, tuple)) else []

    supported = _list_field("supported_actions")
    if not supported:
        # Auto-infer supported_actions from parameters.properties.action if present
        act_prop = (parameters.get("properties") or {}).get("action", {})
        if isinstance(act_prop, dict) and isinstance(act_prop.get("enum"), list):
            supported = [str(x) for x in act_prop["enum"]]

    sec_lvl = str(meta.get("security_level") or tool.get("security_level") or "normal").lower()
    if sec_lvl not in ("low", "normal", "high", "critical"):
        sec_lvl = "normal"

    return {
        "capabilities": _list_field("capabilities"),
        "permissions": _list_field("permissions"),
        "dependencies": _list_field("dependencies"),
        "supported_actions": supported,
        "security_level": sec_lvl,
    }


def _validate(module, filename: str) -> ActionRecord:
    """Returns an ActionRecord; .valid=False + .error set on any problem. Never raises."""
    tool = getattr(module, "TOOL", None)
    if not isinstance(tool, dict):
        return ActionRecord(name=Path(filename).stem, file=filename,
                            error="No module-level TOOL dict (not a discoverable action).")

    name = tool.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return ActionRecord(name=str(name or Path(filename).stem), file=filename,
                            error="TOOL['name'] missing or not a valid identifier.")

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        return ActionRecord(name=name, file=filename,
                            error="TOOL['description'] missing or empty.")

    parameters = tool.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        return ActionRecord(name=name, file=filename,
                            error="TOOL['parameters'] must be a dict with \"type\": \"OBJECT\".")

    handler = (
        tool.get("handler")
        or getattr(module, "execute", None)
        or getattr(module, "run", None)
    )
    if not callable(handler):
        return ActionRecord(name=name, file=filename,
                            error="TOOL['handler'] (or module execute/run) missing or not callable.")
    tool["handler"] = handler

    smeta = _extract_skill_meta(module, tool, parameters)

    return ActionRecord(
        name=name,
        description=description.strip(),
        parameters=parameters,
        handler=handler,
        file=filename,
        valid=True,
        error="",
        behavior=_opt_upper(tool.get("behavior"), _BEHAVIORS),
        scheduling=_opt_upper(tool.get("scheduling"), _SCHEDULING),
        tier=_opt_tier(tool.get("tier")),
        brief=_opt_text(tool.get("brief")),
        capabilities=smeta["capabilities"],
        permissions=smeta["permissions"],
        dependencies=smeta["dependencies"],
        supported_actions=smeta["supported_actions"],
        security_level=smeta["security_level"],
    )


def discover_actions(actions_dir: Path, reserved_names: set[str] | None = None,
                     logger: Callable[[str], None] = print) -> ActionRegistry:
    reserved = reserved_names or set()
    actions_dir.mkdir(parents=True, exist_ok=True)
    valid: dict[str, ActionRecord] = {}
    all_records: list[ActionRecord] = []

    files = sorted(actions_dir.glob("*.py"), key=lambda p: p.name)
    for path in files:
        if path.name.startswith("_"):
            continue
        try:
            module_name = f"actions.{path.stem}"
            module = sys.modules.get(module_name)
            if module is None:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("could not build import spec")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise

            if getattr(module, "TOOL", None) is None:
                continue

            rec = _validate(module, path.name)

            if rec.valid and rec.name in reserved:
                rec = ActionRecord(name=rec.name, file=path.name,
                                   error=f"Name '{rec.name}' collides with a reserved core tool — rejected.")
            elif rec.valid and rec.name in valid:
                other = valid[rec.name].file
                rec = ActionRecord(name=rec.name, file=path.name,
                                   error=f"Name '{rec.name}' already used by action '{other}' — rejected.")

        except Exception as e:
            rec = ActionRecord(name=path.stem, file=path.name,
                               error=f"Failed to load: {e}")
            traceback.print_exc()

        all_records.append(rec)
        if rec.valid:
            valid[rec.name] = rec
            logger(f"Action loaded: {rec.name} ({path.name})")
        else:
            logger(f"Action rejected: {path.name} — {rec.error}")

    registry = ActionRegistry(valid, logger)
    registry._all_records = all_records
    logger(f"Action discovery complete: {len(valid)} active.")
    return registry
