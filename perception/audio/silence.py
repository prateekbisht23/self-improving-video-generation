"""Silence detection via ffmpeg's `silencedetect` filter."""

import re
from pathlib import Path

from perception.ffmpeg import ffmpeg_analyze
from perception.schemas import SilenceRange

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*([\d.]+)")


def parse_silencedetect(log: str, duration: float | None = None) -> list[SilenceRange]:
    out: list[SilenceRange] = []
    start: float | None = None
    for line in log.splitlines():
        if m := _START.search(line):
            start = max(0.0, float(m.group(1)))
        elif (m := _END.search(line)) and start is not None:
            out.append(SilenceRange(start=round(start, 3), end=round(float(m.group(1)), 3)))
            start = None
    if start is not None and duration is not None:  # silence runs to end of file
        out.append(SilenceRange(start=round(start, 3), end=round(duration, 3)))
    return out


def detect_silence(path: str | Path, *, noise_db: float = -35.0, min_dur: float = 0.5,
                   duration: float | None = None) -> list[SilenceRange]:
    log = ffmpeg_analyze(path, audio_filter=f"silencedetect=noise={noise_db}dB:d={min_dur}")
    return parse_silencedetect(log, duration)
