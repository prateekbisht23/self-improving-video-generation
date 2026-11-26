"""The improvement graph end to end on the test database, with scripted models and scripted
benchmark runs: collect -> cluster -> diagnose -> propose -> experiment -> gates -> holdout ->
human approval (interrupt / resume) -> promotion; and the rejection path."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from agent.config import DEFAULT_CONFIG
from db.models import (
    AgentVersion,
    EditingSession,
    Evaluation,
    EvaluationIssue,
    Experiment,
    FailureCluster,
    Project,
    Promotion,
    Render,
    RenderStatus,
    SessionStatus,
    TimelineVersion,
    User,
)
from db.session import session_scope
from improvement import graph as ig
from improvement import registry
from improvement.candidates.generate import CandidateProposal, PolicyChanges
from improvement.diagnosis.diagnose import Diagnosis, RootCause

ASSET = "00000000-0000-0000-0000-0000000000a1"
DEV = ["if-01", "if-02", "pc-01", "ps-01"]


def seed_failures():
    """Four development sessions of the baseline, each with a cut_through_word failure."""
    with session_scope() as s:
        u = User(handle="owner")
        s.add(u)
        s.flush()
        p = Project(owner_id=u.id, title="Benchmark v1")
        s.add(p)
        s.flush()
        for t in DEV:
            e = EditingSession(project_id=p.id, instructions="x", source_asset_ids=[], status=SessionStatus.rendered,
                               agent_version=DEFAULT_CONFIG.version, constraints={"benchmark_task": t},
                               plan={"clips": [{"scene_id": "S1", "src_in": 1.0, "src_out": 4.0}]})
            s.add(e)
            s.flush()
            v = TimelineVersion(session_id=e.id, version=1, content_hash="h", schema_version="1.0", created_by="agent",
                                timeline={"video": [{"scene_id": "S1", "asset_id": ASSET, "src_in": 1.0,
                                                     "src_out": 4.0}]})
            s.add(v)
            s.flush()
            r = Render(timeline_version_id=v.id, status=RenderStatus.done)
            s.add(r)
            s.flush()
            ev = Evaluation(render_id=r.id, timeline_version_id=v.id, session_id=e.id, evaluator_version="eval-1.1",
                            technical_gate_passed=True, pass_rate=0.8, by_category={},
                            report={"checks": [{"id": "temporal.cut_through_word", "passed": False}]})
            s.add(ev)
            s.flush()
            s.add(EvaluationIssue(evaluation_id=ev.id, check_id="temporal.cut_through_word", category="temporal",
                                  kind="deterministic", severity="major", message="1 cut(s) through a spoken word",
                                  evidence=[{"detail": "clip 0 out-point cuts 'scene'"}]))


class Scripted:
    """Answers Diagnosis / CandidateProposal structured-output calls."""

    def __init__(self):
        self.calls = []

    def with_structured_output(self, schema):
        model = self

        class _S:
            def invoke(self, messages):
                model.calls.append((schema.__name__, messages))
                if schema is Diagnosis:
                    return Diagnosis(summary="planner picks mid-word times",
                                     root_causes=[RootCause(cause="plan times ignore word timings",
                                                            evidence=["edge_origin 4/4 from planner"],
                                                            confidence="high")],
                                     fix_directions=["snap edges to word gaps"])
                return CandidateProposal(hypothesis="snapping fixes cuts", target_checks=["temporal.cut_through_word"],
                                         policy_changes=PolicyChanges(snap_cuts="word"), expected_effect="+",
                                         risks="duration drift")
        return _S()


def fake_run(improve_cut: bool):
    def run(version, tasks, splits, path):
        cand = version != DEFAULT_CONFIG.version
        rows = [{"task": t.id, "split": t.split, "status": "rendered", "evaluation_id": f"e{t.id}", "gate": True,
                 "pass_rate": 0.8 + (0.05 if cand and improve_cut else 0),
                 "checks": {"temporal.cut_through_word": bool(cand and improve_cut),
                            "technical.loudness": not (cand and not improve_cut)}} for t in tasks]
        done = {"agent_version": version, "dataset_version": "d", "evaluator_version": "e", "results": rows,
                "summary": {"completion_rate": 1.0, "technical_valid_rate": 1.0,
                            "mean_pass_rate": rows[0]["pass_rate"]}}
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(done))
        return done, path
    return run


def fake_pair(improve_cut: bool):
    run = fake_run(improve_cut)

    def pair(baseline, candidate, tasks, splits, bpath, cpath):
        return run(baseline, tasks, splits, bpath)[1], run(candidate, tasks, splits, cpath)[1]
    return pair


@pytest.fixture
def deps(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "EXPERIMENTS", tmp_path / "experiments")
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "configs")
    seed_failures()

    def make(improve_cut=True):
        assessed = []

        def assess(eid, b, c):
            assessed.append((b, c))
            return {"metrics": {"mean_pass_rate": {"baseline": 0.8, "candidate": 0.85, "delta": 0.05}},
                    "paired": {"mean_diff": 0.05, "ci95": [0.01, 0.09], "wins": 5, "ties": 1, "losses": 0},
                    "checks": {}, "newly_failed": [], "newly_rendered": []}
        d = ig.ImproveDeps(model=Scripted(), embed=None, run_pair=fake_pair(improve_cut), confirm=lambda *a: None,
                           assess=assess,
                           advisory={})
        d.assessed = assessed
        return d
    return make


def test_full_loop_waits_for_approval_then_promotes(deps):
    d, g = deps(), ig.build_graph(InMemorySaver())
    out = ig.start(deps=d, g=g)
    assert out["status"] == "awaiting_approval" and "Promote" in out["question"]
    with session_scope() as s:
        exp = s.scalar(select(Experiment))
        assert exp.status == "awaiting_approval" and exp.gates["eligible"]
        assert exp.change["policy_changes"] == {"snap_cuts": "word"}
        cand = s.scalar(select(AgentVersion).where(AgentVersion.version == exp.candidate_version))
        assert cand.status == "candidate" and cand.parent_version == DEFAULT_CONFIG.version
        assert registry.active(s).version == DEFAULT_CONFIG.version  # nothing changes before approval
        c = s.scalar(select(FailureCluster))
        assert c.check_id == "temporal.cut_through_word" and c.size == 4 and c.rate == 1.0 and c.diagnosis
        assert "chosen_by_planner" in str(c.diagnosis["probes"])
    assert d.assessed  # holdout assessment ran only after the gates passed

    done = ig.decide(out["thread_id"], "approve", by="prateek", note="looks good", deps=d, g=g)
    assert done["status"] == "promoted"
    with session_scope() as s:
        exp = s.scalar(select(Experiment))
        assert registry.active(s).version == exp.candidate_version
        old = s.scalar(select(AgentVersion).where(AgentVersion.version == DEFAULT_CONFIG.version))
        assert old.status == "retired"
        p = s.scalar(select(Promotion))
        assert (p.from_version, p.to_version, p.approved_by) == (DEFAULT_CONFIG.version, exp.candidate_version,
                                                                 "prateek")
        report = open(exp.report_path).read()
        assert "Regression gates" in report and "Holdout assessment" in report and "promoted by" in report
    assert (registry.CONFIG_DIR / f"{exp.candidate_version}.json").exists()


def test_regressing_candidate_is_rejected_without_touching_holdout(deps):
    d, g = deps(improve_cut=False), ig.build_graph(InMemorySaver())
    out = ig.start(deps=d, g=g)
    assert out["status"] == "rejected" and not d.assessed
    with session_scope() as s:
        exp = s.scalar(select(Experiment))
        assert exp.status == "rejected" and exp.gates["regressions"] and not exp.holdout
        assert s.scalar(select(AgentVersion).where(AgentVersion.version == exp.candidate_version)).status == "rejected"
        assert registry.active(s).version == DEFAULT_CONFIG.version


def test_decline_keeps_the_baseline(deps):
    d, g = deps(), ig.build_graph(InMemorySaver())
    out = ig.start(deps=d, g=g)
    assert ig.decide(out["thread_id"], "decline", by="prateek", deps=d, g=g)["status"] == "declined"
    with session_scope() as s:
        assert registry.active(s).version == DEFAULT_CONFIG.version and not s.scalar(select(Promotion))


def test_promotion_requires_an_approved_eligible_experiment(deps):
    deps()
    with session_scope() as s:
        registry.ensure_seed(s)
        exp = Experiment(name="x", baseline_version=DEFAULT_CONFIG.version, candidate_version="v", dataset_version="d",
                         evaluator_version="e", models={}, splits=["development"], change={}, status="rejected",
                         gates={"eligible": False})
        s.add(exp)
        s.flush()
        with pytest.raises(registry.PromotionError):
            registry.promote(s, exp, "someone")
        exp.status = "approved"
        with pytest.raises(registry.PromotionError, match="regression gates"):
            registry.promote(s, exp, "someone")


def test_api_exposes_experiments_and_refuses_premature_decisions(client, deps):
    d, g = deps(), ig.build_graph(InMemorySaver())
    ig.start(deps=d, g=g)
    exps = client.get("/improvement/experiments").json()
    assert len(exps) == 1 and exps[0]["status"] == "awaiting_approval" and exps[0]["eligible"]
    full = client.get(f"/improvement/experiments/{exps[0]['id']}").json()
    assert full["gates"]["eligible"] and "Regression gates" in full["report"]
    assert client.get("/improvement/clusters").json()[0]["check_id"] == "temporal.cut_through_word"
    assert {v["status"] for v in client.get("/improvement/versions").json()} == {"active", "candidate"}
    with session_scope() as s:
        s.scalar(select(Experiment)).status = "rejected"
    r = client.post(f"/improvement/experiments/{exps[0]['id']}/decision", json={"decision": "approve", "by": "x"})
    assert r.status_code == 409


def test_second_round_sees_why_the_first_candidate_was_rejected(deps):
    d, g = deps(improve_cut=False), ig.build_graph(InMemorySaver())
    first = ig.start(deps=d, g=g)
    assert first["status"] == "rejected"
    ig.start(deps=d, g=g)
    propose_prompts = [m[1].content for name, m in d.model.calls if name == "CandidateProposal"]
    assert "(none)" in propose_prompts[0].split("PREVIOUS EXPERIMENTS")[1]
    history = propose_prompts[1].split("PREVIOUS EXPERIMENTS")[1]
    assert first["candidate_version"] in history and "regressions" in history


def test_retest_runs_a_rejected_candidate_again_as_a_new_experiment(deps):
    g = ig.build_graph(InMemorySaver())
    first = ig.start(deps=deps(improve_cut=False), g=g)
    assert first["status"] == "rejected"
    d = deps(improve_cut=True)  # "the code behind the knob was fixed"
    out = ig.retest(first["experiment_id"], "snapping now respects the duration window", deps=d, g=g)
    assert out["status"] == "awaiting_approval" and d.assessed
    with session_scope() as s:
        exps = s.scalars(select(Experiment).order_by(Experiment.created_at)).all()
        assert [e.status for e in exps] == ["rejected", "awaiting_approval"]
        assert exps[1].change["retest_of"] == first["experiment_id"]
        assert exps[1].candidate_version == exps[0].candidate_version
    with pytest.raises(ValueError):
        ig.retest(str(exps[1].id), "not rejected", deps=d, g=g)


def test_rescore_regates_stored_renders_after_a_check_fix(deps, monkeypatch):
    """The candidate fixes cuts but 'regresses' frozen_frames; the check was wrong (still source shots).
    After the check is fixed, both runs are re-scored without re-running the agent, then re-gated."""
    import json

    from evaluation.schemas import EVALUATOR_VERSION, CheckResult
    from improvement.experiments import rescore as rescore_mod

    def pair(baseline, candidate, tasks, splits, bpath, cpath):
        for version, path in ((baseline, bpath), (candidate, cpath)):
            cand = version != baseline
            rows = [{"task": t.id, "split": t.split, "category": "c", "status": "rendered", "evaluation_id": f"e{t.id}",
                     "render_id": f"r{t.id}{int(cand)}", "gate": True, "steps": 5, "repairs": 1,
                     "pass_rate": 0.5 if cand else 0.5,
                     "checks": {"temporal.cut_through_word": cand, "technical.frozen_frames": not cand}}
                    for t in tasks]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"agent_version": version, "dataset_version": "d", "evaluator_version": "e",
                                        "results": rows, "summary": {"completion_rate": 1.0,
                                                                     "technical_valid_rate": 1.0}}))
        return bpath, cpath

    d, g = deps(), ig.build_graph(InMemorySaver())
    d.run_pair = pair
    first = ig.start(deps=d, g=g)
    assert first["status"] == "rejected" and not d.assessed

    seen = []
    monkeypatch.setitem(rescore_mod.RESCORABLE, "technical.frozen_frames",
                        lambda path, dur, tl: CheckResult(id="technical.frozen_frames", category="technical",
                                                          kind="deterministic", passed=True, severity="minor",
                                                          message="still source"))
    out = ig.rescore(first["experiment_id"], "frozen_frames flagged still source shots",
                     ["technical.frozen_frames"], deps=d, g=g,
                     measure=lambda rid: seen.append(rid) or ("/x.mp4", 10.0, {}))
    assert out["status"] == "awaiting_approval" and d.assessed  # the agent wasn't re-run, the holdout was
    assert {r[-1] for r in seen} == {"0", "1"}                   # both versions' renders were re-scored
    with session_scope() as s:
        exps = s.scalars(select(Experiment).order_by(Experiment.created_at)).all()
        assert [e.status for e in exps] == ["rejected", "awaiting_approval"]
        assert exps[1].change["rescore_of"] == first["experiment_id"]
        assert exps[1].comparison["checks"]["technical.frozen_frames"]["delta"] == 0
        cand = json.loads(open(exps[1].candidate_run).read())
    assert cand["evaluator_version"] == EVALUATOR_VERSION and cand["rescored_from"]["evaluator_version"] == "e"
    assert cand["results"][0]["pass_rate"] == 1.0 and cand["results"][0]["failed"] == []
    with pytest.raises(ValueError):
        ig.rescore(first["experiment_id"], "again", ["temporal.cut_through_word"], deps=d, g=g)  # judge/other: no
