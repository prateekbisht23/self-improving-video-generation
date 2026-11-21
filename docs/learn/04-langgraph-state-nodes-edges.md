# 04 — LangGraph: state, nodes, edges

LangChain composes *linear* chains. LangGraph composes **graphs with state**: loops, branches, retries, human approval, and checkpoints. All four PRD workflows (editing, evaluation, memory, improvement) are LangGraph graphs. Code: `agent/graphs/hello_graph.py`.

## The three ideas
1. **State**: a `TypedDict` (or Pydantic model) that flows through the graph. Each node receives the current state and returns a **partial update**, which LangGraph merges in.
2. **Nodes**: plain functions `state -> dict`. They can be LLM calls, tool calls, or ordinary Python.
3. **Edges**:
   - normal: `add_edge("a", "b")`
   - conditional: `add_conditional_edges("a", router_fn, {"label": "node"})`
   - `START` / `END`

```
START → load_context ─route─┬─"speech"─► summarize_with_speech ─► END
                            └─"visual"─► summarize_visual_only ─► END
```
`graph.compile()` returns a Runnable, so it gets `.invoke/.stream` and LangSmith tracing like any chain.

## What later phases add
- **Loops with budgets.** In the editing graph, *predict action → validate → execute → loop until done*, with a max-steps guard against runaway loops (PRD risk table).
- **Reducers.** `Annotated[list, operator.add]` makes a node *append* to a list (for example an action log) instead of replacing it.
- **Checkpointer.** `compile(checkpointer=PostgresSaver(...))` persists state after every step, so a run can resume after a crash and you can inspect or replay any step.
- **Interrupts.** `interrupt()` pauses the graph for a human (confirm a preference, approve a promotion) and resumes with their answer (PRD FR-08 and FR-12).

## Try this
1. `uv run python -c "from agent.graphs.hello_graph import build_graph; print(build_graph().get_graph().draw_mermaid())"` and paste the output into mermaid.live.
2. `for ev in build_graph().stream({"context_path": "out/speech.json"}, stream_mode="updates"): print(ev)` shows each node's partial update.
3. Add a third branch: if the video is longer than 120 s, route to a node that returns `{"summary": "too long"}` without calling the LLM.
