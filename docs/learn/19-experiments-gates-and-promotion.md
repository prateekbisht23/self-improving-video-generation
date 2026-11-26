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
| critical | completion rate and technical-gate rate don't drop; no task that rendered before fails to render now, **confirmed by one re-run** of the candidate (a task that renders on the re-run is reported as flaky) |
| regression | no non-targeted check drops more than 10 points **on at least 2 tasks**; the validation split's mean doesn't drop more than 2 points; paired mean difference ≥ 0 |
| improvement | at least one *targeted* check improves ≥ 10 points **on at least 2 tasks** |

Tasks that hit an **infrastructure error** (network, provider exception) on either side are excluded from the comparison and listed; they say nothing about the agent.

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

### Round 3: rejected (`03fbf7cf`), and two real bugs in a knob
The proposal was finally consistent: `snap_cuts=word` and `captions_follow_reference=true`, run interleaved. It needed two quota days. The resume worked as designed, with `diagnose` retrying a 503 and the experiment continuing its results files.

| | baseline | candidate |
|---|---|---|
| style.caption_match (target) | 0% | **100%** |
| temporal.cut_through_word (target) | 60% | **75%** |
| completion (infrastructure error excluded) | 95.7% | 91.3%: pc-02 and pc-03 stopped rendering |
| temporal.shot_durations | 65% | 45% (5 tasks vs 1) |

Rejected, and rightly so. Reading the failed sessions showed **two bugs in the snapping code**, not the agent being unlucky:
- **pc-02:** the deterministic fixup trimmed the edit to exactly 25.0 s, the window's upper limit. Word snapping then moved that cut 0.08 s outward into the next word gap: 25.08 s, outside the window, so the task failed.
- **shot_durations:** snapping moves an edge up to ~1 s, and that's enough to stretch a planned ~12 s clip past the 12.5 s shot limit.

Fix (`_snap_breaks` in the editing graph): snapping is a refinement, so it **must never break a constraint that the unsnapped action satisfies**. `execute` applies both versions (operations are pure) and keeps the snap only if total duration stays in its window and no clip becomes longer than the max shot. A human wrote this; the improvement loop only turns knobs. And because the knob's *behaviour* changed while its *name* didn't, run files now record `code_revision` (git commit, `-dirty` if uncommitted).

The same round produced three more harness changes:
- **Infrastructure errors.** The baseline lost rs-04 to a DNS outage, which counted against the baseline. Such tasks are now excluded on both sides.
- **One flip is noise.** `style.color_similarity` "regressed" 100% → 67%, but that was 1 task out of 3. `MIN_FLIPS = 2` now applies to regressions and improvements alike.
- **Confirm new failures.** The unchanged baseline failed if-02 in one of three runs, so a single new failure proves little. The candidate is re-run once on each newly failed task, and only a second failure is critical.

**Re-testing after a code fix**: `improvement.cli retest <experiment> --reason "..."` creates a *new* experiment for the same candidate. It enters the graph after `propose` (`update_state(..., as_node="propose")`), so interleaved runs, gates, holdout and human approval all apply unchanged. The record keeps `retest_of` and the reason.

### Retest (`b24e2c29`): the candidate was fine, a check was wrong
The retest ran with the snapping fix (`code_revision` 3394cc4), and this time the knobs did what they promised:

| | baseline | candidate |
|---|---|---|
| style.caption_match (target) | 0% | **100%** |
| temporal.cut_through_word (target) | 43% | **76%** |
| completion | 91.7% | 95.8% (pc-02 failed once, rendered on the confirmation re-run) |
| paired pass rate | | +0.053 (CI −0.06 … +0.17), 13 wins / 4 ties / 7 losses |
| technical.frozen_frames | 100% | **86%**: 3 tasks, so a gating regression |

Rejected again, by a single check. Reading the evidence:
- All three failures were the **same segment, 0.00–2.23 s**, in different tasks.
- All three renders open on the same source shot (11.12 s). `freezedetect` on the *source* shows the moon is nearly still there for about 2.2 s.
- In the baseline, the same opening passed, because word-by-word captions animate over it, so the output never looks frozen. The candidate's own target change (`captions_follow_reference`) correctly removed captions on reference tasks, which exposed the still shot.

