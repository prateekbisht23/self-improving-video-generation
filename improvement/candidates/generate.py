"""Candidate generation (FR-12): diagnoses -> ONE new agent configuration.

The model fills a constrained proposal: values for existing policy knobs (validated by AgentPolicy's
own types and bounds) and short prompt addenda. It cannot add knobs, change code, touch the
evaluator or the benchmark. Then `build_candidate` merges the proposal into the baseline config
and the new config gets its own version string (hash), so every candidate is versioned and the
baseline row is never modified.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, create_model

from agent.config import AgentConfig, AgentPolicy


class NoChange(ValueError):
    """The proposal would reproduce the baseline configuration."""


def _changes_model() -> type[BaseModel]:
    """Every AgentPolicy knob as an optional field (None = keep the baseline value)."""
    fields: dict[str, Any] = {name: (f.annotation | None, Field(default=None, description=f.description))
                              for name, f in AgentPolicy.model_fields.items()}
    return create_model("PolicyChanges", **fields)


PolicyChanges = _changes_model()


class CandidateProposal(BaseModel):
    hypothesis: str = Field(description="if we change X, check Y improves because Z (one sentence)")
    target_checks: list[str] = Field(description="check ids this change should improve")
    policy_changes: PolicyChanges = Field(description="knob values to change; leave others null")
    planner_addendum: str = Field(default="", description="extra planner rules (<= 6 short bullet lines), or ''")
    repair_addendum: str = Field(default="", description="extra repair rules (<= 4 short bullet lines), or ''")
    expected_effect: str
    risks: str = Field(description="which other checks could get worse, and why")


PROPOSE_SYSTEM = """You improve an AI video-editing agent by changing its CONFIGURATION only. \
You get diagnosed failure patterns (ranked by impact) and the configuration options: policy knobs \
(implemented and tested behaviours you can switch on or tune) and free-text rules appended to the \
planner / repair prompts.

Propose ONE candidate that addresses the highest-impact root causes. Rules:
- Prefer a knob when a knob directly addresses a root cause; prompt rules are for what no knob covers.
- Keep prompt additions short, concrete and testable (numbers, not adjectives). Do not repeat existing rules.
- Change only what the diagnoses justify: every change must map to a cited root cause.
- Do not try to fix failures that the diagnosis attributes to the evaluator itself.
- target_checks must be check ids from the diagnoses.
- If previous experiments were rejected, address WHY (e.g. tasks that stopped rendering) instead of
  re-proposing the same change."""


def experiment_history(s, baseline_version: str) -> list[dict]:
    """Earlier experiments against the same baseline: what was tried and what the gates said.
    Development/validation outcomes only (never the holdout assessment)."""
    import json
    from pathlib import Path

    from sqlalchemy import select

    from db.models import Experiment

    out = []
    for e in s.scalars(select(Experiment).where(Experiment.baseline_version == baseline_version,
                                                Experiment.gates.isnot(None)).order_by(Experiment.created_at)):
        why_failed = {}
        if e.candidate_run and Path(e.candidate_run).exists():
            for r in json.loads(Path(e.candidate_run).read_text())["results"]:
                if r["task"] in (e.comparison or {}).get("newly_failed", []):
                    why_failed[r["task"]] = {"error": r.get("error"), "log_tail": (r.get("log") or [])[-8:]}
        g = e.gates
        out.append({"candidate": e.candidate_version, "status": e.status,
                    "policy_changes": e.change.get("policy_changes"),
                    "planner_addendum": e.change.get("planner_addendum"),
                    "targets": e.change.get("targets"), "critical": g.get("critical"),
                    "regressions": g.get("regressions"), "improvements": g.get("improvements"), "notes": g.get("notes"),
                    "check_deltas": {k: v["delta"] for k, v in (e.comparison or {}).get("checks", {}).items()
                                     if v["delta"] not in (None, 0)},
                    "tasks_that_stopped_rendering": why_failed})
    return out


def propose(diagnoses: list[dict], base: AgentConfig, model=None, history: list[dict] | None = None
            ) -> CandidateProposal:
    if model is None:
        from config.models import get_chat_model

        model = get_chat_model("improver")
    knobs = {n: {"current": getattr(base.policy, n), "type": str(f.annotation), "description": f.description}
             for n, f in AgentPolicy.model_fields.items()}
    return model.with_structured_output(CandidateProposal).invoke([
        SystemMessage(PROPOSE_SYSTEM),
        HumanMessage("POLICY KNOBS:\n" + json.dumps(knobs, indent=1)
                     + "\n\nCURRENT PROMPT ADDITIONS:\n" + json.dumps({"planner": base.planner_addendum,
                                                                       "repair": base.repair_addendum})
                     + "\n\nDIAGNOSED FAILURE PATTERNS (highest impact first):\n"
                     + json.dumps(diagnoses, indent=1, default=str)[:30000]
                     + "\n\nPREVIOUS EXPERIMENTS AGAINST THIS BASELINE (learn from them; do not repeat a "
                       "rejected configuration):\n" + (json.dumps(history, indent=1, default=str)[:12000]
                                                         if history else "(none)")),
    ])


def build_candidate(base: AgentConfig, p: CandidateProposal, allowed_targets: set[str] | None = None,
                    release: str | None = None) -> tuple[AgentConfig, dict]:
    """Merge + validate. Returns (config, change record). Raises NoChange / ValidationError."""
    changes = {k: v for k, v in p.policy_changes.model_dump().items() if v is not None}
    policy = AgentPolicy.model_validate(base.policy.model_dump() | changes)  # re-validates bounds

    def join(a: str, b: str) -> str:
        return "\n".join(x for x in (a.strip(), b.strip()) if x)

    cfg = AgentConfig(release=release or base.release, policy=policy,
                      planner_addendum=join(base.planner_addendum, p.planner_addendum)[:1500],
                      repair_addendum=join(base.repair_addendum, p.repair_addendum)[:1000])
    if cfg.config_hash() == base.config_hash():
        raise NoChange("the proposal does not change the configuration")
    targets = [t for t in p.target_checks if allowed_targets is None or t in allowed_targets]
    if not targets:
        raise ValueError(f"proposal targets {p.target_checks}, none of which were diagnosed")
    real_changes = {k: v for k, v in changes.items() if getattr(base.policy, k) != v}
    change = {"hypothesis": p.hypothesis, "targets": targets, "policy_changes": real_changes,
              "planner_addendum": p.planner_addendum.strip(), "repair_addendum": p.repair_addendum.strip(),
              "expected_effect": p.expected_effect, "risks": p.risks}
    return cfg, change
