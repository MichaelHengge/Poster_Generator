"""Element list -> SVG string (mm user units). Kept to features PyMuPDF renders (no gradients/dashes)."""
from html import escape

from . import assets
from .fonts import css_family
from .textfit import MM_PER_PT, width_mm


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _top_round_path(x, y, w, h, r):
    r = min(r, w / 2, h)
    return (f"M{_f(x)},{_f(y + h)} V{_f(y + r)} A{_f(r)},{_f(r)} 0 0 1 {_f(x + r)},{_f(y)} "
            f"H{_f(x + w - r)} A{_f(r)},{_f(r)} 0 0 1 {_f(x + w)},{_f(y + r)} V{_f(y + h)} Z")


def _rect(e):
    attrs = f'fill="{e["fill"]}"'
    if e["opacity"] < 1:
        attrs += f' fill-opacity="{_f(e["opacity"])}"'
    if e["stroke"]:
        attrs += f' stroke="{e["stroke"]}" stroke-width="{_f(e["stroke_w"])}"'
    if e["rx"] > 0 and e["corners"] == "top":
        return f'<path d="{_top_round_path(e["x"], e["y"], e["w"], e["h"], e["rx"])}" {attrs}/>'
    rx = min(e["rx"], e["w"] / 2, e["h"] / 2)
    rx_attr = f' rx="{_f(rx)}"' if rx > 0 else ""
    return f'<rect x="{_f(e["x"])}" y="{_f(e["y"])}" width="{_f(e["w"])}" height="{_f(e["h"])}"{rx_attr} {attrs}/>'


def _text(e):
    size = e["size"] * MM_PER_PT
    lh = size * e["lh"]
    total = sum(len(p) for p in e["paras"]) * lh
    y = e["y"] + (e["h"] - total) / 2 if e["valign"] == "middle" else e["y"]
    first = y + (lh - size) / 2 + size * 0.80
    anchor, x = {"left": ("start", e["x"]), "justify": ("start", e["x"]), "center": ("middle", e["x"] + e["w"] / 2),
                 "right": ("end", e["x"] + e["w"])}[e["align"]]
    style = (f'font-family="{escape(css_family(e["font"]))}" font-size="{_f(size)}" '
             f'fill="{e["color"]}" text-anchor="{anchor}"')
    if e["bold"]:
        style += ' font-weight="bold"'
    if e["italic"]:
        style += ' font-style="italic"'
    out = [f'<text {style}>']
    i = 0
    for para in e["paras"]:
        for j, ln in enumerate(para):
            extra = ""
            ws = justify_spacing(e, ln, last=(j == len(para) - 1))
            if ws:
                extra = f' word-spacing="{_f(ws)}"'
            out.append(f'<tspan x="{_f(x)}" y="{_f(first + i * lh)}"{extra}>{escape(ln)}</tspan>')
            i += 1
    out.append("</text>")
    return "".join(out)


def justify_spacing(e, line, last) -> float:
    """Extra space (mm) per word gap so the line fills the box width; 0 = leave as is."""
    gaps = line.count(" ")
    if e["align"] != "justify" or last or not gaps:
        return 0.0
    natural = width_mm(line, e["size"], e["font"], e["bold"], e["italic"])
    ws = (e["w"] - natural) / gaps
    return ws if 0 < ws < e["size"] * MM_PER_PT * 1.5 else 0.0


def _qr(e):
    n = len(e["matrix"])
    m = e["size"] / n
    parts = []
    for r, row in enumerate(e["matrix"]):
        c = 0
        while c < n:
            if row[c]:
                start = c
                while c < n and row[c]:
                    c += 1
                parts.append(f"M{_f(e['x'] + start * m)},{_f(e['y'] + r * m)}h{_f((c - start) * m)}v{_f(m)}h{_f(-(c - start) * m)}z")
            c += 1
    return f'<path d="{"".join(parts)}" fill="{e["color"]}" shape-rendering="crispEdges"/>'


def to_svg(doc: dict, interactive: bool = False) -> str:
    W, H = doc["W"], doc["H"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{_f(W)}mm" height="{_f(H)}mm" viewBox="0 0 {_f(W)} {_f(H)}">']
    for e in doc["elements"]:
        t = e["type"]
        if t == "rect":
            out.append(_rect(e))
        elif t == "text":
            out.append(_text(e))
        elif t == "image":
            href = f"/api/image/{e['ref']}" if interactive and e.get("ref") else assets.data_url(e["png"])
            out.append(f'<image x="{_f(e["x"])}" y="{_f(e["y"])}" width="{_f(e["w"])}" height="{_f(e["h"])}" '
                       f'preserveAspectRatio="none" href="{href}"/>')
        elif t == "line":
            out.append(f'<line x1="{_f(e["x1"])}" y1="{_f(e["y1"])}" x2="{_f(e["x2"])}" y2="{_f(e["y2"])}" '
                       f'stroke="{e["color"]}" stroke-width="{_f(e["width"])}"/>')
        elif t == "ellipse":
            out.append(f'<ellipse cx="{_f(e["cx"])}" cy="{_f(e["cy"])}" rx="{_f(e["rx"])}" ry="{_f(e["ry"])}" '
                       f'fill="{e["fill"]}" fill-opacity="{_f(e["opacity"])}"/>')
        elif t == "qr":
            out.append(_qr(e))
        elif t == "polygon":
            pts = " ".join(f"{_f(px)},{_f(py)}" for px, py in e["points"])
            out.append(f'<polygon points="{pts}" fill="{e["fill"]}"/>')
    if interactive:   # invisible drag targets for the preview, never exported
        for e in doc["elements"]:
            if e["type"] == "hotspot":
                out.append(f'<rect class="hot" data-idx="{e["idx"]}" x="{_f(e["x"])}" y="{_f(e["y"])}" '
                           f'width="{_f(e["w"])}" height="{_f(e["h"])}"><title>{escape(e["title"])}</title></rect>')
        for e in doc["elements"]:   # edit-mode targets (shown only in edit mode via CSS)
            if e["type"] == "target":
                out.append(f'<rect class="tgt k-{e["kind"]}" data-key="{escape(e["key"])}" data-kind="{e["kind"]}" '
                           f'x="{_f(e["x"])}" y="{_f(e["y"])}" width="{_f(e["w"])}" height="{_f(e["h"])}">'
                           f'<title>{escape(e["label"])}</title></rect>')
        for e in doc["elements"]:
            if e["type"] == "divider":
                sizes = ",".join(_f(v) for v in e["sizes"])
                out.append(f'<rect class="split {e["dir"]}" x="{_f(e["x"])}" y="{_f(e["y"])}" width="{_f(e["w"])}" '
                           f'height="{_f(e["h"])}" data-split="{e["split"]}" data-i="{e["i"]}" data-dir="{e["dir"]}" '
                           f'data-start="{_f(e["start"])}" data-end="{_f(e["end"])}" data-sizes="{sizes}">'
                           f'<title>Drag to resize · double-click to reset</title></rect>')
        for e in doc["elements"]:   # process-flow arrows: click to remove (connect mode only, via CSS)
            if e["type"] == "arrowhot":
                out.append(f'<rect class="arrowhot" data-arrow="{e["idx"]}" x="{_f(e["x"])}" y="{_f(e["y"])}" '
                           f'width="{_f(e["w"])}" height="{_f(e["h"])}"><title>Click to remove this arrow</title></rect>')
    out.append("</svg>")
    return "\n".join(out)
