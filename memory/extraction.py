"""Turn free-text feedback (or an explicit statement) into normalised preference candidates."""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from config.models import get_chat_model

Category = Literal["captions", "color", "pacing", "duration", "transitions", "titles", "structure", "audio",
                   "framing", "other"]


class PreferenceCandidate(BaseModel):
    category: Category
    attribute: str = Field(description="snake_case key for WHAT the preference is about, from this list when it "
                                       "fits: caption_presence, caption_position, caption_case, caption_size, "
                                       "color_look, max_duration, min_duration, transition_style, title_cards, "
                                       "opening_style, ending_style, shot_length, music, framing_mode")
    value: str = Field(description="short normalised value, e.g. 'top', 'all_caps', 'warm', '20s', 'hard_cuts', "
                                   "'none', 'question'")
    statement: str = Field(description="the preference as one short imperative sentence")
    scope: Literal["session", "permanent"] = Field(
        description="'permanent' only if the creator states a general habit (always/never/I prefer/my videos/"
                    "in general); a fix for this particular video is 'session'")
    explicit_general: bool = Field(description="true if the wording clearly states a lasting rule "
                                               "(always, never, every video, from now on)")
    context: list[Literal["talking_head", "b_roll", "explainer", "interview", "multi_source"]] = Field(
        default_factory=list, description="only if the creator limits it to a kind of video; else empty")
    quote: str = Field(description="the exact words from the feedback this came from")


class Extraction(BaseModel):
    candidates: list[PreferenceCandidate]


SYSTEM = """You extract editing preferences from a video creator's feedback for an AI video editor.
Only extract preferences about how videos should be edited (captions, colour, pacing, length, transitions,
titles, structure, audio, framing). Ignore praise without content, and complaints that don't imply a
preference. Do not invent preferences. Distinguish a one-off fix for this video (scope 'session') from a
general habit (scope 'permanent')."""


def extract(text: str, kind: str = "comment", start: float | None = None) -> list[PreferenceCandidate]:
    where = f" (about the moment at {start:.1f}s)" if start is not None else ""
    out: Extraction = get_chat_model("planner").with_structured_output(Extraction).invoke([
        SystemMessage(SYSTEM), HumanMessage(f"Feedback type: {kind}{where}\nFeedback: {text}")])
    return [c.model_copy(update={"attribute": c.attribute.strip().lower().replace(" ", "_")[:64],
                                 "value": c.value.strip().lower()[:160]}) for c in out.candidates]
