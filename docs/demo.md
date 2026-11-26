# Demo walkthrough

A first-time path through the whole system that covers the Phase 6 exit criteria. Allow about 10 minutes.
Most of that time is processing (about 1 min for a 2-minute clip) and the agent's edit, render and evaluation (about 2–4 min).

## Start
```bash
docker compose up -d                                   # Postgres :5433, Redis :6380
uv run alembic upgrade head
uv run python -m services.worker.worker                # terminal 1
uv run uvicorn services.api.main:app --port 8010       # terminal 2
cd apps/web && bun install && bun dev                  # terminal 3 → http://localhost:3010
```

The nav bar shows the active agent version and an **API ok** dot. If the dot is red, the API isn't running. If an edit stays at "Waiting for a worker…", the worker isn't running.

## 1. Create a project
On **Projects**, give the project a title and click **Create project**.

## 2. Upload footage
Click **Upload video…** and pick `samples/nasa_interview.mp4` (any 1 s–10 min video works).

The row moves from *queued* to *processing* to *ready*. The stage chips show the pipeline: probe → scenes → audio → transcript → frames → visual → index.

Optionally upload a second video as **reference**, and the agent will match its pacing, captions and colour.

Once processing is done, **What the agent sees** lets you search the analysed scenes ("rocket", "talking about the moon"). That is the same index the planner uses.

## 3. Describe the edit
Under **New edit**, write instructions. For example: *A 20–25 second short about why this mission matters: open with the strongest statement, keep complete sentences, captions on.* Set the length window and click **Generate edit**.

## 4. Generate the video
The edit page shows the agent working, step by step. When it finishes:
- **Preview** plays the 9:16 render.
- **Timeline** shows the clips (coloured by source, hover for source in/out and the agent's reason for each), the captions, and evaluation issues as red marks. Click anywhere on it to seek.
- **Version history** lists every version the agent saved. Any version can be rendered. A version outside the length target is refused, with the reason.

## 5. Inspect the evaluation
The evaluation appears about a minute after the render:
- the pass rate;
- whether the technical gate passed;
- pass rates per quality dimension;
- every failed check, with its kind (deterministic, signal or model), severity, message and explanation.

Evidence chips carry timestamps, and clicking one jumps the preview to that moment. With two or more evaluated versions, **Compare versions** shows which checks flipped between them.

## 6. Give feedback
Under **Feedback**:
- choose **Accept** or **Reject**, or
- pause the preview and send **Issue at a moment** with "now", or
- send a **Correction** such as "captions at the top".

The memory graph reads the feedback and reports what it learned. If it wants to keep a new preference, it asks first ("Remember it" / "No"). All learned preferences, their confidence and their history are on **Memory**.

## 7. Inspect an improvement experiment
**Improvement** shows:
- agent versions;
- promotions (with the approver's note and a link to the evidence);
- every experiment;
- the latest failure clusters with their diagnoses.

Open experiment `01098cc0`. It has:
- the candidate's hypothesis and knob changes;
- the regression gates, with notes on what didn't gate and why;
- baseline vs candidate, *in scope* or across *all tasks*, next to the A/A control's flip counts;
- per-task paired differences;
- the held-out result;
- the decision.

An experiment that is awaiting approval shows **Approve & promote** / **Decline** here. Starting a new round takes a long time, so it stays on the command line:

```bash
uv run python -m improvement.cli start
```

## 8. Compare agent versions
**Compare versions** diffs two versions' configurations, for example v0.2 against v0.3: `captions_follow_reference false → true`, `trim_black → when_captions_skipped`. It also links the experiment that justified the change. The editor page shows which agent version produced each edit.
