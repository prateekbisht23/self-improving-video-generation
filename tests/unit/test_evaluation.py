"""Known defects must be detected (Phase 3 exit), and evaluation stays independent of the agent."""

import ast
from pathlib import Path

import pytest

import evaluation.evaluators.judges as judges_mod
from editing.operations import apply_action
from editing.timeline.schema import OutputSpec, Timeline
from evaluation.graph import evaluate
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, EvaluationReport
from perception.ffmpeg import ffmpeg
from rendering.ffmpeg.render import render
from tests.fakes import synthetic_context

V = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30"]
A = ["-c:a", "aac", "-ar", "48000"]


def vertical(src, out, *extra_in, vf="scale=1080:1920,setsar=1", af=None, t=None):
    args = ["-i", str(src), *extra_in, "-vf", vf, *V, *A]
    if af:
        args += ["-af", af]
    if t:
        args += ["-t", str(t)]
    ffmpeg(*args, str(out))
    return out


def ev(path, **kw) -> dict[str, CheckResult]:
    x = EvalInput(render_path=str(path), instructions="test", min_duration=kw.pop("min_d", 4),
                  max_duration=kw.pop("max_d", 30), **kw)
    rep = evaluate(x, judges_on=False, transcribe=kw.get("captions_required") is not None)
    return {c.id: c for c in rep.checks} | {"_report": rep}


@pytest.fixture(scope="module")
def good(synthetic, tmp_path_factory):
    ctx = synthetic_context(synthetic)
    t = Timeline(assets=ctx.assets, output=OutputSpec(min_duration=4, max_duration=30))
    for name, args in [("select_clip", {"scene_id": "S1", "src_in": 0.0, "src_out": 3.95}),
                       ("select_clip", {"scene_id": "S3"}), ("generate_captions", {})]:
        t = apply_action(t, name, args, ctx).timeline
    out = tmp_path_factory.mktemp("good")
    return t, render(t, out).path, ctx


def test_clean_render_passes_technical_gate(good):
    tl, path, _ = good
    r = ev(path, timeline=tl.model_dump(mode="json"))
    assert r["_report"].technical_gate_passed, r["_report"].failed
    for cid in ("technical.resolution", "technical.aspect_ratio", "technical.audio_present",
                "technical.av_stream_alignment", "technical.black_frames", "technical.loudness",
                "temporal.repeated_footage"):
        assert r[cid].passed, (cid, r[cid].message)


def test_detects_black_frames_with_timestamps(synthetic, tmp_path):
    r = ev(vertical(synthetic / "black_gap.mp4", tmp_path / "b.mp4"))
    c = r["technical.black_frames"]
    assert c.passed is False and c.evidence[0].start == pytest.approx(2.0, abs=0.15)
    assert not r["_report"].technical_gate_passed  # a 2s black hole is critical


def test_detects_wrong_aspect_and_resolution(synthetic, tmp_path):
    r = ev(synthetic / "cuts.mp4")
    assert r["technical.aspect_ratio"].passed is False and r["technical.resolution"].passed is False


def test_detects_silent_audio(synthetic, tmp_path):
    r = ev(vertical(synthetic / "cuts.mp4", tmp_path / "s.mp4", af="volume=0"))
    assert r["technical.audio_present"].passed is False


def test_detects_av_drift(synthetic, tmp_path):
    out = tmp_path / "drift.mp4"
    ffmpeg("-i", str(synthetic / "cuts.mp4"), "-f", "lavfi", "-t", "3", "-i", "sine=f=440",
           "-map", "0:v", "-map", "1:a", "-vf", "scale=1080:1920,setsar=1", *V, *A, str(out))
    assert ev(out)["technical.av_stream_alignment"].passed is False


def test_detects_duration_out_of_range(good):
    _, path, _ = good
    c = ev(path, min_d=15, max_d=30)["technical.duration_in_range"]
    assert c.passed is False and "required 15-30s" in c.message


