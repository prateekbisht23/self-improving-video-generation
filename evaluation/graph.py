"""Evaluation graph (PRD §7.2 B), with parallel branches.

                        ┌─ technical ──────────┐
                        ├─ temporal ───────────┤
START → extract_features ├─ captions ───────────┼─→ aggregate → END
                        ├─ style ──────────────┤
                        ├─ judge_instructions ─┤
                        ├─ judge_narrative ────┤
                        └─ judge_framing ──────┘

Branches write to `results`, whose reducer (operator.add) concatenates the lists; LangGraph
runs all branches of a superstep before `aggregate` (fan-in).
"""

import operator
import time
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from config.models import model_id
from evaluation.evaluators import captions, judges, style, technical, temporal
from evaluation.features import RenderFeatures, extract_features
from evaluation.inputs import EvalInput
from evaluation.schemas import EVALUATOR_VERSION, CheckResult, EvaluationReport


class EvalState(TypedDict, total=False):
    input: dict
    features: dict
    results: Annotated[list[dict], operator.add]
    report: dict
    started: float


def _x(state) -> EvalInput:
    return EvalInput.model_validate(state["input"])


def _f(state) -> RenderFeatures:
    return RenderFeatures.model_validate(state["features"])


def _opts(config: RunnableConfig) -> dict:
    return config.get("configurable", {})


def extract(state: EvalState, config: RunnableConfig) -> EvalState:
    f = extract_features(_x(state).render_path, transcribe_audio=_opts(config).get("transcribe", True),
                         workdir=_opts(config).get("workdir"))
    return {"features": f.model_dump(), "started": state.get("started") or time.perf_counter()}


def _branch(fn):
    def node(state: EvalState) -> EvalState:
        return {"results": [c.model_dump() for c in fn(_f(state), _x(state))]}
    node.__name__ = fn.__module__.rsplit(".", 1)[-1]
    return node


def _instruction_checks(f, x):
    return temporal.required_content(f, x)


def _judge(fn, check_id: str, category: str):
    def node(state: EvalState, config: RunnableConfig) -> EvalState:
        f = _f(state)
        if not _opts(config).get("judges", True) or not f.readable:
            return {"results": []}
        try:
            res = fn(f, _x(state))
            return {"results": [c.model_dump() for c in (res if isinstance(res, list) else [res])]}
        except Exception as e:  # a judge failure must not sink the whole evaluation
            return {"results": [CheckResult(id=check_id, category=category, kind="model", passed=None,
                                            severity="major", message=f"judge error: {type(e).__name__}: "
                                                                      f"{str(e)[:200]}").model_dump()]}
    return node


def aggregate(state: EvalState, config: RunnableConfig) -> EvalState:
    x = _x(state)
    use_judges = _opts(config).get("judges", True)
    rep = EvaluationReport.aggregate(
        [CheckResult.model_validate(r) for r in state["results"]], render_path=x.render_path,
        judge_model=model_id("judge") if use_judges else None,
        timeline_hash=(x.timeline or {}).get("_hash"), seconds=round(time.perf_counter() - state["started"], 2))
    return {"report": rep.model_dump()}


BRANCHES = {
    "technical": _branch(technical.run),
    "temporal": _branch(temporal.run),
    "captions": _branch(captions.run),
    "style": _branch(style.run),
    "required_content": _branch(_instruction_checks),
    "judge_instructions": _judge(judges.instruction_adherence, "instruction.adherence", "instruction"),
    "judge_narrative": _judge(judges.narrative, "narrative.structure", "narrative"),
    "judge_framing": _judge(judges.framing, "visual.framing", "visual"),
}


def build_graph():
    g = StateGraph(EvalState)
    g.add_node("extract_features", extract)
    g.add_node("aggregate", aggregate)
    g.add_edge(START, "extract_features")
    for name, fn in BRANCHES.items():
        g.add_node(name, fn)
        g.add_edge("extract_features", name)
        g.add_edge(name, "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


def evaluate(x: EvalInput, *, judges_on: bool = True, transcribe: bool = True, workdir: str | None = None,
             metadata: dict | None = None, run_id=None) -> EvaluationReport:
    out = build_graph().invoke(
        {"input": x.model_dump(), "results": [], "started": time.perf_counter()},
        config={"configurable": {"judges": judges_on, "transcribe": transcribe, "workdir": workdir},
                "run_name": "evaluation", "run_id": run_id, "tags": ["evaluation", EVALUATOR_VERSION],
                "metadata": {**(metadata or {}), "evaluator_version": EVALUATOR_VERSION,
                             "judge_model": model_id("judge") if judges_on else None}})
    return EvaluationReport.model_validate(out["report"])
