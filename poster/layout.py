"""Turns settings into a flat list of drawable elements (all coordinates in mm).

The element list is renderer-agnostic: render_svg turns it into SVG (preview, SVG export),
render_pdf into a PDF with embedded fonts (PDF, PNG) and render_pptx into editable PowerPoint shapes.

Fonts are passed around as a (heading family, body family) tuple.
All poster text is sample text - real content is added later in PowerPoint / Illustrator etc.
"""
import math
import random

from . import assets
from . import textfit as T
from .config import page_size_mm
from .structures import make_plan, Ctx
from . import tree as LT

PT = T.MM_PER_PT

SAMPLE = {
    "title": "A Concise and Memorable Title for Your Scientific Poster",
    "authors": "Firstname Lastname¹, Firstname Lastname², Firstname Lastname¹",
    "affiliations": "¹ Department, University, City, Country   ² Institute, Organisation, City, Country",
    "footer_left": "firstname.lastname@university.edu",
    "footer_center": "Conference Name 2026 · City",
    "qr_label": "Scan for the full paper",
}


# ---------------------------------------------------------------- element helpers
def rect(x, y, w, h, fill, rx=0.0, opacity=1.0, stroke=None, stroke_w=0.0, corners="all", name=None):
    return dict(type="rect", x=x, y=y, w=w, h=h, fill=fill, rx=rx, opacity=opacity,
                stroke=stroke, stroke_w=stroke_w, corners=corners, name=name)


def text(x, y, w, h, paras, size, color, font, bold=False, italic=False, align="left",
         valign="top", lh=1.25, name=None):
    return dict(type="text", x=x, y=y, w=w, h=h, paras=paras, size=size, color=color, font=font,
                bold=bold, italic=italic, align=align, valign=valign, lh=lh, name=name)


def image(x, y, w, h, png, name=None, ref=None):
    """ref: image-store id - the on-screen preview loads it by URL instead of embedding the bytes."""
    return dict(type="image", x=x, y=y, w=w, h=h, png=png, name=name, ref=ref)


def target(key, kind, x, y, w, h, label):
    """Clickable / droppable area for edit mode (preview only, never exported).
    kind: text | image | qr. key: path of the edited value (see static/app.js FIELD paths)."""
    return dict(type="target", key=key, kind=kind, x=x, y=y, w=w, h=h, label=label)


def contain(x, y, w, h, aspect):
    """Largest box with the given aspect ratio centred inside (x, y, w, h)."""
    if w / h > aspect:
        iw, ih = h * aspect, h
    else:
        iw, ih = w, w / aspect
    return x + (w - iw) / 2, y + (h - ih) / 2, iw, ih


def content_text(st, key):
    return st["content"].get(key) or SAMPLE[key]


def line(x1, y1, x2, y2, color, width, name=None):
    return dict(type="line", x1=x1, y1=y1, x2=x2, y2=y2, color=color, width=width, name=name)


def ellipse(cx, cy, rx, ry, fill, opacity=1.0, name=None):
    return dict(type="ellipse", cx=cx, cy=cy, rx=rx, ry=ry, fill=fill, opacity=opacity, name=name)


def qr(x, y, size, matrix, color, name="QR code"):
    return dict(type="qr", x=x, y=y, size=size, matrix=matrix, color=color, name=name)


def polygon(points, fill, name=None):
    return dict(type="polygon", points=points, fill=fill, name=name)


def text_height(paras, size, lh):
    return T.n_lines(paras) * size * PT * lh


def parse_ratios(s: str) -> list[float]:
    try:
        r = [float(p) for p in str(s).replace("/", ":").split(":") if p.strip()]
        r = [v for v in r if v > 0][:6]
        return r or [1, 1, 1]
    except ValueError:
        return [1, 1, 1]


# ---------------------------------------------------------------- main entry
def build_poster(st: dict) -> dict:
    W, H = page_size_mm(st)
    s = math.sqrt(W * H / (841 * 1189))          # scale relative to A0
    fs = s * st["font_scale"]                     # font scale
    pal = {k[2:]: v for k, v in st.items() if k.startswith("c_")}
    font = (st["font_heading"], st["font_body"])
    rng = random.Random(st["seed"])
    E: list[dict] = []
    m = st["margin"] * s
    gut = st["gutter"] * s
    radius = st["corner_radius"] * s

    _background(E, st, pal, W, H, s, rng)

    # ------------------------------------------------ top bar
    top_h = _top_bar(E, st, pal, W, H, s, fs, m, font) if st["top_enabled"] else 0.0
    # ------------------------------------------------ bottom bar
    bot_h = _bottom_bar(E, st, pal, W, H, s, fs, m, font)

    # ------------------------------------------------ content
    area = (m, top_h + m, W - m, H - bot_h - m)
    style, key, tkey = _content(E, st, pal, area, s, fs, gut, radius, font, W > H)

    warnings = [e["text"] for e in E if e["type"] == "warning"]
    tree_on = isinstance((st.get("layout_trees") or {}).get(tkey), dict)
    return {"W": W, "H": H, "elements": E, "style": style, "layout_key": key, "warnings": warnings,
            "tree_key": tkey, "tree_active": tree_on}


# ---------------------------------------------------------------- moving sections
def _geometry(st):
    """Content area etc. without drawing the poster (the bars are measured into a throw-away list)."""
    W, H = page_size_mm(st)
    s = math.sqrt(W * H / (841 * 1189))
    fs = s * st["font_scale"]
    pal = {k[2:]: v for k, v in st.items() if k.startswith("c_")}
    font = (st["font_heading"], st["font_body"])
    m, gut = st["margin"] * s, st["gutter"] * s
    scratch: list[dict] = []
    top_h = _top_bar(scratch, st, pal, W, H, s, fs, m, font) if st["top_enabled"] else 0.0
    bot_h = _bottom_bar(scratch, st, pal, W, H, s, fs, m, font)
    return (m, top_h + m, W - m, H - bot_h - m), gut, s, W > H, (W, H)


def _leaf_slots(plan):
    """For every section box: the split and child index that sizes it (the innermost split child holding it)."""
    out = {}
    for p, (x, y, w, h) in enumerate(plan.boxes):
        cx, cy, best = x + w / 2, y + h / 2, None
        for sp in plan.splits:
            if len(sp.boxes) < 2:
                continue
            for c, (bx, by, bw, bh) in enumerate(sp.boxes):
                if bx - 0.5 <= cx <= bx + bw + 0.5 and by - 0.5 <= cy <= by + bh + 0.5:
                    if best is None or bw * bh <= best[0] + 1e-6:
                        best = (bw * bh, sp, c)
        if best:
            out[p] = (best[1], best[2])
    return out


