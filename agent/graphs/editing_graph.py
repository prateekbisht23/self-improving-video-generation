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

from agent.config import DEFAULT_CONFIG, AgentConfig
from agent.prediction.features import ACTIONS, featurize
from agent.prediction.predictors import RulePredictor
from agent.prompts.editing import PLANNER_HUMAN, REPAIR_HUMAN
from agent.runtime import EditDeps
from agent.schemas.plan import EditPlan
from config.models import get_chat_model, model_id
from editing.context import EditContext
from editing.operations import OPERATIONS, READ_ONLY, apply_action
from editing.snapping import next_sentence_end, snap_clip
from editing.timeline.schema import OutputSpec, Timeline

# Behaviour comes from a versioned AgentConfig (agent/config.py). The default config is v0.2.
AGENT_VERSION = DEFAULT_CONFIG.version
MAX_STEPS = DEFAULT_CONFIG.policy.max_steps
MAX_REPAIRS = DEFAULT_CONFIG.policy.max_repairs
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
    max_steps: int
    max_repairs: int


def _deps(config: RunnableConfig) -> EditDeps:
    return config["configurable"]["deps"]


def _cfg(config: RunnableConfig) -> AgentConfig:
    return _deps(config).config


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
    pol = deps.config.policy
    return {"digest": scene_digest(deps.ctx), "timeline": tl.model_dump(mode="json"), "version": 0,
            "step": 0, "repairs": 0, "queue": [], "problems": [], "log": [], "status": "running", "history": [],
            "max_steps": pol.max_steps, "max_repairs": pol.max_repairs}


def load_memory(state: EditState, config: RunnableConfig) -> EditState:
    mem = _deps(config).memory  # Phase 4 fills this from the creator-memory store
    return {"memory_text": "\n".join(f"- {m}" for m in mem) or "(none)"}


def load_style(state: EditState, config: RunnableConfig) -> EditState:
    return {"style_text": style_text(_deps(config).style)}


