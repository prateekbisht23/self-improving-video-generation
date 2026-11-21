# 05 — LangSmith: tracing now, evaluation later

LangSmith records every LLM call, chain step and graph node as a **trace**: a tree of **runs**, each with inputs, outputs, latency, tokens, errors, and the model and prompt used. That makes PRD G7 (observability) work, and Phase 3 and 5 experiments depend on it.

## Setup (free Developer plan)
1. Sign up at https://smith.langchain.com, then go to Settings → API Keys → create a key.
2. In `.env`: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY=...`, `LANGSMITH_PROJECT=sivg-dev`.
3. Any LangChain or LangGraph call is traced automatically. Plain Python functions can be traced with `@traceable` from `langsmith`.

## Reading a trace of `hello_graph`
- The root run is `hello_graph` (we set `run_name` and `tags` in the invoke `config`).
- Its children are `load_context` (no LLM), then the summarize node, which contains `ChatPromptTemplate` and then `ChatOllama`.
- Click the LLM run to see the exact rendered prompt, the response, latency, and (where the provider reports them) token counts.

## How later phases use it
| Feature | Phase | Use |
|---|---|---|
| `metadata={"session_id":..., "agent_version":...}` on invoke | 2 | link DB rows to traces |
| Datasets | 3 | the 30 benchmark tasks |
| `evaluate(target, data=..., evaluators=[...])` | 3, 5 | baseline vs candidate experiments, compared side by side |
| Feedback (`client.create_feedback`) | 4 | human ratings attached to runs |

## Try this
1. Run `uv run python -m agent.graphs.hello_graph out/<clip>.json` and find the trace in your project.
2. Run it twice with different `WHISPER_MODEL` settings, regenerate the context, and compare the two traces.
3. Decorate `perception.context.build_context` with `@traceable(name="perception")` and watch the non-LLM pipeline show up as well.

## Regions (a gotcha we hit)
LangSmith keeps data in separate regions: **US** (`api.smith.langchain.com`, the default), **EU** (`eu.api…`) and **APAC** (`apac.api…`). A key sent to the wrong region gets **403 Forbidden**, the same response a made-up key gets, so it looks like a bad key. Set `LANGSMITH_ENDPOINT` to match the region of the account that created the key.

To check from the command line, look for a 200 from one of the regions:
```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "x-api-key: $LANGSMITH_API_KEY" \
  https://apac.api.smith.langchain.com/api/v1/sessions?limit=1
```

## Our first trace
```
hello_graph                      1.92s   (821 tokens)
├─ load_context                  0.11s
│  └─ route                      0.10s   ← the conditional edge is itself a traced step
└─ summarize_with_speech         1.74s
   └─ RunnableSequence           1.51s   ← the `prompt | model` LCEL chain
      ├─ ChatPromptTemplate      0.00s
      └─ ChatGoogleGenerativeAI  1.50s   ← click this to see the exact prompt and response
```
Reading traces from code (useful for experiment reports later):
`Client().list_runs(project_name="sivg-dev", is_root=True, limit=1)`.