def move_section(st: dict, frm: int, to: int) -> dict:
    """Move section `frm` onto the place of section `to`, taking its box (and size) along.
    The layout becomes an editable tree (see tree.py); for layouts that can't be one, the sections are
    re-ordered and keep their sizes. Returns what the client needs to apply the change."""
    secs = st["sections"]
    n = len(secs)
    frm, to = max(0, min(n - 1, frm)), max(0, min(n - 1, to))
    ids = [sec.get("id") or str(i) for i, sec in enumerate(secs)]
    area, gut, s, landscape, page = _geometry(st)
    style, plan, key, tkey = _make_layout(st, secs, area, gut, s, landscape)
    tree = (st.get("layout_trees") or {}).get(tkey)
    if isinstance(tree, dict) and tree.get("c"):
        tree = LT.bake(tree, secs, area, gut, Ctx((st.get("split_sizes") or {}).get(key)))
    else:
        gen_style, gen_plan, _ = _generated(st, secs, area, gut, landscape)
        tree = LT.capture(gen_plan, secs, gut, gen_style)
    if tree is not None:
        box = {ids[i]: plan.boxes[i] for i in range(min(n, len(plan.boxes)))}
        size_along = lambda sid, d: round(box[sid][2] if d == "h" else box[sid][3], 2)
        new_tree = LT.move(tree, ids[frm], ids[to], size_along)
        order_ids = LT.leaves(new_tree)
        order = [ids.index(i) for i in order_ids if i in ids]
        order += [i for i in range(n) if i not in order]
        result = {"order": order, "tree_key": tkey, "tree": new_tree, "clear_key": "tree|" + tkey,
                  "sizes_key": None, "sizes": None}
        new = dict(st)
        new["sections"] = [secs[i] for i in order]
        new["layout_trees"] = {**(st.get("layout_trees") or {}), tkey: new_tree}
        new["split_sizes"] = {k: v for k, v in (st.get("split_sizes") or {}).items() if k != "tree|" + tkey}
    else:
        order = list(range(n))
        order.insert(to, order.pop(frm))
        sizes = {sp.id: [b[2] if sp.dir == "h" else b[3] for b in sp.boxes] for sp in plan.splits}
        touched = set()
        for p, (sp, c) in _leaf_slots(plan).items():
            if p < len(order) and order[p] < len(plan.boxes):
                src = plan.boxes[order[p]]
                sizes[sp.id][c] = src[2] if sp.dir == "h" else src[3]
                touched.add(sp.id)
        over = dict((st.get("split_sizes") or {}).get(key) or {})
        for sid in touched:
            over[str(sid)] = [round(max(v, 1.0), 2) for v in sizes[sid]]
        result = {"order": order, "tree_key": None, "tree": None, "clear_key": None, "sizes_key": key, "sizes": over}
        new = dict(st)
        new["sections"] = [secs[i] for i in order]
        new["split_sizes"] = {**(st.get("split_sizes") or {}), key: over}
    result["settings"] = new
    result["moved_index"] = order.index(frm)
    return result


# ---------------------------------------------------------------- background
def _background(E, st, pal, W, H, s, rng):
    bg = pal["background"]
    kind = st["background"]
    if kind == "gradient":
        c2 = assets.mix(bg, pal["secondary"], 0.22)
        E.append(image(0, 0, W, H, assets.gradient_png(bg, c2, "diagonal"), name="Background"))
        return
    E.append(rect(0, 0, W, H, bg, name="Background"))
    if kind == "blobs":
        spots = [(0, 0.25), (1, 0.15), (0, 0.8), (1, 0.7), (0.5, 1.0)]
        rng2 = random.Random(st["seed"] * 7 + 3)
        for i, (fx, fy) in enumerate(spots):
            r = min(W, H) * rng2.uniform(0.18, 0.35)
            col = pal["secondary"] if i % 2 == 0 else pal["accent"]
            E.append(ellipse(fx * W + rng2.uniform(-0.05, 0.05) * W, fy * H + rng2.uniform(-0.05, 0.05) * H,
                             r, r, col, opacity=0.10, name="Background shape"))
    elif kind == "grid":
        step = 30 * s
        col = assets.mix(bg, pal["muted"], 0.18)
        x = step
        while x < W:
            E.append(line(x, 0, x, H, col, 0.25 * s, name="Grid"))
            x += step
        y = step
        while y < H:
            E.append(line(0, y, W, y, col, 0.25 * s, name="Grid"))
            y += step


# ---------------------------------------------------------------- top bar
def _logo_boxes(ids, h, aspect, max_w_factor=2.2):
    """(w, h, (bytes, aspect) | None, id) per logo slot; empty slots are placeholders with the given aspect."""
    out = []
    for iid in ids:
        img = assets.load_image(iid) if iid else None
        a = img[1] if img else aspect
        w, hh = h * a, h
        if w > h * max_w_factor:
            w = h * max_w_factor
            hh = w / a
        out.append((w, hh, img, iid))
    return out


