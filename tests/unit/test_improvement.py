"""Self-improvement building blocks: versioned configs, candidate validation, comparison, gates,
holdout isolation. No database, no models."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.config import DEFAULT_CONFIG, AgentConfig, AgentPolicy
from benchmarks.schemas.task import HoldoutAccessError
from improvement.candidates.generate import CandidateProposal, NoChange, PolicyChanges, build_candidate
from improvement.collection import collect
from improvement.experiments.compare import bootstrap_ci, compare
from improvement.promotion.gates import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ versions
def test_default_config_is_the_v02_baseline_version():
    assert DEFAULT_CONFIG.version == "editing-agent-0.2+d43dbd596cae"
    # a knob left at its default does not change the version (new knobs keep old versions valid)
    assert AgentConfig(policy=AgentPolicy(snap_cuts="off")).version == DEFAULT_CONFIG.version


def test_any_behaviour_change_is_a_new_version():
    a = AgentConfig(policy=AgentPolicy(snap_cuts="word"))
    b = AgentConfig(policy=AgentPolicy(snap_cuts="sentence"))
    c = AgentConfig(planner_addendum="- open with a question")
    assert len({DEFAULT_CONFIG.version, a.version, b.version, c.version}) == 4
    assert "Additional rules" in c.planner_system() and "Additional rules" not in DEFAULT_CONFIG.planner_system()
    assert AgentConfig.model_validate(a.model_dump()).version == a.version  # round-trips through JSON/DB


# ------------------------------------------------------------------ candidates
def proposal(**kw):
    base = dict(hypothesis="h", target_checks=["temporal.cut_through_word"], policy_changes=PolicyChanges(),
                expected_effect="e", risks="r")
    return CandidateProposal(**base | kw)


def test_build_candidate_merges_and_versions():
    cfg, change = build_candidate(DEFAULT_CONFIG, proposal(policy_changes=PolicyChanges(snap_cuts="sentence")),
                                  {"temporal.cut_through_word"}, release="0.3")
    assert cfg.policy.snap_cuts == "sentence" and cfg.version.startswith("editing-agent-0.3+")
    assert change["policy_changes"] == {"snap_cuts": "sentence"} and DEFAULT_CONFIG.policy.snap_cuts == "off"


def test_candidate_must_change_something_and_target_diagnosed_checks():
    with pytest.raises(NoChange):
        build_candidate(DEFAULT_CONFIG, proposal())
    with pytest.raises(ValueError, match="none of which were diagnosed"):
        build_candidate(DEFAULT_CONFIG, proposal(planner_addendum="- x"), {"narrative.structure"})


def test_knob_bounds_are_enforced():
    with pytest.raises(ValidationError):
        PolicyChanges(snap_cuts="everything")
    with pytest.raises(ValidationError):
        build_candidate(DEFAULT_CONFIG, proposal(policy_changes=PolicyChanges.model_construct(max_repairs=50)))


# ------------------------------------------------------------------ compare + gates
def result(task, split, pass_rate, checks, gate=True, rendered=True):
    r = {"task": task, "split": split, "status": "rendered" if rendered else "failed"}
    if rendered:
        r |= {"evaluation_id": f"ev-{task}", "pass_rate": pass_rate, "gate": gate, "checks": checks}
    return r


def run(version, rows):
    done = [r for r in rows if r.get("evaluation_id")]
    return {"agent_version": version, "dataset_version": "d", "evaluator_version": "e", "results": rows,
            "summary": {"completion_rate": len(done) / len(rows),
                        "technical_valid_rate": sum(r["gate"] for r in done) / len(rows),
                        "mean_pass_rate": sum(r["pass_rate"] for r in done) / max(len(done), 1)}}


def base_rows():
    return [result(f"t{i}", "validation" if i >= 8 else "development", 0.8,
                   {"temporal.cut_through_word": i % 2 == 0, "technical.loudness": True, "visual.framing": True,
                    "narrative.structure": False}) for i in range(10)]


def test_improvement_passes_gates():
    cand = [dict(r, pass_rate=0.85, checks=dict(r["checks"], **{"temporal.cut_through_word": True}))
            for r in base_rows()]
    cmp = compare(run("b", base_rows()), run("c", cand))
    assert cmp["checks"]["temporal.cut_through_word"]["delta"] == 0.5 and cmp["paired"]["wins"] == 10
    g = evaluate_gates(cmp, ["temporal.cut_through_word"])
    assert g["eligible"] and g["improvements"] and not g["regressions"]


def test_non_target_regression_blocks_but_advisory_does_not():
    cand = [dict(r, checks=dict(r["checks"], **{"temporal.cut_through_word": True, "visual.framing": False}))
            for r in base_rows()]
    cmp = compare(run("b", base_rows()), run("c", cand))
    assert evaluate_gates(cmp, ["temporal.cut_through_word"])["regressions"]
    g = evaluate_gates(cmp, ["temporal.cut_through_word"], advisory={"visual.framing": "flips"})
    assert g["eligible"] and any("advisory" in n for n in g["notes"])


def test_critical_regressions_prevent_promotion():
    cand = [dict(r, checks=dict(r["checks"], **{"temporal.cut_through_word": True})) for r in base_rows()]
    cand[0] = result("t0", "development", 0, {}, rendered=False)        # stopped rendering
    cand[1] = dict(cand[1], gate=False)                                   # fails the technical gate
    g = evaluate_gates(compare(run("b", base_rows()), run("c", cand)), ["temporal.cut_through_word"])
    assert not g["eligible"]
    assert any("no longer render" in c for c in g["critical"]) and any("technical_valid_rate" in c
                                                                      for c in g["critical"])


def test_runs_with_different_evaluators_are_not_comparable():
    b, c = run("b", base_rows()), run("c", base_rows())
    c["evaluator_version"] = "other"
    with pytest.raises(ValueError):
        compare(b, c)


def test_bootstrap_ci_is_deterministic_and_brackets_the_mean():
    d = [0.1, 0.0, 0.05, -0.02, 0.2, 0.0]
    lo, hi = bootstrap_ci(d)
    assert (lo, hi) == bootstrap_ci(d) and lo <= sum(d) / len(d) <= hi


# ------------------------------------------------------------------ holdout isolation
def test_failure_collection_refuses_non_development_splits():
    with pytest.raises(HoldoutAccessError):
        collect(None, "v", ("development", "holdout"))
    with pytest.raises(HoldoutAccessError):
        collect(None, "v", ("validation",))


def test_only_the_holdout_assessment_module_may_load_holdout_tasks():
    offenders = []
    for path in (ROOT / "improvement").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.keyword) and node.arg == "allow_holdout":
                offenders.append(str(path.relative_to(ROOT)))
            if isinstance(node, ast.Constant) and node.value == "holdout":
                offenders.append(str(path.relative_to(ROOT)))
    assert set(offenders) == {"improvement/experiments/holdout.py"}, offenders


class _Seq:
    """Structured-output fake that returns the given proposals in order and records messages."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def with_structured_output(self, schema):
        outer = self

        class _S:
            def invoke(self, messages):
                outer.seen.append(list(messages))
                return outer.answers.pop(0)
        return _S()


