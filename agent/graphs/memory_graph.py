"""Memory graph (PRD §7.2 C): feedback -> preference updates, with human confirmation.

START → receive → extract → update ─(questions?)─► ask ─(interrupt; resumed later)─► apply_answers → finish → END
                                  └─(none)──────────────────────────────────────────────────────────► finish

`ask` calls langgraph.types.interrupt(): the run stops, its state is saved by the Postgres checkpointer
under thread_id = "feedback-<id>", and the API returns the pending questions. When the creator answers,
`resume()` invokes the graph again with Command(resume=answers) on the same thread; LangGraph re-runs
`ask` from the top, interrupt() now returns the answers, and the graph continues.
"""

import uuid
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select

from config.settings import get_settings
from db.models import (
    CreatorPreference,
    EditingSession,
    Feedback,
    FeedbackKind,
    MemoryConfirmation,
    PreferenceSource,
    PreferenceStatus,
)
from db.session import session_scope
from memory import extraction, storage

GENERAL_CONF, CORRECTION_CONF, SESSION_CONF = 0.5, 0.35, 0.8
CONFIRM_AT_SUPPORT = 2


class MemoryState(TypedDict, total=False):
    feedback_id: str
    creator_id: str
    session_id: str
    kind: str
    text: str | None
    start: float | None
    context_tags: list[str]
    memory_used: list[dict]
    candidates: list[dict]
    decisions: list[dict]
    to_confirm: list[str]
    answers: dict
    summary: dict


def receive(state: MemoryState) -> MemoryState:
    with session_scope() as s:
        f = s.get(Feedback, uuid.UUID(state["feedback_id"]))
        e = s.get(EditingSession, f.session_id)
        return {"creator_id": str(f.creator_id), "session_id": str(f.session_id), "kind": f.kind.value,
                "text": f.text, "start": f.start, "context_tags": list(e.context_tags or []),
                "memory_used": list(e.memory_used or []), "decisions": [], "to_confirm": []}


def extract(state: MemoryState) -> MemoryState:
    if not (state.get("text") or "").strip():
        return {"candidates": []}
    cands = extraction.extract(state["text"], state["kind"], state.get("start"))
    return {"candidates": [c.model_dump() for c in cands]}


def update(state: MemoryState) -> MemoryState:
    creator, session = uuid.UUID(state["creator_id"]), uuid.UUID(state["session_id"])
    ev = {"feedback_id": state["feedback_id"], "session_id": state["session_id"]}
    decisions, to_confirm = [], []
    with session_scope() as s:
        if state["kind"] == FeedbackKind.accept.value:  # weak positive signal for what shaped the edit
            for m in state["memory_used"]:
                if "id" not in m:  # entries recording dropped/conflicting preferences
                    continue
                p = s.get(CreatorPreference, uuid.UUID(m["id"]))
                if p and p.status == PreferenceStatus.active:
                    before = p.confidence
                    p.confidence = round(min(0.95, p.confidence + 0.05), 3)
                    storage.log_event(s, p, "accepted_with", before, **ev)
                    decisions.append({"preference": p.statement, "action": "accepted_with"})
        for c in state["candidates"]:
            quote = {**ev, "quote": c["quote"]}
            if c["scope"] == "session":
                p = storage.add_preference(s, creator_id=creator, category=c["category"], attribute=c["attribute"],
                                           value=c["value"], statement=c["statement"],
                                           source=PreferenceSource.feedback, status=PreferenceStatus.session,
                                           confidence=SESSION_CONF, context=c["context"], session_id=session,
                                           evidence=quote)
                decisions.append({"preference": c["statement"], "action": "session_only", "id": str(p.id)})
                continue
            existing = [p for p in storage.same_attribute(s, creator, c["attribute"])
                        if sorted(p.context) == sorted(set(c["context"]))]
            same = [p for p in existing if p.value == c["value"]]
            other = [p for p in existing if p.value != c["value"] and p.status in
                     (PreferenceStatus.active, PreferenceStatus.candidate)]
            if same and same[0].status == PreferenceStatus.rejected:
                storage.log_event(s, same[0], "re_proposed_ignored", same[0].confidence, **quote)
                decisions.append({"preference": c["statement"], "action": "previously_rejected"})
                continue
            for o in other:
                storage.contradict(s, o, quote)
                decisions.append({"preference": o.statement, "action": "contradicted", "id": str(o.id)})
            if same:
                p = same[0]
                storage.reinforce(s, p, quote)
                action = "reinforced"
                if p.status in (PreferenceStatus.candidate, PreferenceStatus.stale) and (
                        p.support_count >= CONFIRM_AT_SUPPORT or c["explicit_general"]):
                    to_confirm.append(str(p.id))
            else:
                p = storage.add_preference(s, creator_id=creator, category=c["category"], attribute=c["attribute"],
                                           value=c["value"], statement=c["statement"],
                                           source=PreferenceSource.feedback, status=PreferenceStatus.candidate,
                                           confidence=GENERAL_CONF if c["explicit_general"] else CORRECTION_CONF,
                                           context=c["context"], evidence=quote)
                action = "new_candidate"
                if c["explicit_general"]:
                    to_confirm.append(str(p.id))
            decisions.append({"preference": p.statement, "action": action, "id": str(p.id),
                              "confidence": p.confidence, "support": p.support_count})
    return {"decisions": decisions, "to_confirm": list(dict.fromkeys(to_confirm))}


