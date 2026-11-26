# Architecture (v0 — Phase 0)

Modular monolith + background workers (PRD §7.1). Phase 0 implements the perception spike, schemas, and the first graph.

```
           ┌──────────── apps/web (Next.js) ───────────┐
           │ dashboard · upload · preview · eval/exp UI │
           └───────────────────┬────────────────────────┘
                               │ HTTP
           ┌───────────────────▼────────────────────────┐
           │ services/api (FastAPI)                      │
           └───────┬───────────────────────┬────────────┘
                   │ enqueue (RQ/Redis)    │ SQL (Postgres)
           ┌───────▼────────┐      ┌───────▼────────┐
           │ services/worker│      │  DB: projects, │
           └───────┬────────┘      │ scenes, tl_ver,│
                   │               │ evals, exps…   │
   ┌───────────────┼───────────────┴────────────────┐
   │ perception/  → MediaContext (scenes+transcript+audio+visual)
   │ agent/graphs → editing · evaluation · memory · improvement (LangGraph)
   │ editing/     → Timeline schema + typed operations + validators
   │ rendering/   → Timeline → ffmpeg argv (deterministic)
   │ evaluation/  → deterministic + model-assisted evaluators
   └───────────────────────────────────────────────────────────────
   models: config/models.py (Ollama by default; provider-swappable)
   tracing: LangSmith
```

## Key invariants
1. **LLMs never produce shell or ffmpeg commands.** They produce typed objects (plans, actions), which are validated (`editing/timeline/schema.py`) before anything runs.
2. **Source media is immutable.** Originals live in `samples/raw/`, and every derived file is new.
3. **Every model is behind `get_chat_model(role)`.** Providers can be swapped and versions recorded.
4. **Evaluation is independent of editing.** The evaluator gets separate prompts, separate model config, and is versioned on its own.

## Phase 0 data flow
`video → probe → PySceneDetect → (wav → silencedetect + ebur128 + faster-whisper) → per-scene frame → vision LLM → MediaContext JSON → hello_graph (LangGraph) → summary`

## Phase 2 additions
```
POST /projects/{id}/edits ─► editing_sessions(queued) ─► RQ ─► run_editing_session
   load_edit_context (scenes S1..Sn, transcript sentences, word timings, hybrid search)
   ensure_style_profile(reference)            ─► style_profiles
   editing graph (LangGraph) ── DbRecorder ──► timeline_versions (every change), agent_actions (every attempt)
   render_version ─► rendering/ffmpeg (Timeline → argv + graph.txt + overlay.ass) ─► renders(meta: hashes, versions)
```
Invariants added:
- every timeline change is a new immutable version;
- every attempted action is logged, including rejected ones;
- a session stores its agent version (prompt hash), model ids, plan and LangSmith `trace_id`.

## Phase 3 additions
```
render ─► enqueue_evaluation (separate RQ job) ─► evaluation graph (LangGraph, parallel branches)
            extract_features(render file: probe, black/freeze/silence, loudness, cuts, ASR of output, frames)
            ├ technical ├ temporal ├ captions ├ style ├ required_content ├ judge ×3 (judge model)
            └► aggregate ─► evaluations (+ report JSON) and evaluation_issues (one row per failed check)

benchmarks/{development,validation,holdout}/*.yaml ─► benchmarks/runner.py
            per task: editing session ─► render ─► evaluation ─► results/<run>.json + .md
            ─► LangSmith dataset `sivg-bench` + one experiment per run (prefix = agent version)
```
Invariants added:
- `evaluation/` never imports the agent (enforced by a test);
- holdout tasks load only with `allow_holdout=True`;
- every report records evaluator version, judge model and timeline hash.

