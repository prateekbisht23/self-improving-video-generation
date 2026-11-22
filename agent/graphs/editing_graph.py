"""Editing graph (PRD §7.2 A).

START → load_context → load_memory → load_style → plan → compile_plan
      → next_action ─(queue empty)→ check ─(ok)→ render → END
            ▲   │                     │
            │   └→ execute ─(ok)──────┤ (back to next_action)
            │          └─(rejected)→ repair ─┘
            └────────────────────── check ─(problems, budget left)→ repair

- `plan` is one structured-output LLM call (EditPlan).
- `compile_plan` turns the plan into typed operations deterministically.
- `execute` validates + applies one operation; success creates a new timeline version.
- `repair` is a small tool-calling loop: the model sees the error/problem and emits tool calls,
  which are queued and go through the SAME validation as planned actions.
- Budgets (max_steps, max_repairs) guarantee termination (PRD risk: agent execution loops).
"""

import time
import uuid
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph

from agent.prediction.features import ACTIONS, featurize
from agent.prediction.predictors import RulePredictor
from agent.prompts.editing import (
    PLANNER_HUMAN,
    PLANNER_SYSTEM,
    REPAIR_HUMAN,
    REPAIR_SYSTEM,
    prompt_hash,
)
from agent.runtime import EditDeps
from agent.schemas.plan import EditPlan
from config.models import get_chat_model, model_id
from editing.context import EditContext
from editing.operations import OPERATIONS, READ_ONLY, apply_action
from editing.timeline.schema import OutputSpec, Timeline

AGENT_NAME = "editing-agent"
AGENT_VERSION = f"{AGENT_NAME}-0.2+{prompt_hash()}"  # 0.2: creator memory, caption case
MAX_STEPS = 40
MAX_REPAIRS = 4
_RULES = RulePredictor()
STAGE_OF = {"select_clip": "assemble", "trim_clip": "assemble", "remove_clip": "assemble",
            "reorder_clips": "assemble", "add_transition": "transitions", "apply_style": "style",
            "set_framing": "style", "adjust_audio": "audio", "generate_captions": "captions",
            "add_caption": "captions", "add_title": "titles", "search_scenes": "search"}


class Action(TypedDict):
    name: str
    args: dict
    source: Literal["plan", "repair", "fixup"]


class EditState(TypedDict, total=False):
    instructions: str
    min_duration: float
    max_duration: float
    digest: str
    style_text: str
    memory_text: str
    plan: dict
    queue: list[Action]
    current: Action | None
    timeline: dict
    version: int
    step: int
    repairs: int
    last_error: str | None
    problems: list[str]
    render: dict | None
    status: str
    log: list[str]
    history: list[list]  # [[action, ok, source], ...] for next-action prediction


def _deps(config: RunnableConfig) -> EditDeps:
    return config["configurable"]["deps"]


def _tl(state: EditState) -> Timeline:
    return Timeline.model_validate(state["timeline"])


