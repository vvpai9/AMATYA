# Universal Skills Ecosystem & Runtime

AMATYA implements a progressive-disclosure skills engine (`core/skills_registry.py`, `actions/skill_runner.py`) combining Anthropic's official skills ecosystem with custom Iron Man JARVIS tactical and scientific skills.

---

## 1. Architecture & Progressive Disclosure

Skills reside in `skills/<skill_name>/SKILL.md`:
- **Lightweight Discovery:** AMATYA loads only the name and one-sentence description at startup, avoiding context window bloat.
- **On-Demand Progressive Disclosure:** When a relevant task is triggered, AMATYA reads the full instruction set, scripts, and examples just in time.

---

## 2. Catalog of Available Skills

The ecosystem comprises **23 specialized skills** across 7 functional domains:

### 1. Document & Enterprise Productivity (Anthropic Official)
- **`docx`:** Create, format, edit, and inspect Microsoft Word documents.
- **`xlsx`:** Process, analyze, calculate formulas, and chart Excel spreadsheets.
- **`pptx`:** Design and generate polished PowerPoint presentations.
- **`pdf`:** Extract text, split/merge pages, and fill forms in PDF files.

### 2. Software Engineering & Systems
- **`mcp-builder`:** Design and scaffold Model Context Protocol (MCP) servers.
- **`webapp-testing`:** End-to-end automated testing with Playwright scripts.
- **`claude-api`:** Multi-turn chat, prompt caching, tool use, and thinking blocks.

### 3. Design, UI & Creative Media
- **`frontend-design`:** Modern reactive web UI design, tailwind components, CSS styling.
- **`algorithmic-art`:** Generative canvas art, mathematical geometry, SVGs.
- **`canvas-design`:** Visual layout composition and graphic structuring.
- **`diagramming`:** Technical architectural diagrams via Mermaid, Graphviz, PlantUML.
- **`slack-gif-creator`:** Generate animated GIF status updates and graphics.

### 4. Communication & Business Operations
- **`customer-journey-mapping`:** Experience maps, personas, touchpoint analytics.
- **`internal-comms`:** Executive briefs, status memos, incident post-mortems.
- **`interactive-storytelling`:** Branching narrative simulations and educational walkthroughs.

### 5. Stark Tactical Cyber Defense Matrix
- **`cyber-defense`:** Host perimeter scan, open port auditing, firewall inspection, SSH auth audit.

### 6. Stark Laboratory & Aerospace Science
- **`stark-calculator`:** Symbolic calculus, kinematic projectile trajectories, orbital mechanics.
- **`armor-diagnostics`:** Mark armor scorecard, core thermal maps, battery health, GPU VRAM.
- **`orbital-mechanics`:** Satellite telemetry (ISS, CSS, Hubble), pass predictions.
- **`space-weather`:** NOAA solar geomagnetic storms, solar flares, radio blackouts.
- **`radio-aerospace`:** Flightradar24 airspace scanner and worldwide radio streaming.

### 7. Desktop & Device Automation
- **`smart-desktop`:** Frecency folder jumping, file manager / terminal launching.
- **`device-automation`:** Android TV ADB control, KDE Connect, AgentRing VoIP.

---

## 3. Skill Runner Tool & Voice Commands

### Spoken Queries:
- *"What skills do you have?"*
- *"List tactical security skills"*
- *"Show info on stark-calculator"*
- *"Run skill docx to generate a project report"*
- *"Use skill diagramming to illustrate our system architecture"*
