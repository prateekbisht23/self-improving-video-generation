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

## Switching providers (Gemini free tier)
`uv sync` installs `langchain-google-genai`. In `.env`:
```
GOOGLE_API_KEY=...                        # https://aistudio.google.com/apikey
MODEL_PLANNER=google_genai:gemini-2.5-flash
MODEL_VISION=google_genai:gemini-2.5-flash
MODEL_JUDGE=google_genai:gemini-2.5-flash-lite
```
No code changes: `init_chat_model` picks `ChatGoogleGenerativeAI` from the `google_genai` prefix.

Free-tier caveats:
- **Rate limits.** There's a per-minute request cap (RPM) and a per-day cap. Describing scenes one at a time is fine, but batch jobs later on need throttling.
- **Data use.** Google may use free-tier inputs to improve its products. Public sample footage is fine. Use a paid key or local models for private footage.
- Ollama (`ollama:qwen3:8b`) remains the offline fallback.

## What we learned wiring Gemini (Nov 2026)
- **Model names go stale.** `gemini-2.5-flash` returned 404 ("no longer available to new users"). List the models your key can use, then pin one exact version. `*-latest` aliases can change under you, which breaks reproducibility (PRD NFR-09).
- **Free-tier capacity varies.** The full Flash models returned 503/504 at peak times, while `gemini-3.5-flash-lite` answered in about 2 s. The factory sets `timeout=60, max_retries=3` for hosted providers, so a transient 503 is retried instead of failing or hanging.
- **Content blocks.** Gemini 3 returns `AIMessage.content` as a *list* of blocks (text plus a thought signature). Use `msg.text` to get the joined string. `with_structured_output` handles this for you.
- **Temperature is ignored** by Gemini 3 ("fixed sampling defaults"). For the judge that means less determinism than temperature 0. Phase 3 will measure evaluator variance with repeated runs (PRD risk: inconsistent LLM evaluations).
- **Keys must be in the process environment.** `get_settings()` exports `.env` with `load_dotenv`, because SDKs read `os.environ` rather than our Settings object.