# ------------------------------------------------------------------ digest helpers
def scene_digest(ctx: EditContext, max_chars: int = 24000) -> str:
    lines = []
    for sc in ctx.scenes.values():
        head = (f"{sc.sid} [{sc.start:.2f}-{sc.end:.2f}] ({sc.duration:.1f}s, speech {sc.speech_ratio:.0%}) "
                f"{sc.description or '(no description)'}")
        if sc.tags:
            head += f" | tags: {', '.join(sc.tags[:6])}"
        lines.append(head)
        for s, e, text in sc.segments:
            lines.append(f"    ({s:.2f}-{e:.2f}) {text}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars] + "\n... (truncated)"


def timeline_digest(tl: Timeline) -> str:
    if not tl.video:
        return "(empty)"
    rows = [f"  [{i}] {c.scene_id or c.asset_id} {c.src_in:.2f}-{c.src_out:.2f} ({c.duration:.2f}s) "
            f"transition_in={c.transition_in} | {c.purpose or ''}" for i, c in enumerate(tl.video)]
    rows.append(f"  total {tl.duration:.2f}s, {len(tl.captions)} captions, {len(tl.titles)} titles, "
                f"color={tl.style.color}")
    return "\n".join(rows)


def style_text(style: dict | None) -> str:
    if not style:
        return "(none)"
    g, sh, obs = style["guidance"], style["shots"], style.get("observed") or {}
    parts = [f"pace {g['pace']}: median shot {sh['median']}s (p10 {sh['p10']}s, p90 {sh['p90']}s), "
             f"{sh['cuts_per_minute']} cuts/min -> aim for clips around {g['target_shot_seconds']}s, "
             f"none longer than {g['max_shot_seconds']}s",
             f"captions: {g['caption_position']}{', ALL CAPS' if g['caption_uppercase'] else ''}",
             f"colour look: {g['color']}", f"transitions: {g['transition']}"]
    if obs.get("narrative_structure"):
        parts.append("narrative: " + " -> ".join(obs["narrative_structure"]))
    return "\n".join(f"- {p}" for p in parts)


# ------------------------------------------------------------------ nodes
def load_context(state: EditState, config: RunnableConfig) -> EditState:
    deps = _deps(config)
    tl = Timeline(assets=deps.ctx.assets,
                  output=OutputSpec(min_duration=state["min_duration"], max_duration=state["max_duration"]))
    deps.recorder.save_version(tl, 0, "agent")
    return {"digest": scene_digest(deps.ctx), "timeline": tl.model_dump(mode="json"), "version": 0,
            "step": 0, "repairs": 0, "queue": [], "problems": [], "log": [], "status": "running", "history": []}


def load_memory(state: EditState, config: RunnableConfig) -> EditState:
    mem = _deps(config).memory  # Phase 4 fills this from the creator-memory store
    return {"memory_text": "\n".join(f"- {m}" for m in mem) or "(none)"}


def load_style(state: EditState, config: RunnableConfig) -> EditState:
    return {"style_text": style_text(_deps(config).style)}


def plan(state: EditState, config: RunnableConfig) -> EditState:
    model = get_chat_model("planner").with_structured_output(EditPlan)
    p: EditPlan = model.invoke([
        SystemMessage(PLANNER_SYSTEM),
        HumanMessage(PLANNER_HUMAN.format(
            instructions=state["instructions"], min_duration=state["min_duration"],
            max_duration=state["max_duration"], style=state["style_text"], memory=state["memory_text"],
            digest=state["digest"])),
    ])
    _deps(config).recorder.save_plan(p.model_dump())
    return {"plan": p.model_dump(), "log": state["log"] + [f"plan: {len(p.clips)} clips, ~{p.estimated_duration:.1f}s"]}


def compile_plan(state: EditState, config: RunnableConfig) -> EditState:
    """Deterministic: EditPlan -> ordered list of typed operations."""
    p = EditPlan.model_validate(state["plan"])
    style = _deps(config).style
    q: list[Action] = [{"name": "select_clip", "source": "plan",
                        "args": {"scene_id": c.scene_id, "src_in": c.src_in, "src_out": c.src_out,
                                 "purpose": c.purpose}} for c in p.clips]
    if p.transition != "cut":
        q += [{"name": "add_transition", "source": "plan",
               "args": {"index": i, "type": p.transition, "duration": 0.35}} for i in range(1, len(p.clips))]
    q.append({"name": "apply_style", "source": "plan", "args": {
        "color": p.color, "caption_position": p.caption_position,
        "caption_uppercase": p.caption_uppercase or bool(style and style["guidance"]["caption_uppercase"])}})
    if p.captions:
        q.append({"name": "generate_captions", "source": "plan", "args": {}})
    if p.title:
        q.append({"name": "add_title", "source": "plan", "args": {"text": p.title[:80], "start": 0, "end": 2.2}})
    return {"queue": q}


def next_action(state: EditState, config: RunnableConfig) -> EditState:
    """Pop the next queued action. Before it runs, the rules predictor guesses it (online, logged),
    which gives a live accuracy signal for FR-07 without letting the predictor drive the agent yet."""
    q = list(state["queue"])
    current = q.pop(0) if q else None
    if current and current["name"] in ACTIONS:
        f = featurize(state["timeline"], [tuple(h) for h in state.get("history", [])], state["instructions"],
                      state["min_duration"], state["max_duration"], state.get("memory_text", ""))
        t0 = time.perf_counter()
        pred = _RULES.predict(f)
        _deps(config).recorder.record_prediction(
            step=state["step"] + 1, predictor=_RULES.name, predicted=pred, actual=current["name"],
            stage=STAGE_OF.get(current["name"], "other"), correct_top1=pred[:1] == [current["name"]],
            correct_top3=current["name"] in pred, valid=all(a in ACTIONS for a in pred),
            latency_ms=round((time.perf_counter() - t0) * 1000, 3))
    return {"current": current, "queue": q}


def execute(state: EditState, config: RunnableConfig) -> EditState:
    deps, act = _deps(config), state["current"]
    tl = _tl(state)
    res = apply_action(tl, act["name"], act["args"], deps.ctx)
    step, version = state["step"] + 1, state["version"]
    new_version = version + 1 if res.changed else version
    if res.changed:
        deps.recorder.save_version(res.timeline, new_version, "agent")
    deps.recorder.record_action(step=step, name=act["name"], args=act["args"], source=act["source"], ok=res.ok,
                                error=res.error, result=res.data if isinstance(res.data, dict | list) else None,
                                version_before=version, version_after=new_version,
                                stage=STAGE_OF.get(act["name"], "other"))
    out: EditState = {"step": step, "version": new_version, "current": None,
                      "history": state.get("history", []) + [[act["name"], res.ok, act["source"]]],
                      "last_error": None if res.ok else f"{act['name']}({act['args']}) rejected: {res.error}",
                      "log": state["log"] + [f"{step:02d} {act['source']:6s} {act['name']}: "
                                             f"{'ok' if res.ok else 'REJECTED ' + (res.error or '')}"]}
    if res.changed:
        out["timeline"] = res.timeline.model_dump(mode="json")
    return out


def _tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(func=lambda **_: None, name=name, description=(schema.__doc__ or name).strip(),
                                         args_schema=schema) for name, (schema, _) in OPERATIONS.items()]


