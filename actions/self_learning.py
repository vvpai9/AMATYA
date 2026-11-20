"""
Self-Learning & Autonomous Skill Generation Action for JARVIS.
Allows JARVIS to learn new concepts, persist custom user preferences and rules,
and dynamically author new drop-in plugins into `plugins/` so JARVIS can upgrade its own capabilities.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
LEARNED_JSON = MEMORY_DIR / "learned_knowledge.json"
LEARNED_MD = MEMORY_DIR / "learned_rules.md"

def _load_knowledge() -> dict:
    if LEARNED_JSON.exists():
        try:
            with open(LEARNED_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"facts": [], "rules": [], "workflows": []}

def _save_knowledge(data: dict) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(LEARNED_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def learn_knowledge(category: str, topic: str, content: str) -> str:
    """Store learned fact, rule, or preference."""
    data = _load_knowledge()
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "category": category,
        "topic": topic,
        "content": content,
    }
    
    if category.lower() in ("rule", "rules"):
        data.setdefault("rules", []).append(entry)
    elif category.lower() in ("workflow", "pipeline"):
        data.setdefault("workflows", []).append(entry)
    else:
        data.setdefault("facts", []).append(entry)

    _save_knowledge(data)

    # Append to human-readable markdown
    try:
        with open(LEARNED_MD, "a", encoding="utf-8") as f:
            f.write(f"\n### [{entry['timestamp']}] {category.upper()}: {topic}\n{content}\n")
    except Exception:
        pass

    return f"Learned and recorded: [{category.upper()}] '{topic}' is now part of my long-term memory."

def dynamic_create_plugin(plugin_name: str, description: str, python_code: str) -> str:
    """Dynamically write a new plugin into plugins/ folder so JARVIS acquires a new tool."""
    clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", plugin_name.lower().strip())
    if not clean_name:
        clean_name = "custom_learned_plugin"
    if clean_name.startswith("_"):
        clean_name = clean_name.lstrip("_")

    plugin_file = PLUGINS_DIR / f"{clean_name}.py"

    # Validate that code has PLUGIN dict and run function, or wrap it
    if "PLUGIN =" not in python_code or "def run(" not in python_code:
        # Wrap the code into a standard JARVIS plugin template
        safe_code = python_code.strip()
        wrapped_code = f'''"""
Auto-generated plugin: {clean_name}
Learned autonomously by JARVIS.
"""

PLUGIN = {{
    "name": "{clean_name}",
    "description": {repr(description)},
    "parameters": {{
        "type": "OBJECT",
        "properties": {{
            "query": {{"type": "STRING", "description": "Input parameter for {clean_name}"}},
        }},
        "required": [],
    }},
}}

def run(parameters: dict, player=None, session_memory=None) -> str:
    query = parameters.get("query", "")
    try:
{safe_code}
    except Exception as e:
        return f"Error executing {clean_name}: {{e}}"
'''
        content_to_write = wrapped_code
    else:
        content_to_write = python_code

    try:
        with open(plugin_file, "w", encoding="utf-8") as f:
            f.write(content_to_write)
        return f"Successfully generated and installed new plugin `{plugin_file.name}` in `{PLUGINS_DIR}`. The new skill is now active."
    except Exception as e:
        return f"Failed to create plugin: {e}"

def check_git_status() -> str:
    """Check git status and commit history."""
    try:
        res = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, timeout=5)
        changed = len(res.stdout.splitlines())
        log = subprocess.run(["git", "log", "-1", "--oneline"], capture_output=True, text=True, timeout=5)
        return f"Git Repository Status: {changed} uncommitted changes. Latest commit: {log.stdout.strip() or 'None'}"
    except Exception as e:
        return f"Git check failed: {e}"

def self_learning(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for self_learning."""
    action = parameters.get("action", "learn").lower().strip()
    category = parameters.get("category", "fact").strip()
    topic = parameters.get("topic", "General").strip()
    content = parameters.get("content", "").strip()
    plugin_name = parameters.get("plugin_name", "")
    plugin_description = parameters.get("plugin_description", "")
    code = parameters.get("code", "")

    if player:
        try: player.write_log(f"LEARN: Executing {action}...")
        except Exception: pass

    if action in ("learn", "remember", "save"):
        if not content:
            return "Please specify what you want me to learn or remember."
        return learn_knowledge(category, topic, content)

    elif action in ("create_plugin", "new_skill", "author_tool"):
        if not plugin_name or not (code or content):
            return "Please provide 'plugin_name' and the 'code' or logic for the new skill."
        desc = plugin_description or content or f"Custom learned plugin for {plugin_name}"
        return dynamic_create_plugin(plugin_name, desc, code or content)

    elif action in ("review", "list", "view"):
        data = _load_knowledge()
        facts_cnt = len(data.get("facts", []))
        rules_cnt = len(data.get("rules", []))
        wf_cnt = len(data.get("workflows", []))
        return f"🧠 Learned Memory: {facts_cnt} facts, {rules_cnt} rules, {wf_cnt} custom workflows registered."

    elif action in ("update", "git_status"):
        return check_git_status()

    return f"Self-learning action '{action}' completed."


TOOL = {
    "name": "self_learning",
    "description": (
        "Self-Learning & Dynamic Skill Authoring engine. Enables JARVIS to learn and permanently remember "
        "new facts, user preferences, custom rules, and operational workflows. Can also dynamically author "
        "and install brand-new drop-in Python plugins into the plugins/ directory so JARVIS gains new tools "
        "and updates itself automatically on command."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "learn | create_plugin | review | update",
            },
            "category": {
                "type": "STRING",
                "description": "fact | rule | workflow (default: fact)",
            },
            "topic": {
                "type": "STRING",
                "description": "Subject or topic title of what is being learned",
            },
            "content": {
                "type": "STRING",
                "description": "Detailed information, fact, rule, or logic to be learned",
            },
            "plugin_name": {
                "type": "STRING",
                "description": "Name for new plugin to create (e.g. crypto_tracker or auto_mailer)",
            },
            "plugin_description": {
                "type": "STRING",
                "description": "Description of what the new plugin does",
            },
            "code": {
                "type": "STRING",
                "description": "Python source code for the new plugin",
            }
        },
        "required": ["action"],
    },
    "handler": self_learning,
}
