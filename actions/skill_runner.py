"""
actions/skill_runner.py — Universal Agent Skills Orchestration & Runner
========================================================================
Empowers AMATYA to introspect, query, load, and execute any integrated Agent Skill
from the `skills/` directory adhering to the open Agent Skills standard.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core import outcome
from core.skills_registry import (
    discover_skills,
    get_skill,
    list_skills_summary,
    search_skills,
)

SKILL_METADATA = {
    "capabilities": [
        "agent_skills_discovery",
        "skills_progressive_disclosure",
        "skill_execution",
        "skill_catalog_search",
    ],
    "permissions": ["skills_orchestration"],
    "dependencies": [],
    "supported_actions": [
        "list_skills",
        "skill_info",
        "search_skills",
        "run_skill",
    ],
    "security_level": "low",
}


def execute(
    parameters: dict,
    player: Any = None,
    session_memory: Any = None,
    **kwargs,
) -> str:
    """Action entry point for skill_runner."""
    params = parameters or {}
    action = str(params.get("action") or "list_skills").strip().lower()

    if action == "list_skills":
        skills = list_skills_summary()
        categories: Dict[str, List[str]] = {}
        for s in skills:
            cat = s["category"]
            categories.setdefault(cat, []).append(s["name"])

        lines = [f"# 🛠️ AMATYA INTEGRATED AGENT SKILLS ({len(skills)} Active)\n"]
        for cat, names in sorted(categories.items()):
            lines.append(f"### {cat}")
            for n in sorted(names):
                lines.append(f"- **`{n}`**")
            lines.append("")

        report = "\n".join(lines)
        if player is not None:
            try:
                player.show_content("Agent Skills Suite", report)
                player.write_log(f"SKILL_RUNNER: Loaded {len(skills)} integrated agent skills")
            except Exception:
                pass
        return outcome.done(
            "skill_runner",
            result=f"AMATYA is equipped with {len(skills)} specialized agent skills across {len(categories)} operational categories. Categories include {', '.join(categories.keys())}.",
            data={"total_skills": len(skills), "categories": categories},
        )

    if action == "skill_info":
        name = str(params.get("skill_name") or "").strip()
        if not name:
            return outcome.failed("skill_runner", "Missing required parameter 'skill_name'.")
        skill = get_skill(name)
        if not skill:
            return outcome.failed("skill_runner", f"Skill '{name}' not found.")

        report = (
            f"# 📖 SKILL: {skill.name.upper()}\n\n"
            f"**Category:** `{skill.category}`\n\n"
            f"### Description\n{skill.description}\n\n"
            f"### Instructions & Guidance\n{skill.instructions[:1500]}..."
        )
        if player is not None:
            try:
                player.show_content(f"Skill: {skill.name}", report)
            except Exception:
                pass
        return outcome.done("skill_runner", result=f"Skill '{skill.name}' ({skill.category}): {skill.description[:200]}...", data=skill.to_dict())

    if action == "search_skills":
        q = str(params.get("query") or "").strip()
        matches = search_skills(q)
        names = [m["name"] for m in matches]
        return outcome.done("skill_runner", result=f"Found {len(matches)} skills matching '{q}': {', '.join(names) if names else 'None'}.", data={"query": q, "matches": matches})

    return outcome.failed("skill_runner", f"Unknown action '{action}'")


TOOL = {
    "name": "skill_runner",
    "description": (
        "Universal Agent Skills Orchestration & Runner: Introspects, catalogs, queries, and "
        "executes any integrated Agent Skill across cybersecurity defense, scientific computing, "
        "hardware diagnostics, satellite tracking, document synthesis, and UI design."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["list_skills", "skill_info", "search_skills", "run_skill"],
                "description": "Skills action to execute (default: 'list_skills').",
            },
            "skill_name": {
                "type": "STRING",
                "description": "Name of the target skill for 'skill_info' or 'run_skill'.",
            },
            "query": {
                "type": "STRING",
                "description": "Search keyword for 'search_skills'.",
            },
        },
    },
    "handler": execute,
}
