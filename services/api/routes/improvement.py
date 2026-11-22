"""Self-improvement (FR-11/12): versions, failure clusters, experiments, human approval.

Starting a loop runs benchmarks for a long time, so it stays a CLI/worker action
(`python -m improvement.cli start`); the API reads results and records the human decision.
"""

import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AgentVersion, Experiment, FailureCluster, Promotion
from db.session import get_db
from improvement import registry

router = APIRouter(prefix="/improvement", tags=["improvement"])


@router.get("/versions")
def versions(db: Session = Depends(get_db)):
    registry.ensure_seed(db)
    db.commit()
    return [{"version": v.version, "status": v.status, "parent": v.parent_version, "origin": v.origin,
             "rationale": v.rationale, "config": v.config, "created_at": v.created_at}
            for v in db.scalars(select(AgentVersion).order_by(AgentVersion.created_at))]


@router.get("/promotions")
def promotions(db: Session = Depends(get_db)):
    return [{"from": p.from_version, "to": p.to_version, "approved_by": p.approved_by, "note": p.note,
             "experiment_id": p.experiment_id, "at": p.created_at}
            for p in db.scalars(select(Promotion).order_by(Promotion.created_at))]


@router.get("/clusters")
def clusters(analysis_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    q = select(FailureCluster)
    if analysis_id is None:
        latest = db.scalar(select(FailureCluster).order_by(FailureCluster.created_at.desc()))
        if latest is None:
            return []
        analysis_id = latest.analysis_id
    rows = db.scalars(q.where(FailureCluster.analysis_id == analysis_id))
    return sorted([{"id": c.id, "analysis_id": c.analysis_id, "agent_version": c.agent_version, "method": c.method,
                    "label": c.label, "check_id": c.check_id, "severity": c.severity, "size": c.size,
                    "rate": c.rate, "tasks": c.tasks, "examples": c.examples, "diagnosis": c.diagnosis}
                   for c in rows], key=lambda c: -c["rate"])


def _exp(e: Experiment, full: bool = False) -> dict:
    out = {"id": e.id, "name": e.name, "status": e.status, "baseline_version": e.baseline_version,
           "candidate_version": e.candidate_version, "change": e.change, "thread_id": e.thread_id,
           "eligible": (e.gates or {}).get("eligible"), "created_at": e.created_at,
           "decision_by": e.decision_by, "decided_at": e.decided_at}
    if full:
        out |= {"dataset_version": e.dataset_version, "evaluator_version": e.evaluator_version, "models": e.models,
                "splits": e.splits, "n_runs": e.n_runs, "comparison": e.comparison, "gates": e.gates,
                "holdout": e.holdout, "decision_note": e.decision_note,
                "report": Path(e.report_path).read_text() if e.report_path and Path(e.report_path).exists() else None}
    return out


@router.get("/experiments")
def experiments(db: Session = Depends(get_db)):
    return [_exp(e) for e in db.scalars(select(Experiment).order_by(Experiment.created_at.desc()))]


@router.get("/experiments/{experiment_id}")
def experiment(experiment_id: uuid.UUID, db: Session = Depends(get_db)):
    e = db.get(Experiment, experiment_id)
    if e is None:
        raise HTTPException(404, "experiment not found")
    return _exp(e, full=True)


class DecisionIn(BaseModel):
    decision: Literal["approve", "decline"]
    by: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=2000)


@router.post("/experiments/{experiment_id}/decision")
def decide(experiment_id: uuid.UUID, body: DecisionIn, db: Session = Depends(get_db)):
    """Resume the improvement graph's approval interrupt with a human decision."""
    e = db.get(Experiment, experiment_id)
    if e is None:
        raise HTTPException(404, "experiment not found")
    if e.status != "awaiting_approval" or not e.thread_id:
        raise HTTPException(409, f"experiment is '{e.status}', not awaiting approval")
    from improvement import graph as ig

    return ig.decide(e.thread_id, body.decision, body.by, body.note)
