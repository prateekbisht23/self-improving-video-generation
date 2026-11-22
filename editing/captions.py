"""Word-synced captions: map source-time word timestamps onto the output timeline."""

from editing.context import EditContext, WordT
from editing.timeline.schema import Caption, Timeline

PUNCT_BREAK = (".", "?", "!", ",", ";", ":")


def _join(tokens: list[str]) -> str:
    """Whisper splits hyphenated words/contractions into tokens ("six", "-year"); glue them back."""
    out = ""
    for t in tokens:
        out += t if (out and t[:1] in "-'’") or out.endswith("-") else (" " + t if out else t)
    return out.strip()


def timeline_words(tl: Timeline, ctx: EditContext) -> list[WordT]:
    """Every spoken word that survives the edit, in timeline time. Words carry their clip index."""
    out: list[WordT] = []
    for ci, (clip, start) in enumerate(zip(tl.video, tl.clip_starts(), strict=True)):
        for w in ctx.words.get(clip.asset_id, []):
            mid = (w.start + w.end) / 2
            if clip.src_in <= mid < clip.src_out:  # word belongs to the clip it is mostly in
                t0 = start + max(w.start, clip.src_in) - clip.src_in
                t1 = start + min(w.end, clip.src_out) - clip.src_in
                if out and t0 < out[-1].end:      # crossfade overlap: keep order monotonic
                    t0 = out[-1].end
                if t1 - t0 > 0.02:
                    out.append(WordT(round(t0, 3), round(t1, 3), w.text, clip=ci))
    return out


def build_captions(tl: Timeline, ctx: EditContext) -> list[Caption]:
    """Chunk words into short caption cards (short-form style: 1-4 words, broken at punctuation)."""
    max_words = tl.style.captions.max_words
    words = timeline_words(tl, ctx)
    caps: list[Caption] = []
    chunk: list[WordT] = []

    def flush():
        if chunk:
            text = _join([w.text for w in chunk])
            end = min(chunk[-1].end + 0.15, tl.duration)  # brief hold so cards don't flicker
            if caps and caps[-1].end > chunk[0].start:
                caps[-1].end = chunk[0].start
            caps.append(Caption(start=chunk[0].start, end=max(end, chunk[0].start + 0.2), text=text))
            chunk.clear()

    for w in words:
        gap = chunk and w.start - chunk[-1].end > 0.6
        new_clip = chunk and w.clip != chunk[-1].clip  # never let a card span a cut
        glued = chunk and w.text[:1] in "-'’"          # keep "six-year" on one card
        if chunk and not glued and (len(chunk) >= max_words or gap or new_clip
                                    or chunk[-1].end - chunk[0].start > 1.6):
            flush()
        chunk.append(w)
        if w.text.endswith(PUNCT_BREAK):
            flush()
    flush()
    total = tl.duration
    return [c for c in caps if c.start < total - 0.05 and c.end > c.start + 0.05]
