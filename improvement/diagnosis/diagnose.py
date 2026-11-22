"""Root-cause diagnosis of a failure cluster (FR-11).

Two layers, deliberately separated:
1. `gather_evidence` (deterministic): for sample sessions in the cluster, pull what the agent did
   (plan, executed actions, repairs, final clips) and compute probes that test common hypotheses
   (e.g. "were the bad cut points chosen by the planner or introduced by repairs?").
2. `diagnose` (model): reads ONLY that evidence and returns root causes that must cite it.

The model never sees holdout data (collection only reads development sessions) and never proposes
code: it explains, and candidate generation later maps explanations to configuration changes.
"""

import json
import re
import uuid
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent.config import AgentConfig
from db.models import EditingSession, StyleProfile
from improvement.clustering.cluster import Cluster

CLIP_EDGE = re.compile(r"clip (\d+) (?:(in|out)-point|starts|ends)")


class RootCause(BaseModel):
    cause: str = Field(description="one specific, testable explanation of why the agent fails this check")
    evidence: list[str] = Field(description="facts from the evidence that support it (cite task ids / numbers)")
    confidence: Literal["low", "medium", "high"]


class Diagnosis(BaseModel):
    summary: str = Field(description="one sentence: what goes wrong")
    root_causes: list[RootCause] = Field(description="most likely first; 1-3 items")
    fix_directions: list[str] = Field(description="what kind of change would address each cause")


DIAGNOSE_SYSTEM = """You diagnose recurring failures of an AI video-editing agent. You get one \
failure pattern (an evaluation check that keeps failing), sample failures, what the agent did in \
those sessions, and measured probes. Explain WHY the agent fails. Rules:
- Every root cause must be supported by the given evidence; cite task ids and numbers.
- Prefer causes that the probes confirm over plausible guesses; say 'low' confidence otherwise.
- If the evidence suggests the CHECK itself is wrong (e.g. it fires on legitimately dark footage), say so.
- Do not invent data. Do not write code."""


def _session_digest(e: EditingSession) -> dict:
    plan = e.plan or {}
    final = e.versions[-1].timeline if e.versions else {}
    acts = [{"step": a.step, "op": a.name, "source": a.source, "ok": a.ok,
             **({"error": (a.error or "")[:160]} if not a.ok else {})} for a in e.actions]
    return {
        "task": (e.constraints or {}).get("benchmark_task"), "instructions": e.instructions[:400],
        "target_seconds": [(e.constraints or {}).get("min_duration"), (e.constraints or {}).get("max_duration")],
        "plan": {"clips": [{"scene": c.get("scene_id"), "in": c.get("src_in"), "out": c.get("src_out")}
                           for c in plan.get("clips", [])],
                 "estimated_duration": plan.get("estimated_duration"), "captions": plan.get("captions"),
                 "title": plan.get("title"), "transition": plan.get("transition")},
        "final_clips": [{"scene": c.get("scene_id"), "in": c.get("src_in"), "out": c.get("src_out")}
                        for c in final.get("video", [])],
        "actions": acts[:30], "repairs": sum(a.source == "repair" for a in e.actions),
        "trace_id": e.trace_id}


def _edge_origin(cluster: Cluster, sessions: dict[str, EditingSession]) -> dict:
    """For cut-related failures: was each bad edge chosen by the planner or changed by repair/fixup?"""
    planned = changed = 0
    for r in cluster.records:
        e = sessions.get(r.session_id)
        if e is None or not e.versions:
            continue
        final = e.versions[-1].timeline.get("video", [])
        plan = (e.plan or {}).get("clips", [])
        for ev in r.evidence:
            m = CLIP_EDGE.search(ev.get("detail", ""))
            if not m or int(m.group(1)) >= len(final):
                continue
            c = final[int(m.group(1))]
            edge = "src_in" if (m.group(2) == "in" or "starts" in m.group(0)) else "src_out"
            same = any(p.get("scene_id") == c.get("scene_id") and p.get(edge) is not None
                       and abs(p[edge] - c[edge]) < 0.02 for p in plan)
            planned += same
            changed += not same
    total = planned + changed
    return {"bad_edges": total, "chosen_by_planner": planned, "changed_by_repair_or_fixup": changed,
            "share_from_planner": round(planned / total, 2) if total else None}


def _duration_probe(sessions: list[EditingSession]) -> dict:
    """Planner arithmetic: estimated vs actual planned duration vs the target window."""
    rows = []
    for e in sessions:
        p = e.plan or {}
        clips = p.get("clips", [])
        actual = round(sum((c.get("src_out") or 0) - (c.get("src_in") or 0) for c in clips), 2)
        c = e.constraints or {}
        rows.append({"task": c.get("benchmark_task"), "estimated": p.get("estimated_duration"), "planned": actual,
                     "target": [c.get("min_duration"), c.get("max_duration")]})
    return {"plans": rows}


def _caption_probe(s, sessions: list[EditingSession]) -> dict:
    rows = []
    for e in sessions:
        obs = {}
        if e.reference_asset_id:
            sp = s.scalar(select(StyleProfile).where(StyleProfile.asset_id == e.reference_asset_id))
            obs = ((sp.profile or {}).get("observed") or {}) if sp else {}
        rows.append({"task": (e.constraints or {}).get("benchmark_task"),
                     "reference_has_captions": obs.get("captions_present"),
                     "plan_added_captions": (e.plan or {}).get("captions"),
                     "instructions_mention_captions": "caption" in e.instructions.lower()})
    return {"captions": rows}


def gather_evidence(s, cluster: Cluster, max_sessions: int = 3) -> dict:
    ids = list(dict.fromkeys(r.session_id for r in cluster.records))
    sessions = {sid: s.get(EditingSession, uuid.UUID(sid)) for sid in ids}
    sample = [sessions[sid] for sid in ids[:max_sessions]]
    probes: dict = {"repairs_per_affected_session": round(
        sum(sum(a.source == "repair" for a in e.actions) for e in sessions.values()) / max(len(sessions), 1), 2)}
    if cluster.check_id in ("temporal.dialogue_continuity", "temporal.cut_through_word"):
        probes["edge_origin"] = _edge_origin(cluster, sessions)
        from improvement.diagnosis.replay import snap_replay

        probes["counterfactual_snap_replay"] = snap_replay(s, ids)
    if cluster.check_id in ("technical.duration_in_range", "agent.no_render", "temporal.shot_durations"):
        probes |= _duration_probe(list(sessions.values()))
    if cluster.check_id.startswith("style.caption") or cluster.check_id.startswith("captions."):
        probes |= _caption_probe(s, list(sessions.values()))
    return {"check": cluster.check_id, "label": cluster.label, "severity": cluster.severity,
            "share_of_renders_failing": cluster.rate, "failures": len(cluster.records), "tasks": cluster.tasks,
            "examples": cluster.examples(), "probes": probes, "sessions": [_session_digest(e) for e in sample]}


def diagnose(evidence: dict, config: AgentConfig, model=None) -> Diagnosis:
    if model is None:
        from config.models import get_chat_model

        model = get_chat_model("improver")
    return model.with_structured_output(Diagnosis).invoke([
        SystemMessage(DIAGNOSE_SYSTEM),
        HumanMessage("CURRENT AGENT CONFIGURATION:\n" + json.dumps(config.describe(), indent=1)
                     + "\n\nFAILURE PATTERN AND EVIDENCE:\n" + json.dumps(evidence, indent=1, default=str)[:30000]),
    ])
