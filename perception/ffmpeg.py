"""Thin, safe wrappers around the ffmpeg/ffprobe binaries.

Commands are always argv lists (never shell strings), so no user/LLM text is ever
interpreted by a shell (PRD FR-06: no arbitrary shell commands).
"""

import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise FFmpegError(f"{args[0]} failed ({proc.returncode}): {proc.stderr[-2000:]}")
    return proc


def ffprobe_json(path: str | Path) -> dict:
    proc = run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)]
    )
    return json.loads(proc.stdout)


def ffmpeg(*args: str) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg quietly, overwriting outputs. Diagnostics land in stderr."""
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args])


def ffmpeg_analyze(path: str | Path, *, audio_filter: str | None = None,
                   video_filter: str | None = None) -> str:
    """Decode a file through an analysis filter and discard output; return stderr logs."""
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path)]
    if audio_filter:
        args += ["-vn", "-af", audio_filter]
    if video_filter:
        args += ["-an", "-vf", video_filter]
    args += ["-f", "null", "-"]
    return run(args).stderr
