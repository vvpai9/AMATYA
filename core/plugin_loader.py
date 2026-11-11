"""
Plugin discovery, validation, collision detection, and dispatch.

Discovery runs once (AmatyaLive.__init__ calls discover_plugins()); the resulting
PluginRegistry is cached for the process lifetime. Enable/disable state is re-read
from config on every call to get_tool_declarations() / run() / list_for_ui(), so
toggling a plugin does not require restarting the app or re-importing anything.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from memory.config_manager import (
    get_plugin_enabled,
    get_plugin_config,
    get_plugin_approved,
    save_plugin_approved,
)

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}

# Optional, and the same contract actions use: a plugin that takes a moment can
# say so, and the model carries on talking instead of waiting on it. See
# core/action_loader.py for what each value means.
_BEHAVIORS = ("BLOCKING", "NON_BLOCKING")
_SCHEDULING = ("WHEN_IDLE", "SILENT", "INTERRUPT")


def _opt_upper(value, allowed: tuple[str, ...]) -> Optional[str]:
    v = str(value or "").strip().upper()
    return v if v in allowed else None

def _opt_tier(value) -> Optional[str]:
    """"core" or "extra" from a declaration, or None when it did not say.

    Anything else is treated as "did not say" rather than as an error: a typo
    should fall back to the default ranking, not stop a working tool loading.
    """
    text = str(value or "").strip().lower()
    return text if text in ("core", "extra") else None


def _opt_text(value) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


@dataclass
class PluginRecord:
    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    run: Optional[Callable] = None
    file: str = ""
    valid: bool = False
    error: str = ""
    settings: Optional[dict] = None   # optional PLUGIN_SETTINGS schema (config fields)
    behavior: Optional[str] = None    # None = the API's default (blocking)
    scheduling: Optional[str] = None  # None = the API's default (WHEN_IDLE)
    # Read by providers/schema.py when a small model gets a tool budget; never
    # sent to any API — main.py strips both before the Gemini config is built.
    #   tier   "core" | "extra" — this file's own opinion of whether it should
    #          survive a tight budget, instead of that being decided by the
    #          order files happen to be discovered in.
    #   brief  a short description used in place of the long one when a budget
    #          is in force. Nothing is deleted: Gemini still gets the full text.
    tier: Optional[str] = None
    brief: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    supported_actions: list[str] = field(default_factory=list)
    security_level: str = "normal"


class PluginRegistry:
    def __init__(self, plugins: dict[str, PluginRecord], logger: Callable[[str], None],
                 notify: Callable[[str], None] | None = None,
                 search_dirs: list[Path] | None = None):
        self._plugins = plugins          # name -> PluginRecord, VALID entries only
        self._all_records: list[PluginRecord] = []   # valid + invalid, for UI listing
        self._logger = logger
        self._search_dirs = search_dirs or []
        # Where user-facing notices go. `logger` is the console transcript and
        # carries everything; `notify` reaches the activity log, so only things
        # the user has to know about are sent to it. Defaults to dropping them,
        # which keeps every existing single-sink caller working unchanged.
        self._notify = notify or (lambda _msg: None)

    # -- called by main.py at LiveConnectConfig build time --
    def get_tool_declarations(self) -> list[dict]:
        decls = []
        for name, rec in self._plugins.items():
            if get_plugin_enabled(name):
                decl = {
                    "name": rec.name,
                    "description": rec.description,
                    "parameters": rec.parameters,
                }
                if rec.behavior:
                    decl["behavior"] = rec.behavior
                # Budget metadata. NOT part of any API's schema — main.py calls
                # providers.schema.strip_meta() before the Gemini config is
                # built, and budget() consumes them on the local-engine path.
                if rec.tier:
                    decl["tier"] = rec.tier
                if rec.brief:
                    decl["brief"] = rec.brief
                decls.append(decl)
        return decls

    def has(self, name: str) -> bool:
        return name in self._plugins

    def scheduling(self, name: str) -> Optional[str]:
        """How this plugin's result should re-enter the conversation, if it said."""
        rec = self._plugins.get(name)
        return rec.scheduling if rec else None

    def load_approved_plugin(self, name: str) -> tuple[bool, str]:
        """Dynamically loads and activates an approved plugin into the active registry."""
        if not get_plugin_approved(name):
            return False, f"Plugin '{name}' is not approved."
        rec = next((r for r in self._all_records if r.name == name), None)
        if not rec:
            return False, f"Plugin '{name}' not found."

        # Locate file on disk
        target_path: Optional[Path] = None
        for pdir in self._search_dirs:
            p = pdir / rec.file
            if p.is_file():
                target_path = p
                break
        if not target_path:
            return False, f"Plugin file '{rec.file}' not found on disk."

        try:
            module_name = f"plugins.{target_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, target_path)
            if spec is None or spec.loader is None:
                return False, "Could not build import spec"
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            run_fn = getattr(module, "run", None)
            if not callable(run_fn):
                return False, "Plugin module does not contain callable run(parameters)"

            rec.run = run_fn
            rec.valid = True
            rec.error = ""

            from core.security import register_tool_permission, PermissionTier, TOOL_PERMISSION_MATRIX
            if rec.name in TOOL_PERMISSION_MATRIX:
                ptier = TOOL_PERMISSION_MATRIX[rec.name].get("default_tier", PermissionTier.REMOTE_DEVICE_CONTROL)
            else:
                ptier = PermissionTier.REMOTE_DEVICE_CONTROL
            register_tool_permission(rec.name, {"default_tier": ptier})

            self._plugins[name] = rec
            self._logger(f"[PluginSecurity] Plugin '{name}' approved and activated into runtime registry.")
            return True, f"Plugin '{name}' loaded successfully."
        except Exception as exc:
            rec.valid = False
            rec.error = f"Failed to import after approval: {exc}"
            return False, rec.error

    # -- called by main.py from _execute_tool's else branch --
    def run(self, name: str, parameters: dict, player=None, session_memory=None) -> str:
        rec = self._plugins.get(name)

        # In-process Plugin Trust Approval Gate (Phase 15.1 Remediation)
        # Check if the plugin was unapproved or pending approval
        if rec is None or not rec.valid or rec.run is None:
            if get_plugin_approved(name):
                # Try loading on-demand if approved after discovery
                ok, msg = self.load_approved_plugin(name)
                if ok:
                    rec = self._plugins.get(name)

        if not get_plugin_approved(name):
            warning_msg = (
                f"Permission Denied: Plugin '{name}' is not trusted for in-process execution. "
                f"⚠️ In-process execution: plugins execute with the full privileges and credentials of the host process. "
                f"Code execution has been suppressed during discovery. "
                f"Please inspect the plugin code and grant explicit trust approval before running it."
            )
            self._logger(f"[PluginSecurity] {warning_msg}")
            return warning_msg

        if rec is None or not rec.valid or rec.run is None:
            return f"Plugin '{name}' is not available."
        if not get_plugin_enabled(name):
            return f"The '{name}' plugin is currently disabled."

        # Centralized Security Gateway Enforcement for Plugins (Phase 15.2 / Section 5)
        try:
            from core.security import authorize_tool_execution
            auth = authorize_tool_execution(
                name,
                parameters,
                execution_context={"player": player, "is_plugin": True},
            )
            if not auth["allowed"]:
                return f"Permission Denied: {auth['reason']}"
        except Exception as exc:
            err_msg = f"Security Gateway error checking plugin '{name}': {exc}. Denied by default (fail-closed)."
            self._logger(f"[PluginRegistry] {err_msg}")
            return f"Permission Denied: {err_msg}"

        try:
            return _call_run(rec.run, parameters, player, session_memory) or "Done."
        except Exception as e:
            self._logger(f"Plugin '{name}' crashed during run(): {e}")
            self._notify(f"Plugin '{name}' failed — see the console for details.")
            traceback.print_exc()
            return f"Sir, the '{name}' plugin failed: {e}"

    # -- called by ui.py's settings tab to render per-plugin config forms --
    def settings_schemas(self) -> list[dict]:
        """One entry per settings SECTION, for enabled plugins that declare a
        PLUGIN_SETTINGS schema. Sections are deduped by namespace so a suite of
        plugins sharing one namespace (e.g. the printer trio) shows a single
        form. Current stored values are merged in so the UI can pre-fill fields.
        """
        seen: set[str] = set()
        out: list[dict] = []
        for name, rec in self._plugins.items():
            if not rec.settings or not get_plugin_enabled(name):
                continue
            ns = rec.settings.get("namespace") or rec.name
            if ns in seen:
                continue
            seen.add(ns)
            out.append({
                "plugin":    rec.name,
                "namespace": ns,
                "title":     rec.settings.get("title") or rec.name,
                "fields":    rec.settings.get("fields", []),
                "values":    get_plugin_config(ns),
                "action":    rec.settings.get("action"),   # optional test/connect button
            })
        return out

    # -- called by ui.py's Plugin Manager overlay --
    def list_for_ui(self) -> list[dict]:
        out = []
        for rec in self._all_records:
            out.append({
                "name": rec.name,
                "description": rec.description,
                "file": rec.file,
                "valid": rec.valid,
                "error": rec.error,
                "enabled": get_plugin_enabled(rec.name) if rec.valid else False,
                "capabilities": rec.capabilities,
                "permissions": rec.permissions,
                "dependencies": rec.dependencies,
                "supported_actions": rec.supported_actions,
                "security_level": rec.security_level,
            })
        return out


