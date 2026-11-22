"""Describe an editing session's context with a few tags, so preferences can be scoped
("in interviews I want ...") and irrelevant ones are not applied indiscriminately (FR-08)."""

PERSON_WORDS = ("man", "woman", "person", "speaker", "speaking", "interview", "presenter", "scientist")


def context_tags(scenes: list[dict], n_assets: int, instructions: str = "") -> list[str]:
    tags: set[str] = set()
    if scenes:
        total = sum(s["end"] - s["start"] for s in scenes) or 1
        speech = sum((s["end"] - s["start"]) * s.get("speech_ratio", 0) for s in scenes) / total
        person = sum((s["end"] - s["start"]) for s in scenes
                     if any(w in (s.get("description") or "").lower() for w in PERSON_WORDS)) / total
        short = sum(1 for s in scenes if s["end"] - s["start"] < 3) / len(scenes)
        if person > 0.5 and speech > 0.5:
            tags |= {"talking_head", "interview"}
        if person < 0.3 or short > 0.5:
            tags.add("b_roll")
        if speech > 0.5 and person < 0.5:
            tags.add("explainer")
    if n_assets > 1:
        tags.add("multi_source")
    if "interview" in instructions.lower():
        tags.add("interview")
    return sorted(tags)
