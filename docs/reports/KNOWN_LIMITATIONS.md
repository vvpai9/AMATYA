# AMATYA Phase 13 — Known Limitations & Operational Boundaries

**Version:** 13.0.0  
**Host Target Profile:** Intel Core i5-11300H (12 logical threads), 16 GB RAM, NVIDIA GeForce GTX 1650 Mobile (4 GB VRAM)  
**Platform:** KDE Plasma 6 Wayland (Linux), PipeWire 1.6

---

## 1. Hardware & Compute Boundaries

1. **Local OCR & Tesseract:**
   - Where the system `tesseract` binary is not installed, AMATYA utilizes local edge/contour heuristic analysis in OpenCV/PIL or authorized cloud vision models. It does not fabricate text.
2. **Video Frame Ingestion:**
   - Full 4K 60fps video stream decoding exceeds edge CPU/GPU real-time memory limits. AMATYA employs keyframe sampling (1 frame per 30 seconds or scene change) rather than dense continuous decoding.
3. **Audio Diarization:**
   - Multi-speaker overlapping dialog in noisy acoustic environments is classified by acoustic turn boundaries; voice identification is strictly tied to verified speaker profiles in `core.voice_auth`. Unknown voices are labeled `Speaker N`.
4. **Scanned PDF Text Quality:**
   - PDFs containing rasterized bitmap scans without embedded font dictionaries rely on visual document analysis; ambiguous symbols are flagged with explicit confidence penalties.

---

## 2. Security Boundaries

1. **System Path Ingestion:**
   - Ingestion of system paths (`/etc`, `/proc`, `/sys`, `/root`) is forbidden by `SecurityGovernance`.
2. **SSRF Guard:**
   - Direct web URL ingestion blocks access to private intranet endpoints (`localhost`, `127.0.0.1`, `192.168.x.x`).
