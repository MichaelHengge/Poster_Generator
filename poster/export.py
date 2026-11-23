"""Element list -> vector PDF (PyMuPDF drawing API, real fonts embedded) and PNG.

Drawing directly (instead of converting the SVG) lets us embed any installed font and
position every word ourselves, which is what makes justified text exact.
"""
import pymupdf

from . import assets
from .fonts import get_font
from .render_svg import justify_spacing
from .textfit import MM_PER_PT

K = 72 / 25.4   # mm -> pt


def _c(hex_color):
    return tuple(v / 255 for v in assets.hex_rgb(hex_color))


def _p(x, y):
    return pymupdf.Point(x * K, y * K)


def _r(x, y, w, h):
    return pymupdf.Rect(x * K, y * K, (x + w) * K, (y + h) * K)


class _Painter:
    """Keeps one open Shape for vector drawing; flushes it before text/images to preserve z-order."""

    def __init__(self, page):
        self.page = page
        self.shape = None

    def sh(self):
        if self.shape is None:
            self.shape = self.page.new_shape()
        return self.shape

    def flush(self):
        if self.shape is not None:
            self.shape.commit()
            self.shape = None


def _rect(P, e):
    sh = P.sh()
    x, y, w, h = e["x"], e["y"], e["w"], e["h"]
    r = min(e["rx"], w / 2, h / 2) if e["rx"] > 0 else 0
    if r > 0 and e["corners"] == "top":
        r = min(e["rx"], w / 2, h)
        sh.draw_line(_p(x, y + h), _p(x, y + r))
        sh.draw_curve(_p(x, y + r), _p(x, y), _p(x + r, y))
        sh.draw_line(_p(x + r, y), _p(x + w - r, y))
        sh.draw_curve(_p(x + w - r, y), _p(x + w, y), _p(x + w, y + r))
        sh.draw_line(_p(x + w, y + r), _p(x + w, y + h))
    elif r > 0:
        sh.draw_rect(_r(x, y, w, h), radius=min(0.5, r / min(w, h)))
    else:
        sh.draw_rect(_r(x, y, w, h))
    stroke = e["stroke"]
    sh.finish(fill=_c(e["fill"]), color=_c(stroke) if stroke else None,
              width=e["stroke_w"] * K if stroke else 0, fill_opacity=e["opacity"], closePath=True)


def _text(P, e):
    P.flush()
    tw = pymupdf.TextWriter(P.page.rect)
    size_mm = e["size"] * MM_PER_PT
    lh = size_mm * e["lh"]
    total = sum(len(p) for p in e["paras"]) * lh
    y0 = e["y"] + (e["h"] - total) / 2 if e["valign"] == "middle" else e["y"]
    base = y0 + (lh - size_mm) / 2 + size_mm * 0.80
    font = get_font(e["font"], e["bold"], e["italic"])
    pt = e["size"]
    i = 0
    for para in e["paras"]:
        for j, ln in enumerate(para):
            by = (base + i * lh) * K
            i += 1
            if not ln:
                continue
            line_w = font.text_length(ln, fontsize=pt) / K   # mm
            ws = justify_spacing(e, ln, last=(j == len(para) - 1))
            if ws:
                cx = e["x"]
                for word in ln.split(" "):
                    tw.append((cx * K, by), word, font=font, fontsize=pt)
                    cx += font.text_length(word + " ", fontsize=pt) / K + ws
                continue
            if e["align"] == "center":
                x = e["x"] + (e["w"] - line_w) / 2
            elif e["align"] == "right":
                x = e["x"] + e["w"] - line_w
            else:
                x = e["x"]
            tw.append((x * K, by), ln, font=font, fontsize=pt)
    tw.write_text(P.page, color=_c(e["color"]))


def to_pdf(doc: dict) -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=doc["W"] * K, height=doc["H"] * K)
    P = _Painter(page)
    for e in doc["elements"]:
        t = e["type"]
        if t == "rect":
            _rect(P, e)
        elif t == "ellipse":
            sh = P.sh()
            sh.draw_oval(_r(e["cx"] - e["rx"], e["cy"] - e["ry"], 2 * e["rx"], 2 * e["ry"]))
            sh.finish(fill=_c(e["fill"]), color=None, width=0, fill_opacity=e["opacity"])
        elif t == "line":
            sh = P.sh()
            sh.draw_line(_p(e["x1"], e["y1"]), _p(e["x2"], e["y2"]))
            sh.finish(color=_c(e["color"]), width=e["width"] * K)
        elif t == "polygon":
            sh = P.sh()
            sh.draw_polyline([_p(x, y) for x, y in e["points"]])
            sh.finish(fill=_c(e["fill"]), color=None, width=0, closePath=True)
        elif t == "qr":
            sh = P.sh()
            n = len(e["matrix"])
            m = e["size"] / n
            for r, row in enumerate(e["matrix"]):
                c = 0
                while c < n:
                    if row[c]:
                        start = c
                        while c < n and row[c]:
                            c += 1
                        sh.draw_rect(_r(e["x"] + start * m, e["y"] + r * m, (c - start) * m, m))
                    c += 1
            sh.finish(fill=_c(e["color"]), color=None, width=0)
        elif t == "image":
            P.flush()
            page.insert_image(_r(e["x"], e["y"], e["w"], e["h"]), stream=e["png"], keep_proportion=False)
        elif t == "text":
            _text(P, e)
    P.flush()
    pdf.set_metadata({"creator": "Poster Generator", "producer": "PyMuPDF"})
    try:
        pdf.subset_fonts()
    except Exception:
        pass
    return pdf.tobytes(garbage=3, deflate=True)


def pdf_to_png(pdf_bytes: bytes, dpi: int = 150) -> bytes:
    with pymupdf.open("pdf", pdf_bytes) as d:
        return d[0].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
