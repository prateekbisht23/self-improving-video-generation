# Implementation Plan: Self-Improving Video Editing Agent

## Context
`prd.md` describes a 6-phase MVP: an agent that understands raw footage, plans and renders 9:16 short-form edits with FFmpeg, evaluates its own output, remembers creator preferences, and improves through controlled experiments (LangChain / LangGraph / LangSmith, FastAPI, Next.js, Postgres, Redis+RQ). The project is also a learning vehicle for these technologies.

Working agreements:
- **Learning notes:** each key topic gets a `docs/learn/NN-<topic>.md` note with a "try this" exercise.
- **Pacing:** one phase at a time, stopping at each phase's exit criteria.
- **Models: free by default.** Everything runs locally through Ollama. All model calls go through one factory, so switching to a hosted API (e.g. `ANTHROPIC_API_KEY`) only means changing `.env`. LangSmith's free Developer plan covers tracing.
- **Footage:** a few clips with clear licenses (public domain / CC: NASA, Wikimedia Commons, Internet Archive, Pexels), each recorded in a manifest, plus synthetic FFmpeg clips for deterministic tests.

Target machine: Apple Silicon, 16 GB RAM, ffmpeg, docker, Ollama, uv, bun. Python is **pinned to 3.12 via uv** (newer versions lack some ML wheels).

## Recommended local model setup (16 GB)
| Role | Default (Ollama) | Why |
|---|---|---|
| planner / reasoning | `qwen3:8b` | good structured (JSON/tool) output at 8B |
| vision (scene descriptions) | `qwen2.5vl:7b` (fallback `gemma3:4b`) | frame → description/tags |
| judge (model-assisted evals) | same as planner, at temperature 0 | independent prompt and version |
| embeddings | `nomic-embed-text` | scene search, failure clustering |
| ASR | faster-whisper `small`, int8 on CPU | local, gives word timestamps |

Factory: `config/models.py::get_chat_model(role)` wraps `langchain.chat_models.init_chat_model` with `MODEL_<ROLE>=provider:model` env vars (for example `ollama:qwen3:8b` or `anthropic:claude-sonnet-5-5`).

## Step 0 — Repository
- Public GitHub repo; commit and push at the end of each phase and at meaningful milestones.
- `.env` is git-ignored (only `.env.example` is committed); downloaded media are git-ignored, only the license manifest is committed.

## Phase 0 — Foundation
Repo layout follows PRD §10. Create only what Phase 0 needs:

1. **Repo and environment**
   - `git init`, `.gitignore` (media, `.env`, `data/`).
   - `pyproject.toml`: uv, Python 3.12, ruff, pytest.
   - Dependencies: fastapi, uvicorn, pydantic, sqlalchemy, alembic, psycopg, rq, redis, langchain, langgraph, langchain-ollama, langsmith, scenedetect[opencv], faster-whisper, numpy.
   - `docker-compose.yml` runs Postgres 16 and Redis 7.
   - `.env.example`: `MODEL_*`, `OLLAMA_BASE_URL`, `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DATABASE_URL`, `REDIS_URL`.
2. **Sample media**
   - `scripts/fetch_samples.py` reads `samples/manifest.yaml` (url, license, attribution, sha256), downloads 3–4 clips of 30–120 s with speech, and normalizes them to mp4.
   - `scripts/make_synthetic.py` builds deterministic clips with FFmpeg (`testsrc2` scenes, hard cuts, a black segment, silence gaps, and `say`-generated speech). These clips also serve as fixtures for the Phase 3 evaluators.
3. **Perception prototype** (pure functions: path in, pydantic out)
   - `perception/video/probe.py`: runs `ffprobe -print_format json` and returns `MediaMetadata` (duration, resolution, fps, aspect ratio, streams).
   - `perception/video/frames.py`: extracts a representative frame per scene (`ffmpeg -ss … -frames:v 1`).
   - `perception/scene_detection/detect.py`: uses PySceneDetect `ContentDetector` and returns `Scene[]`.
   - `perception/audio/extract.py`: produces 16 kHz mono wav. `silence.py` parses `silencedetect` output. `loudness.py` uses `ebur128` (LUFS).
   - `perception/audio/transcribe.py`: faster-whisper with word timestamps.
   - `perception/models/describe.py`: the vision model returns a `SceneDescription` (description, tags) through `with_structured_output`.
   - `perception/context.py`: merges scenes, transcript and audio into `MediaContext` JSON.
   - CLI: `python -m perception.context <video> -o out/context.json`.