def repair(state: EditState, config: RunnableConfig) -> EditState:
    """Tool-calling repair. search_scenes runs immediately (results go back to the model);
    every other call is queued and later validated by `execute` like any planned action."""
    deps = _deps(config)
    tl = _tl(state)
    problem = state.get("last_error") or "; ".join(state.get("problems", []))
    model = get_chat_model("planner").bind_tools(_tools())
    messages = [SystemMessage(REPAIR_SYSTEM), HumanMessage(REPAIR_HUMAN.format(
        problem=problem, instructions=state["instructions"], min_duration=state["min_duration"],
        max_duration=state["max_duration"], duration=tl.duration, timeline=timeline_digest(tl),
        digest=state["digest"]))]
    queued: list[Action] = []
    for _ in range(3):  # at most 3 model turns (search -> act)
        ai = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        pending_search = False
        for call in ai.tool_calls:
            if call["name"] in READ_ONLY:
                r = apply_action(tl, call["name"], call["args"], deps.ctx)
                messages.append(ToolMessage(content=str(r.data if r.ok else r.error)[:3000], tool_call_id=call["id"]))
                pending_search = True
            else:
                queued.append({"name": call["name"], "args": call["args"], "source": "repair"})
                messages.append(ToolMessage(content="queued", tool_call_id=call["id"]))
        if queued or not pending_search:
            break
    return {"queue": queued + list(state["queue"]), "repairs": state["repairs"] + 1, "last_error": None,
            "problems": [], "log": state["log"] + [f"repair #{state['repairs'] + 1}: {problem[:160]} -> "
                                                   f"{[q['name'] for q in queued]}"]}


def check(state: EditState) -> EditState:
    tl = _tl(state)
    problems = tl.render_problems()
    if any(c.duration > 0 for c in tl.video) and len({c.scene_id for c in tl.video}) < len(tl.video) / 2:
        problems.append("most clips reuse the same scenes; vary the footage")
    return {"problems": problems}


