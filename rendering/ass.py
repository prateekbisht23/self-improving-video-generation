"""Timeline captions/titles -> an ASS subtitle file rendered by libass (ffmpeg `subtitles` filter).

ASS (Advanced SubStation Alpha) lets us style text precisely: font, size, outline, position,
all in a coordinate space (PlayRes) that matches the 1080x1920 output.
"""

from editing.timeline.schema import Timeline

_ALIGN = {"bottom": 2, "center": 5, "top": 8}  # numpad layout: 2 = bottom-centre


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _color(rrggbb: str, alpha: str = "00") -> str:
    r, g, b = rrggbb[0:2], rrggbb[2:4], rrggbb[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()  # ASS colours are AABBGGRR


def _text(s: str, upper: bool) -> str:
    s = s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()
    return s.upper() if upper else s


def build_ass(tl: Timeline) -> str:
    o, cs = tl.output, tl.style.captions
    margin_v = {"bottom": int(o.height * 0.17), "center": 0, "top": int(o.height * 0.12)}[cs.position]
    title_size = int(cs.size * 1.15)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {o.width}", f"PlayResY: {o.height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caption,{cs.font},{cs.size},{_color(cs.color)},{_color(cs.highlight)},{_color('000000')},"
        f"{_color('000000', '80')},-1,0,0,0,100,100,0,0,1,{cs.outline},2,{_ALIGN[cs.position]},80,80,{margin_v},1",
        f"Style: Title,{cs.font},{title_size},{_color('FFFFFF')},{_color('FFFFFF')},{_color('000000')},"
        f"{_color('000000', '40')},-1,0,0,0,100,100,0,0,3,18,0,8,80,80,{int(o.height * 0.06)},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for c in tl.captions:
        lines.append(f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Caption,,0,0,0,,{_text(c.text, cs.uppercase)}")
    for t in tl.titles:
        lines.append(f"Dialogue: 1,{_ts(t.start)},{_ts(t.end)},Title,,0,0,0,,{_text(t.text, False)}")
    return "\n".join(lines) + "\n"
