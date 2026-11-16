# Playwright Browser Automation & Web Research

AMATYA includes high-performance browser automation and research capabilities powered by **Playwright** (`actions/browser_control.py`).

---

## 1. Persistent Profiles & Sign-In State

AMATYA stores browser state in `~/.amatya_profiles/<browser>`:
- **Sign-In Persistence:** Log in once to services (GitHub, Google, internal portals), and sessions persist across reboots.
- **Zero Redundant Tabs:** Intelligent context page reuse detects when a target page is already open, navigating in-place rather than spawning duplicate blank tabs.

---

## 2. Capabilities

### 1. Navigation & Content Extraction
- Navigate to URLs, follow redirects, wait for DOM hydration (`networkidle`).
- Extract clean reader-mode text, markdown summaries, and HTML structure.
- Execute JavaScript in page context for dynamic single-page applications.

### 2. Interaction & Form Filling
- Click elements via semantic CSS, XPath, or text selectors.
- Fill input fields, toggle checkboxes, select dropdown options.
- Handle modal dialogues, alerts, and cookie consent popups.

### 3. Visual Page Inspection
- Capture full-page or viewport screenshots.
- Feed visual page layouts directly to AMATYA's vision engine for UI analysis.

---

## 3. Voice Commands & Examples

- *"Open GitHub in browser"*
- *"Search Google for latest space weather report"*
- *"Take a screenshot of the current web page"*
- *"Extract the text from this article"*
- *"Close the active browser window"*
