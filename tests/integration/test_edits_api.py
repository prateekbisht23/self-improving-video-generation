"""Instruction -> plan -> validated actions -> versions -> render, through the API (Phase 2 exit)."""

import pytest

import agent.graphs.editing_graph as eg
from tests.fakes import FakeModel
from tests.integration.conftest import upload
from tests.unit.test_editing_graph import make_plan


@pytest.fixture
def processed(client, project, synthetic):
    if not (synthetic / "speech.mp4").exists():
        pytest.skip("needs macOS `say`")
    a = upload(client, project["id"], synthetic / "speech.mp4").json()   # -> scene S1
    b = upload(client, project["id"], synthetic / "cuts.mp4").json()     # -> scenes S2..S4
    assert client.get(f"/assets/{a['id']}").json()["status"] == "ready"
    return project, a, b


def test_edit_session_end_to_end(client, processed, monkeypatch):
    project, *_ = processed
    fake = FakeModel(make_plan([("S1", 0.0, 6.0), ("S99", 0, 3), ("S4", 8.0, 11.0)], transition="fade"),
                     repairs=[[("select_clip", {"scene_id": "S3", "src_in": 4, "src_out": 7, "position": 1})]])
    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)

    r = client.post(f"/projects/{project['id']}/edits",
                    json={"instructions": "Lab teaser with captions", "min_duration": 8, "max_duration": 15})
    assert r.status_code == 202
    e = client.get(f"/edits/{r.json()['id']}").json()
    assert e["status"] == "rendered", e["error"]
    assert e["agent_version"].startswith("editing-agent-") and e["plan"]["clips"][1]["scene_id"] == "S99"
    assert e["trace_id"] and e["agent_config"]["config_hash"]  # links to the LangSmith root run

    acts = e["actions"]
    assert [a["step"] for a in acts] == list(range(1, len(acts) + 1))          # every attempt logged
    rejected = [a for a in acts if not a["ok"]]
    assert rejected and rejected[0]["version_before"] == rejected[0]["version_after"]  # no change
    assert any(a["source"] == "repair" and a["ok"] for a in acts)

    versions = e["versions"]
    assert [v["version"] for v in versions] == list(range(len(versions)))
    final = versions[-1]
    assert final["renders"] and final["renders"][0]["status"] == "done"
    rid = final["renders"][0]["id"]
    meta = client.get(f"/renders/{rid}").json()["meta"]
    assert meta["probe"]["height"] == 1920 and meta["timeline_sha256"] == final["content_hash"]
    video = client.get(f"/renders/{rid}/video")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"

    tl = client.get(f"/edits/{e['id']}/timeline").json()
    assert 8 <= sum(c["src_out"] - c["src_in"] for c in tl["video"]) and tl["captions"]

    # manual edit: same validation, new version authored by the user
    m = client.post(f"/edits/{e['id']}/actions", json={"name": "apply_style", "args": {"color": "bw"}})
    assert m.status_code == 201 and m.json()["created_by"] == "user"
    bad = client.post(f"/edits/{e['id']}/actions", json={"name": "trim_clip", "args": {"index": 42}})
    assert bad.status_code == 422 and "no clip at index 42" in bad.json()["detail"]
    assert client.get(f"/edits/{e['id']}").json()["actions"][-1]["ok"] is False  # rejected but logged

    # reproducibility: re-render the agent's final version -> identical inputs
    assert client.post(f"/edits/{e['id']}/render", params={"version": final["version"]}).status_code == 202
    again = client.get(f"/edits/{e['id']}").json()["versions"][final["version"]]["renders"]
    assert len(again) == 2
    m1, m2 = (client.get(f"/renders/{x['id']}").json()["meta"] for x in again)
    assert m1["timeline_sha256"] == m2["timeline_sha256"] and m1["filtergraph_sha256"] == m2["filtergraph_sha256"]
    assert m1["argv"][:-1] == m2["argv"][:-1]


def test_edit_requires_ready_sources(client, project):
    r = client.post(f"/projects/{project['id']}/edits", json={"instructions": "anything at all"})
    assert r.status_code == 422 and "ready source assets" in r.json()["detail"]


def test_style_profile_without_model(client, processed):
    _, _, cuts = processed
    p = client.post(f"/assets/{cuts['id']}/style-profile").json()
    assert p["shots"]["count"] == 3 and p["shots"]["median"] == pytest.approx(4.0, abs=0.1)
    assert p["guidance"]["pace"] == "medium" and p["observed"] is None
    assert client.get(f"/assets/{cuts['id']}/style-profile").json() == p
