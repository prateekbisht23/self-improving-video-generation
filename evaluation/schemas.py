"""Evaluation report format (PRD FR-09).

Scores are NOT calibrated quality measurements. Each check says what it measured, how
(`kind`), and points to evidence (timestamps in the rendered video + raw measurements).
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# 1.1: + instruction.preference_satisfaction; 1.2: frozen_frames no longer flags still shots in the source;
# 1.3: ...judged inside the rendered 9:16 window
EVALUATOR_VERSION = "eval-1.3"

Category = Literal["technical", "instruction", "temporal", "captions", "style", "narrative", "visual"]
Kind = Literal["deterministic", "signal", "model"]
Severity = Literal["critical", "major", "minor", "info"]


class Evidence(BaseModel):
    start: float | None = None  # seconds in the rendered video
    end: float | None = None
    detail: str = ""

    @field_validator("start", "end")
    @classmethod
    def _round(cls, v):
        return None if v is None else round(v, 2)


class CheckResult(BaseModel):
    id: str                                  # e.g. "technical.duration_in_range"
    category: Category
    kind: Kind
    passed: bool | None                      # None = not applicable to this edit
    severity: Severity                       # how bad a failure is (critical = technical gate)
    score: float | None = None               # 0..1 where meaningful; uncalibrated
    message: str
    explanation: str | None = None           # required for model-assisted checks
    evidence: list[Evidence] = Field(default_factory=list)
    measurements: dict = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    evaluator_version: str = EVALUATOR_VERSION
    judge_model: str | None = None
    render_path: str
    timeline_hash: str | None = None
    checks: list[CheckResult]
    technical_gate_passed: bool              # every applicable critical check passed
    pass_rate: float                         # passed / applicable checks (uncalibrated aggregate)
    by_category: dict[str, dict]
    failed: list[str]
    seconds: float = 0.0

    @classmethod
    def aggregate(cls, checks: list[CheckResult], **kw) -> "EvaluationReport":
        checks = sorted(checks, key=lambda c: c.id)
        applicable = [c for c in checks if c.passed is not None]
        cats: dict[str, dict] = {}
        for c in applicable:
            d = cats.setdefault(c.category, {"passed": 0, "total": 0})
            d["total"] += 1
            d["passed"] += int(bool(c.passed))
        for d in cats.values():
            d["rate"] = round(d["passed"] / d["total"], 3)
        return cls(checks=checks, by_category=cats,
                   technical_gate_passed=all(c.passed for c in applicable if c.severity == "critical"),
                   pass_rate=round(sum(bool(c.passed) for c in applicable) / max(len(applicable), 1), 3),
                   failed=[c.id for c in applicable if not c.passed], **kw)
