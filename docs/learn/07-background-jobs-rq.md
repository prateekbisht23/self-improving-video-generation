# 07 — Background jobs with Redis + RQ, and resumable pipelines

Code: `services/worker/{jobs,pipeline,worker}.py`.

## Why background jobs
Analysing a 2-minute video takes 30–90 s: Whisper, plus one vision call per scene. An HTTP request must not wait for that (PRD NFR-07). So:
```
POST /projects/{id}/assets  → validate → save file → INSERT asset(status=queued)
                            → queue.enqueue(process_asset, id) → 201 immediately
worker process              → pops job from Redis → run_pipeline(id) → status=ready|failed
GET  /assets/{id}           → client polls status + per-stage progress
```
**RQ** (Redis Queue) is the simplest Python option. A job is "call this importable function with these arguments", serialised into Redis.

## Retries alone are not enough
`enqueue(..., retry=Retry(max=2, interval=[15, 60]))` re-runs a failed job after 15 s and then after 60 s. Retries only help if re-running is **safe** and **cheap**:
- **Idempotent stages.** Each stage *replaces* its output (delete + insert in one transaction), so running it twice never duplicates scenes.
- **Checkpointed progress.** `processing_stages` records `done` per stage, and a retry skips finished stages. `test_failure_then_resume` shows `scenes` keeps `attempts == 1` after a retry.
- **Fine-grained resume.** The visual stage commits after *each* scene. If Gemini rate-limits us on scene 9 of 14, the retry starts at scene 9.
- **Isolation.** A failing stage rolls back only its own transaction. Earlier results survive (PRD FR-03).
- **Deliberate re-runs.** `POST /assets/{id}/process?force_from=visual` resets that stage and everything after it, for example after changing the vision prompt.

## macOS gotcha: fork
RQ's default `Worker` **forks** a child process per job. On macOS, forking after Objective-C, gRPC (the Gemini SDK) or CTranslate2 (Whisper) have started threads can crash the child. We use `SimpleWorker`, which runs jobs in the worker process itself. The trade-off is that a memory leak or crash in one job affects the worker. On Linux in production, the forking worker is fine.

## Tests run the same code path, inline
`RQ_SYNC=true` builds `Queue(is_async=False)`, which runs jobs immediately in-process (our test config uses it to call the pipeline inline). Integration tests therefore exercise upload → pipeline → DB without a worker or a sleep.

## Try this
1. Start a worker (`uv run python -m services.worker.worker`), upload a clip, and watch `GET /assets/{id}` move through `queued → processing → ready`.
2. Stop the worker mid-way (Ctrl-C during `visual`), restart it, and call `POST /assets/{id}/process`. Check which stages say `cached` in the worker log.
3. `uv run rq info -u redis://localhost:6380/0` shows queues, workers and failed jobs.

## What actually happened on the first real run
Three clips were processed back to back and needed 60 vision calls in total. The Gemini free tier allows **15 requests/minute per model**, so the 2nd and 3rd clips hit `429 RESOURCE_EXHAUSTED` with 1 scene left each.
1. The visual stage had already committed 16/17 and 35/36 descriptions, and none were lost.
2. RQ's `Retry(interval=[15, 60])` re-ran the jobs. `probe/scenes/audio/transcript/frames` were reported as cached (`attempts` stayed 1), and only the missing scene was described.
3. Supermoon's visual stage completed on attempt 3 and lightning's on attempt 2. All three assets ended `ready`.

Two fixes followed:
- **Don't hit the limit in the first place.** `MODEL_RPM=14` gives each model a LangChain `InMemoryRateLimiter` (a token bucket), shared by every role that uses the same model in the process.
- **Honest status during retries.** The asset was shown as `failed` while a retry was still scheduled. `process_asset` now reports `queued` with `last_error="retrying (n left) after: …"` when RQ will try again.