def _call_run(run_fn, parameters, player, session_memory):
    """Invoke run() passing only the kwargs it actually declares (or all of them
    if it has **kwargs), so a minimal `def run(parameters):` plugin still works."""
    sig = inspect.signature(run_fn)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    kwargs = {}
    if has_var_kw or "player" in sig.parameters:
        kwargs["player"] = player
    if has_var_kw or "session_memory" in sig.parameters:
        kwargs["session_memory"] = session_memory
    return run_fn(parameters, **kwargs)


def _extract_plugin_manifest_ast(path: Path) -> tuple[Optional[dict], Optional[dict], bool, Optional[str]]:
    """Statically inspects a plugin file using Python AST without executing any module code.

    Returns:
        (plugin_dict, settings_dict, has_run_fn, error_string)
    Security Guarantee:
        Unapproved plugins are NEVER imported or executed during discovery.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        return None, None, False, f"Failed to parse plugin syntax: {exc}"

    plugin_dict = None
    settings_dict = None
    has_run = False

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "PLUGIN":
                        try:
                            plugin_dict = ast.literal_eval(node.value)
                        except Exception as e:
                            return None, None, False, f"PLUGIN constant must be an evaluatable dict literal: {e}"
                    elif target.id == "PLUGIN_SETTINGS":
                        try:
                            settings_dict = ast.literal_eval(node.value)
                        except Exception:
                            settings_dict = None
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            has_run = True

    if not isinstance(plugin_dict, dict):
        return None, None, False, "Missing PLUGIN dict constant."
    if not has_run:
        return None, None, False, "Missing callable run(parameters, ...) function."

    return plugin_dict, settings_dict, True, None


def _validate_manifest(plugin_meta: dict, settings: Optional[dict], has_run_fn: bool, filename: str) -> PluginRecord:
    """Validates statically extracted plugin metadata. Never raises."""
    name = plugin_meta.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return PluginRecord(name=str(name or Path(filename).stem), file=filename,
                             error="PLUGIN['name'] missing or not a valid identifier "
                                   "(letters/digits/underscore, must start with letter/underscore).")

    description = plugin_meta.get("description")
    if not isinstance(description, str) or not description.strip():
        return PluginRecord(name=name, file=filename,
                             error="PLUGIN['description'] missing or empty.")

    parameters = plugin_meta.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        return PluginRecord(name=name, file=filename,
                             error="PLUGIN['parameters'] must be a dict with \"type\": \"OBJECT\".")

    if not has_run_fn:
        return PluginRecord(name=name, file=filename,
                             error="Missing callable run(parameters, ...) function.")

    if not (isinstance(settings, dict) and isinstance(settings.get("fields"), list)):
        settings = None

    return PluginRecord(name=name, description=description.strip(), parameters=parameters,
                         run=None, file=filename, valid=True, error="", settings=settings,
                         behavior=_opt_upper(plugin_meta.get("behavior"), _BEHAVIORS),
                         scheduling=_opt_upper(plugin_meta.get("scheduling"), _SCHEDULING),
                         tier=_opt_tier(plugin_meta.get("tier")),
                         brief=_opt_text(plugin_meta.get("brief")))


def _validate(module, filename: str) -> PluginRecord:
    """Backward-compatible validation from an already-imported module object."""
    plugin_meta = getattr(module, "PLUGIN", None)
    if not isinstance(plugin_meta, dict):
        return PluginRecord(name=Path(filename).stem, file=filename,
                             error="Missing PLUGIN dict constant.")

    run_fn = getattr(module, "run", None)
    rec = _validate_manifest(plugin_meta, getattr(module, "PLUGIN_SETTINGS", None), callable(run_fn), filename)
    if rec.valid:
        rec.run = run_fn
    return rec


# The app's own top-level packages. Named explicitly rather than only probed on
# disk, because the case that matters most is the folder being ABSENT: a plugin
# importing core.undo on a build with no core/ at all must still be told to
# update, not to install something called "core".
_FIRST_PARTY = {"core", "memory", "actions", "plugins", "dashboard", "config"}


def _is_first_party(top: str, plugins_dir: Path) -> bool:
    """True when `top` names part of this app rather than a third-party package.

    The disk probe is the second half so a package added to the project later is
    recognised without anyone remembering to edit the set above.
    """
    if top in _FIRST_PARTY:
        return True
    root = plugins_dir.parent
    try:
        return (root / top).is_dir() or (root / f"{top}.py").is_file()
    except OSError:
        return False


def _load_error(path: Path, plugins_dir: Path, exc: Exception) -> str:
    """Turn an import failure into something the person who downloaded the file
    can act on.
    """
    if isinstance(exc, ModuleNotFoundError):
        missing = (getattr(exc, "name", "") or "").split(".")
        if len(missing) == 2 and missing[0] == "plugins" and missing[1].startswith("_"):
            helper = missing[1] + ".py"
            return (f"Needs the shared file '{helper}', which is not in "
                    f"{plugins_dir.name}/. It comes with this plugin — download "
                    f"'{helper}' into the same folder as {path.name} and restart.")
        if missing and missing[0] not in ("plugins",):
            if _is_first_party(missing[0], plugins_dir):
                needed = "/".join(missing) + ".py"
                return (f"Needs '{needed}', which is part of this app rather than "
                        f"something to install — your copy doesn't have it, so it "
                        f"comes with a newer version. Update the app; there is "
                        f"nothing to pip install.")
            return (f"Needs a package that is not installed: "
                    f"pip install {missing[0]}")
    return f"Failed to load: {exc}"


def get_maha_plugins_dir() -> Path:
    """Return the private Maha-AMATYA plugin directory ($XDG_DATA_HOME/maha-amatya/plugins/)."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "maha-amatya" / "plugins"
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "maha-amatya" / "plugins"
        return Path.home() / "AppData" / "Local" / "maha-amatya" / "plugins"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "maha-amatya" / "plugins"
    else:
        return Path.home() / ".local" / "share" / "maha-amatya" / "plugins"


