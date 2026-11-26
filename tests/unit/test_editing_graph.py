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


def test_editing_graph_is_not_replayed_inside_a_resumed_checkpointed_graph(monkeypatch, synthetic, tmp_path):
    """Regression: run inside a checkpointed parent that crashes and resumes, the editing graph must
    run again on the new input instead of replaying the earlier call's result."""
    from typing import TypedDict

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    monkeypatch.setattr(eg, "get_chat_model", lambda role, **_: fake)
    fake = FakeModel(make_plan([("S1", 0, 5.0), ("S4", 8, 12)]))
    attempt = {"n": 0}

    class P(TypedDict):
        out: list

    def work(state):
        outs = []
        for instr in (["first", "second"] if attempt["n"] == 0 else ["third"]):
            rec = InMemoryRecorder(out_dir=tmp_path, do_render=False)
            outs.append(eg.run_edit(instr, EditDeps(ctx=synthetic_context(synthetic), recorder=rec),
                                    min_duration=8, max_duration=15)["instructions"])
            if attempt["n"] == 0 and instr == "second":
                attempt["n"] += 1
                raise RuntimeError("crash")
        return {"out": outs}

    g = StateGraph(P)
    g.add_node("work", work)
    g.add_edge(START, "work")
    g.add_edge("work", END)
    parent, cfg = g.compile(checkpointer=InMemorySaver()), {"configurable": {"thread_id": "t"}}
    with pytest.raises(RuntimeError):
        parent.invoke({"out": []}, cfg)
    assert parent.invoke(None, cfg)["out"] == ["third"]


def test_snap_repairs_word_keeps_repair_trims_close_to_what_was_asked(monkeypatch, synthetic, tmp_path):
    from agent.config import AgentConfig, AgentPolicy

    deps = EditDeps(ctx=synthetic_context(synthetic), recorder=InMemoryRecorder(out_dir=tmp_path, do_render=False))
    tl = eg.Timeline(assets=deps.ctx.assets, output=eg.OutputSpec(min_duration=8, max_duration=15))
    from editing.operations import apply_action

    tl = apply_action(tl, "select_clip", {"scene_id": "S1", "src_in": 0, "src_out": 9.9}, deps.ctx).timeline
    act = {"name": "trim_clip", "args": {"index": 0, "src_out": 3.1}, "source": "repair"}
    deps.config = AgentConfig(policy=AgentPolicy(snap_cuts="sentence"))
    assert eg._snap_args(tl, act, deps)["src_out"] == pytest.approx(4.0)       # sentence end, +0.9s
    deps.config = AgentConfig(policy=AgentPolicy(snap_cuts="sentence", snap_repairs="word"))
    assert abs(eg._snap_args(tl, act, deps)["src_out"] - 3.1) < 0.25          # nearest word gap
    assert eg._snap_args(tl, {**act, "source": "plan"}, deps)["src_out"] == pytest.approx(4.0)


def test_snapping_never_breaks_a_constraint_the_plain_action_meets(synthetic, tmp_path):
    from agent.config import AgentConfig, AgentPolicy
    from editing.operations import apply_action

    deps = EditDeps(ctx=synthetic_context(synthetic), recorder=InMemoryRecorder(out_dir=tmp_path, do_render=False),
                    config=AgentConfig(policy=AgentPolicy(snap_cuts="sentence")))
    tl = eg.Timeline(assets=deps.ctx.assets, output=eg.OutputSpec(min_duration=5, max_duration=7))
    tl = apply_action(tl, "select_clip", {"scene_id": "S4", "src_in": 8, "src_out": 12}, deps.ctx).timeline  # 4.0s
    state = {"timeline": tl.model_dump(), "current": {"name": "select_clip", "source": "plan",
                                                      "args": {"scene_id": "S1", "src_in": 0.8, "src_out": 3.1}},
             "step": 0, "version": 1, "min_duration": 5, "max_duration": 7, "history": [], "log": []}
    # sentence snapping would make this clip 0.0-4.0 (total 8.0s > 7s); plain 0.8-3.1 gives 6.3s: keep plain
    out = eg.execute(state, {"configurable": {"deps": deps}})
    assert deps.recorder.actions[-1]["args"]["src_in"] == 0.8 and deps.recorder.actions[-1]["args"]["src_out"] == 3.1
    assert eg.Timeline.model_validate(out["timeline"]).duration == pytest.approx(6.3)
    # with room in the window the snap is kept
    deps.recorder.actions.clear()
    eg.execute(state | {"max_duration": 15}, {"configurable": {"deps": deps}})
    assert deps.recorder.actions[-1]["args"]["src_in"] == pytest.approx(0.0)


def test_black_free_keeps_the_longest_clear_part():
    from editing.black import black_free

    assert black_free(0, 5, []) == (0, 5)
    assert black_free(10, 16, [(10.4, 11.4)]) == (11.5, 16)            # fade at the start
    assert black_free(0, 6, [(2.0, 2.5)]) == (2.6, 6)                  # the longer side wins
    assert black_free(0, 1.2, [(0.3, 0.6)]) == (0, 1.2)                # nothing usable left: unchanged
    assert black_free(0, 10, [(1, 8)]) == (0, 10)                      # would cut most of the clip: unchanged


def test_trim_black_moves_clip_edges_off_a_dip_only_where_captions_were_skipped(synthetic, tmp_path):
    from agent.config import AgentConfig, AgentPolicy
    from editing.context import SceneInfo
    from editing.timeline.schema import AssetRef
    from perception.video.black import black_spans

    ctx = synthetic_context(synthetic)
    ctx.assets.append(AssetRef(id="bg", path=str(synthetic / "black_gap.mp4"), duration=6.0))
    ctx.scenes["S5"] = SceneInfo("S5", "d5", "bg", 0, 0.0, 6.0, "colour, black, colour")
    spans = black_spans(str(synthetic / "black_gap.mp4"), 0.0, 6.0)
    assert len(spans) == 1 and spans[0][0] == pytest.approx(2.0, abs=0.1) and spans[0][1] == pytest.approx(4.0, abs=0.1)

    cfg = AgentConfig(policy=AgentPolicy(captions_follow_reference=True, trim_black="when_captions_skipped"))
    act = {"name": "select_clip", "source": "plan", "args": {"scene_id": "S5", "src_in": 0.0, "src_out": 3.5}}
    tl = eg.Timeline(assets=ctx.assets, output=eg.OutputSpec(min_duration=1, max_duration=10))
    state = {"instructions": "short teaser", "memory_text": ""}
    rec = InMemoryRecorder(out_dir=tmp_path, do_render=False)
    no_caps = {"observed": {"captions_present": False}, "guidance": {}}
    out = eg._black_args(tl, act, EditDeps(ctx=ctx, recorder=rec, config=cfg, style=no_caps), state, act["args"])
    assert out["src_in"] == 0.0 and out["src_out"] == pytest.approx(1.9, abs=0.1)
    # scope: without a style reference (or when captions were asked for) the knob is inert
    assert eg._black_args(tl, act, EditDeps(ctx=ctx, recorder=rec, config=cfg), state, act["args"]) == act["args"]
    asked = state | {"instructions": "short teaser with captions"}
    assert eg._black_args(tl, act, EditDeps(ctx=ctx, recorder=rec, config=cfg, style=no_caps), asked,
                          act["args"]) == act["args"]
    always = AgentConfig(policy=AgentPolicy(trim_black="always"))
    assert eg._black_args(tl, act, EditDeps(ctx=ctx, recorder=rec, config=always), state, act["args"]) != act["args"]
    assert cfg.scope() == "reference" and always.scope() is None