def _top_bar(E, st, pal, W, H, s, fs, m, font):
    style = st["top_style"]
    on_bar = style in ("solid", "gradient")
    bg = pal["background"]
    title_col = pal["on_primary"] if on_bar else assets.readable(bg, pal["primary"], pal["secondary"], pal["text"])
    sub_col = pal["on_primary"] if on_bar else pal["text"]
    pad = max(m, 22 * s)
    logo_h = st["logo_size"] * s
    gap = 15 * s

    c = st["content"]
    left = _logo_boxes([c["logo_left"]] if st["logo_left"] else [], logo_h, 1.7)
    nr = int(st["logos_right"])
    right = _logo_boxes([(c["logos_right"][i] if i < len(c["logos_right"]) else "") for i in range(nr)], logo_h, 1.25)
    left_w = sum(b[0] for b in left) + (gap * 2 if left else 0)
    right_w = sum(b[0] for b in right) + gap * (len(right) + 1 if right else 0)
    if st["top_align"] == "center":
        left_w = right_w = max(left_w, right_w)
    tx = m + left_w
    tw = W - 2 * m - left_w - right_w

    # title: shrink until it fits in two lines
    title_pt = 92 * fs
    while True:
        tparas = T.wrap(content_text(st, "title"), tw, title_pt, font[0], True) if st["show_title"] else []
        if T.n_lines(tparas) <= 2 or title_pt < 40 * fs or not tparas:
            break
        title_pt *= 0.93
    auth_pt, aff_pt = 44 * fs, 32 * fs
    aparas = T.wrap(content_text(st, "authors"), tw, auth_pt, font[1], False) if st["show_authors"] else []
    fparas = T.wrap(content_text(st, "affiliations"), tw, aff_pt, font[1], False) if st["show_affiliations"] else []

    th = text_height(tparas, title_pt, 1.15)
    ah = text_height(aparas, auth_pt, 1.25)
    fh = text_height(fparas, aff_pt, 1.25)
    sp1 = 12 * s if (tparas and (aparas or fparas)) else 0
    sp2 = 6 * s if (aparas and fparas) else 0
    block_h = th + sp1 + ah + sp2 + fh
    bar_h = 2 * pad + max(block_h, max((b[1] for b in left + right), default=0))
    accent_h = 5 * s if st["top_accent_line"] else 0

    if style == "solid":
        E.append(rect(0, 0, W, bar_h, pal["primary"], name="Top bar"))
    elif style == "gradient":
        E.append(image(0, 0, W, bar_h, assets.gradient_png(pal["primary"], assets.mix(pal["primary"], pal["secondary"], 0.85)),
                       name="Top bar"))
    if accent_h:
        E.append(rect(0, bar_h, W, accent_h, pal["accent"], name="Top accent line"))

    align = st["top_align"]
    y = (bar_h - block_h) / 2
    if tparas:
        E.append(text(tx, y, tw, th, tparas, title_pt, title_col, font[0], bold=True, align=align, lh=1.15, name="Title"))
        E.append(target("c.title", "text", tx, y, tw, th, "Title"))
    y += th + sp1
    if aparas:
        E.append(text(tx, y, tw, ah, aparas, auth_pt, sub_col, font[1], bold=False, align=align, name="Authors"))
        E.append(target("c.authors", "text", tx, y, tw, ah, "Authors"))
    y += ah + sp2
    if fparas:
        E.append(text(tx, y, tw, fh, fparas, aff_pt, sub_col, font[1], italic=True, align=align, name="Affiliations"))
        E.append(target("c.affiliations", "text", tx, y, tw, fh, "Affiliations"))

    def place_logo(x, w, h, name, img=None, iid="", key=""):
        ly = (bar_h - h) / 2
        rx = min(8 * s, st["corner_radius"] * s)
        light = not on_bar or st["logo_backing"]
        if st["logo_backing"] and on_bar:
            bp = 6 * s
            E.append(rect(x - bp, ly - bp, w + 2 * bp, h + 2 * bp, "#FFFFFF", rx=rx, name=name + " backing"))
        E.append(target(key, "image", x, ly, w, h, name))
        if img:
            E.append(image(x, ly, w, h, img[0], name=name, ref=iid))
            return
        if light:
            base = "#FFFFFF" if on_bar else bg
            fill, stroke = assets.mix(base, pal["secondary"], 0.14), assets.mix(base, pal["secondary"], 0.45)
            lbl = assets.mix(pal["secondary"], pal["text"], 0.35)
            E.append(rect(x, ly, w, h, fill, rx=rx, stroke=stroke, stroke_w=0.8 * s, name=name + " placeholder"))
        else:   # directly on the coloured bar: translucent box
            lbl = pal["on_primary"]
            E.append(rect(x, ly, w, h, pal["on_primary"], rx=rx, opacity=0.16, name=name + " placeholder"))
        pt = min(h * 0.3, w * 0.2) / PT
        E.append(text(x, ly, w, h, [["LOGO"]], pt, lbl, font[0], bold=True, align="center", valign="middle",
                      name=name + " label"))

    if left:
        w, h, img, iid = left[0]
        place_logo(m + gap * 0.5, w, h, "Logo left", img, iid, "c.logo_left")
    x = W - m
    for i, (w, h, img, iid) in enumerate(reversed(right)):
        slot = len(right) - 1 - i
        x -= w + (gap * 0.5 if i == 0 else gap)
        place_logo(x, w, h, f"Logo right {slot + 1}", img, iid, f"c.logos_right.{slot}")
    return bar_h + accent_h


# ---------------------------------------------------------------- bottom bar
def _bottom_bar(E, st, pal, W, H, s, fs, m, font):
    if not st["bottom_enabled"]:          # no footer bar -> no QR code either
        return 0.0
    has_qr = st["qr_enabled"] and st["qr_url"].strip()
    style = st["bottom_style"]
    on_bar = style in ("solid", "gradient")
    col = pal["on_primary"] if on_bar else pal["text"]
    pad = 12 * s
    txt_pt = 30 * fs
    qr_size = st["qr_size"] * s if has_qr else 0
    qr_pad = 4 * s
    bar_h = max(txt_pt * PT * 3 + 2 * pad, qr_size + 2 * qr_pad + 2 * pad)
    y0 = H - bar_h

    if style == "solid":
        E.append(rect(0, y0, W, bar_h, pal["primary"], name="Bottom bar"))
    elif style == "gradient":
        E.append(image(0, y0, W, bar_h, assets.gradient_png(assets.mix(pal["primary"], pal["secondary"], 0.85), pal["primary"]),
                       name="Bottom bar"))
    if st["top_accent_line"]:
        E.append(rect(0, y0 - 3 * s, W, 3 * s, pal["accent"], name="Bottom accent line"))

    right_edge = W - m
    if has_qr:
        qx = right_edge - qr_size - qr_pad
        qy = y0 + (bar_h - qr_size) / 2
        E.append(rect(qx - qr_pad, qy - qr_pad, qr_size + 2 * qr_pad, qr_size + 2 * qr_pad, "#FFFFFF",
                      rx=min(4 * s, st["corner_radius"] * s), name="QR backing"))
        E.append(qr(qx, qy, qr_size, assets.qr_matrix(st["qr_url"].strip()), "#000000"))
        E.append(target("qr_url", "qr", qx - qr_pad, qy - qr_pad, qr_size + 2 * qr_pad, qr_size + 2 * qr_pad, "QR code link"))
        right_edge = qx - qr_pad - 12 * s
        if st["show_qr_label"]:
            lw = min(250 * s, right_edge - W * 0.6)
            paras = T.wrap(content_text(st, "qr_label"), lw, txt_pt, font[1], True)
            th = text_height(paras, txt_pt, 1.2)
            E.append(text(right_edge - lw, y0 + (bar_h - th) / 2, lw, th, paras, txt_pt, col, font[1],
                          bold=True, align="right", lh=1.2, name="QR label"))
            E.append(target("c.qr_label", "text", right_edge - lw, y0 + (bar_h - th) / 2, lw, th, "QR label"))
            right_edge -= lw + 12 * s
    avail = right_edge - m
    for key, align, x, w in (("footer_left", "left", m, avail * 0.45),
                             ("footer_center", "center", m + avail * 0.5, avail * 0.5)):
        if st["show_" + key]:
            paras = T.wrap(content_text(st, key), w, txt_pt, font[1], False)
            th = text_height(paras, txt_pt, 1.2)
            E.append(text(x, y0 + (bar_h - th) / 2, w, th, paras, txt_pt, col, font[1],
                          align="left" if align == "left" else "center", lh=1.2, name=key.replace("_", " ").title()))
            E.append(target("c." + key, "text", x, y0 + (bar_h - th) / 2, w, th,
                            "Contact" if key == "footer_left" else "Event"))
    return bar_h


