"""
core/skills_registry.py — Universal Agent Skills Registry & Discovery Engine
=============================================================================
Discovers, indexes, and validates all modular Agent Skills in the `skills/`
directory adhering to the open Agent Skills specification (YAML frontmatter
in SKILL.md with progressive disclosure).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / "skills"


@dataclass
class SkillInfo:
    name: str
    description: str
    path: Path
    skill_file: Path
    category: str
    license: str = ""
    scripts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    instructions: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "path": str(self.path),
            "scripts": self.scripts,
            "references": self.references,
            "license": self.license,
        }


def _infer_category(name: str, desc: str) -> str:
    n = name.lower()
    d = desc.lower()
    if any(k in n or k in d for k in ("security", "cyber", "sentry", "defense", "auth", "vulnerability")):
        return "Tactical Security & Cyber Defense"
    if any(k in n or k in d for k in ("lab", "math", "physics", "simulation", "calculator", "orbital", "satellite")):
        return "Scientific Modeling & Aerospace"
    if any(k in n or k in d for k in ("armor", "hardware", "diagnostics", "battery", "thermal")):
        return "Hardware & Armor Telemetry"
    if any(k in n or k in d for k in ("docx", "xlsx", "pptx", "pdf", "doc-coauthoring", "office")):
        return "Document & Presentation Synthesis"
    if any(k in n or k in d for k in ("art", "canvas", "design", "theme", "slack-gif")):
        return "Creative Media & UI Design"
    if any(k in n or k in d for k in ("mcp", "testing", "claude-api", "skill-creator", "web-artifacts")):
        return "Engineering & Agent Architecture"
    return "Operations & Intelligence"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter between leading --- delimiters."""
    meta: dict[str, str] = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_meta = parts[1]
            body = parts[2].strip()
            for line in raw_meta.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip().strip("\"'")
                    meta[k] = v
    return meta, body


_REGISTRY_CACHE: Dict[str, SkillInfo] = {}


def discover_skills(force_reload: bool = False) -> Dict[str, SkillInfo]:
    """Discover all skills in `skills/` directory with SKILL.md files."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE and not force_reload:
        return _REGISTRY_CACHE

    skills: Dict[str, SkillInfo] = {}
    if not SKILLS_DIR.is_dir():
        _REGISTRY_CACHE = skills
        return skills

    for skill_path in SKILLS_DIR.iterdir():
        if not skill_path.is_dir() or skill_path.name.startswith("."):
            continue
        skill_file = skill_path / "SKILL.md"
        if not skill_file.is_file():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(content)
            name = meta.get("name") or skill_path.name
            desc = meta.get("description") or (body.split("\n\n")[0] if body else "")
            cat = _infer_category(name, desc)

            # Discover bundled scripts and references
            scripts = []
            scripts_dir = skill_path / "scripts"
            if scripts_dir.is_dir():
                scripts = [f.name for f in scripts_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]

            refs = []
            refs_dir = skill_path / "references"
            if refs_dir.is_dir():
                refs = [f.name for f in refs_dir.rglob("*") if f.is_file() and not f.name.startswith(".")]

            skills[name] = SkillInfo(
                name=name,
                description=desc,
                path=skill_path,
                skill_file=skill_file,
                category=cat,
                license=meta.get("license", ""),
                scripts=scripts,
                references=refs,
                instructions=body,
            )
        except Exception:
            continue

    _REGISTRY_CACHE = skills
    return _REGISTRY_CACHE


def get_skill(name: str) -> Optional[SkillInfo]:
    reg = discover_skills()
    if name in reg:
        return reg[name]
    # Check case-insensitive match or normalized dash/underscore
    norm = name.lower().replace("_", "-")
    for k, v in reg.items():
        if k.lower().replace("_", "-") == norm:
            return v
    return None


def list_skills_summary(category: Optional[str] = None) -> List[Dict[str, Any]]:
    reg = discover_skills()
    res = []
    for s in reg.values():
        if category and s.category.lower() != category.lower():
            continue
        res.append(s.to_dict())
    return sorted(res, key=lambda x: (x["category"], x["name"]))


def search_skills(query: str) -> List[Dict[str, Any]]:
    q = query.strip().lower()
    reg = discover_skills()
    matches = []
    for s in reg.values():
        if q in s.name.lower() or q in s.description.lower() or q in s.category.lower():
            matches.append(s.to_dict())
    return matches