def fixup(state: EditState) -> EditState:
    """Last-resort deterministic fix when repair budget is spent: trim the tail to fit max duration."""
    tl = _tl(state)
    over = tl.duration - state["max_duration"]
    q: list[Action] = []
    if over > 0 and tl.video:
        for i in range(len(tl.video) - 1, -1, -1):
            c = tl.video[i]
            cut = min(over, c.duration - 0.5)
            if cut > 0:
                q.append({"name": "trim_clip", "source": "fixup",
                          "args": {"index": i, "src_out": round(c.src_out - cut, 3)}})
                over -= cut
            if over <= 0:
                break
    return {"queue": q, "problems": [], "repairs": state["repairs"] + 1,
            "log": state["log"] + [f"fixup: {len(q)} deterministic trims"]}


def render_node(state: EditState, config: RunnableConfig) -> EditState:
    tl = _tl(state)
    r = _deps(config).recorder.render(tl, state["version"])
    return {"render": r, "status": "rendered",
            "log": state["log"] + [f"render v{state['version']}: {tl.duration:.2f}s"]}


def fail(state: EditState) -> EditState:
    return {"status": "failed", "log": state["log"] + [f"failed: {state.get('problems') or state.get('last_error')}"]}


# ------------------------------------------------------------------ routing
def after_next(state: EditState) -> str:
    if state["step"] >= MAX_STEPS:
        return "fail"
    return "execute" if state.get("current") else "check"


def after_execute(state: EditState) -> str:
    if state.get("last_error") and state["repairs"] < MAX_REPAIRS:
        return "repair"
    return "next_action"


def after_check(state: EditState) -> str:
    if not state["problems"]:
        return "render"
    if state["repairs"] < MAX_REPAIRS:
        return "repair"
    tl_too_long = any("outside target" in p for p in state["problems"])
    return "fixup" if tl_too_long and state["repairs"] < MAX_REPAIRS + 1 else "fail"


def build_graph():
    g = StateGraph(EditState)
    for name, fn in [("load_context", load_context), ("load_memory", load_memory), ("load_style", load_style),
                     ("plan", plan), ("compile_plan", compile_plan), ("next_action", next_action),
                     ("execute", execute), ("repair", repair), ("check", check), ("fixup", fixup),
                     ("render", render_node), ("fail", fail)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "load_memory")
    g.add_edge("load_memory", "load_style")
    g.add_edge("load_style", "plan")
    g.add_edge("plan", "compile_plan")
    g.add_edge("compile_plan", "next_action")
    g.add_conditional_edges("next_action", after_next, ["execute", "check", "fail"])
    g.add_conditional_edges("execute", after_execute, ["repair", "next_action"])
    g.add_edge("repair", "next_action")
    g.add_conditional_edges("check", after_check, ["render", "repair", "fixup", "fail"])
    g.add_edge("fixup", "next_action")
    g.add_edge("render", END)
    g.add_edge("fail", END)
    return g.compile()


def agent_config() -> dict[str, Any]:
    return {"agent_version": AGENT_VERSION, "planner": model_id("planner"), "max_steps": MAX_STEPS,
            "max_repairs": MAX_REPAIRS, "prompt_hash": prompt_hash()}


def run_edit(instructions: str, deps: EditDeps, *, min_duration: float = 15, max_duration: float = 30,
             run_name: str = "editing_session", metadata: dict | None = None,
             run_id: uuid.UUID | None = None) -> EditState:
    """`run_id` becomes the LangSmith root run id (= trace id), so callers can link to the trace."""
    return build_graph().invoke(
        {"instructions": instructions, "min_duration": min_duration, "max_duration": max_duration},
        config={"configurable": {"deps": deps}, "recursion_limit": 4 * MAX_STEPS + 20, "run_name": run_name,
                "run_id": run_id,
                "tags": ["editing", AGENT_VERSION], "metadata": {**(metadata or {}), **agent_config()}},
    )
