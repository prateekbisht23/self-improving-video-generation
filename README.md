# Self-Improving Video Editing Agent

A multimodal agent that turns raw footage plus natural-language instructions into short-form (9:16) edits, evaluates its own output independently, learns creator preferences, and improves through controlled, evidence-based experiments.

- **Requirements:** [`prd.md`](prd.md)
- **Implementation plan:** [`docs/plan.md`](docs/plan.md)
- **Learning notes:** `docs/learn/` (FFmpeg, scene detection, Whisper, LangChain, LangGraph, LangSmith, ...)

## Stack
Python 3.12 · FastAPI · LangChain · LangGraph · LangSmith · FFmpeg · PySceneDetect · faster-whisper · PostgreSQL · Redis + RQ · Next.js · Ollama (local models by default)

## Status
| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation & technical spike | in progress |
| 1 | Multimodal media intelligence | planned |
| 2 | Editing agent & FFmpeg renderer | planned |
| 3 | Independent evaluation engine | planned |
| 4 | Creator memory & predictive editing | planned |
| 5 | Failure diagnosis & self-improvement | planned |
| 6 | Frontend, integration & demo | planned |
