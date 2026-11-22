# 19 — Controlled self-improvement: versions, experiments, regression gates, promotion

PRD FR-12 / Phase 5: the agent may improve itself, but only through a process that can't quietly make it worse. Code: `agent/config.py`, `improvement/`.

## 1. What is allowed to change: a versioned configuration
`AgentConfig` = base prompts + **prompt addenda** + **policy knobs** (`AgentPolicy`).

| knob | what it does (code written and tested by a human) |
|---|---|
| `snap_cuts` off / word / sentence | moves clip edges into word gaps or onto sentence boundaries before an action runs |
| `snap_max_shift` | how far sentence snapping may move an edge before falling back to a word gap |
| `fixup_extend` | the last-resort deterministic fix may also *lengthen* a too-short edit (v0.2 could only trim) |
| `scene_reuse_check` | the "most clips reuse the same scene" check, which is wrong for two-shot interviews |
| `captions_follow_reference` | no captions when the reference has none and nobody asked for them |
| `max_repairs`, `max_steps` | budgets |

The improvement loop **can't write code**. It chooses knob values (validated by Pydantic types and bounds) and appends short rules to prompts. Generated code changes would need review, sandboxing and tests of their own; a config change only ever recombines behaviours that already passed review.

**Version = hash.** `version = editing-agent-<release>+<sha256(prompts, addenda, non-default knobs)>`. Only knobs that differ from their defaults enter the hash, so adding a new knob (default = old behaviour) keeps every old version string valid. The default config is still exactly `editing-agent-0.2+d43dbd596cae`, so all v0.2 results remain the baseline. The registry (`agent_versions`) stores each config, and `registry.get()` re-hashes it on load, so a stored config that was edited no longer matches its name and is refused.

## 2. The improvement graph (LangGraph, durable)
```
collect → diagnose → propose → experiment → gates ─(eligible)→ final_assessment → approval ⏸ → decide
                                                  └(not)─────→ reject
```
- `propose`: one structured `CandidateProposal` (hypothesis, target checks, knob values, addenda, expected effect, risks). Its targets must be checks that were actually diagnosed.
- `experiment`: runs baseline and candidate on **development + validation** with identical inputs. A results file is reused instead of re-run only when *everything* that affects the outcome matches: agent version, evaluator version, dataset hash, splits, planner and judge models, and all tasks finished.
- `final_assessment`: runs **holdout** once, only after the gates pass. It's the only module in `improvement/` allowed to load holdout tasks (an AST test enforces this), and nothing upstream ever reads its output.
- `approval`: `interrupt()`. The graph is saved in Postgres and waits, for days if need be, until a human calls `improvement.cli approve|decline <thread> --by <name>` or `POST /improvement/experiments/{id}/decision`.
- `decide`: approve → `registry.promote()`: the old version is retired, the new one becomes active, a `promotions` row is written, and the config is exported to `agent/configs/<version>.json` so it also shows up in git. Promotion refuses if the experiment wasn't approved, failed the gates, or the active version changed since the experiment ran.

### Durable execution, and the bug it surfaced
A benchmark run takes ~40 minutes and can be stopped by a 503 or the daily quota. Because the graph is checkpointed after every node, `improvement.cli resume <thread>` re-enters at the failed node, and the runner continues its results file where it stopped.

The first real resume produced impossible numbers: tasks "finished" in 0.1 s, with exactly the scores of *other* tasks. The cause is that a graph invoked *inside a node* of a checkpointed graph is treated by LangGraph as a **subgraph**. It inherits the parent's checkpointer, and on resume its calls are **replayed by position**: the 1st editing run after the resume got the saved result of the 1st editing run before the crash (ac-01's edit for task if-01). The fix is `compile(checkpointer=False)` for the editing and evaluation graphs: they're self-contained runs and must never be replayed. A regression test crashes and resumes a parent graph around `run_edit`; without the fix it returns the old input.

Lessons:
- Durable execution is about *nodes*; anything nested inherits it unless you opt out.
- Impossible timings are a signal. We stopped the run, cleaned the 3 bad results and 5 orphan sessions, and resumed.

## 3. Comparison: paired, and honest about failures
`improvement/experiments/compare.py`:
- **Per-check pass rates** over tasks both versions rendered (like for like).
- **Run-level rates** (completion, technical gate) over *all* tasks. A candidate that stops rendering hard tasks must not look better because they drop out of the averages.
- **Paired per-task differences**, with an unrendered task counting as 0, and a **bootstrap 95% CI** of the mean difference (4,000 resamples, seeded). Pairing matters because tasks differ from each other far more than versions do; comparing each task with itself removes that variance.
- Runs with different evaluator or dataset versions are refused as not comparable.

## 4. Regression gates
A candidate is **eligible** for a human decision only if:

| kind | rule |
|---|---|
| critical | completion rate and technical-gate rate don't drop; no task that rendered before fails to render now |
| regression | no non-targeted check drops more than 10 points; the validation split's mean doesn't drop more than 2 points; paired mean difference ≥ 0 |
| improvement | at least one *targeted* check improves ≥ 10 points |

**Advisory checks** never block. They're computed, not hand-picked: any check whose verdict flipped on more than 15% of re-evaluations of identical renders (from `--reevaluate`). Today that's `visual.framing` (6/23).

The thresholds are coarse on purpose. With 24 tasks, one task flipping a check moves it 4–6 points, so tighter gates would mostly measure noise. **Transient provider errors** (503 "high demand") are not agent failures; the runner retries them once at the end, otherwise a flaky API would show up as a critical "no longer renders" regression.

## 5. First real cycle
(filled in from the run: see the experiment report in `benchmarks/results/experiments/`)

## Try this
1. `uv run python -m improvement.cli status`: versions, experiments, promotions.
2. Read the latest `benchmarks/results/experiments/*-report.md`. Would you approve it? What evidence is missing?
3. Write a candidate by hand: register `AgentConfig(policy=AgentPolicy(snap_cuts="word"))` with `registry.register(...)` and run `benchmarks.runner --agent-version <it> --split development`.
4. Change `MIN_TARGET_GAIN` to 0.05 and recompute the gates on the stored comparison. How many more candidates would pass, and how many of those would be noise?
