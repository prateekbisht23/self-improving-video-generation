"""The editing graph with a scripted model: control flow, validation, repair, budgets."""

import pytest

import agent.graphs.editing_graph as eg
from agent.runtime import EditDeps, InMemoryRecorder
from agent.schemas.plan import EditPlan, PlannedClip
from tests.fakes import FakeModel, synthetic_context


def make_plan(clips, **kw):
    base = dict(understanding="u", hook="h", transition="cut", captions=True, caption_position="bottom",
                title="Lab", color="none", estimated_duration=10)
    return EditPlan(clips=[PlannedClip(scene_id=s, src_in=a, src_out=b, purpose="p") for s, a, b in clips],
                    **base | kw)


def run(monkeypatch, synthetic, tmp_path, fake, render=False, **kw):
    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
    rec = InMemoryRecorder(out_dir=tmp_path, do_render=render)
    final = eg.run_edit("Make a short lab teaser", EditDeps(ctx=synthetic_context(synthetic), recorder=rec),
                        min_duration=8, max_duration=15, **kw)
    return final, rec


def test_happy_path_versions_every_change(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S4", 8, 12)], transition="fade"))
    final, rec = run(monkeypatch, synthetic, tmp_path, fake, render=True)
    assert final["status"] == "rendered"
    assert [a["name"] for a in rec.actions] == ["select_clip", "select_clip", "add_transition", "apply_style",
                                                "generate_captions", "add_title"]
    assert all(a["ok"] for a in rec.actions) and sorted(rec.versions) == list(range(7))
    assert rec.renders[0]["probe"]["height"] == 1920
    assert final["render"]["timeline_sha256"] == rec.versions[6].content_hash()


def test_rejected_action_triggers_tool_call_repair(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S99", 0, 4)]),
                     repairs=[[("select_clip", {"scene_id": "S4", "position": 1})]])
    final, rec = run(monkeypatch, synthetic, tmp_path, fake)
    bad = rec.actions[1]
    assert bad["name"] == "select_clip" and not bad["ok"] and "unknown scene" in bad["error"]
    assert any(a["source"] == "repair" and a["ok"] for a in rec.actions)
    assert final["status"] == "rendered" and "select_clip" in fake.tool_names
    assert "S99" in fake.calls[1][1][1].content  # the repair prompt carried the error


def test_too_long_plan_is_repaired(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0, 9.9), ("S2", 0, 4), ("S3", 4, 8)]),  # 17.9s > 15s
                     repairs=[[("remove_clip", {"index": 2})]])
    final, rec = run(monkeypatch, synthetic, tmp_path, fake)
    assert final["status"] == "rendered"
    assert rec.versions[final["version"]].duration == pytest.approx(13.9)


def test_budget_exhaustion_falls_back_to_deterministic_fixup(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0, 9.9), ("S2", 0, 4), ("S3", 4, 8)]), repairs=[])  # repair does nothing
    final, rec = run(monkeypatch, synthetic, tmp_path, fake)
    assert final["status"] == "rendered" and final["repairs"] == eg.MAX_REPAIRS + 1
    assert rec.versions[final["version"]].duration <= 15 + 1e-6
    assert rec.actions[-1]["source"] == "fixup"


def test_too_short_without_help_fails_cleanly(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S2", 0, 2)]), repairs=[])
    final, rec = run(monkeypatch, synthetic, tmp_path, fake)
    assert final["status"] == "failed" and not rec.renders


def test_online_predictions_are_logged_for_every_action(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S4", 8, 12)], transition="fade"))
    final, rec = run(monkeypatch, synthetic, tmp_path, fake)
    assert [p["actual"] for p in rec.predictions] == [a["name"] for a in rec.actions]
    assert all(p["valid"] and len(p["predicted"]) == 3 for p in rec.predictions)
    assert rec.predictions[0]["predicted"][0] == "select_clip"  # empty timeline -> assemble first


# ------------------------------------------------------------------ Phase 5 policy knobs
def run_cfg(monkeypatch, synthetic, tmp_path, fake, policy, style=None, instructions="Make a short lab teaser"):
    from agent.config import AgentConfig, AgentPolicy

    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
    rec = InMemoryRecorder(out_dir=tmp_path, do_render=False)
    deps = EditDeps(ctx=synthetic_context(synthetic), recorder=rec, style=style,
                    config=AgentConfig(policy=AgentPolicy(**policy)))
    return eg.run_edit(instructions, deps, min_duration=8, max_duration=15), rec


def test_snap_cuts_moves_planned_edges_to_sentence_boundaries(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0.8, 3.1), ("S4", 8, 12)]))  # 0.8 is inside "editing", 3.1 inside "scene"
    final, rec = run_cfg(monkeypatch, synthetic, tmp_path, fake, {"snap_cuts": "sentence"})
    first = rec.actions[0]
    assert first["name"] == "select_clip" and first["ok"]
    assert first["args"]["src_in"] == pytest.approx(0.0) and first["args"]["src_out"] == pytest.approx(4.0)
    assert rec.actions[1]["args"] == {"scene_id": "S4", "src_in": 8, "src_out": 12, "purpose": "p"}  # silent b-roll


