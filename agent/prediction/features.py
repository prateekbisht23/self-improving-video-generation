"""State -> features for next-action prediction. Shared by offline evaluation and the live agent."""

from editing.operations import OPERATIONS, READ_ONLY

ACTIONS = [a for a in OPERATIONS if a not in READ_ONLY]  # the action space
STAGE_OF = {"select_clip": "assemble", "trim_clip": "assemble", "remove_clip": "assemble",
            "reorder_clips": "assemble", "add_transition": "transitions", "apply_style": "style",
            "set_framing": "style", "adjust_audio": "audio", "generate_captions": "captions",
            "add_caption": "captions", "add_title": "titles"}


def _wants(text: str) -> dict[str, bool]:
    t = text.lower()
    return {"want_captions": "caption" in t or "subtitle" in t or "on mute" in t,
            "want_title": "title" in t and "no title" not in t,
            "want_transition": any(w in t for w in ("fade", "dissolve", "transition")),
            "want_color": any(w in t for w in ("colour", "color", "warm", "cool", "vivid", "black and white", "look")),
            "want_caps": "all caps" in t or "uppercase" in t}


def featurize(timeline: dict | None, history: list[tuple[str, bool, str]], instructions: str,
              min_duration: float, max_duration: float, memory_text: str = "") -> dict:
    """history = [(action_name, ok, source), ...] of the actions before this step, oldest first."""
    tl = timeline or {}
    video = tl.get("video", [])
    dur = sum(c["src_out"] - c["src_in"] for c in video) - sum(c.get("transition_duration", 0) for c in video[1:])
    style = tl.get("style", {})
    f = {
        "n_clips": str(min(len(video), 5)),
        "dur_state": "none" if not video else "under" if dur < min_duration else "over" if dur > max_duration
        else "in",
        "has_captions": bool(tl.get("captions")),
        "has_title": bool(tl.get("titles")),
        "has_transition": any(c.get("transition_in", "cut") != "cut" for c in video),
        "color_set": style.get("color", "none") != "none",
        "prev1": history[-1][0] if history else "<start>",
        "prev2": history[-2][0] if len(history) > 1 else "<start>",
        "prev1_ok": history[-1][1] if history else True,
        "prev1_source": history[-1][2] if history else "<start>",
        "styled": any(a == "apply_style" and ok for a, ok, _ in history),
        "step": str(min(len(history), 12)),
        **_wants(instructions + " " + memory_text),
    }
    return f
