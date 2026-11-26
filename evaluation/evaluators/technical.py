"""Deterministic technical checks on the rendered file (the PRD's technical quality gate)."""

from pathlib import Path

from evaluation.evaluators.temporal import clip_starts
from evaluation.features import RenderFeatures, Segment, parse_freeze
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, Evidence
from perception.ffmpeg import run as run_ffmpeg
from rendering.ffmpeg.render import crop_filter

FREEZE_MIN = 2.0       # an output freeze this long is reported
STATIC_SHARE = 0.8     # ...unless the source under it is at least this static (a still shot, not a fault)


def _c(id_, passed, severity, message, **kw) -> CheckResult:
    return CheckResult(id=f"technical.{id_}", category="technical", kind="deterministic", passed=passed,
                       severity=severity, message=message, **kw)


def run(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    if not f.readable:
        return [_c("file_valid", False, "critical", f"render is not a playable video: {f.error}")]
    out = [_c("file_valid", True, "critical", "render decodes: video stream present")]

    ok = (f.width, f.height) == (x.width, x.height)
    out.append(_c("resolution", ok, "critical", f"{f.width}x{f.height} (expected {x.width}x{x.height})",
                  measurements={"width": f.width, "height": f.height}))
    out.append(_c("aspect_ratio", f.aspect_ratio == x.aspect_ratio, "critical",
                  f"aspect {f.aspect_ratio} (expected {x.aspect_ratio})"))

    tol = 0.25
    ok = x.min_duration - tol <= f.duration <= x.max_duration + tol
    out.append(_c("duration_in_range", ok, "critical",
                  f"{f.duration:.2f}s (required {x.min_duration:.0f}-{x.max_duration:.0f}s)",
                  measurements={"duration": f.duration}))

    audible = f.has_audio and f.loudness_lufs is not None and f.loudness_lufs > -50
    out.append(_c("audio_present", audible, "critical",
                  "audible audio track" if audible else f"no audible audio (track={f.has_audio}, "
                                                        f"loudness={f.loudness_lufs})"))

    if f.video_stream_duration and f.audio_stream_duration:
        drift = abs(f.video_stream_duration - f.audio_stream_duration)
        out.append(_c("av_stream_alignment", drift <= 0.1, "critical",
                      f"audio/video stream lengths differ by {drift:.3f}s",
                      measurements={"video": f.video_stream_duration, "audio": f.audio_stream_duration},
                      explanation="Stream-length proxy for A/V sync; lip-sync offset is not measured."))

    bad = [b for b in f.black if b.end - b.start >= 0.3]
    out.append(_c("black_frames", not bad, "critical" if any(b.end - b.start > 1.0 for b in bad) else "major",
                  f"{len(bad)} black segment(s) >= 0.3s" if bad else "no black segments",
                  evidence=[Evidence(start=b.start, end=b.end, detail="black") for b in bad]))

    out.append(frozen_check(f.frozen, x.timeline))

    if f.loudness_lufs is not None:
        ok = abs(f.loudness_lufs - x.loudness_target) <= 1.5 and (f.true_peak_dbfs or -99) <= -0.5
        out.append(_c("loudness", ok, "minor",
                      f"{f.loudness_lufs} LUFS, peak {f.true_peak_dbfs} dBFS (target {x.loudness_target} ±1.5)",
                      measurements={"lufs": f.loudness_lufs, "true_peak": f.true_peak_dbfs}))

    if x.timeline:
        missing = [a["path"] for a in x.timeline.get("assets", []) if not Path(a["path"]).exists()]
        out.append(_c("missing_media", not missing, "critical",
                      f"missing source files: {missing}" if missing else "all source media present"))
    return out


def source_static(z: Segment, tl: dict | None) -> bool:
    """Is the SOURCE footage under an output freeze itself static?

    `technical.frozen_frames` exists to catch render faults (a stalled decode, padded frames). A still
    shot in the source (a locked-off moon, a slide) produces the same "no motion" signal in the output
    but is content, not a fault; whether a still shot is a good editing choice is for the pacing and
    judge checks. So each output freeze is mapped back through the timeline to its source ranges, and
    freezedetect runs there, inside the same 9:16 window the renderer shows, with the same noise
    threshold. (eval-1.2 looked at the full frame: motion outside the crop made a still visible window
    count as "not static", a false fault.)"""
    if not tl or not tl.get("video"):
        return False
    paths = {a["id"]: a["path"] for a in tl.get("assets", [])}
    out = {"width": 1080, "height": 1920} | (tl.get("output") or {})
    covered = 0.0
    for c, start in zip(tl["video"], clip_starts(tl), strict=True):
        a, b = max(z.start, start), min(z.end, start + c["src_out"] - c["src_in"])
        if b - a < 0.25:  # boundary jitter: too short for freezedetect to judge
            continue
        path = paths.get(c["asset_id"])
        if not path or not Path(path).exists():
            return False
        window = crop_filter(c.get("crop_x", 0.5), out["width"], out["height"])
        log = run_ffmpeg(["ffmpeg", "-hide_banner", "-nostdin", "-ss", f"{c['src_in'] + a - start:.3f}",
                          "-t", f"{b - a:.3f}", "-i", path, "-an", "-vf", f"{window},freezedetect=n=-60dB:d=0.5",
                          "-f", "null", "-"], check=False).stderr
        still = sum(max(0.0, min(s.end, b - a) - max(s.start, 0.0)) for s in parse_freeze(log, b - a))
        if still < STATIC_SHARE * (b - a):
            return False
        covered += b - a
    return covered >= STATIC_SHARE * (z.end - z.start)


def frozen_check(segments: list[Segment], tl: dict | None) -> CheckResult:
    long = [z for z in segments if z.end - z.start >= FREEZE_MIN]
    content = [z for z in long if source_static(z, tl)]
    faults = [z for z in long if z not in content]
    ev = ([Evidence(start=z.start, end=z.end, detail="no motion") for z in faults]
          + [Evidence(start=z.start, end=z.end, detail="still source footage") for z in content])
    if faults:
        msg = f"{len(faults)} frozen segment(s) >= {FREEZE_MIN:.0f}s not explained by the source"
    elif content:
        msg = f"{len(content)} static segment(s) >= {FREEZE_MIN:.0f}s, all still shots in the source (not a fault)"
    else:
        msg = "no frozen segments"
    return _c("frozen_frames", not faults, "minor", msg, evidence=ev,
              measurements={"faults": len(faults), "still_source": len(content)})
