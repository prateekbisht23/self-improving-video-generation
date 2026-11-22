"""Every agent render is evaluated in a separate job; reports and issues are stored and linked."""

from sqlalchemy import select

import agent.graphs.editing_graph as eg
from db.models import EvaluationIssue
from db.session import session_scope
from tests.fakes import FakeModel
from tests.integration.test_edits_api import processed  # noqa: F401  (fixture)
from tests.unit.test_editing_graph import make_plan


def test_render_is_auto_evaluated_and_issues_are_stored(client, processed, monkeypatch):  # noqa: F811
    project, *_ = processed
    # clip boundaries at 1.0s / 6.0s fall inside spoken words of the real transcript -> known temporal defect
    fake = FakeModel(make_plan([("S1", 0.0, 1.0), ("S1", 2.0, 6.0), ("S3", 4.0, 8.0)], title=None))
    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
    sid = client.post(f"/projects/{project['id']}/edits",
                      json={"instructions": "teaser", "min_duration": 8, "max_duration": 15}).json()["id"]

    evs = client.get(f"/edits/{sid}/evaluations").json()
    assert len(evs) == 1
    ev = evs[0]
    assert ev["technical_gate_passed"] and ev["evaluator_version"] == "eval-1.0" and ev["judge_model"] is None
    assert ev["version"] == client.get(f"/edits/{sid}").json()["versions"][-1]["version"]  # linked to version
    assert "temporal.cut_through_word" in ev["failed"]

    full = client.get(f"/evaluations/{ev['id']}").json()["report"]
    ids = {c["id"] for c in full["checks"]}
    assert {"technical.duration_in_range", "captions.sync", "temporal.repeated_footage"} <= ids
    with session_scope() as s:
        issues = s.scalars(select(EvaluationIssue).where(EvaluationIssue.check_id == "temporal.cut_through_word")).all()
        assert issues and issues[0].start is not None
        assert all("out-point cuts" in e["detail"] or "in-point cuts" in e["detail"] for e in issues[0].evidence)

    # manual re-evaluation of the same render creates a second, independent report
    rid = ev["render_id"]
    assert client.post(f"/renders/{rid}/evaluate").status_code == 202
    assert len(client.get(f"/edits/{sid}/evaluations").json()) == 2