def plan(state: EditState, config: RunnableConfig) -> EditState:
    model = get_chat_model("planner").with_structured_output(EditPlan)
    p: EditPlan = model.invoke([
        SystemMessage(_cfg(config).planner_system()),
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
    deps = _deps(config)
    style = deps.style
    q: list[Action] = [{"name": "select_clip", "source": "plan",
                        "args": {"scene_id": c.scene_id, "src_in": c.src_in, "src_out": c.src_out,
                                 "purpose": c.purpose}} for c in p.clips]
    if p.transition != "cut":
        q += [{"name": "add_transition", "source": "plan",
               "args": {"index": i, "type": p.transition, "duration": 0.35}} for i in range(1, len(p.clips))]
    q.append({"name": "apply_style", "source": "plan", "args": {
        "color": p.color, "caption_position": p.caption_position,
        "caption_uppercase": p.caption_uppercase or bool(style and style["guidance"]["caption_uppercase"])}})
    if p.captions and not _skip_captions(deps, state):
        q.append({"name": "generate_captions", "source": "plan", "args": {}})
    if p.title:
        q.append({"name": "add_title", "source": "plan", "args": {"text": p.title[:80], "start": 0, "end": 2.2}})
    return {"queue": q}


CAPTION_WORDS = ("caption", "subtitle", "on mute", "sound off")


def _skip_captions(deps: EditDeps, state: EditState) -> bool:
    """Policy captions_follow_reference: the reference has no captions and nobody asked for them."""
    if not (deps.config.policy.captions_follow_reference and deps.style):
        return False
    observed = deps.style.get("observed") or {}
    if observed.get("captions_present", True):
        return False
    asked = (state["instructions"] + " " + state.get("memory_text", "")).lower()
    return not any(w in asked for w in CAPTION_WORDS)


def _snap_args(tl: Timeline, act: Action, deps: EditDeps) -> dict:
    """Policy snap_cuts: move the in/out points of select_clip / trim_clip to speech boundaries."""
    pol = deps.config.policy
    mode = pol.snap_cuts
    if act.get("source") in ("repair", "fixup") and mode != "off" and pol.snap_repairs != "same":
        mode = pol.snap_repairs
    args = dict(act["args"])
    if mode == "off" or act["name"] not in ("select_clip", "trim_clip"):
        return args
    try:
        if act["name"] == "select_clip":
            sc = deps.ctx.scene(args["scene_id"])
            src_in = args.get("src_in") if args.get("src_in") is not None else sc.start
            src_out = args.get("src_out") if args.get("src_out") is not None else sc.end
            asset = sc.asset_id
        else:
            c = tl.video[args["index"]]
            sc = deps.ctx.scene(c.scene_id) if c.scene_id else None
            src_in = args.get("src_in") if args.get("src_in") is not None else c.src_in
            src_out = args.get("src_out") if args.get("src_out") is not None else c.src_out
            asset = c.asset_id
        lo, hi = (sc.start, sc.end) if sc else (0.0, float("inf"))
        new_in, new_out = snap_clip(float(src_in), float(src_out), deps.ctx.words.get(asset, []), lo, hi, mode,
                                    deps.config.policy.snap_max_shift)
    except (KeyError, IndexError, TypeError, ValueError):
        return args  # invalid args: let the operation report the error as usual
    if (new_in, new_out) != (src_in, src_out):
        args |= {"src_in": new_in, "src_out": new_out}
    return args


def _snap_breaks(state: EditState, deps: EditDeps, plain: Timeline, snapped: Timeline) -> str | None:
    """Snapping is a refinement: it must not break a constraint the unsnapped action satisfies.

    Round 3 showed both cases: the fixup trimmed pc-02 to 25.0s and word snapping moved the edge
    0.08s past the 25s limit (task failed); and snapping stretched ~12s clips past the max shot length."""
    lo, hi = state["min_duration"], state["max_duration"]
    d0, d1 = plain.duration, snapped.duration
    if (lo <= d0 <= hi and not lo <= d1 <= hi) or d0 <= hi < d1:
        return "duration"
    cap = ((deps.style or {}).get("guidance") or {}).get("max_shot_seconds") or 12.0
    if sum(c.duration > cap for c in snapped.video) > sum(c.duration > cap for c in plain.video):
        return "shot length"
    return None


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
    plain_args, args = dict(act["args"]), _snap_args(tl, act, deps)
    res = apply_action(tl, act["name"], args, deps.ctx)
    if args != plain_args:  # keep the snap only if it breaks nothing the plain action satisfies
        plain = apply_action(tl, act["name"], plain_args, deps.ctx)
        if plain.ok and (not res.ok or _snap_breaks(state, deps, plain.timeline or tl, res.timeline or tl)):
            res, args = plain, plain_args
    act = {**act, "args": args}
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
    messages = [SystemMessage(_cfg(config).repair_system()), HumanMessage(REPAIR_HUMAN.format(
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


def check(state: EditState, config: RunnableConfig) -> EditState:
    tl = _tl(state)
    problems = tl.render_problems()
    if (_cfg(config).policy.scene_reuse_check and any(c.duration > 0 for c in tl.video)
            and len({c.scene_id for c in tl.video}) < len(tl.video) / 2):
        problems.append("most clips reuse the same scenes; vary the footage")
    return {"problems": problems}


def fixup(state: EditState, config: RunnableConfig) -> EditState:
    """Last-resort deterministic fix when repair budget is spent: trim the tail to fit max duration
    (and, with policy fixup_extend, lengthen an edit that is too short)."""
    tl = _tl(state)
    over = tl.duration - state["max_duration"]
    q: list[Action] = []
    if _cfg(config).policy.fixup_extend and tl.video and tl.duration < state["min_duration"]:
        q = _extend_actions(tl, state, _deps(config))
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
            "log": state["log"] + [f"fixup: {len(q)} deterministic actions"]}


def _extend_actions(tl: Timeline, state: EditState, deps: EditDeps) -> list[Action]:
    """Grow a too-short edit towards the middle of the target window: first extend clips to later
    sentence ends inside their scene, then append unused speech scenes (trimmed to fit)."""
    goal = (state["min_duration"] + state["max_duration"]) / 2
    need = goal - tl.duration
    q: list[Action] = []
    for i in range(len(tl.video) - 1, -1, -1):
        c = tl.video[i]
        if need <= 0 or not c.scene_id:
            continue
        sc = deps.ctx.scene(c.scene_id)
        words = deps.ctx.words.get(c.asset_id, [])
        end, t = c.src_out, c.src_out
        while (nxt := next_sentence_end(t, words, sc.end)) is not None and nxt - c.src_out <= need:
            end, t = nxt, nxt
        if end == c.src_out and sc.end - c.src_out > 0.3 and not words:  # silent b-roll: just extend
            end = min(sc.end, c.src_out + need)
        if end > c.src_out:
            q.append({"name": "trim_clip", "source": "fixup", "args": {"index": i, "src_out": round(end, 3)}})
            need -= end - c.src_out
    used = {c.scene_id for c in tl.video}
    for sc in sorted(deps.ctx.scenes.values(), key=lambda s: -s.speech_ratio):
        if need <= 0.5:
            break
        if sc.sid in used or sc.duration < 1.0:
            continue
        take = min(sc.duration, need)
        q.append({"name": "select_clip", "source": "fixup",
                  "args": {"scene_id": sc.sid, "src_in": sc.start, "src_out": round(sc.start + take, 3),
                           "purpose": "fixup: extend a too-short edit"}})
        need -= take
    return q


def render_node(state: EditState, config: RunnableConfig) -> EditState:
    tl = _tl(state)
    r = _deps(config).recorder.render(tl, state["version"])
    return {"render": r, "status": "rendered",
            "log": state["log"] + [f"render v{state['version']}: {tl.duration:.2f}s"]}


def fail(state: EditState) -> EditState:
    return {"status": "failed", "log": state["log"] + [f"failed: {state.get('problems') or state.get('last_error')}"]}


# ------------------------------------------------------------------ routing
def after_next(state: EditState) -> str:
    if state["step"] >= state.get("max_steps", MAX_STEPS):
        return "fail"
    return "execute" if state.get("current") else "check"


def after_execute(state: EditState) -> str:
    if state.get("last_error") and state["repairs"] < state.get("max_repairs", MAX_REPAIRS):
        return "repair"
    return "next_action"


def after_check(state: EditState) -> str:
    if not state["problems"]:
        return "render"
    budget = state.get("max_repairs", MAX_REPAIRS)
    if state["repairs"] < budget:
        return "repair"
    wrong_length = any("outside target" in p for p in state["problems"])
    return "fixup" if wrong_length and state["repairs"] < budget + 1 else "fail"


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
    # checkpointer=False: never inherit a parent graph's checkpointer. When this graph runs inside a
    # node of a checkpointed graph (the improvement loop), LangGraph would otherwise treat it as a
    # subgraph and, on resume, REPLAY earlier results by call position for different inputs.
    return g.compile(checkpointer=False)


def agent_config(cfg: AgentConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    return {"agent_version": cfg.version, "planner": model_id("planner"), "max_steps": cfg.policy.max_steps,
            "max_repairs": cfg.policy.max_repairs, "config_hash": cfg.config_hash(), "config": cfg.model_dump()}


def run_edit(instructions: str, deps: EditDeps, *, min_duration: float = 15, max_duration: float = 30,
             run_name: str = "editing_session", metadata: dict | None = None,
             run_id: uuid.UUID | None = None) -> EditState:
    """`run_id` becomes the LangSmith root run id (= trace id), so callers can link to the trace.
    The agent's behaviour is deps.config (a versioned AgentConfig)."""
    cfg = deps.config
    meta = agent_config(cfg)
    meta.pop("config")
    return build_graph().invoke(
        {"instructions": instructions, "min_duration": min_duration, "max_duration": max_duration},
        config={"configurable": {"deps": deps}, "recursion_limit": 4 * cfg.policy.max_steps + 20,
                "run_name": run_name, "run_id": run_id,
                "tags": ["editing", cfg.version], "metadata": {**(metadata or {}), **meta}},
    )