# ---------------------------------------------------------------- content area
def tree_key(st, landscape):
    """Identifies a rearranged layout (independent of the number of sections, which may change later)."""
    ratios = parse_ratios(st["columns"])
    return f"{st['layout_style']}|{st['seed']}|{'L' if landscape else 'P'}|{':'.join(f'{r:g}' for r in ratios)}"


def _generated(st, secs, area, gut, landscape, gap_extra=None):
    ratios = parse_ratios(st["columns"])
    # the key identifies "this generated layout"; user-dragged sizes are stored under it
    key_suffix = f"{st['seed']}|{len(secs)}|{'L' if landscape else 'P'}|{':'.join(f'{r:g}' for r in ratios)}"
    # same seed -> same random choices; only the given gaps get wider
    return make_plan(st["layout_style"], area, len(secs), ratios, gut, random.Random(f"layout-{st['seed']}"),
                     landscape, st.get("split_sizes"), key_suffix, gap_extra)


def _from_tree(st, tree, tkey, secs, area, gut, gap_extra=None):
    key = "tree|" + tkey
    ctx = Ctx((st.get("split_sizes") or {}).get(key), gap_extra)
    plan = LT.plan_from_tree(tree, secs, area, gut, ctx)
    plan.splits = ctx.splits
    return tree.get("style") or "columns", plan, key


def _make_layout(st, secs, area, gut, s, landscape):
    """Section boxes for this poster: the generated layout - or the user's rearranged version of it -
    with room made for flow arrows."""
    tkey = tree_key(st, landscape)
    tree = (st.get("layout_trees") or {}).get(tkey)
    if isinstance(tree, dict) and tree.get("c"):
        def plan_with(gap_extra):
            return _from_tree(st, tree, tkey, secs, area, gut, gap_extra)
    else:
        def plan_with(gap_extra):
            return _generated(st, secs, area, gut, landscape, gap_extra)
    style, plan, key = plan_with(None)
    extra, _ = _arrow_room(plan, secs, st, gut, s)
    if extra:
        style, plan, key = plan_with(extra)
    _, local = _arrow_room(plan, secs, st, gut, s)
    for ia, ib, horiz, extra in local:     # gaps that aren't a split boundary: shrink just those two boxes
        (ax, ay, aw, ah), (bx, by, bw, bh) = plan.boxes[ia], plan.boxes[ib]
        e = extra / 2
        if horiz:
            if bx >= ax + aw - 0.6:
                plan.boxes[ia], plan.boxes[ib] = (ax, ay, aw - e, ah), (bx + e, by, bw - e, bh)
            else:
                plan.boxes[ia], plan.boxes[ib] = (ax + e, ay, aw - e, ah), (bx, by, bw - e, bh)
        else:
            if by >= ay + ah - 0.6:
                plan.boxes[ia], plan.boxes[ib] = (ax, ay, aw, ah - e), (bx, by + e, bw, bh - e)
            else:
                plan.boxes[ia], plan.boxes[ib] = (ax, ay + e, aw, ah - e), (bx, by, bw, bh - e)
    return style, plan, key, tkey


def _content(E, st, pal, area, s, fs, gut, radius, font, landscape):
    secs = st["sections"] or [{"title": "Section", "figure": "auto"}]
    titles = [sec["title"] for sec in secs]
    if st["number_sections"]:
        titles = [f"{i + 1}. {t}" for i, t in enumerate(titles)]
    style, plan, key, tkey = _make_layout(st, secs, area, gut, s, landscape)
    fig_counter = [0]
    look = (st["arrow_style"], pal.get(st["arrow_color"], pal["accent"]), pal["background"], st["arrow_size"], s)
    boxes = {(sec.get("id") or str(i)): box for i, (sec, box) in enumerate(zip(secs, plan.boxes))}
    pairs = [(n, boxes[a], boxes[b]) for n, (a, b) in enumerate(st["flow_arrows"]) if a in boxes and b in boxes]
    # connectors between sections that don't face each other run *behind* the cards, so they only show in the gaps
    for n, A, B in pairs:
        if not _facing(A, B, s, plan.boxes):
            _elbow(E, look, A, B, n)
    for i, (sec, title, box) in enumerate(zip(secs, titles, plan.boxes)):
        # placeholder randomness is tied to the section (its id), so moving a section keeps its look
        brng = random.Random(f"{st['seed']}-{sec.get('id') or i}")
        _section(E, st, pal, title, *box, s, fs, radius, font, brng, fig_counter, sec, sec.get("id") or str(i))
        E.append(dict(type="hotspot", x=box[0], y=box[1], w=box[2], h=box[3], idx=i, title=sec["title"]))
    # process-flow arrows: the ones built into the "Process flow" layout, then the user's connections
    for cx, cy, aw, ah in plan.arrows:      # the Process flow layout's own arrows: scaled to fit their gap
        gap = aw / 0.55
        factor = {"chevron": 2.0, "triangle": 2.0, "block": 2.4, "circle": 3.03, "line": 3.2}.get(look[0], 2.0)
        fit = (gap - 2 * max(5 * s, gut * 0.3)) / (factor * aw / 2)
        _arrow(E, look[0], look[1], look[2], min(look[3], fit), s, cx, cy, aw, "right", gap=gap)
    for n, A, B in pairs:
        if _facing(A, B, s, plan.boxes):
            _connection(E, look, A, B, gut, n)
    # resize handles in the gaps between neighbouring children of every split (preview only)
    for sp in plan.splits:
        axis = 0 if sp.dir == "h" else 1
        sizes = [b[2 + axis] for b in sp.boxes]
        for i in range(len(sp.boxes) - 1):
            a, b = sp.boxes[i], sp.boxes[i + 1]
            if sp.dir == "h":
                g = (a[0] + a[2], a[1], b[0] - a[0] - a[2], a[3])
            else:
                g = (a[0], a[1] + a[3], a[2], b[1] - a[1] - a[3])
            E.append(dict(type="divider", x=g[0], y=g[1], w=g[2], h=g[3], split=sp.id, i=i, dir=sp.dir,
                          start=a[axis], end=b[axis] + b[2 + axis], sizes=sizes))
    return style, key, tkey