def route(state: MemoryState) -> str:
    return "ask" if state["to_confirm"] else "finish"


def ask(state: MemoryState, config) -> MemoryState:
    thread = config["configurable"]["thread_id"]
    with session_scope() as s:  # idempotent: this node re-runs from the top when resumed
        have = set(s.scalars(select(MemoryConfirmation.preference_id).where(MemoryConfirmation.thread_id == thread)))
        questions = []
        for pid in state["to_confirm"]:
            p = s.get(CreatorPreference, uuid.UUID(pid))
            q = (f"Should I remember this for future videos: \"{p.statement}\"? "
                 f"(seen {p.support_count}x, confidence {p.confidence:.2f})")
            if p.id not in have:
                s.add(MemoryConfirmation(thread_id=thread, creator_id=p.creator_id, preference_id=p.id, question=q))
            questions.append({"preference_id": pid, "question": q})
    answers = interrupt({"thread_id": thread, "questions": questions})
    return {"answers": answers}


def apply_answers(state: MemoryState, config) -> MemoryState:
    thread = config["configurable"]["thread_id"]
    decisions = list(state["decisions"])
    with session_scope() as s:
        for pid, answer in (state.get("answers") or {}).items():
            p = s.get(CreatorPreference, uuid.UUID(pid))
            if p is None:
                continue
            if answer == "confirm":
                storage.confirm(s, p)
            elif answer == "reject":
                storage.reject(s, p)
            else:
                continue
            decisions.append({"preference": p.statement, "action": f"creator_{answer}ed", "id": pid})
            for mc in s.scalars(select(MemoryConfirmation).where(MemoryConfirmation.thread_id == thread,
                                                                 MemoryConfirmation.preference_id == p.id)):
                mc.status, mc.answer = "answered", {"answer": answer}
    return {"decisions": decisions}


def finish(state: MemoryState) -> MemoryState:
    summary = {"candidates": len(state.get("candidates", [])), "decisions": state["decisions"],
               "asked": state.get("to_confirm", []), "answers": state.get("answers")}
    with session_scope() as s:
        s.get(Feedback, uuid.UUID(state["feedback_id"])).processed = summary
    return {"summary": summary}


def build_graph(checkpointer=None):
    g = StateGraph(MemoryState)
    for name, fn in [("receive", receive), ("extract", extract), ("update", update), ("ask", ask),
                     ("apply_answers", apply_answers), ("finish", finish)]:
        g.add_node(name, fn)
    g.add_edge(START, "receive")
    g.add_edge("receive", "extract")
    g.add_edge("extract", "update")
    g.add_conditional_edges("update", route, ["ask", "finish"])
    g.add_edge("ask", "apply_answers")
    g.add_edge("apply_answers", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)


@lru_cache
def _checkpointer(url: str):
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    conn = psycopg.connect(url.replace("+psycopg", ""), autocommit=True, prepare_threshold=0, row_factory=dict_row)
    saver = PostgresSaver(conn)
    saver.setup()  # creates checkpoint tables once (idempotent)
    return saver


def graph():
    return build_graph(_checkpointer(get_settings().database_url))


def _result(out: dict, thread: str) -> dict:
    pending = out.get("__interrupt__")
    if pending:
        return {"status": "awaiting_confirmation", "thread_id": thread, **pending[0].value}
    return {"status": "done", "thread_id": thread, **out.get("summary", {})}


def process_feedback(feedback_id: uuid.UUID | str) -> dict:
    thread = f"feedback-{feedback_id}"
    cfg = {"configurable": {"thread_id": thread}, "run_name": "memory_update", "tags": ["memory"],
           "metadata": {"feedback_id": str(feedback_id)}}
    return _result(graph().invoke({"feedback_id": str(feedback_id)}, cfg), thread)


def resume(thread_id: str, answers: dict[str, str]) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}, "run_name": "memory_update_resume", "tags": ["memory"]}
    return _result(graph().invoke(Command(resume=answers), cfg), thread_id)
