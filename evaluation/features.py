"""Measure a rendered video independently of how it was made.

Everything here is computed from the output file: stream info, black/frozen segments,
silences, loudness, cut points, a fresh transcription of the output audio, and sampled frames.
"""

import json
import re
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from perception.audio.extract import extract_audio
from perception.audio.loudness import measure_loudness
from perception.audio.silence import detect_silence
from perception.ffmpeg import ffmpeg_analyze, run
from perception.scene_detection.detect import detect_scenes
from perception.video.frames import extract_frame
from perception.video.probe import probe


class Word(BaseModel):
    start: float
    end: float
    text: str


class Segment(BaseModel):
    start: float
    end: float


class RenderFeatures(BaseModel):
    path: str
    readable: bool
    error: str | None = None
    duration: float = 0.0
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    fps: float | None = None
    has_audio: bool = False
    video_stream_duration: float | None = None
    audio_stream_duration: float | None = None
    black: list[Segment] = Field(default_factory=list)
    frozen: list[Segment] = Field(default_factory=list)
    silences: list[Segment] = Field(default_factory=list)
    loudness_lufs: float | None = None
    true_peak_dbfs: float | None = None
    shots: list[Segment] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)      # ASR of the OUTPUT audio
    frames: list[tuple[float, str]] = Field(default_factory=list)

    @property
    def transcript(self) -> str:
        return " ".join(w.text for w in self.words)


_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*([\d.]+)")


def _stream_durations(path: str) -> tuple[float | None, float | None]:
    out = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", path]).stdout
    v = a = None
    for s in json.loads(out).get("streams", []):
        d = float(s["duration"]) if s.get("duration") not in (None, "N/A") else None
        if s["codec_type"] == "video":
            v = d
        elif s["codec_type"] == "audio":
            a = d
    return v, a


def parse_black(log: str) -> list[Segment]:
    return [Segment(start=float(a), end=float(b)) for a, b in _BLACK.findall(log)]


def parse_freeze(log: str, duration: float) -> list[Segment]:
    starts = [float(x) for x in _FREEZE_START.findall(log)]
    ends = [float(x) for x in _FREEZE_END.findall(log)]
    ends += [duration] * (len(starts) - len(ends))
    return [Segment(start=s, end=e) for s, e in zip(starts, ends, strict=False)]


def extract_features(path: str | Path, *, transcribe_audio: bool = True, n_frames: int = 12,
                     workdir: str | Path | None = None) -> RenderFeatures:
    path = str(path)
    try:
        m = probe(path)
    except Exception as e:
        return RenderFeatures(path=path, readable=False, error=str(e)[:500])
    f = RenderFeatures(path=path, readable=m.has_video and m.duration > 0, duration=m.duration, width=m.width,
                       height=m.height, aspect_ratio=m.aspect_ratio, fps=m.fps, has_audio=m.has_audio)
    if not f.readable:
        f.error = "no decodable video stream"
        return f
    f.video_stream_duration, f.audio_stream_duration = _stream_durations(path)
    log = ffmpeg_analyze(path, video_filter="blackdetect=d=0.25:pix_th=0.10,freezedetect=n=-60dB:d=1.5")
    f.black, f.frozen = parse_black(log), parse_freeze(log, m.duration)
    f.shots = [Segment(start=s.start, end=s.end) for s in detect_scenes(path, duration=m.duration, fps=m.fps)]

    work = Path(workdir or tempfile.mkdtemp(prefix="sivg-eval-"))
    work.mkdir(parents=True, exist_ok=True)
    if m.has_audio:
        loud = measure_loudness(path)
        f.loudness_lufs, f.true_peak_dbfs = loud["integrated_lufs"], loud["true_peak_dbfs"]
        wav = extract_audio(path, work / "eval_audio.wav")
        f.silences = [Segment(start=s.start, end=s.end) for s in detect_silence(wav, noise_db=-40, min_dur=0.8,
                                                                               duration=m.duration)]
        if transcribe_audio:
            from perception.audio.transcribe import transcribe

            segs, _ = transcribe(wav)
            f.words = [Word(start=w.start, end=w.end, text=w.text) for s in segs for w in s.words]
    for i in range(n_frames):
        t = round((i + 0.5) * m.duration / n_frames, 2)
        f.frames.append((t, str(extract_frame(path, t, work / f"eval_frame_{i:02d}.jpg", width=540))))
    return f