# ---------------------------------------------------------------- process-flow arrows
ARROW_TURN = {"right": 0, "down": 90, "left": 180, "up": 270}


def _turned(points, cx, cy, direction):
    """Points given for an arrow pointing right (around 0, 0), turned to `direction` and moved to (cx, cy)."""
    a = math.radians(ARROW_TURN[direction])
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in points]


def _arrow(E, style, color, halo, size, s, cx, cy, length, direction, gap=0.0):
    """One arrow of the chosen style centred at (cx, cy). `gap` = free space it sits in (for the line style)."""
    Lh = length * size / 2                     # half length
    name = "Flow arrow"
    if style == "chevron":
        pts = [(-Lh, -Lh * 1.5), (Lh, 0), (-Lh, Lh * 1.5), (-Lh + Lh * 0.76, 0)]
        E.append(polygon(_turned(pts, cx, cy, direction), color, name=name))
    elif style == "triangle":
        pts = [(-Lh, -Lh * 1.2), (Lh, 0), (-Lh, Lh * 1.2)]
        E.append(polygon(_turned(pts, cx, cy, direction), color, name=name))
    elif style == "block":
        t, hx = Lh * 0.42, Lh * 0.1
        pts = [(-Lh * 1.2, -t), (hx, -t), (hx, -Lh * 1.1), (Lh * 1.2, 0), (hx, Lh * 1.1), (hx, t), (-Lh * 1.2, t)]
        E.append(polygon(_turned(pts, cx, cy, direction), color, name=name))
    elif style == "circle":
        r = Lh * 1.35
        E.append(ellipse(cx, cy, r * 1.12, r * 1.12, halo, name=name + " ring"))
        E.append(ellipse(cx, cy, r, r, color, name=name))
        k = r * 0.5
        pts = [(-k * 0.55, -k), (k * 0.85, 0), (-k * 0.55, k)]
        E.append(polygon(_turned(pts, cx, cy, direction), "#FFFFFF", name=name + " head"))
    else:   # line: a stroke across the gap with a head, reaching a little into the cards when the gap is small
        reach = max(gap / 2, Lh * 1.6)
        head = Lh * 0.9
        x0, x1 = -reach, reach - head
        w = max(1.2 * s, Lh * 0.22)
        shaft = [(x0, -w / 2), (x1, -w / 2), (x1, w / 2), (x0, w / 2)]
        E.append(polygon(_turned(shaft, cx, cy, direction), color, name=name + " line"))
        E.append(polygon(_turned([(x1 - 0.01, -head * 0.75), (reach, 0), (x1 - 0.01, head * 0.75)], cx, cy, direction),
                         color, name=name))


def _arrow_span(st, gut, s):
    """Gap an arrow of the current style and size needs (arrow length plus a little air on both sides)."""
    base = max(24 * s, min(gut * 0.55, 40 * s))
    lh = base * st["arrow_size"] / 2
    length = {"chevron": 2.0, "triangle": 2.0, "block": 2.4, "circle": 3.03, "line": 3.2}.get(st["arrow_style"], 2.0) * lh
    return length + 2 * max(5 * s, gut * 0.3)


def _arrow_room(plan, secs, st, gut, s):
    """For every arrow between neighbouring sections, find the split gap it sits in and how much wider that gap
    must be. Returns ({split id: {boundary: extra mm}} for a second layout pass,
    [(box index a, box index b, horizontal, extra mm)] for gaps that are not a split boundary)."""
    need = _arrow_span(st, gut, s)
    index = {(sec.get("id") or str(i)): i for i, sec in enumerate(secs[:len(plan.boxes)])}
    boxes = {k: plan.boxes[i] for k, i in index.items()}
    eps = 0.6
    out: dict = {}
    local = []
    for a, b in st["flow_arrows"]:
        if a not in boxes or b not in boxes or not _facing(boxes[a], boxes[b], s, plan.boxes):
            continue
        (ax, ay, aw, ah), (bx, by, bw, bh) = boxes[a], boxes[b]
        horiz = min(ay + ah, by + bh) - max(ay, by) > 10 * s and (bx >= ax + aw - eps or bx + bw <= ax + eps)
        if horiz:
            lo, hi = (ax + aw, bx) if bx >= ax + aw - eps else (bx + bw, ax)
            mid = (max(ay, by) + min(ay + ah, by + bh)) / 2
        else:
            lo, hi = (ay + ah, by) if by >= ay + ah - eps else (by + bh, ay)
            mid = (max(ax, bx) + min(ax + aw, bx + bw)) / 2
        extra = need - (hi - lo)
        if extra <= 0:
            continue
        for sp in plan.splits:                       # outermost split whose boundary is exactly this gap
            if sp.dir != ("h" if horiz else "v"):
                continue
            found = False
            for i in range(len(sp.boxes) - 1):
                c1, c2 = sp.boxes[i], sp.boxes[i + 1]
                if horiz:
                    e1, e2, cross = c1[0] + c1[2], c2[0], (c1[1], c1[1] + c1[3])
                else:
                    e1, e2, cross = c1[1] + c1[3], c2[1], (c1[0], c1[0] + c1[2])
                if abs(e1 - lo) < eps and abs(e2 - hi) < eps and cross[0] - eps <= mid <= cross[1] + eps:
                    slot = out.setdefault(sp.id, {})
                    slot[i] = max(slot.get(i, 0.0), extra)
                    found = True
                    break
            if found:
                break
        else:
            local.append((index[a], index[b], horiz, extra))
    return out, local


