"""Re-score stored experiment runs under a newer evaluator, without re-running the agent.

When an experiment exposes a flaw in a CHECK (round 3 retest: `technical.frozen_frames` flagged still
shots in the source as render faults), a human fixes the check and bumps EVALUATOR_VERSION. The renders
themselves didn't change, so re-running the agent would only add noise and spend quota. Instead, the
changed checks are recomputed on the stored renders of BOTH versions; everything else is copied.

Only deterministic checks can be re-scored this way: re-running a model judge is a new sample, not a
re-score. Each re-scored file records what it was derived from (`rescored_from`).
"""

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import text

from benchmarks.runner import summarize
from db.session import session_scope
from evaluation.evaluators.technical import frozen_check
from evaluation.features import parse_freeze
from evaluation.schemas import EVALUATOR_VERSION, CheckResult
from perception.ffmpeg import ffmpeg_analyze


def _frozen(path: str, duration: float, timeline: dict) -> CheckResult:
    log = ffmpeg_analyze(path, video_filter="freezedetect=n=-60dB:d=1.5")
    return frozen_check(parse_freeze(log, duration), timeline)


RESCORABLE: dict[str, Callable[[str, float, dict], CheckResult]] = {"technical.frozen_frames": _frozen}


def _render(render_id: str) -> tuple[str, float, dict]:
    with session_scope() as s:
        row = s.execute(text("select r.path, r.duration, tv.timeline from renders r "
                             "join timeline_versions tv on tv.id = r.timeline_version_id where r.id = :i"),
                        {"i": render_id}).one()
    return row.path, row.duration, row.timeline


def _aggregate(checks: dict[str, bool | None]) -> dict:
    """The EvaluationReport aggregation, over stored pass/fail values (None = not applicable)."""
    applicable = {k: v for k, v in checks.items() if v is not None}
    cats: dict[str, dict] = {}
    for k, v in applicable.items():
        c = cats.setdefault(k.split(".")[0], {"passed": 0, "total": 0})
        c["total"] += 1
        c["passed"] += int(bool(v))
    for c in cats.values():
        c["rate"] = round(c["passed"] / c["total"], 3)
    return {"pass_rate": round(sum(bool(v) for v in applicable.values()) / max(len(applicable), 1), 3),
            "failed": [k for k, v in applicable.items() if not v], "by_category": cats}


def rescore_result(r: dict, checks: list[str], measure=None) -> dict:
    """Recompute `checks` for one task result; pass rate, failed list and categories follow. The
    technical gate only depends on critical checks, and every re-scorable check is minor, so it can't
    change. Faithfulness first: re-aggregating the STORED values must reproduce the stored pass rate."""
    if not r.get("evaluation_id") or not r.get("render_id") or not r.get("checks"):
        return r
    if _aggregate(r["checks"])["pass_rate"] != r["pass_rate"]:
        raise ValueError(f"{r['task']}: stored checks don't reproduce pass_rate {r['pass_rate']}")
    path, duration, timeline = (measure or _render)(r["render_id"])
    r = {**r, "checks": dict(r["checks"])}
    for cid in checks:
        if r["checks"].get(cid) is not None:
            r["checks"][cid] = RESCORABLE[cid](path, duration, timeline).passed
    return r | _aggregate(r["checks"])


def rescore_run(src: Path, dst: Path, checks: list[str], measure=None) -> Path:
    unknown = [c for c in checks if c not in RESCORABLE]
    if unknown:
        raise ValueError(f"not re-scorable (only deterministic checks are): {unknown}")
    run = json.loads(Path(src).read_text())
    if run["evaluator_version"] == EVALUATOR_VERSION:
        raise ValueError(f"{src} is already scored with {EVALUATOR_VERSION}")
    results = [rescore_result(r, checks, measure) for r in run["results"]]
    out = {**run, "results": results, "evaluator_version": EVALUATOR_VERSION,
           "summary": {**(run.get("summary") or {}), **summarize(results)},
           "rescored_from": {"path": str(src), "evaluator_version": run["evaluator_version"], "checks": checks},
           "langsmith_experiment": None}
    Path(dst).write_text(json.dumps(out, indent=2, default=str))
    return Path(dst)
