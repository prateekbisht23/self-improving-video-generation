# 11 — The editing agent: LangGraph loops, budgets, tool calling

Code: `agent/graphs/editing_graph.py`, `agent/prompts/editing.py`, `agent/schemas/plan.py`.

```
load_context → load_memory → load_style → plan → compile_plan → next_action ⇄ execute
                                                                      │          └─rejected→ repair ─┐
                                                                      └─queue empty→ check ──problems→ repair/fixup
                                                                                        └─ok→ render
```

## Plan, then act
- **`plan`**: one structured-output call that returns an `EditPlan` (clips with scene ids and sentence-aligned times, hook, transition, captions, colour). The prompt shows every scene *with its transcript sentences and timestamps*, so the model can cut on sentence boundaries.
- **`compile_plan`**: deterministic code turns the plan into a queue of typed operations. The LLM decides *what*; code decides *how*.
- **`next_action` → `execute`**: pop, validate, apply, record. This loop is where Phase 4 plugs in next-action predictors.

## State vs dependencies
State (`EditState`) holds only JSON-able data: the timeline, queue, counters and log. The scene context, recorder and style profile travel in `config["configurable"]["deps"]`. That keeps the state traceable in LangSmith and checkpointable later, and lets tests inject fakes.

## Tool calling for repair
When an action is rejected, or `check` finds a problem (for example duration outside the target), `repair` binds the operation schemas as **tools**:
```python
model.bind_tools([StructuredTool.from_function(..., args_schema=SelectClip), ...])
ai = model.invoke(messages)          # ai.tool_calls = [{"name": "trim_clip", "args": {...}, "id": ...}]
```
- `search_scenes` is read-only: it runs immediately, and the result goes back to the model as a `ToolMessage`. That's the standard tool-calling message protocol.
- Every other call is **queued**, not executed. It then passes through the same `execute` validation as planned actions. The model never gets a privileged path.

## Termination is designed, not hoped for
- `MAX_STEPS = 40` actions and `MAX_REPAIRS = 4` model repairs.
- Once the repair budget is spent, a **deterministic `fixup`** trims the tail to fit the max duration. If the edit is still invalid (for example too short), the graph ends in `fail` with the reason.
- `recursion_limit` is set above the step budget so LangGraph's own guard never fires first.

## Observed behaviour (baseline agent, Gemini 3.5 Flash-Lite)
| Run | What happened |
|---|---|
| Interview, 18–28 s | The plan said ~25 s, but its clips summed to **34.5 s** (LLMs add badly). Repair #1 trimmed to 16.7 s (too far) and repair #2 added a clip to reach 24.1 s, but **appended it after the ending**, which broke the narrative order. |
| Supermoon, 20–28 s | Valid on the first try, no repairs. |

These are kept as *baseline failures* on purpose. Phase 3's evaluators should detect them (duration estimate error, narrative order, mid-sentence cuts), and Phase 5 must show a measured improvement.

## Agent versioning
`AGENT_VERSION = editing-agent-0.1+<prompt hash>`. Changing any prompt changes the version. It's stored on every session along with the model ids and budgets, and attached to the LangSmith trace as metadata. The session's `trace_id` *is* the root run id, because we pass `run_id` in the invoke config. (`collect_runs()` gave a different id, so don't use it for linking.)

## Try this
1. Open a session's trace (`trace_id` from `GET /edits/<id>`) and find the `plan` LLM call. Read the full prompt the model saw.
2. In a test, give `FakeModel` a plan with a bad scene id and a repair batch, and watch the log (`tests/unit/test_editing_graph.py`).
3. Set `MAX_REPAIRS = 0` and run an over-long plan. Which node fixes it?
