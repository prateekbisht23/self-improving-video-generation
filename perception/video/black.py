"""Dips to black inside the window a 9:16 render will actually show (source time).

Measured on the rendered window, not the full frame: a dark sky can fill the 9:16 crop of a frame
whose edges are lit, and the evaluator's `technical.black_frames` sees the output window.
"""

import re
from functools import lru_cache

from perception.ffmpeg import run
from rendering.ffmpeg.render import crop_filter

_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")


@lru_cache(maxsize=1024)
def black_spans(path: str, start: float, end: float, crop_x: float = 0.5, width: int = 1080, height: int = 1920,
                min_dur: float = 0.1) -> tuple[tuple[float, float], ...]:
    """Black spans (source seconds) in [start, end] of `path`, inside the crop window. Same pixel
    threshold as the evaluator; a shorter minimum duration, so avoidance has a margin."""
    if end - start <= 0:
        return ()
    log = run(["ffmpeg", "-hide_banner", "-nostdin", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", path,
               "-an", "-vf", f"{crop_filter(crop_x, width, height)},blackdetect=d={min_dur}:pix_th=0.10",
               "-f", "null", "-"], check=False).stderr
    return tuple((round(start + float(a), 3), round(start + float(b), 3)) for a, b in _BLACK.findall(log))