So a correct improvement tripped a check meant for **render faults**: a stalled decode, or padded frames. All 10 renders ever flagged by `frozen_frames`, across all versions, turned out to be still shots in the source.

**Fixing the check (evaluator `eval-1.2`):**
- `frozen_check` maps each output freeze back through the timeline (`clip_starts`) to its source ranges and runs `freezedetect` there.
- A freeze counts as a fault unless the source under it is at least 80% static.
- Pieces under 0.25 s are skipped: a freeze ending 0.06 s into the next clip is frame-boundary jitter that `freezedetect` can't judge.
- The source is the full frame and the output a 9:16 crop, so motion outside the crop makes the source look *less* static. That errs toward reporting a fault.
- A unit test keeps the positive control: the same freeze over *moving* source footage still fails.

**Re-scoring instead of re-running** (`improvement.cli rescore <experiment> --check technical.frozen_frames --reason "..."`): the renders didn't change, only the measuring stick did. So re-running the agent would add noise and spend a quota day.
- `rescore_run` recomputes only the named checks on the stored renders of **both** versions, and the confirmation run, then re-aggregates.
- It copies everything else.
- It enters the graph after `experiment`, so gates, a fresh holdout and human approval apply unchanged.

Guards:
- **Deterministic checks only.** Re-running a model judge draws a new sample; that isn't a re-score.
- **The evaluator version must have changed.** Each file records `rescored_from`.
- **Faithfulness first.** Re-aggregating the *stored* check values must reproduce every stored pass rate before anything is changed, the same idea as the replay sanity check in note 18. The first attempt failed on exactly this kind of detail: non-applicable checks are `None`.

Result under `eval-1.2`:
- frozen_frames 100% → 100%, so there are no regressions;
- both targets improved;
- the paired mean is +0.059;
- the candidate is **eligible** and goes to the holdout.

Is fixing a check after it blocked your candidate moving the goalposts? It would be if the fix were "loosen the threshold until it passes". The safeguards here:
- the fix comes with a mechanism (static source);
- it applies to both versions and to every past render;
- it keeps a positive control;
- the final word is a holdout the loop has never seen, plus a human.

**Holdout (`c11acf32`), six tasks never seen by the loop:**

| | baseline | candidate |
|---|---|---|
| paired pass rate | | −0.013 (CI −0.065 … +0.027), 3 wins / 1 tie / 2 losses |
| style.caption_match (target) | 0% | 100% (n=1: only one holdout task has a reference) |
| temporal.cut_through_word (target) | 83% | 83% |
| temporal.shot_durations | 83% | 50% |
| repairs per task | 0.5 | 2.67 |

The development/validation gains didn't show up as a measurable holdout improvement:
- the caption target has a single applicable task;
- the holdout baseline already cuts cleanly (83%), so there is little room to gain.

The cost *did* repeat: shot_durations dropped on dev/val (−10 points) and again on the holdout, and the candidate needs more repairs in both. Two independent samples pointing the same way is the strongest signal in this experiment: word snapping still makes shots longer and edits harder to fit.

That is the point of a holdout. The gates said "eligible"; the holdout says "the benefit isn't established and a cost is". The experiment is `awaiting_approval`, and the decision is a human's.

## Try this
1. `uv run python -m improvement.cli status`: versions, experiments, promotions.
2. Read the latest `benchmarks/results/experiments/*-report.md`. Would you approve it? What evidence is missing?
3. Write a candidate by hand: register `AgentConfig(policy=AgentPolicy(snap_cuts="word"))` with `registry.register(...)` and run `benchmarks.runner --agent-version <it> --split development`.
4. Use round 2 as an A/A test: for the 20 tasks without a reference, count per-check flips between `9f1e5c7f-baseline-dev-val.json` and `9f1e5c7f-candidate-dev-val.json`. That's the noise floor for one run per version. Which gate thresholds does it violate?
5. Change `MIN_TARGET_GAIN` to 0.05 and recompute the gates on the stored comparison. How many more candidates would pass, and how many of those would be noise?
6. Find a still shot in a source with `ffmpeg -ss <t> -t 5 -i source.mp4 -vf freezedetect=n=-60dB:d=0.5 -an -f null -`. Cut it into a timeline without captions and evaluate under `eval-1.2`. Then make a real fault (`tpad=stop_mode=clone:stop_duration=3` on moving footage). Does the check tell them apart?
