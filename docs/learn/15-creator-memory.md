# 15 — Creator memory: cautious, contextual, auditable

Code: `memory/` (extraction, context, storage, retrieval), `agent/graphs/memory_graph.py`, `services/api/routes/memory.py`.

## A preference is not a sentence, it's a record
| field | why |
|---|---|
| `category`, `attribute`, `value` | `caption_position = top`. Conflicts are exact: same attribute, different value |
| `statement` | what the planner and the creator read |
| `context` | `["interview"]` = only for interview-like sessions; `[]` = everywhere |
| `source` | explicit (settings) / feedback / inferred |
| `status` | candidate → active; session; rejected; stale |
| `confidence`, `support_count`, `contradict_count` | how much to trust it |
| `evidence`, `last_seen_at`, `confirmed_at` | where it came from, and recency |
| `preference_events` | an append-only audit log of every change, with confidence before and after |

## The learning policy (the important part)
| event | effect |
|---|---|
| creator states it in settings | active, 0.90 |
| feedback, general wording ("always", "never") | candidate 0.50 → **ask now** |
| feedback, a plain correction | candidate 0.35, **never applied** |
| the same thing seen again in another session | +0.15, support +1 → at 2, **ask** |
| contradicted | −0.25; an active one below 0.5 → stale |
| creator confirms / rejects | active (≥ 0.85) / rejected, and never re-proposed |
| feedback about *this* video ("for this one…") | `session` scope: applies to that session only |

This implements the PRD's acceptance criteria literally:
- *a single correction does not become a permanent preference*: `test_single_correction_is_not_applied_until_reinforced_and_confirmed`;
- *contextually irrelevant preferences are not applied*: the context filter;
- *updates are auditable*: `GET /creators/me/preferences/{id}/events`.

## Retrieval and conflict resolution
1. Take the creator's active preferences plus this session's session-scoped ones.
2. Drop any whose `context` doesn't overlap the session's context tags (`talking_head`, `interview`, `b_roll`, `explainer`, `multi_source`, derived from the analysed scenes).
3. For each attribute keep one winner: **session > context-specific > generic**, then confidence, then recency.
4. Record both the winners (`editing_sessions.memory_used`, with the reason) and the dropped ones (with why).

## Seen end to end (Gemini, demo project)
Same instruction ("20–25 s clip about the Europa Clipper launch"), before and after one piece of feedback:

| | edit A (no memory) | edit B (after feedback + confirmation) |
|---|---|---|
| captions | bottom, normal case | **top, ALL CAPS** |
| title card | "Europa Clipper Launch" | **none** |
| memory used | — | 3 preferences |

Feedback text: *"I always want my captions at the top and in all caps, and please never put title cards in my videos. For this one, the ending felt a bit abrupt."*
- Extracted: three general rules (asked to confirm) and one session-only note ("make the ending less abrupt"). The session note was correctly **not** carried into edit B.
- The independent evaluator (`eval-1.1`) checked edit B: **preference satisfaction 3/3**, citing frame evidence such as "captions at 1.0 s ('THE EUROPA CLIPPER MISSION') are entirely in uppercase".

## Try this
1. `curl localhost:8010/creators/me/preferences` and `.../{id}/events`.
2. Give feedback that contradicts an active preference twice and watch it go stale.
3. Add an explicit preference with `"context": ["b_roll"]`, then edit an interview: it shows up under `dropped` with the reason.