def _facing(A, B, s, others=()):
    """True if B is directly beside or above/below A (they share an edge range) with no other section between."""
    ax, ay, aw, ah = A
    bx, by, bw, bh = B
    eps = 0.5
    if min(ay + ah, by + bh) - max(ay, by) > 10 * s and (bx >= ax + aw - eps or bx + bw <= ax + eps):
        lo, hi = (ax + aw, bx) if bx >= ax + aw - eps else (bx + bw, ax)
        corridor = (lo, max(ay, by), hi - lo, min(ay + ah, by + bh) - max(ay, by))
    elif min(ax + aw, bx + bw) - max(ax, bx) > 10 * s and (by >= ay + ah - eps or by + bh <= ay + eps):
        lo, hi = (ay + ah, by) if by >= ay + ah - eps else (by + bh, ay)
        corridor = (max(ax, bx), lo, min(ax + aw, bx + bw) - max(ax, bx), hi - lo)
    else:
        return False
    cx, cy, cw, ch = corridor
    for o in others:
        if o is A or o is B:
            continue
        if min(cx + cw, o[0] + o[2]) - max(cx, o[0]) > eps and min(cy + ch, o[1] + o[3]) - max(cy, o[1]) > eps:
            return False
    return True


def _connection(E, look, A, B, gut, idx):
    """Arrow from section box A to box B. Neighbours get an arrow in the gap between them (pointing
    right/left/down/up); sections that do not face each other get an elbow connector line."""
    style, color, halo, size, s = look
    ax, ay, aw, ah = A
    bx, by, bw, bh = B
    eps = 0.5
    ov_y = (max(ay, by), min(ay + ah, by + bh))
    ov_x = (max(ax, bx), min(ax + aw, bx + bw))
    base = max(24 * s, min(gut * 0.55, 40 * s))
    if ov_y[1] - ov_y[0] > 10 * s and (bx >= ax + aw - eps or bx + bw <= ax + eps):
        right = bx >= ax + aw - eps
        x0, x1 = (ax + aw, bx) if right else (bx + bw, ax)
        cx, cy, d, gap = (x0 + x1) / 2, (ov_y[0] + ov_y[1]) / 2, "right" if right else "left", x1 - x0
    elif ov_x[1] - ov_x[0] > 10 * s and (by >= ay + ah - eps or by + bh <= ay + eps):
        down = by >= ay + ah - eps
        y0, y1 = (ay + ah, by) if down else (by + bh, ay)
        cx, cy, d, gap = (ov_x[0] + ov_x[1]) / 2, (y0 + y1) / 2, "down" if down else "up", y1 - y0
    else:
        _elbow(E, look, A, B, idx)
        return
    if gap > base * size * 3.2 + 3 * gut:   # facing each other but far apart: a straight connector line across
        _arrow(E, "line", color, halo, size, s, cx, cy, base, d, gap=gap)
    else:   # sections made room for it; if they couldn't make enough, the arrow shrinks to fit the gap
        factor = {"chevron": 2.0, "triangle": 2.0, "block": 2.4, "circle": 3.03, "line": 3.2}.get(style, 2.0)
        fit = (gap - 2 * max(3 * s, gut * 0.15)) / (factor * base / 2)
        size = max(0.3, min(size, fit))
        _arrow(E, style, color, halo, size, s, cx, cy, base, d, gap=gap)
    r = base * size * 1.4
    E.append(dict(type="arrowhot", idx=idx, x=cx - r, y=cy - r, w=2 * r, h=2 * r))


def _elbow(E, look, A, B, idx):
    """Connector for sections that do not face each other: out of A sideways, then up/down into B."""
    style, color, halo, size, s = look
    ax, ay, aw, ah = A
    bx, by, bw, bh = B
    w = max(1.2 * s, 4 * s * size)
    acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
    sx = ax + aw if bcx > acx else ax                  # leave A on the side facing B
    down = bcy > acy
    ey = by if down else by + bh                         # enter B from above / below
    head = 14 * s * size
    E.append(polygon([(min(sx, bcx), acy - w / 2), (max(sx, bcx) + w / 2, acy - w / 2),
                      (max(sx, bcx) + w / 2, acy + w / 2), (min(sx, bcx), acy + w / 2)], color, name="Flow connector"))
    y0, y1 = sorted((acy, ey - head if down else ey + head))
    E.append(polygon([(bcx - w / 2, y0), (bcx + w / 2, y0), (bcx + w / 2, y1), (bcx - w / 2, y1)], color, name="Flow connector"))
    tip = ey
    base_y = ey - head if down else ey + head
    E.append(polygon([(bcx - head * 0.7, base_y), (bcx, tip), (bcx + head * 0.7, base_y)], color, name="Flow arrow"))
    r = head * 1.5
    E.append(dict(type="arrowhot", idx=idx, x=bcx - r, y=acy - r, w=2 * r, h=2 * r))


# ---------------------------------------------------------------- one section card
def _card(E, st, pal, surface, x, y, w, h, s, radius, name):
    card = st["card_style"]
    if card == "none":
        return
    if st["shadow"]:
        E.append(rect(x + 1.5 * s, y + 2.5 * s, w, h, "#000000", rx=radius, opacity=0.10, name=f"{name} shadow"))
    if card == "filled":
        E.append(rect(x, y, w, h, surface, rx=radius, name=f"{name} card"))
    elif card == "outlined":       # outline only: the card shows the page background
        E.append(rect(x, y, w, h, surface, rx=radius, stroke=assets.mix(pal["primary"], surface, 0.35),
                      stroke_w=1.2 * s, name=f"{name} card"))
    else:                          # filled_outlined: card colour plus a stronger primary-coloured outline
        E.append(rect(x, y, w, h, surface, rx=radius, stroke=assets.mix(pal["primary"], surface, 0.15),
                      stroke_w=1.6 * s, name=f"{name} card"))


