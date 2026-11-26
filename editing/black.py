"""Keep clips out of dips to black (policy `trim_black`). Pure: spans in, new in/out points out."""


def black_free(src_in: float, src_out: float, spans: list[tuple[float, float]] | tuple, margin: float = 0.1,
               min_keep: float = 1.0) -> tuple[float, float]:
    """The longest part of [src_in, src_out] that stays `margin` seconds clear of every black span.

    Returns the original interval when there is no black in it, or when the longest clear part is
    shorter than `min_keep` seconds or than 40% of the clip (cutting most of a clip away to dodge a
    dip would do more damage than the dip)."""
    cuts = sorted((max(src_in, a - margin), min(src_out, b + margin)) for a, b in spans if b > src_in and a < src_out)
    if not cuts:
        return src_in, src_out
    pieces, t = [], src_in
    for a, b in cuts:
        if a > t:
            pieces.append((t, a))
        t = max(t, b)
    if t < src_out:
        pieces.append((t, src_out))
    if not pieces:
        return src_in, src_out
    a, b = max(pieces, key=lambda p: p[1] - p[0])
    if b - a < max(min_keep, 0.4 * (src_out - src_in)):
        return src_in, src_out
    return round(a, 3), round(b, 3)
