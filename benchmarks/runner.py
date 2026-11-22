"""Run benchmark tasks end-to-end and record them as a LangSmith experiment.

    uv run python -m benchmarks.runner --split development [--limit 3] [--no-judges]
    uv run python -m benchmarks.runner --split holdout --allow-holdout      # final assessment only
    uv run python -m benchmarks.runner --reevaluate benchmarks/results/<run>.json   # evaluator stability
    uv run python -m benchmarks.runner --split development --agent-version <version>  # a registered version

Per task: ensure source/reference assets (by sample id) -> editing session (agent) -> render
-> independent evaluation. Results go to benchmarks/results/<run_id>.json (resumable) and to a
LangSmith experiment over the dataset `sivg-bench`, so runs of different agent versions can be
compared side by side.
"""

import argparse
import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from benchmarks.schemas.task import BenchmarkTask, dataset_version, load_tasks
from config.models import model_id
from config.settings import get_settings
from db.models import AssetStatus, EditingSession, Evaluation, Project
from db.session import session_scope
from evaluation.schemas import EVALUATOR_VERSION

RESULTS = Path(__file__).resolve().parent / "results"
PROJECT_TITLE = "Benchmark v1"
DATASET = "sivg-bench"


class QuotaExhausted(RuntimeError):
    """The model provider's DAILY quota ran out: every further task would fail the same way."""

    def __init__(self, path: Path, where: str):
        super().__init__(f"daily model quota exhausted at {where}; resume later with --resume {path}")
        self.path = path


