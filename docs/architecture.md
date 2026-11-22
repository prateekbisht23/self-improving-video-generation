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
