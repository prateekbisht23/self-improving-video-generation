"""Improvement graph (PRD §7.2 D): failures -> clusters -> diagnosis -> candidate -> experiment
-> regression gates -> holdout assessment -> human approval -> promote or reject.

START → collect → diagnose → propose → experiment → gates ─(eligible)→ final_assessment → approval ⏸ → decide → END
                                                          └(not)──────→ reject ─────────────────────→ END

Durable execution: compiled with the Postgres checkpointer, every finished node is saved under
thread_id = "improve-<uuid>". Long nodes (benchmark runs) write resumable results files, so if a
run stops (e.g. the provider's daily quota), `resume(thread)` re-enters at the failed node and the
benchmark continues where it stopped. `approval` is an interrupt(): the graph waits, possibly for
days, until a human answers with `decide(thread, "approve" | "decline", by=...)`.

Data boundary: collect/diagnose/propose only ever see development sessions. Candidates are
selected on development + validation. Holdout is touched once, by `final_assessment`
(improvement/experiments/holdout.py), after the gates.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from agent.config import AgentConfig
from benchmarks.schemas.task import dataset_version, load_tasks
from config.models import model_id
from db.models import AgentVersion, Experiment, FailureCluster
from db.session import session_scope
from evaluation.schemas import EVALUATOR_VERSION
from improvement import registry
from improvement.candidates.generate import build_candidate, propose
from improvement.clustering.cluster import cluster
from improvement.collection import collect
from improvement.diagnosis.diagnose import diagnose, gather_evidence
from improvement.experiments import holdout as holdout_mod
from improvement.experiments.compare import compare
from improvement.experiments.run import EXPERIMENTS, run_pair
from improvement.promotion.gates import advisory_checks, evaluate_gates
from improvement.promotion.report import write_report

SELECTION_SPLITS = ["development", "validation"]


@dataclass
class ImproveDeps:
    """Injectable side effects (tests swap in fakes)."""
    model: Any = None                      # improver chat model (None = config/models.py)
    embed: Any = "default"                 # texts -> vectors; None disables semantic clustering
    run_pair: Any = run_pair               # (baseline, candidate, tasks, splits, bpath, cpath) -> paths
    assess: Any = holdout_mod.assess
    advisory: dict = field(default_factory=advisory_checks)


class ImproveState(TypedDict, total=False):
    baseline_version: str
    analysis_id: str
    cluster_ids: list[str]
    diagnoses: list[dict]
    candidate_version: str
    experiment_id: str
    baseline_run: str
    candidate_run: str
    eligible: bool
    report: str
    decision: dict
    status: str
    max_clusters: int
    log: list[str]


def _deps(config) -> ImproveDeps:
    return (config.get("configurable") or {}).get("deps") or ImproveDeps()


def _embedder(deps: ImproveDeps):
    if deps.embed != "default":
        return deps.embed
    from config.models import get_embeddings
    from config.settings import get_settings

    if not get_settings().pipeline_embeddings:
        return None
    emb = get_embeddings()
    return emb.embed_documents


def _bump(release: str) -> str:
    major, _, minor = release.partition(".")
    return f"{major}.{int(minor or 0) + 1}"


# ------------------------------------------------------------------ nodes
def collect_node(state: ImproveState, config) -> ImproveState:
    deps = _deps(config)
    analysis = uuid.uuid4()
    with session_scope() as s:
        base = registry.active(s)
        fs = collect(s, base.version)
        if not fs.records:
            raise RuntimeError(f"no development-split failures recorded for {base.version}; run the benchmark first")
        clusters = cluster(fs, _embedder(deps))
        rows = []
        for c in clusters:
            row = FailureCluster(analysis_id=analysis, agent_version=base.version, method=c.method, key=c.key,
                                 label=c.label, check_id=c.check_id, category=c.category, severity=c.severity,
                                 size=len(c.records), n_sessions=c.n_sessions, rate=c.rate, tasks=c.tasks,
                                 issue_ids=[r.issue_id for r in c.records if r.issue_id is not None],
                                 examples=c.examples())
            s.add(row)
            rows.append((row, c))
        s.flush()
        # diagnose the highest-impact patterns, skipping checks too noisy to optimise against
        top = [row for row, c in rows if c.check_id not in deps.advisory][: state.get("max_clusters", 3)]
        ids = [str(r.id) for r in top]
    return {"baseline_version": base.version, "analysis_id": str(analysis), "cluster_ids": ids, "log": [
        f"collected {len(fs.records)} failures from {fs.renders} renders / {fs.sessions} sessions "
        f"of {base.version}; {len(clusters)} clusters; diagnosing {len(ids)}"]}


def diagnose_node(state: ImproveState, config) -> ImproveState:
    deps = _deps(config)
    out = []
    with session_scope() as s:
        base = registry.get(s, state["baseline_version"])
        for cid in state["cluster_ids"]:
            row = s.get(FailureCluster, uuid.UUID(cid))
            from improvement.clustering.cluster import Cluster
            from improvement.collection import FailureRecord

            c = Cluster(row.key, row.method, row.check_id, row.category, row.severity, row.label, rate=row.rate)
            c.records = [_record(s, i, row) for i in row.issue_ids] or [
                FailureRecord(None, ex["session_id"], None, ex["task"], row.check_id, row.category, "deterministic",
                              row.severity, ex["message"]) for ex in row.examples]
            evidence = gather_evidence(s, c)
            d = diagnose(evidence, base, deps.model)
            row.diagnosis = {"probes": evidence["probes"], **d.model_dump()}
            out.append({"check": row.check_id, "label": row.label, "share_of_renders_failing": row.rate,
                        "severity": row.severity, "tasks": row.tasks, "probes": evidence["probes"],
                        **d.model_dump()})
    return {"diagnoses": out, "log": state["log"] + [f"diagnosed {len(out)} clusters"]}


def _record(s, issue_id: int, row: FailureCluster):
    from db.models import EditingSession, Evaluation, EvaluationIssue
    from improvement.collection import FailureRecord

    i = s.get(EvaluationIssue, issue_id)
    ev = s.get(Evaluation, i.evaluation_id)
    e = s.get(EditingSession, ev.session_id)
    return FailureRecord(i.id, str(e.id), str(ev.id), (e.constraints or {}).get("benchmark_task"), i.check_id,
                         i.category, i.kind, i.severity, i.message, i.explanation or "", list(i.evidence or []),
                         e.trace_id)


def propose_node(state: ImproveState, config) -> ImproveState:
    deps = _deps(config)
    with session_scope() as s:
        base = registry.get(s, state["baseline_version"])
        from improvement.candidates.generate import experiment_history

        p = propose(state["diagnoses"], base, deps.model, experiment_history(s, base.version))
        cfg, change = build_candidate(base, p, {d["check"] for d in state["diagnoses"]}, release=_bump(base.release))
        registry.register(s, cfg, parent=base.version, origin="improver", rationale=p.hypothesis)
        exp = Experiment(name=f"{base.version} vs {cfg.version}", analysis_id=uuid.UUID(state["analysis_id"]),
                         baseline_version=base.version, candidate_version=cfg.version,
                         dataset_version=dataset_version(), evaluator_version=EVALUATOR_VERSION,
                         models={r: model_id(r) for r in ("planner", "judge", "improver")},
                         splits=SELECTION_SPLITS, change=change, n_runs=1, status="created",
                         thread_id=config["configurable"].get("thread_id"))
        s.add(exp)
        s.flush()
        eid = str(exp.id)
    return {"candidate_version": cfg.version, "experiment_id": eid,
            "log": state["log"] + [f"candidate {cfg.version}: {change['hypothesis'][:200]}"]}


def experiment_node(state: ImproveState, config) -> ImproveState:
    deps = _deps(config)
    tasks = load_tasks(SELECTION_SPLITS)
    tag = state["experiment_id"][:8]
    with session_scope() as s:
        s.get(Experiment, uuid.UUID(state["experiment_id"])).status = "running"
    bpath, cpath = deps.run_pair(state["baseline_version"], state["candidate_version"], tasks, SELECTION_SPLITS,
                                 EXPERIMENTS / f"{tag}-baseline-dev-val.json",
                                 EXPERIMENTS / f"{tag}-candidate-dev-val.json")
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        exp.baseline_run, exp.candidate_run = str(bpath), str(cpath)
    return {"baseline_run": str(bpath), "candidate_run": str(cpath),
            "log": state["log"] + [f"runs: baseline {bpath.name}, candidate {cpath.name}"]}


def gates_node(state: ImproveState, config) -> ImproveState:
    import json
    from pathlib import Path

    deps = _deps(config)
    base = json.loads(Path(state["baseline_run"]).read_text())
    cand = json.loads(Path(state["candidate_run"]).read_text())
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        exp.comparison = compare(base, cand)
        exp.gates = evaluate_gates(exp.comparison, exp.change["targets"], deps.advisory)
        eligible = exp.gates["eligible"]
    return {"eligible": eligible, "log": state["log"] + [f"gates: eligible={eligible}"]}


def holdout_node(state: ImproveState, config) -> ImproveState:
    deps = _deps(config)
    h = deps.assess(state["experiment_id"], state["baseline_version"], state["candidate_version"])
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        exp.holdout = h
        exp.status = "awaiting_approval"
        report = _write(s, exp)
    return {"report": str(report), "status": "awaiting_approval",
            "log": state["log"] + [f"holdout paired mean diff {h['paired']['mean_diff']:+.3f}"]}


def approval_node(state: ImproveState, config) -> ImproveState:
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        summary = {"experiment_id": str(exp.id), "report": state["report"], "candidate": exp.candidate_version,
                   "baseline": exp.baseline_version, "improvements": exp.gates["improvements"],
                   "holdout_paired": (exp.holdout or {}).get("paired"),
                   "question": f"Promote {exp.candidate_version} to replace {exp.baseline_version}?"}
    answer = interrupt(summary)  # waits for a human: decide(thread, "approve" | "decline", by=...)
    return {"decision": answer}


def decide_node(state: ImproveState) -> ImproveState:
    d = state.get("decision") or {}
    approve = d.get("decision") == "approve"
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        exp.decision_by, exp.decision_note = d.get("by") or "unknown", d.get("note")
        exp.decided_at = datetime.now(UTC)
        if approve:
            exp.status = "approved"
            registry.promote(s, exp, exp.decision_by, d.get("note") or "")
        else:
            exp.status = "declined"
            _set_candidate(s, exp.candidate_version, "rejected")
        status = exp.status
        report = _write(s, exp)
    return {"status": status, "report": str(report), "log": state["log"] + [f"decision: {status}"]}


def reject_node(state: ImproveState) -> ImproveState:
    with session_scope() as s:
        exp = s.get(Experiment, uuid.UUID(state["experiment_id"]))
        exp.status = "rejected"
        _set_candidate(s, exp.candidate_version, "rejected")
        report = _write(s, exp)
    return {"status": "rejected", "report": str(report), "log": state["log"] + ["rejected by regression gates"]}


def _set_candidate(s, version: str, status: str) -> None:
    row = s.scalar(select(AgentVersion).where(AgentVersion.version == version))
    if row and row.status == "candidate":
        row.status = status


def _write(s, exp: Experiment):
    clusters = []
    if exp.analysis_id:
        clusters = [c for c in s.scalars(select(FailureCluster).where(FailureCluster.analysis_id == exp.analysis_id))
                    if c.diagnosis]
    path = write_report(exp, clusters, EXPERIMENTS)
    exp.report_path = str(path)
    return path


# ------------------------------------------------------------------ graph
def build_graph(checkpointer=None):
    g = StateGraph(ImproveState)
    for name, fn in [("collect", collect_node), ("diagnose", diagnose_node), ("propose", propose_node),
                     ("experiment", experiment_node), ("gates", gates_node), ("final_assessment", holdout_node),
                     ("approval", approval_node), ("decide", decide_node), ("reject", reject_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "collect")
    g.add_edge("collect", "diagnose")
    g.add_edge("diagnose", "propose")
    g.add_edge("propose", "experiment")
    g.add_edge("experiment", "gates")
    g.add_conditional_edges("gates", lambda st: "final_assessment" if st["eligible"] else "reject",
                            ["final_assessment", "reject"])
    g.add_edge("final_assessment", "approval")
    g.add_edge("approval", "decide")
    g.add_edge("decide", END)
    g.add_edge("reject", END)
    return g.compile(checkpointer=checkpointer)


def graph():
    from agent.graphs.memory_graph import _checkpointer
    from config.settings import get_settings

    return build_graph(_checkpointer(get_settings().database_url))


def _cfg(thread: str, deps: ImproveDeps | None = None, name: str = "improvement") -> dict:
    c: dict = {"configurable": {"thread_id": thread}, "run_name": name, "tags": ["improvement"],
               "recursion_limit": 50}
    if deps:
        c["configurable"]["deps"] = deps
    return c


def _result(out: dict, thread: str) -> dict:
    pending = out.get("__interrupt__")
    if pending:
        return {"status": "awaiting_approval", "thread_id": thread, **pending[0].value}
    return {"thread_id": thread, **{k: out.get(k) for k in ("status", "experiment_id", "candidate_version",
                                                             "report", "log")}}


def start(max_clusters: int = 3, deps: ImproveDeps | None = None, g=None) -> dict:
    thread = f"improve-{uuid.uuid4()}"
    out = (g or graph()).invoke({"max_clusters": max_clusters, "log": []}, _cfg(thread, deps))
    return _result(out, thread)


def resume(thread: str, deps: ImproveDeps | None = None, g=None) -> dict:
    """Continue a run that stopped with an error (e.g. quota) from its last finished node."""
    out = (g or graph()).invoke(None, _cfg(thread, deps, "improvement_resume"))
    return _result(out, thread)


def decide(thread: str, decision: str, by: str, note: str = "", deps: ImproveDeps | None = None, g=None) -> dict:
    if decision not in ("approve", "decline"):
        raise ValueError("decision must be 'approve' or 'decline'")
    out = (g or graph()).invoke(Command(resume={"decision": decision, "by": by, "note": note}),
                                _cfg(thread, deps, "improvement_decision"))
    return _result(out, thread)


def candidate_config(version: str) -> AgentConfig:
    with session_scope() as s:
        return registry.get(s, version)
