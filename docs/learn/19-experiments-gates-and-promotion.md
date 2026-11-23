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
- `propose`: one structured `CandidateProposal` (hypothesis, target checks, knob values, addenda, expected effect, risks). Its targets must be checks that were actually diagnosed, and every knob its text mentions must actually be set. If one isn't, the proposal goes back to the model with the mismatch; if it's still inconsistent, the step fails instead of testing something other than what it describes.
- `experiment`: runs baseline and candidate on **development + validation** with identical inputs, **interleaved task by task** (B,C then C,B, …), with a fresh baseline each time. Round 2 showed why (section 5).
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

## 5. Real cycles
Reports: `benchmarks/results/experiments/<id8>-report.md`.

### Round 1: rejected (`89615a10`)
Diagnosis picked the top 3 clusters: narrative.structure, caption_match and shot_length_similarity. The proposal combined three changes: `snap_cuts=sentence`, `captions_follow_reference=true`, and a planner rule "align in/out points to sentence boundaries".

| | baseline v0.2 | candidate | |
|---|---|---|---|
| completion | 95.8% | 87.5% | **critical**: pc-02 and pc-06 stopped rendering |
| validation mean | 0.662 | 0.540 | regression (> 2 points) |
| paired mean Δ | | −0.052 (CI −0.154 … +0.025) | regression |
| narrative.structure (target) | 5% | 14% | +10: on the threshold, not a clear gain |
| cut_through_word (not targeted) | 52% | 81% | +29 |

The gates rejected the candidate even though several checks improved. That's the point of gates: the gains came with two edits that no longer rendered. The pc-02 log shows why. Each duration repair moved clips to an exact length, then sentence snapping moved the edges again: 25.8 → 15.9 → 30.0 → 19.0 s, until repairs ran out. **Two good ideas fought each other.** That led to a new knob, `snap_repairs` (repair actions snap only to word gaps), and to *experiment history*: the next proposal sees earlier candidates, their gate results and the logs of tasks that stopped rendering.

### What the cycle exposed in the harness itself
1. **Nested-graph replay** (section 2): resumed runs reused other tasks' results.
2. **Memory leakage**: benchmark tasks ran as the demo creator, so 20 of 24 baseline tasks silently had that creator's three remembered preferences. One of them was "add captions", which is also why rs-01 kept captions. Now each task runs as its own creator, `bench-<task id>`. Runs record `creator_isolation: true`, and `comparable()` refuses runs without it. Round 1 is still internally fair (both versions had the same memory), but its baseline can't be reused.
3. **Agent variance**: re-running the *same* v0.2 baseline with clean memory, if-02 failed to render, although it rendered before. With one run per version, the critical rule "no task newly fails" is noise-sensitive: a candidate can be rejected for a coin flip that the baseline also makes. The honest fix is several runs per version and a rule over failure *rates*. That needs about 3× the quota, so today we accept the conservative bias: a good candidate may be rejected, but a bad one won't be promoted.

### Round 2: rejected (`9f1e5c7f`), and what it taught about noise
This time diagnosis covered the top 5 clusters on clean (isolated) data, and the proposal saw round 1's history. The hypothesis read well: *"enable captions_follow_reference and set snap_cuts to word with snap_repairs to word"*, which avoids the sentence-snapping fight. But the structured answer set **only** `captions_follow_reference`. The snap fields were null, so they were silently dropped. Structured output guarantees the *shape* of an answer, not that its parts agree. Fix: `unset_knobs()` checks for this and sends the proposal back (see `propose` above).

That accident turned the run into a natural experiment. `captions_follow_reference` can only act on the 4 tasks with a reference video, so on the other 20 the two versions behave **identically**: an A/A test. The gates still saw:

| check | baseline | candidate | |
|---|---|---|---|
| style.caption_match (target, 4 tasks the knob acts on) | 0% | **100%** | real: the knob works |
| temporal.cut_through_word (target) | 52% | 65% | **+13 with no relevant change: noise** |
| temporal.repeated_footage | 100% | 74% | **−26 on 6 tasks the knob can't touch: noise** |
| technical.black_frames | 91% | 78% | noise |

The 6 repeated-footage failures all fell on the candidate. Across the five v0.2-equivalent runs we have, that check failed on 3, 0, 0, 0 and 6 tasks. The failures cluster **by run, not by task**: the candidate ran last, in the afternoon, with more 503 retries and more repairs (2.4 vs 1.9 per task). Tasks inside one run aren't independent, because they share provider conditions. So a per-task sign test (6–0, "p ≈ 0.03") is overconfident. The gate rejected the candidate for the wrong reason, and could just as easily have *accepted* one for the wrong reason, since cut_through_word's +13 cleared the improvement threshold without any change that could cause it.

Fix: **interleave**. `run_pair()` runs each task under both versions back to back, alternating which goes first, so drift in the provider during the day hits both versions equally. The holdout assessment does the same. What interleaving can't fix is the agent's own randomness. With one run per version, ±10–15 points on a single check is within noise, so the per-check gates stay coarse, and a candidate is only worth promoting if its gain is large and on the tasks it can actually affect.

Also fixed: on `--resume`, a re-evaluated task kept yesterday's `daily_quota` flag, so the runner stopped immediately with a false "quota exhausted".

## Try this
1. `uv run python -m improvement.cli status`: versions, experiments, promotions.
2. Read the latest `benchmarks/results/experiments/*-report.md`. Would you approve it? What evidence is missing?
3. Write a candidate by hand: register `AgentConfig(policy=AgentPolicy(snap_cuts="word"))` with `registry.register(...)` and run `benchmarks.runner --agent-version <it> --split development`.
4. Use round 2 as an A/A test: for the 20 tasks without a reference, count per-check flips between `9f1e5c7f-baseline-dev-val.json` and `9f1e5c7f-candidate-dev-val.json`. That's the noise floor for one run per version. Which gate thresholds does it violate?
5. Change `MIN_TARGET_GAIN` to 0.05 and recompute the gates on the stored comparison. How many more candidates would pass, and how many of those would be noise?
