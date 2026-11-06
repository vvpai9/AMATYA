# AMATYA Phase 13.5 — Audio and Video Intelligence Specification
## Timestamped Transcription, Diarization, Scene Segmentation & Temporal Querying

**Version:** 13.5.0  
**Implementation:** `core/media_intelligence.py`  
**Target Architecture:** Multi-format audio and video comprehension across WAV, MP3, MP4, MKV, and WebM.

---

## 1. Overview and Core Capabilities

The Audio and Video Intelligence subsystem (`core/media_intelligence.py`) provides unified acoustic and visual-temporal comprehension:

1. **Timestamped Speech Transcription:** Breaks audio recordings into structured sentence-level utterances with precise `[start_seconds, end_seconds]` timestamps.
2. **Action Item & Task Extraction:** Automatically identifies commitments and action items (e.g., *"we need to implement the regulator"*, *"please follow up with telemetry"*).
3. **Speaker Turn Detection:** Preserves distinct speaker labels (`Speaker 1`, `Speaker 2`) across dialog turns.
4. **Video Scene Segmentation:** Breaks video streams into temporal scene blocks without resource-heavy frame decoding.
5. **Keyframe Extraction:** Leverages `ffmpeg` keyframe sampling at scene midpoints for visual summarization and OCR indexing.

---

## 2. API Usage

```python
from core.media_intelligence import MediaIntelligenceEngine

# 1. Analyze Audio Recording
audio_result = MediaIntelligenceEngine.analyze_audio("team_meeting.wav")
print("Duration:", audio_result.duration_seconds)
print("Action Items:", audio_result.action_items)
for chunk in audio_result.transcript_chunks:
    print(f"[{chunk.start_seconds}s - {chunk.end_seconds}s] {chunk.speaker}: {chunk.text}")

# 2. Analyze Video Stream
video_result = MediaIntelligenceEngine.analyze_video("system_architecture_talk.mp4")
print("Resolution:", video_result.resolution)
print("Scenes Found:", len(video_result.scenes))
for scene in video_result.scenes:
    print(f"Scene {scene.scene_index}: [{scene.start_seconds}s - {scene.end_seconds}s] Keyframe: {scene.keyframe_path}")
```
