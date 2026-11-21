"""Smallest useful LangGraph: MediaContext -> summary, with one conditional edge.

    uv run python -m agent.graphs.hello_graph out/context.json

Graph:  load_context ──► route ──(has speech)──► summarize_with_speech ──► END
                             └──(no speech)───► summarize_visual_only ──► END
"""

import sys
from pathlib import Path
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from config.models import get_chat_model
from perception.schemas import MediaContext


class State(TypedDict, total=False):
    context_path: str
    context: MediaContext
    digest: str
    summary: str


def load_context(state: State) -> State:
    ctx = MediaContext.model_validate_json(Path(state["context_path"]).read_text())
    lines = [f"[{s.start:6.1f}-{s.end:6.1f}] {s.description or '(no description)'}"
             + (f' | says: "{" ".join(t.text for t in s.transcript)[:160]}"' if s.transcript else "")
             for s in ctx.scenes]
    return {"context": ctx, "digest": "\n".join(lines)}


def route(state: State) -> str:
    return "speech" if state["context"].transcript else "visual"


PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a video editor's assistant. Summarise raw footage for an editor in "
               "4-6 bullet points, then name the single best 3-6 second moment to open a "
               "short-form vertical video with, citing its timestamps."),
    ("human", "Duration: {duration:.1f}s. {mode}\nScenes:\n{digest}"),
])


def _summarize(state: State, mode: str) -> State:
    chain = PROMPT | get_chat_model("planner")  # LCEL: prompt -> model, one Runnable
    msg = chain.invoke({"duration": state["context"].metadata.duration,
                        "mode": mode, "digest": state["digest"]})
    return {"summary": msg.content}


def summarize_with_speech(state: State) -> State:
    return _summarize(state, "The footage contains speech; weigh what is said heavily.")


def summarize_visual_only(state: State) -> State:
    return _summarize(state, "The footage has no speech; judge moments visually.")


def build_graph():
    g = StateGraph(State)
    g.add_node("load_context", load_context)
    g.add_node("summarize_with_speech", summarize_with_speech)
    g.add_node("summarize_visual_only", summarize_visual_only)
    g.add_edge(START, "load_context")
    g.add_conditional_edges("load_context", route,
                            {"speech": "summarize_with_speech", "visual": "summarize_visual_only"})
    g.add_edge("summarize_with_speech", END)
    g.add_edge("summarize_visual_only", END)
    return g.compile()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    graph = build_graph()
    result = graph.invoke({"context_path": sys.argv[1] if len(sys.argv) > 1 else "out/context.json"},
                          config={"run_name": "hello_graph", "tags": ["phase0"]})
    print(result["summary"])
