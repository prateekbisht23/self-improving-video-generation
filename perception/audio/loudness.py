"""EBU R128 loudness via ffmpeg's `ebur128` filter (summary block at end of log)."""

import re
from pathlib import Path

from perception.ffmpeg import ffmpeg_analyze


def _grab(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    if not m or m.group(1) in ("-inf", "inf"):
        return None
    return float(m.group(1))


def measure_loudness(path: str | Path) -> dict[str, float | None]:
    log = ffmpeg_analyze(path, audio_filter="ebur128=peak=true")
    summary = log[log.rfind("Summary:"):] if "Summary:" in log else log
    return {
        "integrated_lufs": _grab(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summary),
        "loudness_range_lu": _grab(r"LRA:\s+(-?[\d.]+)\s+LU", summary),
        "true_peak_dbfs": _grab(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summary),
    }