def test_default_policy_leaves_edges_alone(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S1", 0.8, 3.1), ("S4", 8, 12)]))
    final, rec = run_cfg(monkeypatch, synthetic, tmp_path, fake, {})
    assert rec.actions[0]["args"]["src_in"] == 0.8 and rec.actions[0]["args"]["src_out"] == 3.1


STYLE_NO_CAPTIONS = {"guidance": {"pace": "medium", "target_shot_seconds": 4, "max_shot_seconds": 8,
                                  "caption_position": "bottom", "caption_uppercase": False, "color": "none",
                                  "transition": "cut"},
                     "shots": {"median": 4, "p10": 2, "p90": 6, "cuts_per_minute": 15},
                     "observed": {"captions_present": False}}


@pytest.mark.parametrize("on,instructions,expect_captions", [
    (False, "Make a short lab teaser", True),            # v0.2 behaviour: plan says captions -> captions
    (True, "Make a short lab teaser", False),            # reference has none, nobody asked -> skip
    (True, "Make a teaser with captions", True),         # the instructions win
])
def test_captions_follow_reference(monkeypatch, synthetic, tmp_path, on, instructions, expect_captions):
    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S4", 8, 12)]))
    final, rec = run_cfg(monkeypatch, synthetic, tmp_path, fake, {"captions_follow_reference": on},
                         style=STYLE_NO_CAPTIONS, instructions=instructions)
    assert ("generate_captions" in [a["name"] for a in rec.actions]) is expect_captions


def test_fixup_extend_rescues_a_too_short_edit(monkeypatch, synthetic, tmp_path):
    fake = FakeModel(make_plan([("S2", 0, 2)]), repairs=[])
    final, rec = run_cfg(monkeypatch, synthetic, tmp_path, fake, {"fixup_extend": True})
    assert final["status"] == "rendered"
    assert 8 <= rec.versions[final["version"]].duration <= 15
    assert {a["name"] for a in rec.actions if a["source"] == "fixup"} >= {"trim_clip", "select_clip"}


def test_scene_reuse_check_can_be_switched_off(monkeypatch, synthetic, tmp_path):
    clips = [("S1", 0, 3), ("S1", 3.3, 6), ("S1", 6.2, 9.5)]  # one long interview scene, three sentences
    on, _ = run_cfg(monkeypatch, synthetic, tmp_path, FakeModel(make_plan(clips), repairs=[]), {})
    off, _ = run_cfg(monkeypatch, synthetic, tmp_path, FakeModel(make_plan(clips), repairs=[]),
                     {"scene_reuse_check": False})
    assert on["status"] == "failed" and off["status"] == "rendered"


def test_prompt_addendum_reaches_the_planner(monkeypatch, synthetic, tmp_path):
    from agent.config import AgentConfig

    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S4", 8, 12)]))
    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
    deps = EditDeps(ctx=synthetic_context(synthetic), recorder=InMemoryRecorder(out_dir=tmp_path, do_render=False),
                    config=AgentConfig(planner_addendum="- End on a complete sentence."))
    eg.run_edit("teaser", deps, min_duration=8, max_duration=15)
    assert "End on a complete sentence." in fake.calls[0][1][0].content
    assert deps.config.version in eg.agent_config(deps.config)["agent_version"]