def test_detects_repeated_footage_and_cut_through_word(good):
    tl, path, ctx = good
    bad = tl.model_dump(mode="json")
    bad["video"] = [dict(bad["video"][0], src_in=0.0, src_out=0.9),          # ends inside "editing" (0.7-1.1)
                    dict(bad["video"][0], src_in=0.2, src_out=3.0)]          # repeats 0.2-0.9
    words = {"speech": [(w.start, w.end, w.text) for w in ctx.words["speech"]]}
    r = ev(path, timeline=bad, source_words=words)
    assert r["temporal.repeated_footage"].passed is False
    assert r["temporal.cut_through_word"].passed is False
    assert "editing" in r["temporal.cut_through_word"].evidence[0].detail


def test_detects_caption_desync(good):
    tl, path, _ = good
    ok = ev(path, timeline=tl.model_dump(mode="json"), captions_required=True)
    assert ok["captions.sync"].passed and ok["captions.accuracy"].measurements["wer"] < 0.2
    shifted = tl.model_dump(mode="json")
    for c in shifted["captions"]:
        c["start"] += 0.8
        c["end"] += 0.8
    bad = ev(path, timeline=shifted, captions_required=True)
    assert bad["captions.sync"].passed is False


def test_gate_and_pass_rate_aggregation():
    mk = lambda i, p, sev: CheckResult(id=i, category="technical", kind="deterministic", passed=p,  # noqa: E731
                                       severity=sev, message="")
    rep = EvaluationReport.aggregate([mk("a", True, "critical"), mk("b", False, "minor"), mk("c", None, "critical")],
                                     render_path="x")
    assert rep.technical_gate_passed and rep.pass_rate == 0.5 and rep.failed == ["b"]
    rep2 = EvaluationReport.aggregate([mk("a", False, "critical")], render_path="x")
    assert not rep2.technical_gate_passed


def test_judge_failure_is_contained(good, monkeypatch):
    _, path, _ = good

    def boom(role, **_):
        raise RuntimeError("quota")

    monkeypatch.setattr(judges_mod, "get_chat_model", boom)
    rep = evaluate(EvalInput(render_path=path, instructions="t", min_duration=4, max_duration=30),
                   judges_on=True, transcribe=False)
    j = {c.id: c for c in rep.checks}["visual.framing"]
    assert j.passed is None and "judge error" in j.message and rep.technical_gate_passed


def test_evaluation_never_imports_the_agent():
    root = Path(__file__).resolve().parents[2] / "evaluation"
    for py in root.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.startswith(("agent", "services")) for n in names), f"{py} imports {names}"


def test_frozen_frames_separates_render_faults_from_still_source_shots(tmp_path):
    from evaluation.evaluators.technical import frozen_check
    from evaluation.features import Segment

    still = tmp_path / "still.mp4"   # 1 s of motion, then 4 s of a locked-off frame
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=1,tpad=stop_mode=clone:stop_duration=4", *V, str(still))
    moving = tmp_path / "moving.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=5", *V, str(moving))

    def tl(path):
        return {"assets": [{"id": "a", "path": str(path)}],
                "video": [{"asset_id": "a", "src_in": 0.0, "src_out": 0.5},
                          {"asset_id": "a", "src_in": 1.5, "src_out": 4.5}]}

    freeze = [Segment(start=0.5, end=3.5)]           # output 0.5-3.5 = second clip = source 1.5-4.5
    ok = frozen_check(freeze, tl(still))
    assert ok.passed and ok.measurements == {"faults": 0, "still_source": 1}
    bad = frozen_check(freeze, tl(moving))           # the output froze although the source moves: a fault
    assert not bad.passed and bad.evidence[0].detail == "no motion"
    assert not frozen_check(freeze, None).passed      # no timeline: cannot explain it, so it stays a failure
    assert frozen_check([Segment(start=0, end=1.9)], tl(moving)).passed  # shorter than the minimum