def _proposal(hyp, **knobs):
    return CandidateProposal(hypothesis=hyp, target_checks=["temporal.cut_through_word"],
                             policy_changes=PolicyChanges(**knobs), expected_effect="+", risks="-")


def test_proposal_whose_text_and_fields_disagree_is_sent_back():
    from improvement.candidates.generate import propose

    bad = _proposal("set snap_cuts to word and captions_follow_reference", captions_follow_reference=True)
    good = _proposal("set snap_cuts to word and captions_follow_reference", captions_follow_reference=True,
                     snap_cuts="word")
    m = _Seq(bad, good)
    assert propose([], DEFAULT_CONFIG, m) is good
    assert "snap_cuts" in m.seen[1][-1].content  # the correction names the missing knob


def test_proposal_that_stays_inconsistent_fails_loudly():
    from improvement.candidates.generate import InconsistentProposal, propose

    bad = _proposal("use snap_cuts=word")
    with pytest.raises(InconsistentProposal):
        propose([], DEFAULT_CONFIG, _Seq(bad, bad), attempts=2)


def test_experiment_runs_versions_interleaved(monkeypatch, tmp_path):
    from improvement.experiments import run as run_mod

    calls = []
    monkeypatch.setattr(run_mod, "EXPERIMENTS", tmp_path)
    monkeypatch.setattr(run_mod, "run_benchmark",
                        lambda tasks, splits, agent_version, path, **kw: calls.append((agent_version, len(tasks))))
    tasks = [type("T", (), {"id": i})() for i in range(3)]
    run_mod.run_pair("B", "C", tasks, ["development"], tmp_path / "b.json", tmp_path / "c.json")
    assert calls == [("B", 1), ("C", 1), ("C", 1), ("B", 1), ("B", 1), ("C", 1), ("B", 3), ("C", 3)]


