"""Element list -> editable PowerPoint slide (python-pptx native shapes)."""
import io

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from . import assets

EMU_PER_MM = 36000
MAX_SLIDE_MM = 1422.4  # PowerPoint limit: 56 inches


def _rgb(h):
    return RGBColor(*assets.hex_rgb(h))


def _set_alpha(shape, opacity):
    if opacity >= 1:
        return
    sf = shape._element.spPr.find(qn("a:solidFill"))
    clr = sf[0] if sf is not None and len(sf) else None
    if clr is not None:
        a = clr.makeelement(qn("a:alpha"), {"val": str(int(opacity * 100000))})
        clr.append(a)


def to_pptx(doc: dict) -> bytes:
    W, H = doc["W"], doc["H"]
    k = min(1.0, MAX_SLIDE_MM / max(W, H))   # scale down if slide would exceed PowerPoint's limit

    def L(v):
        return Emu(int(round(v * k * EMU_PER_MM)))

    prs = Presentation()
    prs.slide_width, prs.slide_height = L(W), L(H)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    shapes = slide.shapes

    for e in doc["elements"]:
        t = e["type"]
        if t == "rect":
            r = min(e["rx"], e["w"] / 2, e["h"] / 2)
            if r <= 0:
                kind = MSO_SHAPE.RECTANGLE
            elif e["corners"] == "top":
                kind = MSO_SHAPE.ROUND_2_SAME_RECTANGLE
            else:
                kind = MSO_SHAPE.ROUNDED_RECTANGLE
            sh = shapes.add_shape(kind, L(e["x"]), L(e["y"]), L(e["w"]), L(e["h"]))
            if r > 0:
                sh.adjustments[0] = min(0.5, r / min(e["w"], e["h"]))
                if kind == MSO_SHAPE.ROUND_2_SAME_RECTANGLE:
                    sh.adjustments[1] = 0.0
            sh.fill.solid()
            sh.fill.fore_color.rgb = _rgb(e["fill"])
            _set_alpha(sh, e["opacity"])
            if e["stroke"]:
                sh.line.color.rgb = _rgb(e["stroke"])
                sh.line.width = L(e["stroke_w"])
            else:
                sh.line.fill.background()
            sh.shadow.inherit = False
        elif t == "ellipse":
            sh = shapes.add_shape(MSO_SHAPE.OVAL, L(e["cx"] - e["rx"]), L(e["cy"] - e["ry"]), L(2 * e["rx"]), L(2 * e["ry"]))
            sh.fill.solid()
            sh.fill.fore_color.rgb = _rgb(e["fill"])
            _set_alpha(sh, e["opacity"])
            sh.line.fill.background()
            sh.shadow.inherit = False
        elif t == "line":
            sh = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, L(e["x1"]), L(e["y1"]), L(e["x2"]), L(e["y2"]))
            sh.line.color.rgb = _rgb(e["color"])
            sh.line.width = L(e["width"])
        elif t == "polygon":
            pts = [(int(round(px * k * EMU_PER_MM)), int(round(py * k * EMU_PER_MM))) for px, py in e["points"]]
            fb = shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
            fb.add_line_segments(pts[1:], close=True)
            sh = fb.convert_to_shape()
            sh.fill.solid()
            sh.fill.fore_color.rgb = _rgb(e["fill"])
            sh.line.fill.background()
            sh.shadow.inherit = False
        elif t == "image":
            sh = shapes.add_picture(io.BytesIO(e["png"]), L(e["x"]), L(e["y"]), L(e["w"]), L(e["h"]))
        elif t == "qr":
            sh = shapes.add_picture(io.BytesIO(assets.qr_png(e["matrix"], e["color"])),
                                    L(e["x"]), L(e["y"]), L(e["size"]), L(e["size"]))
        elif t == "text":
            sh = shapes.add_textbox(L(e["x"]), L(e["y"]), L(e["w"] * 1.02), L(e["h"]))
            tf = sh.text_frame
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.NONE
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE if e["valign"] == "middle" else MSO_ANCHOR.TOP
            align = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT,
                     "justify": PP_ALIGN.JUSTIFY}[e["align"]]
            for i, lines in enumerate(e["paras"]):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.alignment = align
                p.line_spacing = Pt(e["size"] * k * e["lh"])
                run = p.add_run()
                run.text = " ".join(lines)
                f = run.font
                f.name = e["font"]
                f.size = Pt(e["size"] * k)
                f.bold = e["bold"]
                f.italic = e["italic"]
                f.color.rgb = _rgb(e["color"])
        else:
            continue
        if e.get("name"):
            sh.name = e["name"]

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