def _section(E, st, pal, title, x, y, w, h, s, fs, radius, font, rng, fig_counter, sec, sid):
    card = st["card_style"]
    hstyle = st["header_style"]
    surface = pal["surface"] if card not in ("none", "outlined") else pal["background"]
    pad = 14 * s if card != "none" else 0
    hdr_pt = 50 * fs
    body_pt = 27 * fs
    cap_pt = 22 * fs
    lh = 1.3
    name = title
    figure = sec.get("figure", "auto")
    figs = sec.get("figs") or {}
    body = (sec.get("body") or "").strip()
    # placeholder text gets its own random stream, so typing text never changes the figure layout
    txt_rng = random.Random(rng.random())

    _card(E, st, pal, surface, x, y, w, h, s, radius, name)

    # ---- header
    hdr_mm = hdr_pt * PT
    title_w = w - 2 * max(pad, 14 * s)
    tparas = T.wrap(title, title_w, hdr_pt, font[0], True)
    while T.n_lines(tparas) > 1 and hdr_pt > 30 * fs:
        hdr_pt *= 0.92
        hdr_mm = hdr_pt * PT
        tparas = T.wrap(title, title_w, hdr_pt, font[0], True)
    tparas = [tparas[0][:2]]
    nl = len(tparas[0])
    extra = hdr_mm * 1.1 * (nl - 1)
    if hstyle == "band":
        band_h = hdr_mm * 1.9 + extra
        E.append(rect(x, y, w, band_h, pal["primary"], rx=radius, corners="top" if card != "none" else "all",
                      name=f"{name} header"))
        E.append(text(x + max(pad, 14 * s), y, title_w, band_h, tparas, hdr_pt, pal["on_primary"], font[0], bold=True,
                      valign="middle", lh=1.1, name=f"{name} title"))
        cy = y + band_h + max(pad, 12 * s)
    elif hstyle == "pill":
        widest = max(T.width_mm(l, hdr_pt, font[0], True) for l in tparas[0])
        tw = min(widest + 2 * hdr_mm, w - 2 * max(pad, 10 * s))
        ph = hdr_mm * 1.7 + extra
        px, py = x + max(pad, 10 * s), y + max(pad, 10 * s)
        E.append(rect(px, py, tw, ph, pal["primary"], rx=ph / 2 if radius > 0 else 0, name=f"{name} header"))
        E.append(text(px, py, tw, ph, tparas, hdr_pt, pal["on_primary"], font[0], bold=True, align="center",
                      valign="middle", lh=1.1, name=f"{name} title"))
        cy = py + ph + 12 * s
    else:  # underline / plain
        ty = y + max(pad, 6 * s)
        hcol = assets.readable(surface, pal["primary"], pal["secondary"], pal["text"])
        E.append(text(x + pad, ty, title_w, hdr_mm * 1.15 * nl, tparas, hdr_pt, hcol, font[0], bold=True,
                      lh=1.15, name=f"{name} title"))
        cy = ty + hdr_mm * (1.15 * nl + 0.15)
        if hstyle == "underline":
            E.append(rect(x + pad, cy + 2 * s, min(w - 2 * pad, 120 * s), 3.5 * s, pal["accent"],
                          rx=1.75 * s if radius > 0 else 0, name=f"{name} underline"))
            cy += 14 * s
        else:
            cy += 6 * s

    # ---- body
    bx, bw = x + pad, w - 2 * pad
    bottom = y + h - max(pad, 6 * s)
    bh = bottom - cy
    line_mm = body_pt * PT * lh
    E.append(target(f"s.{sid}.title", "text", x, y, w, max(cy - y, 1), f"{title} - title"))
    if bh < line_mm:
        return
    E.append(target(f"s.{sid}.body", "text", bx, cy, bw, bh, f"{title} - text"))

    has_imgs = any(f.get("img") for f in figs.values())
    roll = rng.random()
    if figure == "no":
        want_fig = False
    elif figure == "yes" or has_imgs:
        want_fig = bh > 4 * line_mm
    else:
        want_fig = st["figures"] and roll < st["figure_density"] and bh > 6 * line_mm
    regions = []
    # draw all random proportions up front, so choosing a figure position never changes anything else
    r_side, r_top, r_fig, r_two = rng.uniform(0.35, 0.45), rng.uniform(0.12, 0.35), rng.uniform(0.40, 0.62), rng.random()
    align = sec.get("fig_align") or "auto"
    placed = align != "auto"           # the user chose the position: keep exactly the figures they have
    if placed:
        v_al, h_al = align.split("-")
    else:
        v_al, h_al = "middle", ("right" if bw / bh > 1.7 else "center")
    n_figs = 2 if (figs.get("1") or {}).get("img") else (1 if (placed or has_imgs) else None)
    fig_args = (pal, surface, s, fs, cap_pt, font, r_two, fig_counter, name, radius, figs, f"s.{sid}", n_figs)
    gap = 14 * s
    cap_room = cap_pt * PT * 1.25 * 2 + 10 * s

    def natural_h(width):   # height a single figure of this width needs (picture aspect, or 4:3 for a placeholder)
        f0 = figs.get("0") or {}
        img = assets.load_image(f0["img"]) if f0.get("img") else None
        n = n_figs or 1
        fw1 = (width - 12 * s * (n - 1)) / n
        return fw1 / (img[1] if img else 4 / 3) + cap_room

    if want_fig and h_al in ("left", "right"):
        # figure beside the text; on wide boxes the text gets 35-45 %, otherwise half
        tw = bw * (r_side if bw / bh > 1.7 else 0.5)
        fw = bw - tw - gap
        fx = bx + tw + gap if h_al == "right" else bx
        fh = bh
        if placed:            # only as tall as the figure needs, at the top / middle / bottom
            # at most 70 % of the height, so top / middle / bottom stay visibly different
            fh = max(min(bh, 6 * line_mm), min(bh * 0.7, natural_h(fw)))
        fy = {"top": cy, "middle": cy + (bh - fh) / 2, "bottom": cy + bh - fh}[v_al]
        _figures(E, fx, fy, fw, fh, *fig_args)
        regions.append((bx if h_al == "right" else bx + fw + gap, cy, tw, bh))
    elif want_fig:
        fig_h = min(bh - 2 * line_mm - 10 * s, bh * r_fig)
        if placed and has_imgs:
            fig_h = min(bh - 2 * line_mm - 10 * s, max(bh * 0.3, natural_h(bw)))
        if v_al == "top":
            used = _figures(E, bx, cy, bw, fig_h, *fig_args)
            ry = cy + used + 8 * s
            regions.append((bx, ry, bw, bottom - ry))
        elif v_al == "bottom":
            used_h = fig_h
            regions.append((bx, cy, bw, bh - used_h - 8 * s))
            _figures(E, bx, bottom - used_h, bw, used_h, *fig_args)
        else:
            lines_top = max(1, int((bh * r_top) / line_mm))
            top_h = lines_top * line_mm
            fig_h = min(bh - top_h - 10 * s, fig_h)
            regions.append((bx, cy, bw, top_h))
            fy = cy + top_h + 8 * s
            used = _figures(E, bx, fy, bw, fig_h, *fig_args)
            ry = fy + used + 8 * s
            regions.append((bx, ry, bw, bottom - ry))
    else:
        regions.append((bx, cy, bw, bh))
    if body:
        if _flow_text(E, st, regions, body, body_pt, lh, pal, font, name):
            E.append(dict(type="warning", text=f"Text of “{title}” is too long for its box"))
    else:
        for r in regions:
            _text_block(E, st, txt_rng, *r, body_pt, lh, pal, font, name)