def test_only_transient_provider_errors_are_retried():
    from improvement.graph import transient

    assert transient(RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand"))
    assert not transient(RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel 503"))
    assert not transient(ValueError("proposal targets [] none of which were diagnosed"))


def test_a_failure_that_renders_on_the_rerun_is_flaky_not_critical():
    cand = [dict(r, checks=dict(r["checks"], **{"temporal.cut_through_word": True})) for r in base_rows()]
    cand[0] = result("t0", "development", 0, {}, rendered=False)
    rerun = run("c", [result("t0", "development", 0.8, base_rows()[0]["checks"])])
    g = evaluate_gates(compare(run("b", base_rows()), run("c", cand), rerun), ["temporal.cut_through_word"])
    assert not any("no longer render" in c for c in g["critical"]) and any("flaky" in n for n in g["notes"])
    # the critical rates count the re-run result for a flaky task, so completion did not drop
    assert not g["critical"]


def test_infrastructure_errors_are_excluded_on_both_sides():
    base = base_rows()
    base[3] = {"task": "t3", "split": "development", "status": "error", "error": "ConnectError: DNS"}
    cand = [dict(r, checks=dict(r["checks"], **{"temporal.cut_through_word": True})) for r in base_rows()]
    cmp = compare(run("b", base), run("c", cand))
    assert cmp["excluded_infra_errors"] == ["t3"] and cmp["tasks"] == 9
    assert cmp["metrics"]["completion_rate"]["delta"] == 0


def test_a_single_task_flip_does_not_gate():
    rows = [dict(r, checks=dict(r["checks"], **{"style.color_similarity": True})) if i < 3 else r
            for i, r in enumerate(base_rows())]
    cand = [dict(r, checks=dict(r["checks"], **{"temporal.cut_through_word": True})) for r in rows]
    cand[0] = dict(cand[0], checks=dict(cand[0]["checks"], **{"style.color_similarity": False}))  # 1 of 3 flips
    g = evaluate_gates(compare(run("b", rows), run("c", cand)), ["temporal.cut_through_word"])
    assert g["eligible"] and any("color_similarity" in n and "not gating" in n for n in g["notes"])


def test_config_scope_only_when_every_change_is_scoped_the_same_way():
    assert DEFAULT_CONFIG.scope() is None
    cap = AgentConfig(policy=AgentPolicy(captions_follow_reference=True))
    assert cap.scope() == "reference"
    assert AgentConfig(policy=AgentPolicy(captions_follow_reference=True, snap_cuts="word")).scope() is None
    assert AgentConfig(planner_addendum="x", policy=AgentPolicy(captions_follow_reference=True)).scope() is None


def test_scope_claim_captions_knob_is_inert_without_a_reference():
    """Pins the 'reference' scope of captions_follow_reference: no style reference -> baseline path."""
    from types import SimpleNamespace

    from agent.graphs.editing_graph import _skip_captions
    cfg = AgentConfig(policy=AgentPolicy(captions_follow_reference=True))
    state = {"instructions": "make a short", "memory_text": ""}
    assert not _skip_captions(SimpleNamespace(config=cfg, style=None), state)
    no_caps = {"observed": {"captions_present": False}}
    assert _skip_captions(SimpleNamespace(config=cfg, style=no_caps), state)
    assert not _skip_captions(SimpleNamespace(config=DEFAULT_CONFIG, style=no_caps), state)


def _scoped_runs(in_lost: int, ctrl_flips: int):
    """4 in-scope tasks (r*) where the target goes 0 -> 1 and `in_lost` lose a judge check,
    plus 16 control tasks (c*) where `ctrl_flips` flip that judge check both ways."""
    b, c = [], []
    for i in range(4):
        b.append(result(f"r{i}", "development", 0.8, {"style.caption_match": False, "instruction.adherence": True}))
        c.append(result(f"r{i}", "development", 0.8, {"style.caption_match": True,
                                                       "instruction.adherence": i >= in_lost}))
    for i in range(16):
        flip = i < ctrl_flips
        b.append(result(f"c{i}", "development", 0.8, {"instruction.adherence": not (flip and i % 2)}))
        c.append(result(f"c{i}", "development", 0.8, {"instruction.adherence": not (flip and not i % 2)}))
    return run("b", b), run("c", c), {"name": "reference", "tasks": [f"r{i}" for i in range(4)]}


def test_scoped_gates_judge_in_scope_tasks_against_the_control_noise():
    b, c, scope = _scoped_runs(in_lost=2, ctrl_flips=6)   # judge flips on 6/16 identical-code tasks
    cmp = compare(b, c, scope=scope)
    assert cmp["control"]["checks"]["instruction.adherence"] == {"n": 16, "flips": 6}
    g = evaluate_gates(cmp, ["style.caption_match"])
    assert g["eligible"] and g["scope"] == "reference"
    assert any("within A/A noise" in n for n in g["notes"])  # 2 of 4 is what that noise produces
    b, c, scope = _scoped_runs(in_lost=4, ctrl_flips=0)   # a check that never flips by chance
    g = evaluate_gates(compare(b, c, scope=scope), ["style.caption_match"])
    assert not g["eligible"] and g["regressions"][0].startswith("instruction.adherence")
    unscoped = evaluate_gates(compare(*_scoped_runs(in_lost=2, ctrl_flips=6)[:2]), ["style.caption_match"])
    assert unscoped["scope"] is None and "thresholds" in unscoped


def test_technical_gate_failure_that_passes_its_rerun_is_flaky_not_critical():
    base = base_rows()
    cand = [dict(r) for r in base]
    cand[3] = dict(cand[3], gate=False)
    rerun = run("c", [dict(base[3])])
    cmp = compare(run("b", base), run("c", cand), rerun)
    assert cmp["gate_flaky"] == ["t3"] and cmp["after_rerun"]["technical_valid_rate"]["delta"] == 0
    assert cmp["metrics"]["technical_valid_rate"]["delta"] < 0  # still reported as measured
    g = evaluate_gates(cmp, ["temporal.cut_through_word"])
    assert not g["critical"] and any("passed on the re-run" in n for n in g["notes"])
    g = evaluate_gates(compare(run("b", base), run("c", cand), run("c", [dict(base[3], gate=False)])),
                       ["temporal.cut_through_word"])
    assert any("technical_valid_rate" in x for x in g["critical"])
