"""Shot boundary detection with PySceneDetect.

AdaptiveDetector compares each frame's change score against a rolling average of its
neighbours, so it catches soft cuts/dissolves without firing on steady camera motion.
Measured on samples/nasa_supermoon.mp4 (see docs/learn/02): ContentDetector(27) merged the
whole 0-32s intro into one scene; AdaptiveDetector(2.0) found the 5.3/8.5/27.9s changes.
"""

from pathlib import Path

from scenedetect import AdaptiveDetector, ContentDetector, detect

from perception.schemas import Scene

DETECTOR_VERSION = "adaptive-2.0-v1"  # recorded with results so re-runs are comparable


def detect_scenes(video: str | Path, *, duration: float | None = None, fps: float | None = None,
                  min_scene_len_s: float = 0.6, method: str = "adaptive",
                  threshold: float | None = None) -> list[Scene]:
    """Return ordered scenes. A video with no cuts yields one scene covering everything."""
    min_frames = max(1, round(min_scene_len_s * (fps or 30)))
    if method == "adaptive":
        detector = AdaptiveDetector(adaptive_threshold=threshold or 2.0, min_scene_len=min_frames)
    else:
        detector = ContentDetector(threshold=threshold or 27.0, min_scene_len=min_frames)
    spans = [(s.seconds, e.seconds) for s, e in detect(str(video), detector)]
    if not spans:
        if duration is None:
            raise ValueError("no scenes detected and duration unknown")
        spans = [(0.0, duration)]
    if duration is not None:  # clamp to container duration (FR-03 acceptance)
        spans = [(max(0.0, s), min(e, duration)) for s, e in spans if s < duration]
    return [
        Scene(id=f"scene_{i:03d}", index=i, start=round(s, 3), end=round(e, 3))
        for i, (s, e) in enumerate(spans)
    ]
