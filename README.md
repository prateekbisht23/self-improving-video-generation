# Self-Improving Video Editing Agent

A multimodal agent that turns raw footage plus natural-language instructions into short-form (9:16) edits, evaluates its own output independently, learns creator preferences, and improves through controlled, evidence-based experiments.

- **Requirements:** [`prd.md`](prd.md)
- **Implementation plan:** [`docs/plan.md`](docs/plan.md)
- **Learning notes:** `docs/learn/` (FFmpeg, scene detection, Whisper, LangChain, LangGraph, LangSmith, ...)

## Stack
Python 3.12 · FastAPI · LangChain · LangGraph · LangSmith · FFmpeg · PySceneDetect · faster-whisper · PostgreSQL · Redis + RQ · Next.js · Ollama (local models by default)

## Quickstart
Requires an ffmpeg with libass/freetype for captions (see [`docs/learn/01-ffmpeg-ffprobe.md`](docs/learn/01-ffmpeg-ffprobe.md)).

```bash
cp .env.example .env            # add LANGSMITH_API_KEY
docker compose up -d            # Postgres :5433, Redis :6380
uv sync
ollama pull qwen3:8b && ollama pull qwen2.5vl:7b && ollama pull nomic-embed-text

uv run python scripts/make_synthetic.py     # deterministic test clips
uv run python scripts/fetch_samples.py      # licensed sample footage
uv run pytest

uv run alembic upgrade head
uv run python -m services.worker.worker              # background processing (separate terminal)
uv run uvicorn services.api.main:app --port 8010     # API docs: http://localhost:8010/docs

# upload footage -> processed in the background
curl -X POST localhost:8010/projects -H 'content-type: application/json' -d '{"title":"demo"}'
curl -F file=@samples/nasa_interview.mp4 localhost:8010/projects/<project_id>/assets
curl localhost:8010/assets/<asset_id>                         # status + per-stage progress
curl "localhost:8010/projects/<project_id>/search?q=moon"     # hybrid scene search

# ask the agent for an edit -> plan, validated actions, versions, render
curl -X POST localhost:8010/projects/<project_id>/edits -H 'content-type: application/json' \
  -d '{"instructions":"20-25s teaser that opens with the launch news, with captions","min_duration":20,"max_duration":25}'
curl localhost:8010/edits/<edit_id>                           # plan, actions, versions, renders, trace_id
curl -o edit.mp4 localhost:8010/renders/<render_id>/video
curl localhost:8010/edits/<edit_id>/evaluations              # independent evaluation (auto after render)

# benchmark (needs a "Benchmark v1" project with samples/*.mp4 uploaded and processed)
uv run python -m benchmarks.runner --split development validation
uv run python -m benchmarks.runner --split holdout --allow-holdout   # final assessment only

# standalone (no DB) analysis + first graph
uv run python -m perception.context samples/nasa_interview.mp4 -o out/nasa_interview.json
uv run python -m agent.graphs.hello_graph out/nasa_interview.json
cd apps/web && bun dev                      # http://localhost:3000
```

Sample footage credits: see [`samples/manifest.yaml`](samples/manifest.yaml).

## Status
| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation & technical spike | done |
| 1 | Multimodal media intelligence | done |
| 2 | Editing agent & FFmpeg renderer | done |
| 3 | Independent evaluation engine | done |
| 4 | Creator memory & predictive editing | done |
| 5 | Failure diagnosis & self-improvement | planned |
| 6 | Frontend, integration & demo | planned |
