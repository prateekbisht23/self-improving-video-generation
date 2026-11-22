"""A scripted stand-in for a chat model: returns a fixed plan and queued tool-call batches."""

from langchain_core.messages import AIMessage

from editing.context import EditContext, SceneInfo, WordT
from editing.timeline.schema import AssetRef


class FakeModel:
    def __init__(self, plan=None, repairs=None):
        self.plan, self.repairs, self.calls = plan, list(repairs or []), []

    def with_structured_output(self, schema):
        return _Structured(self)

    def bind_tools(self, tools):
        self.tool_names = [t.name for t in tools]
        return _Tools(self)


class _Structured:
    def __init__(self, m):
        self.m = m

    def invoke(self, messages):
        self.m.calls.append(("plan", messages))
        return self.m.plan


class _Tools:
    def __init__(self, m):
        self.m = m

    def invoke(self, messages):
        self.m.calls.append(("repair", messages))
        batch = self.m.repairs.pop(0) if self.m.repairs else []
        return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"call_{i}"}
                                                 for i, (n, a) in enumerate(batch)])


def synthetic_context(syn) -> EditContext:
    """speech.mp4 = one 9.9s scene with words; cuts.mp4 = three 4s scenes, no speech."""
    sp = AssetRef(id="speech", path=str(syn / "speech.mp4"), duration=9.9)
    cu = AssetRef(id="cuts", path=str(syn / "cuts.mp4"), duration=12.0)
    words = [WordT(0.0, 0.3, "Welcome"), WordT(0.3, 0.5, "to"), WordT(0.5, 0.7, "the"), WordT(0.7, 1.1, "editing"),
             WordT(1.1, 1.6, "lab."), WordT(2.0, 2.4, "Today"), WordT(2.4, 2.6, "we"), WordT(2.6, 2.9, "test"),
             WordT(2.9, 3.3, "scene"), WordT(3.3, 3.9, "detection."), WordT(5.0, 5.4, "Every"),
             WordT(5.4, 5.7, "word"), WordT(5.7, 6.2, "six"), WordT(6.2, 6.6, "-year"), WordT(6.6, 7.0, "counts.")]
    scenes = {"S1": SceneInfo("S1", "d1", "speech", 0, 0.0, 9.9, "test bars, narrator", transcript="Welcome...",
                              speech_ratio=0.8, segments=[(0.0, 1.6, "Welcome to the editing lab.")]),
              "S2": SceneInfo("S2", "d2", "cuts", 0, 0.0, 4.0, "test pattern"),
              "S3": SceneInfo("S3", "d3", "cuts", 1, 4.0, 8.0, "solid red"),
              "S4": SceneInfo("S4", "d4", "cuts", 2, 8.0, 12.0, "mandelbrot fractal")}

    def search(q, k):
        return [s for s in scenes.values() if q.lower() in s.description][:k]

    return EditContext(assets=[sp, cu], scenes=scenes, words={"speech": words}, search=search)
