"""Static configuration: page sizes, palette presets and default settings."""
import re


# Portrait dimensions in millimetres (width, height)
PAGE_SIZES = {
    "A0": (841, 1189),
    "A1": (594, 841),
    "A2": (420, 594),
    "A3": (297, 420),
    "A4": (210, 297),
    "36x48 in": (914, 1219),
    "24x36 in": (610, 914),
}

PALETTE_KEYS = ["primary", "secondary", "accent", "background", "surface", "text", "on_primary", "muted"]

PALETTE_LABELS = {
    "primary": "Primary",
    "secondary": "Secondary",
    "accent": "Accent",
    "background": "Background",
    "surface": "Cards",
    "text": "Text",
    "on_primary": "Text on primary",
    "muted": "Muted / captions",
}

PRESET_PALETTES = {
    "Ocean": ["#0B4F6C", "#1C9CD8", "#F4A259", "#F2F6F9", "#FFFFFF", "#1E2A32", "#FFFFFF", "#6B7C87"],
    "Forest": ["#2D6A4F", "#52B788", "#F2C14E", "#F3F6F2", "#FFFFFF", "#1B2A22", "#FFFFFF", "#6A7B70"],
    "Sunset": ["#7B2D43", "#E07A5F", "#F2CC8F", "#FBF6F1", "#FFFFFF", "#2B1F22", "#FFFFFF", "#8A7470"],
    "Teal & Coral": ["#006D77", "#83C5BE", "#E29578", "#EDF6F9", "#FFFFFF", "#10292B", "#FFFFFF", "#5E7A7D"],
    "University Blue": ["#003366", "#4A90C2", "#E87722", "#FFFFFF", "#F2F5F9", "#1A1A1A", "#FFFFFF", "#5F6B7A"],
    "Lavender": ["#4B3F72", "#8E7DBE", "#F4B860", "#F7F5FB", "#FFFFFF", "#241E33", "#FFFFFF", "#77708A"],
    "Okabe-Ito (colour-blind safe)": ["#0072B2", "#009E73", "#E69F00", "#FFFFFF", "#F4F7FA", "#1D1D1D", "#FFFFFF", "#666666"],
    "Slate": ["#2F3E46", "#84A98C", "#CAD2C5", "#FFFFFF", "#F4F6F5", "#222222", "#FFFFFF", "#6C757D"],
    "Monochrome": ["#212529", "#495057", "#ADB5BD", "#FFFFFF", "#F8F9FA", "#212529", "#FFFFFF", "#6C757D"],
    "Midnight (dark)": ["#1F2A44", "#3E92CC", "#F7B32B", "#0F1626", "#1B2438", "#E8ECF3", "#FFFFFF", "#9AA6BD"],
}


def preset_dicts():
    return {name: dict(zip(PALETTE_KEYS, cols)) for name, cols in PRESET_PALETTES.items()}


DEFAULT_SECTIONS = [
    {"title": t, "figure": "auto"}
    for t in ["Introduction", "Objectives", "Methods", "Results", "Discussion", "Conclusion", "References", "Acknowledgements"]
]
FIGURE_MODES = ("auto", "yes", "no")
# where a section's figure sits (edit mode): "auto" or "<top|middle|bottom>-<left|center|right>"
FIG_ALIGNS = ("auto",) + tuple(f"{v}-{h}" for v in ("top", "middle", "bottom") for h in ("left", "center", "right"))


def fig_align(v) -> str:
    v = str(v or "auto")
    if v in ("left", "center", "right"):          # older settings: horizontal only
        v = "middle-" + v
    return v if v in FIG_ALIGNS else "auto"

DEFAULTS = {
    # format
    "size": "A0",
    "orientation": "portrait",
    "custom_w": 841,
    "custom_h": 1189,
    # palette
    "palette_name": "Ocean",
    **{f"c_{k}": v for k, v in zip(PALETTE_KEYS, PRESET_PALETTES["Ocean"])},
    # style
    "font_heading": "Arial",
    "font_body": "Arial",
    "text_align": "left",
    "font_scale": 1.0,
    "corner_radius": 6,
    "card_style": "filled",
    "header_style": "band",
    "shadow": True,
    "number_sections": False,
    "margin": 25,
    "gutter": 18,
    "background": "solid",
    # top bar
    "top_enabled": True,
    "top_style": "solid",
    "top_align": "left",
    "top_accent_line": True,
    "show_title": True,
    "show_authors": True,
    "show_affiliations": True,
    "logo_size": 90,
    "logo_backing": True,
    "logo_left": True,          # placeholder logo top-left on/off
    "logos_right": 1,           # number of placeholder logos top-right
    # bottom bar
    "bottom_enabled": True,
    "bottom_style": "solid",
    "show_footer_left": True,
    "show_footer_center": True,
    "qr_enabled": True,
    "qr_url": "https://example.org",
    "show_qr_label": True,
    "qr_size": 70,
    # layout
    "layout_style": "auto",
    "split_sizes": {},
    "layout_trees": {},          # rearranged layouts (see poster/tree.py), by tree key
    "columns": "1:1:1",
    "sections": DEFAULT_SECTIONS,
    "figures": True,
    "figure_density": 0.6,
    "seed": 1,
    # process-flow arrows between sections: [[from section id, to section id], ...]
    "flow_arrows": [],
    "arrow_style": "chevron",
    "arrow_color": "accent",
    "arrow_size": 1.0,
    # poster content (edit mode); empty text = sample text, images are ids from the image store
    "content": {},
}

