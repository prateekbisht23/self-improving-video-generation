"""Next-action predictors with one interface: predict(features) -> ranked action names (top 3)."""

import hashlib
import json
from collections import Counter, defaultdict

from agent.prediction.features import ACTIONS


class RulePredictor:
    """Hand-written workflow state machine (the baseline)."""
    name = "rules-v1"

    def fit(self, X, y):
        return self

    def predict(self, f: dict) -> list[str]:
        order: list[str] = []
        if not f["prev1_ok"] and f["prev1"] in ACTIONS:  # after a rejection the repair usually re-assembles
            order += ["select_clip", "trim_clip", "remove_clip"]
        if f["dur_state"] == "none":
            order.append("select_clip")
        if f["dur_state"] == "over":
            order += ["trim_clip", "remove_clip"]
        if f["dur_state"] == "under" or f["prev1"] == "select_clip":
            order.append("select_clip")
        if f["want_transition"] and not f["has_transition"]:
            order.append("add_transition")
        if not f["styled"]:
            order.append("apply_style")
        if not f["has_captions"]:
            order.append("generate_captions")
        if not f["has_title"]:
            order.append("add_title")
        order += ["trim_clip", "select_clip", "remove_clip"]
        return list(dict.fromkeys(order))[:3]


class MarkovPredictor:
    """'What usually follows the previous action' — a trivial learned reference point."""
    name = "markov-1"

    def fit(self, X, y):
        self.table = defaultdict(Counter)
        self.prior = Counter(y)
        for f, a in zip(X, y, strict=True):
            self.table[f["prev1"]][a] += 1
        return self

    def predict(self, f: dict) -> list[str]:
        ranked = [a for a, _ in self.table.get(f["prev1"], Counter()).most_common()]
        ranked += [a for a, _ in self.prior.most_common()]
        return list(dict.fromkeys(ranked))[:3]


class LearnedPredictor:
    """Multinomial logistic regression over one-hot / boolean state features."""

    def __init__(self, C: float = 1.0):
        self.C = C
        self.name = "learned-logreg"

    def fit(self, X, y):
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline

        self.model = make_pipeline(DictVectorizer(sparse=False), LogisticRegression(C=self.C, max_iter=3000))
        self.model.fit(X, y)
        digest = hashlib.sha256(json.dumps([X, y], sort_keys=True, default=str).encode()).hexdigest()[:8]
        self.name = f"learned-logreg-{digest}"
        return self

    def predict(self, f: dict) -> list[str]:
        proba = self.model.predict_proba([f])[0]
        classes = self.model.classes_
        return [classes[i] for i in proba.argsort()[::-1][:3]]


class LLMPredictor:
    """Ask the planner model for the 3 most likely next operations (validated against the action space)."""

    def __init__(self):
        from config.models import model_id

        self.name = f"llm:{model_id('planner').split(':', 1)[-1]}"

    def fit(self, X, y):
        return self

    def predict(self, f: dict) -> list[str]:
        from langchain_core.messages import HumanMessage, SystemMessage
        from pydantic import BaseModel, Field

        from config.models import get_chat_model
        from editing.operations import OPERATIONS

        class Next(BaseModel):
            actions: list[str] = Field(description="the 3 most likely next operations, most likely first")

        space = "\n".join(f"- {a}: {(OPERATIONS[a][0].__doc__ or '').strip()}" for a in ACTIONS)
        out = get_chat_model("planner").with_structured_output(Next).invoke([
            SystemMessage("You predict the next operation an AI video editor will perform. Answer only with "
                          f"operation names from this list:\n{space}"),
            HumanMessage("Current editing state:\n" + json.dumps(f, indent=1))])
        return [a.strip() for a in out.actions][:3]