def _columns(x, y, w, h, size):
    """Very wide text areas are split into columns (~75 characters per line)."""
    max_col_w = size * PT * 0.5 * 75
    ncol = max(1, math.ceil(w / max_col_w)) if w > max_col_w * 1.25 else 1
    gap = size * PT * 1.5
    cw = (w - gap * (ncol - 1)) / ncol
    return [(x + i * (cw + gap), y, cw, h) for i in range(ncol)]


def _text_block(E, st, rng, x, y, w, h, size, lh, pal, font, name):
    """Placeholder paragraph filling the area."""
    nl = int(h / (size * PT * lh))
    cols = _columns(x, y, w, h, size)
    for i, (cx, cy, cw, _) in enumerate(cols):
        lines = T.fill_lines(rng, cw, nl, size, font[1])
        if lines:
            E.append(text(cx, cy, cw, len(lines) * size * PT * lh, [lines], size, pal["text"], font[1],
                          align=st["text_align"], lh=lh, name=f"{name} text" + (f" {i + 1}" if len(cols) > 1 else "")))


def _flow_text(E, st, regions, body, size, lh, pal, font, name):
    """The user's text, flowed through the text areas (and their columns) in reading order.
    Shrinks the type down to 75 % (still readable on a poster) until it fits; returns True if it still overflows (then it is cut with …)."""
    paras = [p.split() for p in body.split("\n")]
    base = size
    while True:
        cols = [c for r in regions for c in _columns(*r, size)]
        placed, pi, wi = [], 0, 0          # pi/wi: current paragraph / word
        for cx, cy, cw, ch in cols:
            cap = int(ch / (size * PT * lh))
            col_paras, cur_para = [], []
            while cap > 0 and pi < len(paras):
                words = paras[pi]
                line = ""
                while wi < len(words):
                    trial = f"{line} {words[wi]}" if line else words[wi]
                    if line and T.width_mm(trial, size, font[1]) > cw:
                        break
                    line = trial
                    wi += 1
                cur_para.append(line)
                cap -= 1
                if wi >= len(words):            # paragraph finished
                    col_paras.append(cur_para)
                    cur_para, pi, wi = [], pi + 1, 0
            if cur_para:
                col_paras.append(cur_para)
            placed.append((cx, cy, cw, col_paras))
        done = pi >= len(paras)
        if done or size <= base * 0.75:
            break
        size *= 0.94
    if not done:                                 # mark the cut
        for cx, cy, cw, cps in reversed(placed):
            if cps and cps[-1]:
                cps[-1][-1] = cps[-1][-1].rstrip(" .,;") + " …"
                break
    for i, (cx, cy, cw, cps) in enumerate(placed):
        n = sum(len(p) for p in cps)
        if n:
            E.append(text(cx, cy, cw, n * size * PT * lh, cps, size, pal["text"], font[1], align=st["text_align"],
                          lh=lh, name=f"{name} text" + (f" {i + 1}" if len(placed) > 1 else "")))
    return not done


def _figures(E, x, y, w, h, pal, surface, s, fs, cap_pt, font, r_two, fig_counter, name, radius, figs, key, n=None):
    """1-2 figures with captions inside (x, y, w, h): the user's pictures or placeholders. Returns used height.
    n: number of figures, or None to let a wide area show two placeholders side by side (layout mode look)."""
    if n is None:
        n = 2 if (w > 2.2 * h and r_two < 0.7) else 1
    gap = 12 * s
    fw = (w - gap * (n - 1)) / n
    # captions: up to two lines (user captions may be long), slightly smaller type if needed
    caps = []
    for i in range(n):
        f = figs.get(str(i)) or {}
        caps.append((f.get("caption") or "").strip())
    cap_lines = 1
    for c in caps:
        if c and len(T.wrap(c, fw, cap_pt, font[1])[0]) > 1:
            cap_lines = 2
    cap_h = cap_pt * PT * 1.25 * cap_lines + 6 * s
    fh = h - cap_h
    if fh < 20 * s:
        return 0
    fill = assets.mix(surface, pal["secondary"], 0.14)
    stroke = assets.mix(surface, pal["secondary"], 0.45)
    for i in range(n):
        fx = x + i * (fw + gap)
        fig_counter[0] += 1
        num = fig_counter[0]
        f = figs.get(str(i)) or {}
        img = assets.load_image(f["img"]) if f.get("img") else None
        cap_y = y + fh + 5 * s
        if img:   # picture and caption kept together, centred in the figure area
            ix, iy, iw, ih = contain(fx, y, fw, fh, img[1])
            iy = y + (fh - ih) / 2
            E.append(image(ix, iy, iw, ih, img[0], name=f"Figure {num}", ref=f["img"]))
            cap_y = iy + ih + 5 * s
        else:
            E.append(rect(fx, y, fw, fh, fill, rx=min(radius * 0.6, 6 * s), stroke=stroke, stroke_w=0.8 * s,
                          name=f"Figure {num} placeholder"))
            E.append(line(fx, y, fx + fw, y + fh, stroke, 0.6 * s, name=f"Figure {num} guide"))
            E.append(line(fx, y + fh, fx + fw, y, stroke, 0.6 * s, name=f"Figure {num} guide"))
            lbl_pt = 36 * fs
            lw = T.width_mm(f"Figure {num}", lbl_pt, font[0], True) + 16 * s
            lh_mm = lbl_pt * PT * 1.8
            E.append(rect(fx + (fw - lw) / 2, y + (fh - lh_mm) / 2, lw, lh_mm, fill, rx=min(radius * 0.6, 6 * s),
                          name=f"Figure {num} label bg"))
            E.append(text(fx, y + (fh - lh_mm) / 2, fw, lh_mm, [[f"Figure {num}"]], lbl_pt,
                          assets.mix(pal["secondary"], pal["text"], 0.35), font[0], bold=True, align="center",
                          valign="middle", name=f"Figure {num} label"))
        cap = caps[i] or "Short caption describing what the figure shows."
        lines = T.wrap(f"Figure {num}: {cap}", fw, cap_pt, font[1])[0]
        if len(lines) > cap_lines:
            lines = lines[:cap_lines]
            lines[-1] = lines[-1].rstrip(" .,;") + " …"
        E.append(text(fx, cap_y, fw, cap_pt * PT * 1.25 * len(lines), [lines], cap_pt, pal["muted"], font[1],
                      italic=True, name=f"Figure {num} caption"))
        E.append(target(f"{key}.fig.{i}", "image", fx, y, fw, h, f"Figure {num}"))
    return h