# ------------------------------------------------------------------ assets
def benchmark_assets() -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Sample id -> ready asset id in the benchmark project (uploaded once via the API)."""
    with session_scope() as s:
        p = s.scalar(select(Project).where(Project.title == PROJECT_TITLE))
        if p is None:
            raise SystemExit(f"create project '{PROJECT_TITLE}' and upload samples/*.mp4 first (see docs)")
        ids = {a.original_filename.rsplit(".", 1)[0]: a.id for a in p.assets if a.status == AssetStatus.ready}
        return p.id, ids


# ------------------------------------------------------------------ personalization
def seed_creator(task: BenchmarkTask) -> uuid.UUID:
    """A fresh creator per personalization task, holding the task's preferences as explicit memory.
    Retrieval (context filter + conflict resolution) then runs exactly as for a real creator."""
    from db.models import CreatorPreference, User
    from memory.storage import add_explicit

    with session_scope() as s:
        u = s.scalar(select(User).where(User.handle == f"bench-{task.id}"))
        if u is None:
            u = User(handle=f"bench-{task.id}", display_name=f"benchmark creator for {task.id}")
            s.add(u)
            s.flush()
        for p in s.scalars(select(CreatorPreference).where(CreatorPreference.creator_id == u.id)):
            s.delete(p)
        s.flush()
        for i, stmt in enumerate(task.preferences):
            add_explicit(s, u.id, category="other", attribute=f"{task.id}_pref_{i}", value=stmt.lower()[:160],
                         statement=stmt)
        return u.id


# ------------------------------------------------------------------ one task
def run_task(task: BenchmarkTask, *, judges: bool = True, agent_version: str | None = None) -> dict:
    from services.worker.editing import ensure_style_profile, run_editing_session

    project_id, assets = benchmark_assets()
    missing = [s for s in task.sources + ([task.reference] if task.reference else []) if s not in assets]
    if missing:
        raise RuntimeError(f"benchmark assets not ready: {missing}")
    c = task.constraints
    t0 = time.perf_counter()
    if task.reference:
        ensure_style_profile(assets[task.reference])
    creator_id = seed_creator(task) if task.preferences else None
    with session_scope() as s:
        e = EditingSession(project_id=project_id, instructions=task.instructions, creator_id=creator_id,
                           agent_version=agent_version,
                           source_asset_ids=[str(assets[x]) for x in task.sources],
                           reference_asset_id=assets[task.reference] if task.reference else None,
                           constraints={**c.model_dump(), "preferences": task.preferences,
                                        "benchmark_task": task.id, "dataset_version": dataset_version()})
        s.add(e)
        s.flush()
        sid = e.id
    try:
        out = run_editing_session(str(sid))
    except Exception as ex:
        return {"task": task.id, "session_id": str(sid), "status": "error", "error": f"{type(ex).__name__}: {ex}"[:500],
                "daily_quota": "PerDay" in str(ex), "seconds": round(time.perf_counter() - t0, 1)}
    res = {"task": task.id, "category": task.category, "split": task.split, "session_id": str(sid),
           "status": out["status"], "steps": out["steps"], "log": out["log"]}
    with session_scope() as s:
        e = s.get(EditingSession, sid)
        acts = e.actions
        res |= {"rejected": sum(not a.ok for a in acts), "repairs": sum(a.source == "repair" for a in acts),
                "fixups": sum(a.source == "fixup" for a in acts), "trace_id": e.trace_id, "error": e.error}
    if out.get("render_id"):
        res |= evaluation_fields(out["render_id"], judges)
    res["seconds"] = round(time.perf_counter() - t0, 1)
    return res


def evaluation_fields(render_id: str, judges: bool = True) -> dict:
    from services.worker.evaluation import evaluate_render

    ev = evaluate_render(render_id, judges_on=judges)
    with session_scope() as s:
        rep = s.get(Evaluation, uuid.UUID(ev["evaluation_id"])).report
    checks = {c["id"]: c for c in rep["checks"]}
    res = {"judge_errors": sum(1 for c in rep["checks"] if c["message"].startswith("judge error"))}
    if res["judge_errors"] and any("PerDay" in c["message"] or "RESOURCE_EXHAUSTED" in c["message"]
                                   for c in rep["checks"]):
        res["daily_quota"] = True
    res |= {"render_id": render_id, "evaluation_id": ev["evaluation_id"],
            "gate": rep["technical_gate_passed"], "pass_rate": rep["pass_rate"], "failed": rep["failed"],
            "by_category": rep["by_category"],
            "checks": {k: v["passed"] for k, v in checks.items()},
            "scores": {k: v["score"] for k, v in checks.items() if v["score"] is not None},
            "duration": next((v["measurements"].get("duration") for k, v in checks.items()
                              if k == "technical.duration_in_range"), None)}
    return res


# ------------------------------------------------------------------ summaries
def summarize(results: list[dict]) -> dict:
    done = [r for r in results if r.get("evaluation_id")]
    out = {"tasks": len(results), "completed": len(done),
           "completion_rate": round(len(done) / max(len(results), 1), 3),
           "technical_valid_rate": round(sum(bool(r["gate"]) for r in done) / max(len(results), 1), 3),
           "mean_pass_rate": round(statistics.fmean(r["pass_rate"] for r in done), 3) if done else None,
           "mean_actions": round(statistics.fmean(r["steps"] for r in done), 1) if done else None,
           "repairs_per_task": round(statistics.fmean(r["repairs"] for r in done), 2) if done else None}
    per_check: dict[str, list] = {}
    for r in done:
        for k, v in r["checks"].items():
            if v is not None:
                per_check.setdefault(k, []).append(bool(v))
    out["check_pass_rates"] = {k: round(sum(v) / len(v), 3) for k, v in sorted(per_check.items())}
    cats: dict[str, list] = {}
    for r in done:
        cats.setdefault(r["category"], []).append(r["pass_rate"])
    out["by_task_category"] = {k: round(statistics.fmean(v), 3) for k, v in sorted(cats.items())}
    return out


def write_markdown(run: dict, path: Path) -> None:
    s = run["summary"]
    lines = [f"# Benchmark run {run['run_id']}", "",
             f"- agent `{run['agent_version']}` · evaluator `{run['evaluator_version']}` · dataset "
             f"`{run['dataset_version']}` · splits {run['splits']}",
             f"- planner `{run['models']['planner']}` · judge `{run['models']['judge']}` · started {run['started']}",
             "", "| metric | value |", "|---|---|"]
    for k in ("tasks", "completed", "completion_rate", "technical_valid_rate", "mean_pass_rate", "mean_actions",
              "repairs_per_task"):
        lines.append(f"| {k} | {s[k]} |")
    lines += ["", "## Check pass rates", "", "| check | pass rate |", "|---|---|"]
    lines += [f"| {k} | {v:.0%} |" for k, v in s["check_pass_rates"].items()]
    lines += ["", "## Tasks", "", "| task | category | status | gate | pass rate | duration | repairs | failed |",
              "|---|---|---|---|---|---|---|---|"]
    for r in run["results"]:
        lines.append(f"| {r['task']} | {r.get('category', '')} | {r['status']} | {r.get('gate', '')} | "
                     f"{r.get('pass_rate', '')} | {r.get('duration') or ''} | {r.get('repairs', '')} | "
                     f"{', '.join(x.split('.', 1)[1] for x in r.get('failed', []))} |")
    path.write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------ LangSmith
def sync_dataset(tasks: list[BenchmarkTask]):
    """Upsert tasks as examples (inputs only; no hidden labels are uploaded)."""
    from langsmith import Client

    c = Client()
    ds = c.read_dataset(dataset_name=DATASET) if c.has_dataset(dataset_name=DATASET) else \
        c.create_dataset(DATASET, description="Self-improving video editing benchmark (PRD §8)")
    existing = {ex.metadata.get("task_id"): ex for ex in c.list_examples(dataset_id=ds.id)}
    for t in tasks:
        inputs = {"task_id": t.id, "instructions": t.instructions, "sources": t.sources, "reference": t.reference,
                  "constraints": t.constraints.model_dump(), "preferences": t.preferences}
        meta = {"task_id": t.id, "split": t.split, "category": t.category, "dataset_version": dataset_version()}
        if t.id in existing:
            c.update_example(existing[t.id].id, inputs=inputs, metadata=meta, split=t.split)
        else:
            c.create_example(dataset_id=ds.id, inputs=inputs, metadata=meta, split=t.split)
    return c, ds


def log_experiment(run: dict, tasks: list[BenchmarkTask]) -> str | None:
    """Record results as a LangSmith experiment (target replays stored results; no re-execution)."""
    try:
        c, ds = sync_dataset(tasks)
    except Exception as e:  # tracing/LangSmith is optional for a local run
        print(f"LangSmith dataset sync skipped: {e}")
        return None
    by_task = {r["task"]: r for r in run["results"]}
    wanted = {t.id for t in tasks}
    examples = [ex for ex in c.list_examples(dataset_id=ds.id) if ex.metadata.get("task_id") in wanted]

    def target(inputs: dict) -> dict:
        r = by_task[inputs["task_id"]]
        return {k: r.get(k) for k in ("status", "gate", "pass_rate", "checks", "scores", "repairs", "steps",
                                      "duration", "session_id", "trace_id", "evaluation_id")}

    def gate(outputs: dict) -> dict:
        return {"key": "technical_gate", "score": int(bool(outputs.get("gate")))}

    def pass_rate(outputs: dict) -> dict:
        return {"key": "pass_rate", "score": outputs.get("pass_rate") or 0.0}

    def completed(outputs: dict) -> dict:
        return {"key": "completed", "score": int(outputs.get("status") == "rendered")}

    def repairs(outputs: dict) -> dict:
        return {"key": "repairs", "score": outputs.get("repairs") or 0}

    def judged(outputs: dict) -> list[dict]:
        sc = outputs.get("scores") or {}
        return [{"key": k.replace(".", "_"), "score": v} for k, v in sc.items()
                if k in ("instruction.adherence", "narrative.structure", "captions.accuracy")]

    res = c.evaluate(target, data=examples, evaluators=[gate, pass_rate, completed, repairs, judged],
                     experiment_prefix=run["agent_version"], max_concurrency=0,
                     metadata={k: run[k] for k in ("run_id", "agent_version", "evaluator_version",
                                                   "dataset_version", "splits")} | run["models"],
                     description=f"benchmark run {run['run_id']}")
    return res.experiment_name


# ------------------------------------------------------------------ evaluator stability
def reevaluate(path: Path, judges: bool = True) -> dict:
    """Re-run the evaluator on the SAME renders and compare check outcomes (reproducibility)."""
    from services.worker.evaluation import evaluate_render

    run = json.loads(path.read_text())
    same, total, det_same, det_total, diffs = 0, 0, 0, 0, []
    for r in run["results"]:
        if not r.get("render_id"):
            continue
        ev = evaluate_render(r["render_id"], judges_on=judges)
        with session_scope() as s:
            rep = s.get(Evaluation, uuid.UUID(ev["evaluation_id"])).report
        now = {c["id"]: (c["passed"], c["kind"]) for c in rep["checks"]}
        for cid, before in r["checks"].items():
            if cid not in now or before is None or now[cid][0] is None:
                continue
            total += 1
            same += before == now[cid][0]
            if now[cid][1] != "model":
                det_total += 1
                det_same += before == now[cid][0]
            if before != now[cid][0]:
                diffs.append(f"{r['task']} {cid}: {before} -> {now[cid][0]}")
    out = {"source_run": run["run_id"], "checks_compared": total, "agreement": round(same / max(total, 1), 3),
           "non_model_agreement": round(det_same / max(det_total, 1), 3),
           "model_agreement": round((same - det_same) / max(total - det_total, 1), 3), "flips": diffs}
    (path.with_suffix(".stability.json")).write_text(json.dumps(out, indent=2))
    return out


# ------------------------------------------------------------------ CLI
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", nargs="+", default=["development"])
    ap.add_argument("--allow-holdout", action="store_true")
    ap.add_argument("--tasks", nargs="*", help="only these task ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-judges", action="store_true")
    ap.add_argument("--resume", type=Path, help="continue a previous results file")
    ap.add_argument("--reevaluate", type=Path)
    ap.add_argument("--no-langsmith", action="store_true")
    ap.add_argument("--agent-version", help="registered agent version (default: the active one)")
    a = ap.parse_args()
    get_settings()
    import os

    os.environ["AUTO_EVALUATE"] = "false"  # the runner evaluates inline
    get_settings.cache_clear()
    if a.reevaluate:
        print(json.dumps(reevaluate(a.reevaluate, judges=not a.no_judges), indent=2))
        return

    tasks = load_tasks(a.split, allow_holdout=a.allow_holdout)
    if a.tasks:
        tasks = [t for t in tasks if t.id in a.tasks]
    tasks = tasks[: a.limit] if a.limit else tasks
    try:
        run, path = run_benchmark(tasks, splits=a.split, agent_version=a.agent_version, judges=not a.no_judges,
                                  resume=a.resume, langsmith=not a.no_langsmith)
    except QuotaExhausted as e:
        raise SystemExit(str(e)) from None
    print(json.dumps(run["summary"], indent=2))
    print(f"results: {path}")


def run_benchmark(tasks: list[BenchmarkTask], *, splits: list[str], agent_version: str | None = None,
                  judges: bool = True, resume: Path | None = None, path: Path | None = None,
                  langsmith: bool = True, label: str = "") -> tuple[dict, Path]:
    """Run (or resume) tasks with one agent version; results file is written after every task.
    `path` fixes the results file name up front (experiments use it so a stopped run resumes)."""
    from improvement import registry

    with session_scope() as s:
        version = agent_version or registry.active(s).version
        registry.get(s, version)  # must exist (and still hash to its name)
    RESULTS.mkdir(exist_ok=True)
    if resume is None and path is not None and path.exists():
        resume = path
    if resume:
        run = json.loads(resume.read_text())
        path = resume
        if run["agent_version"] != version:
            raise ValueError(f"{resume} was run with {run['agent_version']}, not {version}")
    else:
        rid = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + "-".join(s[:3] for s in splits) + label
        run = {"run_id": path.stem if path else rid, "agent_version": version,
               "evaluator_version": EVALUATOR_VERSION,
               "dataset_version": dataset_version(), "splits": splits, "judges": judges,
               "models": {r: model_id(r) for r in ("planner", "vision", "judge", "embeddings")},
               "started": datetime.now(UTC).isoformat(timespec="seconds"), "results": []}
        path = path or RESULTS / f"{rid}.json"
    done = {r["task"] for r in run["results"] if r.get("status") != "error"}
    run["results"] = [r for r in run["results"] if r["task"] in done]
    for r in run["results"]:  # judges failed (e.g. quota) on an otherwise finished task: re-evaluate only
        if r.get("judge_errors") and r.get("render_id"):
            print(f"re-evaluating {r['task']} (judge errors: {r['judge_errors']})", flush=True)
            r.update(evaluation_fields(r["render_id"], judges))
            if r.get("daily_quota"):
                path.write_text(json.dumps(run, indent=2))
                raise QuotaExhausted(path, r["task"])
    for i, t in enumerate(tasks, 1):
        if t.id in done:
            continue
        print(f"[{i}/{len(tasks)}] {t.id} ({t.category}) ...", flush=True)
        r = run_task(t, judges=judges, agent_version=version)
        run["results"].append(r)
        if r.get("daily_quota"):
            path.write_text(json.dumps(run, indent=2))
            raise QuotaExhausted(path, t.id)
        print(f"    -> {r['status']} gate={r.get('gate')} pass_rate={r.get('pass_rate')} "
              f"repairs={r.get('repairs')} {r['seconds']}s failed={r.get('failed')}", flush=True)
        run["summary"] = summarize(run["results"])
        path.write_text(json.dumps(run, indent=2))
    run["summary"] = summarize(run["results"])
    run["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
    if langsmith and not run.get("langsmith_experiment"):
        run["langsmith_experiment"] = log_experiment(run, tasks)
    path.write_text(json.dumps(run, indent=2))
    write_markdown(run, path.with_suffix(".md"))
    return run, path


if __name__ == "__main__":
    main()
