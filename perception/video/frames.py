"""Representative-frame extraction."""

from pathlib import Path

from perception.ffmpeg import ffmpeg


def extract_frame(video: str | Path, t: float, out: str | Path, width: int = 768) -> Path:
    """Grab one frame at time `t` (seconds), scaled to `width` px wide, as JPEG.

    `-ss` *before* `-i` = fast keyframe seek, then decode to the exact frame.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
           "-vf", f"scale={width}:-2", "-q:v", "3", str(out))
    return out
