"""Model-assisted evaluators. Separate prompts and the `judge` model role; they see only the
instructions and the rendered output (transcript of its audio + sampled frames), never the plan."""

import base64
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config.models import get_chat_model
from evaluation.features import RenderFeatures
from evaluation.inputs import EvalInput
from evaluation.schemas import CheckResult, Evidence
from perception.style import contact_sheet


class Requirement(BaseModel):
    requirement: str = Field(description="one concrete requirement from the instructions or preferences")
    source: Literal["instructions", "preference"] = Field(default="instructions",
                                                          description="where the requirement comes from")
    met: bool
    timestamp: float | None = Field(default=None, description="seconds in the video where this is (not) met")
    evidence: str = Field(description="what in the transcript/frames shows this")


class InstructionVerdict(BaseModel):
    requirements: list[Requirement]
    explanation: str


class NarrativeIssue(BaseModel):
    start: float
    end: float
    problem: str


class NarrativeVerdict(BaseModel):
    opening: int = Field(ge=1, le=5, description="does the first ~3s hook the viewer")
    coherence: int = Field(ge=1, le=5, description="is the message clear and complete")
    sequencing: int = Field(ge=1, le=5, description="are ideas in a logical order (no non sequiturs)")
    ending: int = Field(ge=1, le=5, description="does it end on a relevant, complete thought")
    call_to_action: bool = Field(description="does it end with a call to action")
    issues: list[NarrativeIssue]
    explanation: str


class FrameIssue(BaseModel):
    timestamp: float
    problem: str = Field(description="e.g. on-screen text cut off by the crop, subject's face cut off, blurry")
    severity: str = Field(description="'major' if it clearly harms the video, else 'minor'")


class FramingVerdict(BaseModel):
    issues: list[FrameIssue]
    explanation: str


JUDGE_SYSTEM = ("You are a strict, independent reviewer of short vertical videos. You did not make the video. "
                "Judge only from the evidence given; cite timestamps in seconds. Do not be generous.")


def transcript_lines(f: RenderFeatures) -> str:
    lines, cur, t0 = [], [], None
    for w in f.words:
        t0 = w.start if t0 is None else t0
        cur.append(w.text)
        if w.text.endswith((".", "?", "!")) or len(cur) >= 14:
            lines.append(f"[{t0:5.1f}s] {' '.join(cur)}")
            cur, t0 = [], None
    if cur:
        lines.append(f"[{t0:5.1f}s] {' '.join(cur)}")
    return "\n".join(lines) or "(no speech)"


def _image(f: RenderFeatures) -> dict:
    b64 = base64.b64encode(contact_sheet(f.frames, cols=6, width=180)).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}


def instruction_adherence(f: RenderFeatures, x: EvalInput) -> list[CheckResult]:
    prefs = "\n".join(f"- {p}" for p in x.preferences) or "(none)"
    v: InstructionVerdict = get_chat_model("judge").with_structured_output(InstructionVerdict).invoke([
        SystemMessage(JUDGE_SYSTEM + " List every concrete requirement in the instructions (content, order, "
                                     "duration, captions, tone) and in the creator's standing preferences "
                                     "(mark those source='preference'), and decide if the video meets each."),
        HumanMessage(content=[
            {"type": "text", "text": f"INSTRUCTIONS:\n{x.instructions}\n\nCREATOR PREFERENCES:\n{prefs}\n\n"
                                     f"VIDEO: {f.duration:.1f}s, "
                                     f"{f.width}x{f.height}.\nTRANSCRIPT OF ITS AUDIO:\n{transcript_lines(f)}\n\n"
                                     "FRAMES (timestamps in yellow):"}, _image(f)])])
    out = []
    for cid, reqs in (("instruction.adherence", [r for r in v.requirements if r.source == "instructions"]),
                      ("instruction.preference_satisfaction", [r for r in v.requirements if r.source == "preference"])):
        if cid.endswith("satisfaction") and not x.preferences:
            continue
        met = [r for r in reqs if r.met]
        score = len(met) / len(reqs) if reqs else None
        out.append(CheckResult(
            id=cid, category="instruction", kind="model", passed=(len(met) == len(reqs)) if reqs else None,
            severity="major", score=round(score, 3) if score is not None else None,
            message=f"{len(met)}/{len(reqs)} {'preferences' if 'pref' in cid else 'requirements'} met",
            explanation=v.explanation,
            evidence=[Evidence(start=r.timestamp, end=r.timestamp, detail=f"{'MET' if r.met else 'UNMET'}: "
                               f"{r.requirement} — {r.evidence}") for r in reqs],
            measurements={"requirements": [r.model_dump() for r in reqs]}))
    return out


def narrative(f: RenderFeatures, x: EvalInput) -> CheckResult:
    if not f.words:
        return CheckResult(id="narrative.structure", category="narrative", kind="model", passed=None,
                           severity="major", message="no speech to judge")
    v: NarrativeVerdict = get_chat_model("judge").with_structured_output(NarrativeVerdict).invoke([
        SystemMessage(JUDGE_SYSTEM + " Assess the story of this edited video from its transcript. Edits can "
                                     "reorder footage; flag ideas out of order, missing setup, abrupt endings."),
        HumanMessage(f"INSTRUCTIONS:\n{x.instructions}\n\nTRANSCRIPT ({f.duration:.1f}s):\n{transcript_lines(f)}")])
    scores = {"opening": v.opening, "coherence": v.coherence, "sequencing": v.sequencing, "ending": v.ending}
    return CheckResult(id="narrative.structure", category="narrative", kind="model",
                       passed=min(scores.values()) >= 3, severity="major",
                       score=round(sum(scores.values()) / 20, 3),
                       message=", ".join(f"{k} {s}/5" for k, s in scores.items()) +
                               f"; CTA {'yes' if v.call_to_action else 'no'}",
                       explanation=v.explanation, measurements={**scores, "call_to_action": v.call_to_action},
                       evidence=[Evidence(start=i.start, end=i.end, detail=i.problem) for i in v.issues])


def framing(f: RenderFeatures, x: EvalInput) -> CheckResult:
    v: FramingVerdict = get_chat_model("judge").with_structured_output(FramingVerdict).invoke([
        SystemMessage(JUDGE_SYSTEM + " These are frames from a 9:16 video that was cropped from wider footage. "
                                     "Report framing problems: text or graphics cut off at the edges, faces or "
                                     "subjects cut off, unreadable frames. Report none if frames look fine."),
        HumanMessage(content=[{"type": "text", "text": "FRAMES (timestamps in yellow):"}, _image(f)])])
    major = [i for i in v.issues if i.severity.lower().startswith("maj")]
    return CheckResult(id="visual.framing", category="visual", kind="model", passed=not major, severity="major",
                       message=f"{len(major)} major / {len(v.issues) - len(major)} minor framing issue(s)",
                       explanation=v.explanation,
                       evidence=[Evidence(start=i.timestamp, end=i.timestamp, detail=f"{i.severity}: {i.problem}")
                                 for i in v.issues])


JUDGES = [instruction_adherence, narrative, framing]
