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
