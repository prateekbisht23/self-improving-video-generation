# 16 — LangGraph checkpointing and human-in-the-loop interrupts

Code: `agent/graphs/memory_graph.py`.

## The problem
The memory graph sometimes needs an answer from a human ("Should I remember X?"). Holding an HTTP request open for minutes, or for days, isn't an option. The graph has to **stop, persist, and resume later**, possibly in another process.

## The pieces
```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt, Command

graph = builder.compile(checkpointer=PostgresSaver(conn))   # state is saved after every step
cfg = {"configurable": {"thread_id": "feedback-<id>"}}      # one thread = one conversation/run

def ask(state, config):
    ...create MemoryConfirmation rows (idempotently)...
    answers = interrupt({"questions": [...]})               # 1st run: stops here
    return {"answers": answers}                             # resumed run: gets the answers

out = graph.invoke({"feedback_id": ...}, cfg)               # out["__interrupt__"] holds the questions
...hours later, another process...
graph.invoke(Command(resume={"<pref id>": "confirm"}), cfg) # same thread_id -> continues
```
- **Checkpointer**: after each node, the full state goes to Postgres (`checkpoints`, `checkpoint_writes` and `checkpoint_blobs`, created by `saver.setup()`).
- **`interrupt(value)`**: pauses the run and surfaces `value` to the caller under `__interrupt__`.
- **`Command(resume=...)`**: continues the thread. The interrupted node **re-runs from its first line**, and this time `interrupt()` returns the resume value. That's why `ask` creates its `MemoryConfirmation` rows idempotently (it checks which ones exist first). Anything before `interrupt()` in a node runs twice.

## Our API around it
- `POST /edits/{id}/feedback` runs the graph. The response is either `done`, or `awaiting_confirmation` with a `thread_id` and the questions.
- `GET /memory/confirmations` lists pending questions (from the table, rather than by scanning checkpoints).
- `POST /memory/confirmations/{thread_id}` takes `{"answers": {"<pref id>": "confirm" | "reject"}}` and resumes the graph.

## Gotchas we hit
- Use a plain `postgresql://` URL with `psycopg.connect(autocommit=True, row_factory=dict_row)`. The SQLAlchemy-style `postgresql+psycopg://` doesn't work here.
- **Alembic and unnamed constraints**: autogenerate emitted `create_foreign_key(None, ...)`, and the downgrade failed with "it has no name". The failed downgrade was also hidden by a `grep` in our own shell pipeline. Always name constraints and read migration output in full.
- A param named `kind` plus `**detail` containing a `kind` key gives `TypeError: got multiple values for argument`. Watch out for `**kwargs` collisions in audit helpers.
