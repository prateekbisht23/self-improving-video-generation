# 20 — The frontend: making long-running agent work visible

Phase 6 puts a Next.js app on top of the API. The app has no intelligence of its own. Its job is to make four slow, asynchronous systems easy to read and act on:
- media processing;
- the editing graph;
- the evaluator;
- the improvement loop.

## 1. Client components and one API
Every page is a client component (`"use client"`) that calls FastAPI from the browser.

Next.js could fetch on the server (React Server Components), but here:
- the data changes while you watch: a job is running, a render appears;
- the API already validates everything;
- one origin of truth is easier to reason about than two.

`lib/api.ts` is the only place that does `fetch`. It turns every failure into a message a person can act on:
- **unreachable:** "Is the API running?";
- **422:** FastAPI's `detail` list flattened into `field: message`;
- **409:** the server's sentence, for example "agent is still working on this session".

**CORS.** The browser calls `localhost:8010` from `localhost:3010`, a different origin. The API therefore has to answer with `Access-Control-Allow-Origin`. Because this is a local, single-user tool, any localhost port is allowed (`allow_origin_regex`).

The port moved from 3000 to 3010 because, on this machine, another service owned IPv4 :3000. Next bound only the IPv6 side, and `localhost` resolved differently in different clients: the same "works for me / doesn't for you" trap as API port 8000.

## 2. Polling, not push
Background jobs (RQ) don't notify the browser. `useApi(path, poll)` refetches while there is something to wait for. The delay is a function of the latest data, so polling stops by itself:

```ts
useApi<EditDetail>(`/edits/${id}`, (e) => (WORKING.has(e.status) ? 3000 : null));
useApi<EvaluationSummary[]>(`/edits/${id}/evaluations`, (list) =>
  latestDone && !list.some((x) => x.render_id === latestDone.id) ? 5000 : null);
```

Server-sent events or websockets would be lower latency, but they need the worker to publish progress somewhere the API can stream from (Redis pub/sub). For jobs that take tens of seconds, a 3 s poll is simpler and good enough.

## 3. Evidence you can click
Evaluation checks attach `Evidence(start, end, detail)` in **output** seconds. The editor page uses them in three places:
- each piece of evidence is a button that seeks the `<video>` to that moment;
- failed checks become red marks on the timeline's *issues* track, in the same time base as the clips and captions;
- the playhead follows `timeupdate`, so you can see which clip and caption sit under an issue.

This only works because the evaluator recorded timestamps in the rendered video's time, not the source's. Clip *n* starts at `clip_starts()[n]`, and transitions overlap the previous clip. The TypeScript `clipStarts` reproduces the Python one exactly; if they disagreed, every marker would drift.

## 4. Human-in-the-loop screens are interrupts
Two LangGraph `interrupt()`s now have a UI:
- **Memory confirmation:** feedback runs the memory graph. If it wants to remember something new, it stops and returns questions, which the feedback panel shows ("Remember it" / "No"). Unanswered threads also wait on `/memory`, with a badge in the nav. Answering posts to `/memory/confirmations/{thread}`, which resumes the graph with `Command(resume=answers)`.
- **Promotion:** an experiment at `awaiting_approval` shows Approve / Decline with a required name and an optional note. That posts to `/improvement/experiments/{id}/decision`, which resumes the improvement graph's thread. The CLI and the UI resume the *same* checkpoint, so a decision taken in one shows up in the other.

## 5. Showing an experiment honestly
The experiment page shows the evidence a decision needs:
- the hypothesis and the knob changes;
- the gates, including the notes that explain why something *didn't* gate;
- metrics, per-check deltas and per-task paired differences with the CI.

For a scoped candidate it defaults to the **in-scope** view and puts the A/A control's flip count next to each check. Without that column, "visual.framing 100% → 50%" looks like a regression. With "4/17 flips in the control" beside it, it reads as what it is: noise on 4 tasks.

**Compare versions** diffs the flattened configs (`policy.trim_black: off → when_captions_skipped`) and lists the experiments that compared the two. A version is only a configuration, so the diff *is* the change.

## 6. Testing it like a user
The end-to-end check drives a real browser through the exit criteria:
1. create a project;
2. upload;
3. instruct;
4. render;
5. evaluate;
6. give feedback;
7. open an experiment;
8. compare versions.

One lesson from automating it: a controlled React `<textarea>` only updates state through React's `onChange`. A tool that sets `element.value` directly leaves the DOM showing text while React's state is still `""`, so the submit button stays disabled. Typing real key events works. If a form "has text but won't submit", check React's state, not the DOM.

## Try this
1. Open an edit, pause the preview on a moment you dislike, and send an *Issue at a moment* using "now". Find the row in the `feedback` table: which timeline version and render did it attach to?
2. Click an evidence chip of `temporal.cut_through_word` and listen. Is the cut really mid-word? Do the same for a `narrative.structure` (model) chip. Which kind of evidence do you trust more, and why?
3. Apply an operation by hand (the action log shows names and argument shapes), render the new version, evaluate it, then use **Compare versions** in the editor to see which checks flipped.
4. In `/improvement/experiments/<id>`, switch between *in scope* and *all tasks*. Which conclusions change? Which number would you have quoted if you only had the "all tasks" view?
5. Replace polling with server-sent events for one endpoint: the worker publishes `edit:<id>` progress to Redis, and a FastAPI `StreamingResponse` relays it. What happens when the browser reconnects mid-job?
