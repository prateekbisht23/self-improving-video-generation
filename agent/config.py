"""Versioned agent configuration (PRD FR-12, NFR-09).

An agent version = base prompts + prompt addenda + policy knobs. The improvement loop may only
change THIS object (it never writes code): it appends text to the prompts and turns knobs that
humans implemented and tested. Each distinct config hashes to a distinct version string.

The hash covers the base prompts, the addenda and only the policy fields that DIFFER from their
defaults. So adding a new knob (default = old behaviour) keeps every existing version string valid:
the default config is still `editing-agent-0.2+d43dbd596cae`, exactly the v0.2 baseline.
"""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from agent.prompts.editing import PLANNER_HUMAN, PLANNER_SYSTEM, REPAIR_HUMAN, REPAIR_SYSTEM

AGENT_NAME = "editing-agent"


class AgentPolicy(BaseModel):
    """Behaviour knobs. Defaults reproduce agent v0.2 exactly."""

    max_steps: int = Field(default=40, ge=10, le=80, description="hard cap on executed actions")
    max_repairs: int = Field(default=4, ge=0, le=8, description="LLM repair rounds before giving up / fixup")
    snap_cuts: Literal["off", "word", "sentence"] = Field(
        default="off", description="move clip in/out points to word gaps ('word') or sentence boundaries "
                                   "('sentence') using the source word timings, before the action is applied")
    snap_max_shift: float = Field(
        default=2.0, ge=0.5, le=8.0, description="sentence snapping: max seconds an edge may move to reach a "
                                                 "sentence boundary before falling back to the nearest word gap")
    fixup_extend: bool = Field(
        default=False, description="when the edit is too SHORT after repairs, the deterministic fixup extends "
                                   "clips to the next sentence end / adds unused speech scenes (v0.2 only trims)")
    scene_reuse_check: bool = Field(
        default=True, description="check() flags edits where most clips come from the same scene; wrong for "
                                  "sources made of a few long scenes (e.g. a two-shot interview)")
    captions_follow_reference: bool = Field(
        default=False, description="with a reference video that has NO captions, skip captions unless the "
                                   "instructions or creator preferences ask for them")


class AgentConfig(BaseModel):
    release: str = "0.2"
    planner_addendum: str = Field(default="", max_length=1500,
                                  description="extra rules appended to the planner system prompt")
    repair_addendum: str = Field(default="", max_length=1000,
                                 description="extra rules appended to the repair system prompt")
    policy: AgentPolicy = Field(default_factory=AgentPolicy)

    def planner_system(self) -> str:
        return PLANNER_SYSTEM + (f"\n\nAdditional rules:\n{self.planner_addendum.strip()}"
                                 if self.planner_addendum.strip() else "")

    def repair_system(self) -> str:
        return REPAIR_SYSTEM + (f"\n\nAdditional rules:\n{self.repair_addendum.strip()}"
                                if self.repair_addendum.strip() else "")

    def policy_delta(self) -> dict:
        return self.policy.model_dump(exclude_defaults=True)

    def config_hash(self) -> str:
        text = PLANNER_SYSTEM + PLANNER_HUMAN + REPAIR_SYSTEM + REPAIR_HUMAN
        if self.planner_addendum.strip() or self.repair_addendum.strip() or self.policy_delta():
            text += json.dumps({"planner": self.planner_addendum.strip(), "repair": self.repair_addendum.strip(),
                                "policy": self.policy_delta()}, sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:12]

    @property
    def version(self) -> str:
        return f"{AGENT_NAME}-{self.release}+{self.config_hash()}"

    def describe(self) -> dict:
        return {"version": self.version, "policy_changes": self.policy_delta(),
                "planner_addendum": self.planner_addendum, "repair_addendum": self.repair_addendum}


DEFAULT_CONFIG = AgentConfig()
