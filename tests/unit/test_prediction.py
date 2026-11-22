from agent.prediction.features import ACTIONS, featurize
from agent.prediction.predictors import LearnedPredictor, MarkovPredictor, RulePredictor


def f(**kw):
    base = featurize(None, [], "make a short with captions and a title", 15, 30)
    return base | kw


def test_featurize_tracks_state_and_wants():
    tl = {"video": [{"src_in": 0, "src_out": 40, "transition_in": "cut"}], "captions": [], "titles": [],
          "style": {"color": "none"}}
    x = featurize(tl, [("select_clip", True, "plan")], "fade please, ALL CAPS captions", 15, 30)
    assert x["dur_state"] == "over" and x["prev1"] == "select_clip" and x["want_transition"] and x["want_caps"]


def test_rules_follow_the_workflow():
    r = RulePredictor()
    assert r.predict(f())[0] == "select_clip"
    assert r.predict(f(dur_state="over", n_clips="3"))[0] == "trim_clip"
    assert all(a in ACTIONS for a in r.predict(f(dur_state="in", styled=True, has_captions=True, has_title=True)))


def test_learned_and_markov_fit_and_rank():
    X = [f(prev1="<start>"), f(prev1="select_clip"), f(prev1="apply_style"), f(prev1="generate_captions")] * 5
    y = ["select_clip", "apply_style", "generate_captions", "add_title"] * 5
    for m in (MarkovPredictor().fit(X, y), LearnedPredictor().fit(X, y)):
        assert m.predict(f(prev1="apply_style"))[0] == "generate_captions"
        assert len(m.predict(f())) == 3
