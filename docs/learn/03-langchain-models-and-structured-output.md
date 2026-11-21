# 03 — LangChain: models, messages, prompts, structured output

LangChain gives us one interface over many model providers, plus composable building blocks. We use a small, stable subset of it.

## Chat models via one factory
`config/models.py` → `get_chat_model(role)` → `init_chat_model(model, model_provider=...)`.
- Roles (`planner`, `vision`, `judge`) map to `provider:model` strings in `.env`, so moving from `ollama:qwen3:8b` to `anthropic:claude-sonnet-5-5` is a config change.
- The judge runs at temperature 0. Evaluations should be as repeatable as possible.

## Messages
`SystemMessage` sets the rules, `HumanMessage` carries the input, and the model returns an `AIMessage`. Multimodal input is a list of content blocks: `{"type": "text", ...}` plus `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}` (see `perception/models/describe.py`).

## Structured output: the most important pattern in this project
```python
model.with_structured_output(SceneDescription).invoke(messages)  # -> SceneDescription instance
```
- You pass a **Pydantic model**. LangChain turns it into a JSON schema (tool or JSON mode), and the reply is parsed and validated into that type.
- `Field(description=...)` text is sent to the model, so treat it as part of the prompt.
- Everything the agent decides later (editing plans, actions, evaluation findings) uses this pattern. Free-text replies never drive behaviour directly.

## Prompts + LCEL
```python
chain = ChatPromptTemplate.from_messages([...]) | get_chat_model("planner")
chain.invoke({"digest": ...})
```
`|` composes **Runnables**. Every Runnable has `.invoke / .batch / .stream`, and each step appears as a child run in LangSmith.

## Gotchas with local models
- Small models sometimes produce invalid JSON. `with_structured_output(..., include_raw=True)` lets you inspect failures, and a retry fixes most of them.
- qwen3 has a "thinking" mode that emits reasoning text first. We turn it off (`reasoning=False`) for structured calls.

## Try this
1. In a REPL: `from config.models import get_chat_model; get_chat_model("planner").invoke("Name 3 jump-cut techniques").content`
2. Write a Pydantic model `Hook(text: str, start: float, end: float)` and use `with_structured_output` to pull the best hook out of `out/<clip>.json`'s transcript.
