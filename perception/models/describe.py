"""Frame -> SceneDescription with a vision-capable chat model."""

import base64
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from config.models import get_chat_model
from perception.schemas import SceneDescription

SYSTEM = (
    "You describe single video frames for a video-editing system. Be literal and concrete: "
    "describe only what is visible (people, objects, setting, on-screen text, shot type such as "
    "close-up / wide). Do not speculate about the story."
)


def describe_frame(frame: str | Path, transcript_hint: str | None = None) -> SceneDescription:
    b64 = base64.b64encode(Path(frame).read_bytes()).decode()
    text = "Describe this frame."
    if transcript_hint:
        text += f' Speech during this shot (may help with context): "{transcript_hint[:300]}"'
    model = get_chat_model("vision").with_structured_output(SceneDescription)
    return model.invoke([
        SystemMessage(SYSTEM),
        HumanMessage(content=[
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]),
    ])
