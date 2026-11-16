# AMATYA Phase 13.4 — Visual Intelligence Specification
## Technical Diagram Analysis, Screenshot Interpretation & Visual Desktop Verification

**Version:** 13.4.0  
**Implementation:** `core/visual_intelligence.py`  
**Target Architecture:** Technical visual understanding across circuit schematics, block diagrams, plots, and Wayland desktop screenshots.

---

## 1. Overview and Core Capabilities

The Visual Intelligence subsystem (`core/visual_intelligence.py`) enables AMATYA to reason over technical images and visually verify desktop automations:

1. **Classification & Structural Understanding:** Classifies images as screenshots, schematics, block diagrams, mathematical plots, or photographs based on geometry and visual statistics.
2. **Technical Schematics & Edge Density:** Evaluates circuit diagrams, detects schematic canvases, and quantifies wire/component edge density.
3. **Uncertainty Quantification:** Flags ambiguous connections or faded symbols instead of hallucinating components, values, or connections.
4. **Visual Action Verification:** Compares pre- and post-action screenshots via structural differencing, calculating `change_ratio` and bounding boxes of affected screen areas.
5. **Multimodal Cloud Grounding:** Integrates with Gemini multimodal vision when explicitly authorized, while providing native offline PIL/OpenCV fallbacks.

---

## 2. API Usage

```python
from core.visual_intelligence import VisualIntelligenceEngine

# 1. Analyze an image or schematic
result = VisualIntelligenceEngine.analyze_image("circuit.png", query="What voltage regulator is shown?")
print("Image Type:", result.image_type)
print("Uncertainties:", result.uncertainties)

# 2. Verify an automated desktop action
verification = VisualIntelligenceEngine.verify_action(
    before_image_path="before_click.png",
    after_image_path="after_click.png",
    expected_change_region=(100, 200, 400, 500),
)
print("Action Verified:", verification.verified)
print("Change Ratio:", verification.change_ratio)
print("Changed Boxes:", verification.changed_boxes)
```
