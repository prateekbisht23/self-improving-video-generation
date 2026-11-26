"""Baseline-vs-candidate comparison report (Markdown): what a human reads before approving."""

from pathlib import Path

from db.models import Experiment, FailureCluster


def _pct(x):
    return "–" if x is None else f"{x:.0%}"


def _scope_section(title: str, sc: dict, targets: list[str]) -> list[str]:
    p = sc["paired"]
    L = [f"### {title}: in scope '{sc['name']}' ({len(sc['task_ids'])} tasks: {', '.join(sc['task_ids'])})", "",
         f"Paired: mean Δ {p['mean_diff']:+.3f} (95% CI {p['ci95'][0]:+.3f} … {p['ci95'][1]:+.3f}); "
         f"wins {p['wins']} / ties {p['ties']} / losses {p['losses']}.", "",
         "| check | baseline | candidate | Δ | n |", "|---|---|---|---|---|"]
    for k, v in sc["checks"].items():
        if v["delta"] or k in targets:
            mark = " ⬅ target" if k in targets else ""
            delta = "" if v["delta"] is None else f"{v['delta']:+.0%}"
            L.append(f"| {k}{mark} | {_pct(v['baseline'])} | {_pct(v['candidate'])} | {delta} | {v['n']} |")
    return L + ["", "(checks that did not change are omitted)", ""]


def render_report(exp: Experiment, clusters: list[FailureCluster]) -> str:
    ch, cmp, g = exp.change or {}, exp.comparison or {}, exp.gates or {}
    L = [f"# Experiment {exp.name}", "",
         f"- experiment `{exp.id}` · status **{exp.status}**",
         f"- baseline `{exp.baseline_version}` → candidate `{exp.candidate_version}`",
         f"- dataset `{exp.dataset_version}` · evaluator `{exp.evaluator_version}` · splits {exp.splits} · "
         f"runs per version: {exp.n_runs}",
         f"- models: {', '.join(f'{k}={v}' for k, v in (exp.models or {}).items())}",
         f"- results: baseline `{exp.baseline_run}`, candidate `{exp.candidate_run}`", "",
         "## Why this candidate", "", f"**Hypothesis:** {ch.get('hypothesis', '')}", "",
         f"**Targets:** {', '.join(ch.get('targets', []))}", "",
         f"**Policy changes:** `{ch.get('policy_changes', {})}`", ""]
    if ch.get("planner_addendum"):
        L += ["**Planner prompt addition:**", "", "```", ch["planner_addendum"], "```", ""]
    if ch.get("repair_addendum"):
        L += ["**Repair prompt addition:**", "", "```", ch["repair_addendum"], "```", ""]
    L += [f"**Expected effect:** {ch.get('expected_effect', '')}", "", f"**Risks:** {ch.get('risks', '')}", ""]
    if clusters:
        L += ["## Failure patterns it was derived from (development split)", "",
              "| cluster | renders affected | severity | tasks | root cause (top) |", "|---|---|---|---|---|"]
        for c in clusters:
            rc = ((c.diagnosis or {}).get("root_causes") or [{}])[0]
            L.append(f"| {c.label[:70]} | {_pct(c.rate)} | {c.severity} | {len(c.tasks)} | "
                     f"{(rc.get('cause') or '')[:140]} ({rc.get('confidence', '')}) |")
        L.append("")
    if cmp:
        L += ["## Results: development + validation", "", "| metric | baseline | candidate | Δ |", "|---|---|---|---|"]
        for k, v in cmp["metrics"].items():
            L.append(f"| {k} | {v['baseline']} | {v['candidate']} | {v['delta']} |")
        p = cmp["paired"]
        L += ["", f"Paired per-task pass rate: mean Δ **{p['mean_diff']:+.3f}** (95% bootstrap CI "
              f"{p['ci95'][0]:+.3f} … {p['ci95'][1]:+.3f}); wins {p['wins']} / ties {p['ties']} / "
              f"losses {p['losses']}.",
              ""]
        L += ["| split | n | baseline | candidate | Δ |", "|---|---|---|---|---|"]
        for sp, v in cmp["by_split"].items():
            L.append(f"| {sp} | {v['n']} | {v['baseline']} | {v['candidate']} | {v['delta']:+.3f} |")
        L += ["", "| check | baseline | candidate | Δ | n |", "|---|---|---|---|---|"]
        for k, v in cmp["checks"].items():
            mark = " ⬅ target" if k in ch.get("targets", []) else ""
            delta = "" if v["delta"] is None else f"{v['delta']:+.0%}"
            L.append(f"| {k}{mark} | {_pct(v['baseline'])} | {_pct(v['candidate'])} | {delta} | {v['n']} |")
        L.append("")
        if cmp.get("scope"):
            L += _scope_section("Development + validation", cmp["scope"], ch.get("targets", []))
    if g:
        L += ["## Regression gates", "", f"**Eligible for promotion: {'YES' if g['eligible'] else 'NO'}**", ""]
        for title, key in (("Critical", "critical"), ("Regressions", "regressions"),
                           ("Improvements", "improvements"), ("Notes", "notes")):
            if g.get(key):
                L += [f"{title}:", ""] + [f"- {x}" for x in g[key]] + [""]
        if g.get("advisory_checks"):
            L += [f"Advisory (not gating): {', '.join(g['advisory_checks'])}", ""]
    if exp.holdout:
        h = exp.holdout
        L += ["## Holdout assessment (independent; never seen by diagnosis or candidate generation)", "",
              "| metric | baseline | candidate | Δ |", "|---|---|---|---|"]
        for k, v in h["metrics"].items():
            L.append(f"| {k} | {v['baseline']} | {v['candidate']} | {v['delta']} |")
        p = h["paired"]
        L += ["", f"Paired: mean Δ {p['mean_diff']:+.3f} (95% CI {p['ci95'][0]:+.3f} … {p['ci95'][1]:+.3f}); "
              f"wins {p['wins']} / ties {p['ties']} / losses {p['losses']}.", ""]
        targets = ch.get("targets", [])
        rows = [(k, v) for k, v in h["checks"].items() if k in targets or (v["delta"] or 0) <= -0.15]
        if rows:
            L += ["| check | baseline | candidate | n |", "|---|---|---|---|"]
            L += [f"| {k} | {_pct(v['baseline'])} | {_pct(v['candidate'])} | {v['n']} |" for k, v in rows]
            L.append("")
        if h.get("scope"):
            L += _scope_section("Holdout", h["scope"], targets)
    if exp.decision_by:
        L += ["## Decision", "",
              f"{exp.status} by **{exp.decision_by}** at {exp.decided_at}: {exp.decision_note or ''}", ""]
    return "\n".join(L)


def write_report(exp: Experiment, clusters: list[FailureCluster], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{str(exp.id)[:8]}-report.md"
    path.write_text(render_report(exp, clusters))
    return path
