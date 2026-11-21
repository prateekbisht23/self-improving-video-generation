"""ffprobe -> MediaMetadata."""

from fractions import Fraction
from math import gcd
from pathlib import Path

from perception.ffmpeg import ffprobe_json
from perception.schemas import MediaMetadata, StreamInfo


def _fps(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    return round(float(Fraction(rate)), 3)


def probe(path: str | Path) -> MediaMetadata:
    data = ffprobe_json(path)
    streams = data.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)

    width = height = None
    aspect = None
    if video:
        width, height = int(video["width"]), int(video["height"])
        g = gcd(width, height)
        aspect = f"{width // g}:{height // g}"

    duration = float(data["format"].get("duration") or (video or audio or {}).get("duration", 0))
    return MediaMetadata(
        path=str(path),
        duration=round(duration, 3),
        width=width,
        height=height,
        # avg_frame_rate is the real average; r_frame_rate can be a timebase artefact.
        fps=_fps(video.get("avg_frame_rate")) if video else None,
        aspect_ratio=aspect,
        has_audio=audio is not None,
        has_video=video is not None,
        size_bytes=int(data["format"].get("size", 0)),
        streams=[
            StreamInfo(index=s["index"], codec_type=s["codec_type"], codec_name=s.get("codec_name"))
            for s in streams
        ],
    )