## Phase 4 additions
```
edit request ─► context_tags(scenes, instructions) ─► memory.retrieval (active + session prefs, conflicts resolved)
            ─► editing graph (prompt gets preference lines) ─► editing_sessions.memory_used (exact prefs used)
            └► before every action: rules predictor ─► action_predictions (mode=online)

POST /edits/{id}/feedback ─► memory graph (LangGraph + PostgresSaver)
            receive ─► extract (planner, structured) ─► update (candidate / reinforce / contradict / session-only)
            ─(needs confirmation)─► ask: interrupt() ─► API returns questions
POST /memory/confirmations/{thread} ─► Command(resume=answers) ─► apply_answers ─► finish
            every change ─► preference_events (audit trail)

agent_actions ─► agent/prediction/evaluate.py (rules, markov, logreg, LLM; GroupKFold by session) ─► action_predictions (offline)
```
Invariants added:
- a single correction never becomes an active preference; activation needs creator confirmation;
- rejected preferences are never re-proposed; session-scoped feedback never leaves its session;
- every preference change is an event with its evidence (feedback id, quote);
- holdout benchmark sessions are never used to train or evaluate predictors.

## Phase 5 additions
```
agent_versions (registry: config JSON + hash; one active) ─► worker / benchmark runner pin a version per session

improvement graph (LangGraph + PostgresSaver, thread improve-<uuid>)
  collect      evaluation_issues + unrendered sessions of the active version, development split only
  diagnose     rule clusters ─► embedding sub-clusters ─► evidence + probes (edge origin, captions,
               duration, counterfactual snap replay) ─► improver model ─► Diagnosis (root causes)
  propose      diagnoses + experiment history ─► CandidateProposal (knob values + prompt addenda only)
  experiment   baseline vs candidate on development + validation, interleaved per task (creator isolation)
  gates        paired comparison + bootstrap CI ─► critical / regression / improvement gates
  final_assessment   holdout, only after gates pass (improvement/experiments/holdout.py is the only reader)
  approval     interrupt() ─► CLI `approve|decline` or POST /improvement/experiments/{id}/decision
  decide       registry.promote(): retire old, activate new, promotions row, agent/configs/<version>.json

side entries (same graph, same gates/holdout/approval):
  retest   after a code fix      update_state(as_node="propose")
  rescore  after an evaluator fix (deterministic checks only, stored renders)  update_state(as_node="experiment")
  submit   human-written candidate (origin=human)
```
Invariants added:
- the improvement loop changes configuration (knobs, prompt addenda), never code;
- diagnosis reads development only; holdout is read only by `holdout.py` (AST-enforced test);
- runs are compared only when version, evaluator, dataset, splits, models and creator isolation match;
- promotion needs a human decision, passed gates, and an unchanged active baseline;
- scoped candidates (knob `scope`) are gated on in-scope tasks against an in-experiment A/A control
  (out-of-scope tasks run baseline code); flips must beat the control's rate (binomial tail, alpha 0.05);
- editing and evaluation graphs compile with `checkpointer=False` so a resumed parent never replays them.

## Phase 6 additions
```
apps/web (Next.js, :3010)  ──fetch/CORS──►  services/api (FastAPI, :8010)  ──enqueue──►  RQ worker
  /                       projects                                         processing, edit, render, evaluate
  /projects/[id]          upload (XHR progress), assets+stages, new edit, scene search
  /edits/[id]             preview ◄─ /renders/{id}/video (HTTP range)
                          timeline + issue markers (evidence in output seconds), versions, evaluation,
                          evaluation diff, feedback ─► memory graph (interrupt → confirm in UI), action log
  /memory                 preferences, pending confirmations
  /improvement            versions, promotions, experiments, failure clusters
  /improvement/experiments/[id]   gates, scoped comparison + A/A control, holdout, approve/decline
                                  ─► POST /decision resumes the improvement graph's interrupt
  /improvement/compare    config diff between versions + the experiments that compared them
```
- The browser polls while jobs run (`useApi` with a data-dependent delay); there's no push channel.
- The UI and the CLI resume the same LangGraph checkpoints, so a decision taken in one shows up in the other.