ARROW_STYLES = ("chevron", "triangle", "block", "circle", "line")
CONTENT_TEXT_KEYS = ("title", "authors", "affiliations", "footer_left", "footer_center", "qr_label")

NUMERIC_KEYS = {k for k, v in DEFAULTS.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
BOOL_KEYS = {k for k, v in DEFAULTS.items() if isinstance(v, bool)}


def merge_settings(user: dict | None) -> dict:
    """Merge user supplied settings onto defaults, coercing types."""
    st = dict(DEFAULTS)
    for k, v in (user or {}).items():
        if k not in DEFAULTS:
            continue
        try:
            if k in BOOL_KEYS:
                v = bool(v)
            elif k in NUMERIC_KEYS:
                v = float(v)
        except (TypeError, ValueError):
            continue
        st[k] = v
    st["logos_right"] = int(max(0, min(4, st["logos_right"])))
    st["sections"] = normalize_sections(st["sections"])
    st["content"] = normalize_content(st["content"])
    fa = st["flow_arrows"] if isinstance(st["flow_arrows"], list) else []
    st["flow_arrows"] = [[str(p[0]), str(p[1])] for p in fa if isinstance(p, list) and len(p) == 2][:80]
    if st["arrow_style"] not in ARROW_STYLES:
        st["arrow_style"] = "chevron"
    if st["arrow_color"] not in ("accent", "primary", "secondary"):
        st["arrow_color"] = "accent"
    st["arrow_size"] = max(0.5, min(2.5, st["arrow_size"]))
    if not isinstance(st["layout_trees"], dict):
        st["layout_trees"] = {}
    if not isinstance(st["split_sizes"], dict):
        st["split_sizes"] = {}
    st["seed"] = int(st["seed"])
    from .fonts import resolve
    st["font_heading"] = resolve(str(st["font_heading"]))
    st["font_body"] = resolve(str(st["font_body"]))
    if st["text_align"] not in ("left", "justify", "center", "right"):
        st["text_align"] = "left"
    if st["card_style"] not in ("filled", "outlined", "filled_outlined", "none"):
        st["card_style"] = "filled"
    return st


def normalize_sections(raw) -> list[dict]:
    """Accepts the old newline-separated string or a list of {title, figure} dicts."""
    if isinstance(raw, str):
        raw = [{"title": t} for t in raw.split(chr(10))]
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        fig = item.get("figure", "auto")
        figs = item.get("figs") if isinstance(item.get("figs"), dict) else {}
        out.append({"id": str(item.get("id") or "")[:40], "title": title[:200],
                    "figure": fig if fig in FIGURE_MODES else "auto",
                    "body": str(item.get("body") or "")[:20000],
                    "fig_align": fig_align(item.get("fig_align")),
                    "figs": {str(k): {"img": image_id(v.get("img")), "caption": str(v.get("caption") or "")[:600]}
                             for k, v in figs.items() if str(k) in ("0", "1") and isinstance(v, dict)}})
    return out[:40]


def image_id(v) -> str:
    """Ids of the image store are 16 hex characters; anything else means 'no image'."""
    v = str(v or "")
    return v if re.fullmatch(r"[0-9a-f]{16}", v) else ""


def normalize_content(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {k: str(raw.get(k) or "")[:4000] for k in CONTENT_TEXT_KEYS}
    out["logo_left"] = image_id(raw.get("logo_left"))
    lr = raw.get("logos_right")
    out["logos_right"] = [image_id(v) for v in (lr if isinstance(lr, list) else [])][:4]
    return out


def page_size_mm(st: dict) -> tuple[float, float]:
    if st["size"] == "Custom":
        w, h = max(100.0, st["custom_w"]), max(100.0, st["custom_h"])
        w, h = sorted((w, h))
    else:
        w, h = PAGE_SIZES.get(st["size"], PAGE_SIZES["A0"])
    if st["orientation"] == "landscape":
        w, h = h, w
    return float(w), float(h)
