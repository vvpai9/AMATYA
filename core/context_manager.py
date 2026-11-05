"""
AMATYA Continuous Contextual Intelligence & Entity Resolver (core/context_manager.py)
=====================================================================================
Implements Section 4 (Continuous Contextual Intelligence) of AMATYA Phase 12:
  - Contextual Entity Resolution: Resolves pronouns and elliptical commands across turns.
  - Multi-Modal State Integration: Integrates conversation turns, active tasks, desktop window,
    active project, connected devices, and system telemetry.
  - Ambiguity Detection: Prompts for concise clarification when multiple interpretations exist.
  - Context Compression & Token Scoping: Prevents prompt bloat by extracting task-relevant context.
  - Cross-Session Continuity: Seamlessly picks up tasks and context across restarts.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from memory.config_manager import BASE_DIR

CONTEXT_FILE = BASE_DIR / "memory" / "context_state.json"
_LOCK = threading.RLock()


class ContextManager:
    """Tracks, aggregates, and scopes contextual intelligence across turns and sessions."""

    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or CONTEXT_FILE
        self._state: dict[str, Any] = {
            "last_file": "",
            "last_project": str(BASE_DIR),
            "last_app": "",
            "current_window_id": "",
            "current_window_title": "",
            "previous_window_id": "",
            "previous_window_title": "",
            "last_device": "phone",
            "last_url": "",
            "last_entity": "",
            "last_tool": "",
            "last_task": None,
            "recent_files": [],
            "recent_projects": [],
            "recent_turns": [],
            "updated_at": 0.0,
        }
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if self.state_path.exists():
                try:
                    data = json.loads(self.state_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._state.update(data)
                        # Canonicalize recent_projects and remove duplicate relative paths
                        projs: list[str] = []
                        for p in self._state.get("recent_projects", []):
                            try:
                                norm = str(Path(p).expanduser().resolve())
                            except Exception:
                                norm = str(p)
                            if norm and norm not in projs:
                                projs.append(norm)
                        self._state["recent_projects"] = projs[:5]
                        if self._state.get("last_project"):
                            try:
                                self._state["last_project"] = str(Path(self._state["last_project"]).expanduser().resolve())
                            except Exception:
                                pass
                except Exception:
                    pass

    def _save(self) -> None:
        with _LOCK:
            try:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self._state["updated_at"] = time.time()
                self.state_path.write_text(
                    json.dumps(self._state, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

    def get_state(self) -> dict[str, Any]:
        with _LOCK:
            return dict(self._state)

    def update_entity(self, **kwargs: Any) -> dict[str, Any]:
        """Update tracked entities and maintain recent history queues."""
        with _LOCK:
            if "window_id" in kwargs or "window_title" in kwargs:
                new_wid = str(kwargs.pop("window_id", "") or "")
                new_wtitle = str(kwargs.pop("window_title", "") or "")
                if new_wid and new_wid != self._state.get("current_window_id"):
                    self._state["previous_window_id"] = self._state.get("current_window_id", "")
                    self._state["previous_window_title"] = self._state.get("current_window_title", "")
                    self._state["current_window_id"] = new_wid
                    self._state["current_window_title"] = new_wtitle
                elif new_wtitle and new_wtitle != self._state.get("current_window_title"):
                    self._state["previous_window_title"] = self._state.get("current_window_title", "")
                    self._state["current_window_title"] = new_wtitle

            for k, v in kwargs.items():
                if v is not None and v != "":
                    self._state[k] = v
                    if k in ("last_file", "last_url", "last_project", "last_app"):
                        self._state["last_entity"] = v

            # Maintain recent lists
            if kwargs.get("last_file"):
                lf = str(kwargs["last_file"])
                rfiles = self._state.setdefault("recent_files", [])
                if lf in rfiles:
                    rfiles.remove(lf)
                rfiles.insert(0, lf)
                self._state["recent_files"] = rfiles[:10]

            if kwargs.get("last_project"):
                raw_lp = str(kwargs["last_project"]).strip()
                try:
                    lp = str(Path(raw_lp).expanduser().resolve())
                except Exception:
                    lp = raw_lp
                self._state["last_project"] = lp
                rprojs = self._state.setdefault("recent_projects", [])
                norm_rprojs: list[str] = []
                for p in rprojs:
                    try:
                        p_norm = str(Path(p).expanduser().resolve())
                    except Exception:
                        p_norm = str(p)
                    if p_norm != lp and p_norm not in norm_rprojs:
                        norm_rprojs.append(p_norm)
                norm_rprojs.insert(0, lp)
                self._state["recent_projects"] = norm_rprojs[:5]

            self._save()
            return dict(self._state)

    def record_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Automatically extract context entities from executed tool calls."""
        updates: dict[str, Any] = {"last_tool": tool_name}
        if not isinstance(args, dict):
            self.update_entity(**updates)
            return

        for fkey in ("file_path", "path", "source_path", "output_path", "target_path"):
            val = args.get(fkey)
            if isinstance(val, str) and val.strip():
                p = Path(val.strip()).expanduser()
                if p.suffix:
                    updates["last_file"] = str(p)
                else:
                    updates["last_project"] = str(p)

        if args.get("project_path") or args.get("repo_path"):
            updates["last_project"] = str(args.get("project_path") or args.get("repo_path"))

        if args.get("app_name") or args.get("app"):
            updates["last_app"] = str(args.get("app_name") or args.get("app"))

        if args.get("url"):
            updates["last_url"] = str(args["url"])

        if args.get("device_id") or args.get("device"):
            updates["last_device"] = str(args.get("device_id") or args.get("device"))

        if args.get("window_id") or args.get("title"):
            updates["window_id"] = str(args.get("window_id", ""))
            updates["window_title"] = str(args.get("title", ""))

        self.update_entity(**updates)

    def record_turn(self, role: str, text: str) -> None:
        """Record a conversational turn for contextual recall."""
        with _LOCK:
            turns = self._state.setdefault("recent_turns", [])
            turns.append({
                "role": role,
                "text": text[:400],
                "time": time.time(),
            })
            if len(turns) > 20:
                self._state["recent_turns"] = turns[-20:]
            self._save()

    def record_active_task(
        self,
        task_id: str,
        goal: str,
        artifacts: list[str] | None = None,
        result_summary: str = "",
    ) -> None:
        """Record the outcome and artifacts of an active or completed task."""
        with _LOCK:
            task_dict = {
                "task_id": task_id,
                "goal": goal,
                "artifacts": artifacts or [],
                "result_summary": result_summary or goal,
                "time": time.time(),
            }
            self._state["last_task"] = task_dict
            if artifacts:
                self.update_entity(last_file=artifacts[0])
            self._save()

    def detect_ambiguity(self, instruction: str) -> dict[str, Any]:
        """Check if an instruction is ambiguous or requires entity clarification."""
        res = self.resolve_references(instruction)
        text = (instruction or "").strip().lower()
        is_ambig = bool(res.get("ambiguous", False))

        # Check pronoun references that failed to resolve
        if not is_ambig and ("that" in text or "it" in text or "this" in text) and not res.get("resolutions"):
            is_ambig = True

        # Check 'other/another' entity references that failed to resolve
        if not is_ambig and re.search(r"\b(the\s+other|another)\s+(project|repo|repository|file|document|device|window|app)\b", text):
            if not res.get("resolutions"):
                is_ambig = True

        q = res.get("clarification_question")
        if not q and is_ambig:
            if re.search(r"\b(the\s+other|another)\s+(project|repo|repository)\b", text):
                q = "Which other project did you have in mind?"
            elif re.search(r"\b(the\s+other|another)\s+(file|document)\b", text):
                q = "Which other file did you have in mind?"
            elif re.search(r"\b(the\s+other|another)\s+device\b", text):
                q = "Which other device did you mean?"
            elif re.search(r"\b(the\s+other|another)\s+(window|app)\b", text):
                q = "Which other window or application did you mean?"
            else:
                q = f"Could you specify what entity you mean by '{instruction}'?"

        return {
            "is_ambiguous": is_ambig,
            "clarification_question": q,
            "resolutions": res.get("resolutions", {}),
        }

    def resolve_references(self, instruction: str) -> dict[str, Any]:
        """Resolve pronouns and elliptical instructions into fully qualified operations."""
        text = (instruction or "").strip()
        lower = text.lower()
        st = self.get_state()
        resolutions: dict[str, Any] = {}
        resolved_text = text
        recommended_action: dict[str, Any] | None = None
        ambiguous = False
        clarification_question = ""

        # 1. "Send that file to my phone" / "send the same file to my phone"
        if re.search(r"\b(send|share|transfer|push)\s+(that|this|the\s+same|the)\s+(file|document|pdf|image|report)\b", lower):
            target_file = st.get("last_file") or st.get("last_entity") or ""
            target_device = st.get("last_device") or "phone"
            resolutions["file_path"] = target_file
            resolutions["device"] = target_device
            if target_file:
                resolved_text = f"Send file '{target_file}' to device '{target_device}'."
                recommended_action = {
                    "tool": "device_control",
                    "parameters": {"action": "send_file", "device": target_device, "file_path": target_file},
                }
            else:
                ambiguous = True
                clarification_question = "Which file should I send to your phone?"

        # 2. "Use the previous output" / "use that output"
        elif re.search(r"\buse\s+(the\s+)?(previous|last|that)\s+output\b", lower):
            last_task = st.get("last_task")
            if isinstance(last_task, dict) and last_task.get("result_summary"):
                resolutions["previous_output"] = last_task["result_summary"]
                resolved_text = f"Process using previous output: '{last_task['result_summary']}'"
            else:
                ambiguous = True
                clarification_question = "There is no recent task output recorded. What information should I use?"

        # 3. "Check the same project again" / "test that project again"
        elif re.search(r"\b(check|test|inspect|compile|build|audit)\s+(the\s+same|that|this)\s+(project|repo|repository)\b", lower):
            proj = st.get("last_project") or str(BASE_DIR)
            resolutions["project_path"] = proj
            resolved_text = f"Inspect repository status and run tests in project '{proj}'."
            recommended_action = {
                "tool": "creator",
                "parameters": {"action": "check_project", "project_path": proj},
            }

        # 4. "Do the same thing for the other project" / "Test the other project" / "Check another project"
        elif re.search(r"\b(the\s+other|another)\s+(project|repo|repository)\b", lower):
            cur_p = ""
            if st.get("last_project"):
                try:
                    cur_p = str(Path(st.get("last_project", "")).expanduser().resolve())
                except Exception:
                    cur_p = str(st.get("last_project", ""))

            recent_p: list[str] = []
            for p in st.get("recent_projects", []):
                try:
                    p_norm = str(Path(p).expanduser().resolve())
                except Exception:
                    p_norm = str(p)
                if p_norm and p_norm != cur_p and p_norm not in recent_p:
                    recent_p.append(p_norm)

            if recent_p:
                target_p = recent_p[0]
                resolutions["project_path"] = target_p
                resolved_text = f"Perform previous operation on alternative project '{target_p}'."
            else:
                ambiguous = True
                clarification_question = "Which other project did you have in mind?"

        # 5. "Close the previous window" / "switch to previous window"
        elif re.search(r"\b(close|focus|switch\s+to)\s+(the\s+)?(previous|last|prior)\s+window\b", lower):
            verb = "close_window" if "close" in lower else "focus_window"
            prev_id = st.get("previous_window_id") or st.get("current_window_id") or ""
            prev_title = st.get("previous_window_title") or st.get("current_window_title") or ""
            resolutions["window_id"] = prev_id
            resolutions["window_title"] = prev_title
            target_desc = prev_title or prev_id or "previous window"
            resolved_text = f"{'Close' if verb == 'close_window' else 'Focus'} window '{target_desc}' (id={prev_id})."
            recommended_action = {
                "tool": "kwin_desktop",
                "parameters": {"action": verb, "window_id": prev_id, "title": prev_title},
            }

        # 6. "Continue what you were doing" / "resume the task"
        elif re.search(r"\b(continue|resume)\s+(what\s+you\s+were\s+doing|the\s+task|previous\s+task|that\s+task)\b", lower):
            last_task = st.get("last_task")
            resolutions["last_task"] = last_task
            if isinstance(last_task, dict) and last_task.get("goal"):
                resolved_text = f"Resume task '{last_task.get('goal')}' from step {last_task.get('current_step_index', 0) + 1}."
                recommended_action = {
                    "tool": "orchestrator",
                    "parameters": {"action": "resume_last_task"},
                }
            else:
                ambiguous = True
                clarification_question = "No paused task was found to resume."

        # 7. "Open that" / "open it"
        elif re.search(r"^\s*open\s+(that|it|this)(\s+file|\s+project|\s+folder|\s+link|\s+url)?\s*[\.!\?]?\s*$", lower):
            target = st.get("last_file") or st.get("last_url") or st.get("last_project") or st.get("last_app") or ""
            resolutions["target"] = target
            if target:
                resolved_text = f"Open '{target}'."
                recommended_action = {"tool": "open_app", "parameters": {"app_name": target}}
            else:
                ambiguous = True
                clarification_question = "What application, file, or URL would you like me to open?"

        return {
            "original": text,
            "resolved": resolved_text,
            "resolved_text": resolved_text,
            "resolutions": resolutions,
            "recommended_action": recommended_action,
            "ambiguous": ambiguous,
            "clarification_question": clarification_question,
            "context_snapshot": {
                "last_file": st.get("last_file"),
                "last_project": st.get("last_project"),
                "last_app": st.get("last_app"),
                "current_window": st.get("current_window_title"),
                "previous_window": st.get("previous_window_title"),
                "last_device": st.get("last_device"),
            },
        }

    def build_scoped_context_prompt(self, max_turns: int = 4) -> str:
        """Construct a compact, privacy-aware context prompt for models without token bloat."""
        st = self.get_state()
        lines: list[str] = [
            f"Context: Project={Path(st.get('last_project', '')).name or 'root'} | "
            f"App={st.get('last_app') or 'none'} | "
            f"Window={st.get('current_window_title') or 'none'} | "
            f"File={Path(st.get('last_file', '')).name or 'none'}"
        ]

        turns = st.get("recent_turns", [])[-max_turns:]
        if turns:
            lines.append("Recent turns:")
            for t in turns:
                lines.append(f"  {t['role'].capitalize()}: {t['text'][:120]}")

        return "\n".join(lines)


_CONTEXT_MGR: ContextManager | None = None
_CM_LOCK = threading.Lock()


def get_context_manager() -> ContextManager:
    global _CONTEXT_MGR
    with _CM_LOCK:
        if _CONTEXT_MGR is None:
            _CONTEXT_MGR = ContextManager()
    return _CONTEXT_MGR
