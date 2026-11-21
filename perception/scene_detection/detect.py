"""Shot boundary detection with PySceneDetect."""

from pathlib import Path

from scenedetect import ContentDetector, detect

from perception.schemas import Scene


def detect_scenes(video: str | Path, *, threshold: float = 27.0,
                  min_scene_len_s: float = 0.6, duration: float | None = None) -> list[Scene]:
    """Return ordered scenes. A video with no cuts yields one scene covering everything."""
    # min_scene_len is in frames; 15 frames ~= 0.5s at 30fps. Keep it simple for now.
    raw = detect(str(video), ContentDetector(threshold=threshold,
                                             min_scene_len=max(1, int(min_scene_len_s * 30))))
    spans = [(s.seconds, e.seconds) for s, e in raw]
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
