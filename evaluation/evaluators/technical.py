"""Deterministic technical checks on the rendered file (the PRD's technical quality gate)."""

from pathlib import Path

from evaluation.features import RenderFeatures
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, Evidence


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

    frozen = [z for z in f.frozen if z.end - z.start >= 2.0]
    out.append(_c("frozen_frames", not frozen, "minor",
                  f"{len(frozen)} frozen segment(s) >= 2s" if frozen else "no frozen segments",
                  evidence=[Evidence(start=z.start, end=z.end, detail="no motion") for z in frozen]))

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