4. **Schemas**
   - `editing/timeline/schema.py`: Timeline v0 (output spec 1080×1920; video, audio and caption tracks; clips with `asset_id` and `src_in`/`src_out`). Validators check boundaries against asset duration.
   - `benchmarks/schemas/task.py`: `BenchmarkTask` (source, instructions, reference, hard constraints, expected checks, split), plus one example YAML.
5. **LangChain / LangGraph / LangSmith hello**
   - `agent/graphs/hello_graph.py`: a `StateGraph` that loads a MediaContext, summarizes it with the planner, uses a conditional edge (no speech goes to a visual-only summary), then ends.
   - Runs with `LANGSMITH_TRACING=true`, so nodes and LLM calls show up as one trace.
6. **App skeletons**
   - `services/api/main.py`: FastAPI with `/health`, plus a DB ping.
   - `apps/web`: `bunx create-next-app` (TypeScript, app router) with one page that calls `/health`.
7. **Tests**
   - `tests/unit/`: probe, silence parsing, scene count on the synthetic clips, and timeline validation (out-of-bounds clip rejected).
8. **Learning notes**
   - `docs/learn/01-ffmpeg-ffprobe.md`: streams, `-ss` placement, filtergraphs, silencedetect/ebur128.
   - `02-scene-detection-and-whisper.md`
   - `03-langchain-models-and-structured-output.md`
   - `04-langgraph-state-nodes-edges.md`
   - `05-langsmith-tracing.md`
   - Plus `docs/architecture.md`, a first version.

## Later phases (each ends at the PRD exit criteria and adds learn notes)
- **P1 Media intelligence:**
  - SQLAlchemy models + Alembic (projects, media_assets, scenes, transcripts).
  - Upload API.
  - RQ jobs with staged, idempotent processing and retries.
  - Scene embeddings for text search.
  - *Learn:* Alembic, RQ, idempotent pipelines, embeddings.
- **P2 Editing agent + renderer:**
  - Typed editing tools (PRD FR-06 table).
  - Timeline versioning.
  - FFmpeg renderer that compiles a validated timeline into a filtergraph (trim/concat, crop/scale to 9:16, `xfade`, `subtitles`/ASS captions, `volume`/`loudnorm`). It is built as an argv list, never a shell string.
  - Editing graph (PRD §7.2A).
  - Reference style profile.
  - *Learn:* complex filtergraphs, LangChain tool calling, LangGraph loops and budgets.
- **P3 Evaluation:**
  - At least 5 deterministic checks (duration, resolution/aspect, `blackdetect`, audio presence, loudness, repeated footage).
  - At least 4 model/signal-assisted evaluators (instruction adherence, narrative, caption WER via jiwer, style similarity).
  - Evaluation graph.
  - 30-task benchmark with 18/6/6 splits.
  - LangSmith datasets and experiments.
  - *Learn:* LLM-as-judge pitfalls, LangSmith `evaluate()`.
- **P4 Memory + prediction:**
  - Preference store with confidence, recency and evidence.
  - Memory graph with a human-confirmation `interrupt`.
  - Next-action predictors (rules, LLM, and a small sklearn classifier) with top-1/top-3 metrics.
  - *Learn:* LangGraph checkpointer and interrupts, the Postgres checkpointer.
- **P5 Self-improvement:**
  - Failure clustering (rules, then embeddings + HDBSCAN/k-means).
  - Diagnosis.
  - Candidate prompt/policy versions.
  - Experiment runner.
  - Regression gates.
  - Human-approved promotion. The holdout split is enforced at the data-access layer.
- **P6 Frontend + demo:**
  - Next.js dashboard, editor view, evaluation view and improvement view.
  - End-to-end docs and demo.

## Verification (Phase 0 exit criteria)
1. `docker compose up -d`, then `uv sync`, then `uv run pytest tests/unit`. All tests pass.
2. `uv run python scripts/make_synthetic.py && uv run python scripts/fetch_samples.py`. Clips appear in `samples/`, and their licenses are recorded.
3. `uv run python -m perception.context samples/<clip>.mp4 -o out/context.json`. The output has ordered scenes inside the clip's duration, word-timestamped transcript, silence ranges, LUFS, and a description and tags per scene.
4. `uv run python -m agent.graphs.hello_graph out/context.json`. It prints a summary, and the trace (nodes plus LLM call) is visible in LangSmith. Requires a (free) LangSmith API key.
5. `uv run uvicorn services.api.main:app` serves `/health` with `db: ok`, and `bun dev` in `apps/web` shows it.

## Prerequisites
- A free LangSmith API key in `.env`.
- Ollama models pulled (about 12 GB total).
