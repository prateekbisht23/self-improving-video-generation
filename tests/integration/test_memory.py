"""Creator memory: persistence, cautious learning, human confirmation via LangGraph interrupt,
contradiction handling, scoping, conflict resolution, and use in later editing sessions."""

import pytest
from sqlalchemy import select

import agent.graphs.editing_graph as eg
import memory.extraction as mx
from db.models import CreatorPreference, PreferenceStatus, User
from db.session import session_scope
from memory import storage
from memory.extraction import PreferenceCandidate
from memory.retrieval import retrieve
from tests.fakes import FakeModel
from tests.integration.test_edits_api import processed  # noqa: F401
from tests.unit.test_editing_graph import make_plan

TOP = dict(category="captions", attribute="caption_position", value="top", statement="Put captions at the top",
           context=[], quote="captions should be at the top")


def cand(**kw) -> PreferenceCandidate:
    return PreferenceCandidate(**{**TOP, "scope": "permanent", "explicit_general": False, **kw})


@pytest.fixture
def edit(client, processed, monkeypatch):  # noqa: F811
    """Factory: run an editing session with a scripted planner; returns (session json, planner prompt text)."""
    project, *_ = processed

    def run():
        fake = FakeModel(make_plan([("S1", 0.0, 5.0), ("S3", 4.0, 8.0)], title=None))
        monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
        sid = client.post(f"/projects/{project['id']}/edits",
                          json={"instructions": "lab teaser", "min_duration": 8, "max_duration": 15}).json()["id"]
        prompt = fake.calls[0][1][1].content
        return client.get(f"/edits/{sid}").json(), prompt
    return run


def feedback(client, monkeypatch, sid, text, *cands, kind="correction"):
    monkeypatch.setattr(mx, "extract", lambda *a, **k: list(cands))
    r = client.post(f"/edits/{sid}/feedback", json={"kind": kind, "text": text})
    assert r.status_code == 201, r.text
    return r.json()["memory"]


def test_single_correction_is_not_applied_until_reinforced_and_confirmed(client, edit, monkeypatch):
    s1, _ = edit()
    m = feedback(client, monkeypatch, s1["id"], "the captions should be at the top", cand())
    assert m["status"] == "done" and m["decisions"][0]["action"] == "new_candidate"
    pref = client.get("/creators/me/preferences").json()[0]
    assert pref["status"] == "candidate" and pref["confidence"] == 0.35

    s2, prompt2 = edit()                        # a candidate never shapes an edit
    assert "captions at the top" not in prompt2 and not [m for m in s2["memory_used"] if "id" in m]

    m = feedback(client, monkeypatch, s2["id"], "again: captions at the top please", cand())
    assert m["status"] == "awaiting_confirmation"                    # graph paused (interrupt)
    q = client.get("/memory/confirmations").json()
    assert len(q) == 1 and "Put captions at the top" in q[0]["question"]

    done = client.post(f"/memory/confirmations/{m['thread_id']}", json={"answers": {q[0]["preference_id"]: "confirm"}})
    assert done.status_code == 200 and done.json()["status"] == "done"   # resumed from the Postgres checkpoint
    assert client.get("/memory/confirmations").json() == []
    pref = client.get("/creators/me/preferences").json()[0]
    assert pref["status"] == "active" and pref["confidence"] >= 0.85 and pref["support_count"] == 2

    s3, prompt3 = edit()                         # now it shapes the next edit, and that is recorded
    assert "Put captions at the top" in prompt3
    assert s3["memory_used"][0]["statement"] == "Put captions at the top"

    kinds = [e["kind"] for e in client.get(f"/creators/me/preferences/{pref['id']}/events").json()]
    assert kinds == ["created", "reinforced", "confirmed"]          # auditable


def test_rejected_preferences_stay_rejected(client, edit, monkeypatch):
    s1, _ = edit()
    m = feedback(client, monkeypatch, s1["id"], "always use warm colours",
                 cand(category="color", attribute="color_look", value="warm", statement="Use a warm look",
                      explicit_general=True))
    assert m["status"] == "awaiting_confirmation"            # general wording -> ask right away
    pid = m["questions"][0]["preference_id"]
    client.post(f"/memory/confirmations/{m['thread_id']}", json={"answers": {pid: "reject"}})
    again = feedback(client, monkeypatch, s1["id"], "warm colours!",
                     cand(category="color", attribute="color_look", value="warm", statement="Use a warm look"))
    assert again["decisions"][0]["action"] == "previously_rejected"
    assert client.get("/creators/me/preferences", params={"status": "rejected"}).json()[0]["id"] == pid


def test_contradictions_lower_confidence_then_mark_stale(client, edit, monkeypatch):
    client.post("/creators/me/preferences", json={"statement": "Captions at the top", "category": "captions",
                                                  "attribute": "caption_position", "value": "top"})
    s1, _ = edit()
    bottom = cand(value="bottom", statement="Captions at the bottom")
    feedback(client, monkeypatch, s1["id"], "bottom please", bottom)
    top = next(p for p in client.get("/creators/me/preferences").json() if p["value"] == "top")
    assert top["status"] == "active" and top["confidence"] == 0.65   # one contradiction is not enough
    feedback(client, monkeypatch, s1["id"], "really, bottom", bottom)
    top = next(p for p in client.get("/creators/me/preferences").json() if p["value"] == "top")
    assert top["status"] == "stale" and top["contradict_count"] == 2


def test_session_feedback_applies_to_that_session_only(client, edit, monkeypatch):
    s1, _ = edit()
    feedback(client, monkeypatch, s1["id"], "for this one make it black and white",
             cand(category="color", attribute="color_look", value="bw", statement="Black and white for this video",
                  scope="session"))
    with session_scope() as s:
        p = s.scalar(select(CreatorPreference))
        assert p.status == PreferenceStatus.session and str(p.session_id) == s1["id"]
        mine = [r.statement for r in retrieve(s, p.creator_id, [], session_id=p.session_id)[0]]
        other = [r.statement for r in retrieve(s, p.creator_id, [], session_id=None)[0]]
    assert mine == ["Black and white for this video"] and other == []


def test_context_scoping_and_conflict_resolution(client):
    with session_scope() as s:
        u = User(handle="ctx-test")
        s.add(u)
        s.flush()
        kw = dict(category="color", attribute="color_look")
        storage.add_explicit(s, u.id, value="warm", statement="Warm look", **kw)
        storage.add_explicit(s, u.id, value="cool", statement="Cool look for interviews", context=["interview"], **kw)
        storage.add_explicit(s, u.id, value="vivid", statement="Vivid for b-roll", context=["b_roll"], **kw)
        interview, dropped = retrieve(s, u.id, ["talking_head", "interview"])
        broll, _ = retrieve(s, u.id, ["b_roll"])
        generic, _ = retrieve(s, u.id, [])
    assert [p.statement for p in interview] == ["Cool look for interviews"]   # specific beats generic
    assert any("lost to" in d["why"] for d in dropped) and any("does not match" in d["why"] for d in dropped)
    assert [p.statement for p in broll] == ["Vivid for b-roll"] and [p.statement for p in generic] == ["Warm look"]


def test_feedback_validation(client, edit):
    s1, _ = edit()
    assert client.post(f"/edits/{s1['id']}/feedback", json={"kind": "timestamp_issue", "text": "x",
                                                            "start": 999}).status_code == 422
    assert client.post(f"/edits/{s1['id']}/feedback", json={"kind": "correction"}).status_code == 422
    assert client.post(f"/edits/{s1['id']}/feedback", json={"kind": "accept"}).status_code == 201
