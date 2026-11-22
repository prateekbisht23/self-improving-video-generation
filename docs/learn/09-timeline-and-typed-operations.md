# 09 — The timeline and typed editing operations

Code: `editing/timeline/schema.py`, `editing/operations/__init__.py`, `editing/captions.py`.

## Why a timeline instead of "let the LLM write ffmpeg"
An ffmpeg command written by an LLM is unvalidatable, unreproducible, and a shell-injection risk. Instead:
```
LLM → EditPlan (structured output) → typed operations → Timeline (validated data) → renderer → ffmpeg argv
```
The `Timeline` is plain data. You can diff it, hash it, version it, re-render it, and show it in a UI.

## Two clocks
- **Source time**: seconds inside an asset (`src_in`, `src_out`).
- **Timeline time**: seconds in the output, used for captions and titles.

A transition *overlaps* adjacent clips, so clip *i* starts at `start(i-1) + dur(i-1) − transition(i)`. That's `Timeline.clip_starts()`, and every caption calculation depends on it.

## The operation contract
Each operation in `OPERATIONS` has:
1. a **Pydantic input schema**. Its docstring and field descriptions double as the LLM tool description.
2. a **pure function**, `(timeline, args, ctx) → new timeline`. It works on a deep copy and never mutates.
3. **whole-timeline re-validation** afterwards (asset bounds, transition lengths, overlays inside the duration).
4. a structured `ActionResult` with an **actionable error**, such as `no clip at index 7; timeline has 3 clips (0-2)`. The repair loop feeds that error straight back to the model.

So "invalid operations cannot modify the timeline" (PRD FR-06) is enforced by construction, and `test_invalid_actions_leave_timeline_unchanged` checks the content hash before and after.

## Derived tracks stay consistent
Captions generated from the transcript (`captions_source="transcript"`) are **regenerated** after any clip change, so reordering clips can't leave captions on the wrong footage. Titles and manual captions are clamped to the new duration.

## Word-synced captions
`timeline_words` maps each Whisper word from source time onto the timeline: a word belongs to the clip containing its midpoint. `build_captions` then chunks the words into cards:
- at most `max_words` words per card;
- break at punctuation, at pauses over 0.6 s, and **at every cut** (a card must never straddle two shots);
- glue Whisper's split tokens back together: `six` + `-year` becomes "six-year".

## Versioning
Every successful operation creates a `timeline_versions` row with the full JSON, a `content_hash` (sha256 of canonical JSON) and its parent. Every attempt, including rejected ones, goes into `agent_actions` with its source (`plan`, `repair`, `fixup` or `user`) and workflow stage. Phase 4's next-action predictor trains on that log.

## Try this
1. `curl localhost:8010/edits/<id>` and read `actions`. Find a rejected one and its error.
2. `curl -X POST localhost:8010/edits/<id>/actions -H 'content-type: application/json' -d '{"name":"reorder_clips","args":{"order":[1,0,2]}}'`, then compare `GET /edits/<id>/timeline?version=N` across versions.
3. Try an invalid op (`{"name":"trim_clip","args":{"index":99}}`) and confirm no new version appears.