def discover_plugins(plugins_dir: Path, core_tool_names: set[str],
                      logger: Callable[[str], None] = print,
                      notify: Callable[[str], None] | None = None) -> PluginRegistry:
    """Scans plugins_dir and private Maha-AMATYA plugin directory for *.py files.

    CRITICAL SECURITY GUARANTEES (Phase 15.1 Remediation):
    1. Static AST Analysis: Plugins are inspected statically without importing or
       executing module-level code.
    2. Pre-Import Trust Approval Gate: Unapproved plugins are NEVER imported via
       spec.loader.exec_module(). Their top-level code cannot run during discovery.
    3. Explicit Trust Required: Only plugins approved via config_manager are imported
       into Python runtime.
    """
    plugins_dir.mkdir(parents=True, exist_ok=True)
    valid: dict[str, PluginRecord] = {}
    all_records: list[PluginRecord] = []

    search_dirs = [plugins_dir]
    maha_dir = get_maha_plugins_dir()
    if maha_dir.exists() and maha_dir != plugins_dir:
        search_dirs.append(maha_dir)

    for pdir in search_dirs:
        files = sorted(pdir.glob("*.py"), key=lambda p: p.name)  # deterministic order
        for path in files:
            if path.name.startswith("_"):
                continue

            # STEP 1: Static AST Manifest Inspection (Zero Code Execution)
            plugin_dict, settings_dict, has_run_fn, err = _extract_plugin_manifest_ast(path)
            if err:
                rec = PluginRecord(name=path.stem, file=path.name, error=err)
                all_records.append(rec)
                logger(f"Plugin rejected: {path.name} — {err}")
                continue

            rec = _validate_manifest(plugin_dict, settings_dict, has_run_fn, path.name)
            if not rec.valid:
                all_records.append(rec)
                logger(f"Plugin rejected: {path.name} — {rec.error}")
                continue

            if rec.name in core_tool_names:
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' collides with a core tool — rejected.")
                all_records.append(rec)
                logger(f"Plugin rejected: {path.name} — {rec.error}")
                continue

            if rec.name in valid:
                other = valid[rec.name].file
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' already used by plugin '{other}' — rejected.")
                all_records.append(rec)
                logger(f"Plugin rejected: {path.name} — {rec.error}")
                continue

            # STEP 2: Pre-Import Trust Approval Gate
            # If not approved, DO NOT import or execute module code!
            is_approved = get_plugin_approved(rec.name)
            if not is_approved:
                rec.valid = False
                rec.error = (
                    f"Plugin '{rec.name}' requires explicit trust approval before loading executable code. "
                    f"⚠️ In-process execution: plugins execute with host privileges. Code import suppressed."
                )
                all_records.append(rec)
                logger(f"[PluginSecurity] Untrusted plugin discovered: '{rec.name}' ({path.name}). Code execution suppressed until approved.")
                continue

            # STEP 3: Safe Import of Pre-Approved Plugin
            try:
                module_name = f"plugins.{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("could not build import spec")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                run_fn = getattr(module, "run", None)
                if not callable(run_fn):
                    rec.valid = False
                    rec.error = "Missing callable run(parameters, ...) function."
                    all_records.append(rec)
                    logger(f"Plugin rejected: {path.name} — {rec.error}")
                    continue

                rec.run = run_fn
                rec.valid = True

                from core.security import register_tool_permission, PermissionTier, TOOL_PERMISSION_MATRIX
                # Centrally assigned permission tier: cannot be lowered by plugin self-declaration
                if rec.name in TOOL_PERMISSION_MATRIX:
                    ptier = TOOL_PERMISSION_MATRIX[rec.name].get("default_tier", PermissionTier.REMOTE_DEVICE_CONTROL)
                else:
                    ptier = PermissionTier.REMOTE_DEVICE_CONTROL
                register_tool_permission(rec.name, {"default_tier": ptier})

                valid[rec.name] = rec
                all_records.append(rec)
                logger(f"Plugin loaded: {rec.name} ({path.name}) [Trust: TRUSTED, Tier: {int(ptier)}] ⚠️ In-process execution")

            except Exception as e:
                rec = PluginRecord(name=path.stem, file=path.name,
                                    error=_load_error(path, pdir, e))
                traceback.print_exc()
                all_records.append(rec)
                logger(f"Plugin rejected: {path.name} — {rec.error}")

    notify = notify or (lambda _msg: None)
    registry = PluginRegistry(valid, logger, notify, search_dirs=search_dirs)
    registry._all_records = all_records
    rejected = len(all_records) - len(valid)
    logger(f"Plugin discovery complete: {len(valid)} active, "
           f"{rejected} rejected/pending, {len(all_records)} total.")
    if rejected:
        notify(f"{rejected} plugin(s) could not be loaded or pending approval — see the console.")
    return registry
