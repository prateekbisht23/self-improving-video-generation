"""Deterministic Timeline -> ffmpeg compiler and runner (PRD FR-06 render_timeline).

    inputs:   one `-ss src_in -t dur -i file` per clip (input seeking = fast + frame accurate)
    per clip: crop to 9:16 (crop_x picks the window) -> scale -> fps -> colour look
    join:     cut -> concat ; transition -> xfade (video) + acrossfade (audio)
    overlay:  captions + titles burned in from an ASS file (libass)
    audio:    loudnorm to the output target (EBU R128, default -14 LUFS)

The filtergraph is written to a file and passed with `-/filter_complex`, and ffmpeg runs with
cwd = the render directory, so no path or text ever needs shell or filtergraph escaping.
"""

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from editing.timeline.schema import Timeline
from perception.audio.loudness import measure_loudness
from perception.ffmpeg import FFmpegError, ffmpeg
from perception.video.probe import probe
from rendering.ass import build_ass

RENDERER_VERSION = "ffmpeg-renderer-1.0"

COLOR_FILTERS = {
    "none": "",
    "warm": "colorbalance=rs=.06:gs=.01:bs=-.06:rm=.04:bm=-.04,eq=saturation=1.08",
    "cool": "colorbalance=rs=-.05:bs=.06:bm=.04,eq=saturation=1.02",
    "vivid": "eq=saturation=1.35:contrast=1.06",
    "muted": "eq=saturation=0.72:contrast=0.97",
    "bw": "hue=s=0,eq=contrast=1.1",
}


@dataclass
class RenderPlan:
    argv: list[str]
    filtergraph: str
    ass: str | None
    duration: float


@dataclass
class RenderResult:
    path: str
    duration: float
    seconds: float
    argv: list[str]
    filtergraph_sha256: str
    ass_sha256: str | None
    timeline_sha256: str
    renderer_version: str
    ffmpeg_version: str
    probe: dict
    loudness_lufs: float | None = None
    loudness_correction_db: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def crop_filter(crop_x: float, width: int, height: int) -> str:
    """The widest window of the output's aspect that fits the source (even dimensions), slid
    horizontally by crop_x. Shared with the evaluator, which inspects the same window in the source."""
    cw = f"trunc(min(iw\\,ih*{width}/{height})/2)*2"
    ch = f"trunc(min(ih\\,iw*{height}/{width})/2)*2"
    return f"crop=w='{cw}':h='{ch}':x='(iw-ow)*{crop_x:.3f}':y='(ih-oh)/2'"

def ffmpeg_version() -> str:
    out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    return out.splitlines()[0] if out else "unknown"


def compile_timeline(tl: Timeline, out_name: str = "output.mp4") -> RenderPlan:
    problems = tl.render_problems()
    if not tl.video:
        raise ValueError("; ".join(problems))
    o = tl.output
    args: list[str] = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    graph: list[str] = []
    color = COLOR_FILTERS[tl.style.color]

    n_inputs = 0
    for i, c in enumerate(tl.video):
        a = tl.asset(c.asset_id)
        dur = f"{c.duration:.3f}"
        args += ["-ss", f"{c.src_in:.3f}", "-t", dur, "-i", str(Path(a.path).resolve())]
        vin = n_inputs
        n_inputs += 1
        if a.has_audio:
            ain = f"{vin}:a"
        else:  # silent track of the same length keeps audio/video aligned through joins
            args += ["-f", "lavfi", "-t", dur, "-i", "anullsrc=r=48000:cl=stereo"]
            ain = f"{n_inputs}:a"
            n_inputs += 1
        crop = crop_filter(c.crop_x, o.width, o.height)
        vchain = ["setpts=PTS-STARTPTS", crop, f"scale={o.width}:{o.height}:flags=lanczos", "setsar=1",
                  f"fps={o.fps}", "format=yuv420p", "settb=AVTB"]
        if color:
            vchain.insert(4, color)
        graph.append(f"[{vin}:v]{','.join(vchain)}[v{i}]")
        graph.append(f"[{ain}]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"volume={c.volume:.3f}[a{i}]")

    acc_v, acc_a, acc_dur = "v0", "a0", tl.video[0].duration
    for i, c in enumerate(tl.video[1:], start=1):
        nv, na = f"jv{i}", f"ja{i}"
        if c.transition_in == "cut":
            graph.append(f"[{acc_v}][{acc_a}][v{i}][a{i}]concat=n=2:v=1:a=1[{nv}][{na}]")
            acc_dur += c.duration
        else:
            d = c.transition_duration
            graph.append(f"[{acc_v}][v{i}]xfade=transition={c.transition_in}:duration={d:.3f}:"
                         f"offset={acc_dur - d:.3f}[{nv}]")
            graph.append(f"[{acc_a}][a{i}]acrossfade=d={d:.3f}:c1=tri:c2=tri[{na}]")
            acc_dur += c.duration - d
        acc_v, acc_a = nv, na

    ass = None
    if tl.captions or tl.titles:
        ass = build_ass(tl)
        graph.append(f"[{acc_v}]subtitles=filename=overlay.ass[vout]")
    else:
        graph.append(f"[{acc_v}]null[vout]")
    graph.append(f"[{acc_a}]loudnorm=I={o.loudness_lufs}:TP=-1.5:LRA=11,aresample=48000[aout]")

    args += ["-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(o.fps),
             "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
             "-t", f"{tl.duration:.3f}", out_name]
    return RenderPlan(argv=args, filtergraph=";\n".join(graph), ass=ass, duration=tl.duration)


def render(tl: Timeline, out_dir: str | Path, out_name: str = "output.mp4") -> RenderResult:
    """Compile and run. Writes graph.txt, overlay.ass, timeline.json and the video into out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = compile_timeline(tl, out_name)
    (out_dir / "graph.txt").write_text(plan.filtergraph)
    (out_dir / "timeline.json").write_text(json.dumps(tl.model_dump(mode="json"), indent=2))
    if plan.ass:
        (out_dir / "overlay.ass").write_text(plan.ass)
    t0 = time.perf_counter()
    proc = subprocess.run(plan.argv, cwd=out_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"render failed ({proc.returncode}): {proc.stderr[-2000:]}")
    lufs, gain = _fix_loudness(out_dir / out_name, tl.output.loudness_lufs)
    meta = probe(out_dir / out_name)
    sha = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
    return RenderResult(
        path=str(out_dir / out_name), duration=meta.duration, seconds=round(time.perf_counter() - t0, 2),
        argv=plan.argv, filtergraph_sha256=sha(plan.filtergraph), ass_sha256=sha(plan.ass) if plan.ass else None,
        timeline_sha256=tl.content_hash(), renderer_version=RENDERER_VERSION, ffmpeg_version=ffmpeg_version(),
        probe=meta.model_dump(), loudness_lufs=lufs, loudness_correction_db=gain,
    )


def _fix_loudness(path: Path, target: float, tolerance: float = 0.7) -> tuple[float | None, float]:
    """Single-pass loudnorm undershoots on short programmes. Measure the result and, if needed,
    apply one linear gain correction (video stream copied, so this is cheap and lossless for video)."""
    measured = measure_loudness(path)["integrated_lufs"]
    if measured is None or abs(measured - target) <= tolerance:
        return measured, 0.0
    gain = round(target - measured, 2)
    tmp = path.with_name("loudfix_" + path.name)
    ffmpeg("-i", str(path), "-c:v", "copy", "-af", f"volume={gain}dB,alimiter=limit=0.891:level=false",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(tmp))
    tmp.replace(path)
    return measure_loudness(path)["integrated_lufs"], gain
