"""A failed stage must not corrupt earlier stages, and a retry must resume, not restart."""

import pytest
from sqlalchemy import select

from db.models import ProcessingStage, Scene
from db.session import session_scope
from services.worker.pipeline import run_pipeline
from tests.integration.conftest import upload


def _stages(asset_id):
    with session_scope() as s:
        return {st.name: (st.status.value, st.attempts) for st in s.scalars(
            select(ProcessingStage).where(ProcessingStage.asset_id == asset_id))}


def test_failure_then_resume(client, project, synthetic, monkeypatch):
    # Make the frames stage fail during the initial (inline) processing.
    calls = {"n": 0}

    def flaky_frames(asset_id, force):
        calls["n"] += 1
        raise TimeoutError("simulated transient failure")

    import services.worker.pipeline as p

    monkeypatch.setattr(p, "STAGES", [(n, flaky_frames if n == "frames" else f) for n, f in p.STAGES])
    asset = upload(client, project["id"], synthetic / "cuts.mp4").json()
    aid = asset["id"]

    detail = client.get(f"/assets/{aid}").json()
    assert detail["status"] == "failed" and "simulated transient failure" in detail["last_error"]
    st = _stages(aid)
    assert st["scenes"] == ("done", 1) and st["frames"] == ("failed", 1) and st["index"] == ("pending", 0)
    with session_scope() as s:  # completed work survived the failure
        assert len(s.scalars(select(Scene).where(Scene.asset_id == aid)).all()) == 3

    monkeypatch.undo()  # "the transient problem went away"
    summary = run_pipeline(aid)
    assert summary["probe"] == summary["scenes"] == summary["transcript"] == "cached"  # resumed
    st = _stages(aid)
    assert st["scenes"] == ("done", 1) and st["frames"] == ("done", 2) and st["index"] == ("done", 1)
    assert client.get(f"/assets/{aid}").json()["status"] == "ready"


def test_force_from_reruns_downstream_only(client, project, synthetic):
    aid = upload(client, project["id"], synthetic / "cuts.mp4").json()["id"]
    r = client.post(f"/assets/{aid}/process", params={"force_from": "frames"})
    assert r.status_code == 202
    st = _stages(aid)
    assert st["scenes"][1] == 1 and st["frames"][1] == 2 and st["index"][1] == 2


def test_unknown_force_stage_rejected(client, project, synthetic):
    aid = upload(client, project["id"], synthetic / "cuts.mp4").json()["id"]
    assert client.post(f"/assets/{aid}/process", params={"force_from": "bogus"}).status_code == 422


@pytest.mark.parametrize("stage", ["scenes"])
def test_restage_is_idempotent(client, project, synthetic, stage):
    aid = upload(client, project["id"], synthetic / "cuts.mp4").json()["id"]
    run_pipeline(aid, force_from=stage)
    with session_scope() as s:  # replaced, not duplicated
        assert len(s.scalars(select(Scene).where(Scene.asset_id == aid)).all()) == 3
