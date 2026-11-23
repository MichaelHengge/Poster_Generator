"""Layout styles: each generator splits the content area into n section boxes.

Every layout is built from *splits* (a rectangle divided into side-by-side or stacked
children with weights). Each split gets a sequential id; the user can override a split's
weights by dragging the gap between two children in the preview. Overrides are looked up
by layout key + split id, so the randomness (rng calls, number of splits) must never depend
on overridden sizes - only on the base weights.

Section boxes are returned in reading order, so the i-th section of the user's list always
lands in the i-th box: swapping two sections swaps their places without changing geometry.
"""
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]  # x, y, w, h

LAYOUT_STYLES = {
    "columns": "Classic columns",
    "columns_span": "Columns + wide section",
    "hero": "Hero key figure",
    "bento": "Bento grid",
    "sidebar": "Sidebar",
    "flow": "Process flow",
    "hero_bottom": "Hero at bottom",
    "spotlight": "Centre spotlight",
    "sandwich": "Hero top & bottom",
    "features": "Two features",
    "mosaic": "Mosaic",
}


@dataclass
class Split:
    id: int
    dir: str            # "h" = side by side, "v" = stacked
    boxes: list[Box]
    gap: float
    rect: Box | None = None      # the area that was split (used to rebuild the layout as an editable tree)


@dataclass
class Plan:
    boxes: list[Box]
    arrows: list[tuple[float, float, float, float]] = field(default_factory=list)  # cx, cy, w, h
    splits: list[Split] = field(default_factory=list)


class Ctx:
    """Collects splits and applies user size overrides ({split id: [weights]})."""

    def __init__(self, overrides: dict | None, gap_extra: dict | None = None):
        self.overrides = overrides if isinstance(overrides, dict) else {}
        self.gap_extra = gap_extra or {}      # {split id: {boundary i: extra mm}} - room for flow arrows
        self.splits: list[Split] = []

    def split(self, direction, x, y, w, h, weights, gap) -> list[Box]:
        sid = len(self.splits)
        ov = self.overrides.get(str(sid))
        if (isinstance(ov, list) and len(ov) == len(weights)
                and all(isinstance(v, (int, float)) and v > 0 for v in ov)):
            weights = [float(v) for v in ov]
        tot = sum(weights)
        ex = self.gap_extra.get(sid, {})
        gaps = [gap + ex.get(i, 0.0) for i in range(len(weights) - 1)]
        size = w if direction == "h" else h
        if sum(gaps) > size * 0.4:            # never let arrow room eat the boxes
            k = (size * 0.4 - gap * len(gaps)) / max(1e-6, sum(gaps) - gap * len(gaps))
            gaps = [gap + max(0.0, g - gap) * max(0.0, k) for g in gaps]
        out = []
        if direction == "h":
            avail, cx = w - sum(gaps), x
            for i, wt in enumerate(weights):
                bw = avail * wt / tot
                out.append((cx, y, bw, h))
                cx += bw + (gaps[i] if i < len(gaps) else 0)
        else:
            avail, cy = h - sum(gaps), y
            for i, wt in enumerate(weights):
                bh = avail * wt / tot
                out.append((x, cy, w, bh))
                cy += bh + (gaps[i] if i < len(gaps) else 0)
        self.splits.append(Split(sid, direction, list(out), gap, (x, y, w, h)))   # copy: generators extend their lists
        return out


# ------------------------------------------------------------------ helpers
def allocate(n, weights):
    """Split n items into len(weights) bins (>= 1 each) proportional to weights."""
    k = len(weights)
    if k == 0:
        return []
    counts = [1] * k
    left = n - k
    tot = sum(weights) or 1
    quotas = [left * w / tot for w in weights]
    for i, q in enumerate(quotas):
        counts[i] += int(q)
    rem = n - sum(counts)
    for i in sorted(range(k), key=lambda i: quotas[i] - int(quotas[i]), reverse=True)[:rem]:
        counts[i] += 1
    return counts


def stack(ctx, box, k, gap, rng) -> list[Box]:
    return ctx.split("v", *box, [rng.uniform(0.7, 1.4) for _ in range(k)], gap)


def columns_in(ctx, box, n, ratios, gap, rng) -> list[Box]:
    """Columns with sections stacked, column-major reading order."""
    ratios = ratios[:max(1, n)]
    counts = allocate(n, ratios)                 # from base ratios, never from overridden widths
    out = []
    for col, k in zip(ctx.split("h", *box, ratios, gap), counts):
        out += stack(ctx, col, k, gap, rng)
    return out


def row_or_columns(ctx, box, n, ratios, gap, rng) -> list[Box]:
    """Up to 3 sections side by side, more become columns."""
    if n <= 3:
        return ctx.split("h", *box, [rng.uniform(0.8, 1.3) for _ in range(n)], gap)
    return columns_in(ctx, box, n, ratios, gap, rng)


# ------------------------------------------------------------------ generators
def g_columns(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    return Plan(columns_in(ctx, (x0, y0, x1 - x0, y1 - y0), n, ratios, gap, rng))


def g_columns_span(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    nc = len(ratios)
    if nc < 2 or n < nc + 1:
        return None
    full_h = y1 - y0
    width = rng.randint(2, nc)
    a = rng.randint(0, nc - width)
    b = a + width - 1
    sh = full_h * rng.uniform(0.24, 0.36)
    pos = rng.choice(["top", "middle", "middle", "bottom"])
    sy = {"top": y0, "bottom": y1 - sh, "middle": y0 + (full_h - sh) * rng.uniform(0.35, 0.65)}[pos]

    # vertical segments (computed from base geometry so allocation never depends on overrides)
    segs = []   # (col index, y, h)
    for ci in range(nc):
        if a <= ci <= b:
            if sy - y0 - gap > gap:
                segs.append((ci, y0, sy - y0 - gap))
            by = sy + sh + gap
            if y1 - by > gap:
                segs.append((ci, by, y1 - by))
        else:
            segs.append((ci, y0, full_h))
    if n - 1 < len(segs):
        return None
    counts = allocate(n - 1, [ratios[ci] * h for ci, _, h in segs])

    cols = ctx.split("h", x0, y0, x1 - x0, full_h, ratios, gap)
    span_box = (cols[a][0], sy, cols[b][0] + cols[b][2] - cols[a][0], sh)
    keyed = [((a, sy + 0.1), span_box)]
    for (ci, sy2, sh2), k in zip(segs, counts):
        for bx in stack(ctx, (cols[ci][0], sy2, cols[ci][2], sh2), k, gap, rng):
            keyed.append(((ci, bx[1]), bx))
    return Plan([bx for _, bx in sorted(keyed, key=lambda t: t[0])])


def g_hero(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    W, H = x1 - x0, y1 - y0
    if n < 2:
        return None
    intro = 2 if n >= 5 else 1
    has_intro = n >= 4 and rng.random() < 0.5
    ih = H * rng.uniform(0.14, 0.19)
    hh = H * rng.uniform(0.28, 0.36)
    weights = [ih, hh, H - ih - hh] if has_intro else [hh, H - hh]
    rows = ctx.split("v", x0, y0, W, H, weights, gap)
    boxes = []
    if has_intro:
        boxes += ctx.split("h", *rows[0], [rng.uniform(0.8, 1.3) for _ in range(intro)], gap)
    boxes.append(rows[-2])
    boxes += columns_in(ctx, rows[-1], n - len(boxes), ratios, gap, rng)
    return Plan(boxes)


def g_bento(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    maxc = 4 if landscape else 3
    rows, rem, prev = [], n, 0
    while rem > 0:
        opts = [c for c in range(1, maxc + 1) if c <= rem and not (c == 1 and prev == 1)] or [rem]
        k = rng.choices(opts, weights=[{1: 1, 2: 3, 3: 3, 4: 2}[c] for c in opts])[0]
        rows.append(k)
        rem -= k
        prev = k
    heights = [rng.uniform(0.7, 1.0) if k == 1 else rng.uniform(0.9, 1.5) for k in rows]
    boxes = []
    for row, k in zip(ctx.split("v", x0, y0, x1 - x0, y1 - y0, heights, gap), rows):
        boxes += ctx.split("h", *row, [rng.choice([0.7, 1, 1, 1.4, 1.8]) for _ in range(k)], gap)
    return Plan(boxes)


def g_sidebar(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    if n < 3:
        return None
    W, H = x1 - x0, y1 - y0
    sw = W * rng.uniform(0.26, 0.33)
    left = rng.random() < 0.6
    kl = max(1, min(n - 2, round(n * 0.4)))
    hh = H * rng.uniform(0.4, 0.55)
    outer = ctx.split("h", x0, y0, W, H, [sw, W - sw] if left else [W - sw, sw], gap)
    side_box, main_box = (outer[0], outer[1]) if left else (outer[1], outer[0])
    side = stack(ctx, side_box, kl, gap, rng)
    top, rest = ctx.split("v", *main_box, [hh, H - hh], gap)
    main = [top] + row_or_columns(ctx, rest, n - kl - 1, [1, 1], gap, rng)
    return Plan(side + main if left else main + side)


def g_flow(ctx, area, n, ratios, gap, rng, landscape):
    x0, y0, x1, y1 = area
    if n < 4:
        return None
    W, H = x1 - x0, y1 - y0
    a = 1 if n < 6 else 2
    k = min(4 if landscape else 3, n - a - 1)
    if k < 2:
        return None
    r = n - a - k
    ih = H * rng.uniform(0.15, 0.2)
    ph = H * rng.uniform(0.22, 0.3)
    rows = ctx.split("v", x0, y0, W, H, [ih, ph, H - ih - ph], gap)
    boxes = ctx.split("h", *rows[0], [rng.uniform(0.8, 1.3) for _ in range(a)], gap)
    agap = gap * 3.2
    proc = ctx.split("h", *rows[1], [1] * k, agap)
    arrows = []
    for b1, b2 in zip(proc, proc[1:]):
        cx = (b1[0] + b1[2] + b2[0]) / 2
        arrows.append((cx, rows[1][1] + rows[1][3] / 2, agap * 0.55, min(agap * 0.9, rows[1][3] * 0.3)))
    boxes += proc
    boxes += row_or_columns(ctx, rows[2], r, ratios, gap, rng)
    return Plan(boxes, arrows=arrows)




def g_hero_bottom(ctx, area, n, ratios, gap, rng, landscape):
    """Columns on top, one big key-figure section across the bottom."""
    x0, y0, x1, y1 = area
    W, H = x1 - x0, y1 - y0
    if n < 2:
        return None
    hh = H * rng.uniform(0.36, 0.46)
    top, hero = ctx.split("v", x0, y0, W, H, [H - hh, hh], gap)
    return Plan(columns_in(ctx, top, n - 1, ratios, gap, rng) + [hero])


def g_spotlight(ctx, area, n, ratios, gap, rng, landscape):
    """One big central section with smaller ones all around it."""
    x0, y0, x1, y1 = area
    W, H = x1 - x0, y1 - y0
    rest = n - 1
    if rest < 2:
        return None
    if rest == 2:
        t, l, r, b = 0, 1, 1, 0
    elif rest == 3:
        t, l, r, b = 1, 1, 1, 0
    else:
        cap = 4 if landscape else 3
        t, l, r, b = allocate(rest, [1.1, 1, 1, 1.1])
        t, b = min(t, cap), min(b, cap)
        extra = rest - (t + l + r + b)            # overflow from capped rows goes to the sides
        l += (extra + 1) // 2
        r += extra // 2
    band = H * rng.uniform(0.15, 0.2)
    weights = ([band] if t else []) + [H - band * ((t > 0) + (b > 0))] + ([band] if b else [])
    rows = ctx.split("v", x0, y0, W, H, weights, gap)
    mid = rows[1] if t else rows[0]
    sw = rng.uniform(0.22, 0.27) if landscape else rng.uniform(0.24, 0.3)
    left, centre, right = ctx.split("h", *mid, [sw, 1 - 2 * sw, sw], gap)
    boxes = []
    if t:
        boxes += ctx.split("h", *rows[0], [rng.uniform(0.8, 1.3) for _ in range(t)], gap)
    boxes += stack(ctx, left, l, gap, rng)
    boxes.append(centre)
    boxes += stack(ctx, right, r, gap, rng)
    if b:
        boxes += ctx.split("h", *rows[-1], [rng.uniform(0.8, 1.3) for _ in range(b)], gap)
    return Plan(boxes)


def g_sandwich(ctx, area, n, ratios, gap, rng, landscape):
    """A wide key section at the top and one at the bottom, smaller sections in between."""
    x0, y0, x1, y1 = area
    W, H = x1 - x0, y1 - y0
    if n < 3:
        return None
    th = H * rng.uniform(0.2, 0.26)
    bh = H * rng.uniform(0.2, 0.26)
    top, mid, bottom = ctx.split("v", x0, y0, W, H, [th, H - th - bh, bh], gap)
    return Plan([top] + row_or_columns(ctx, mid, n - 2, ratios, gap, rng) + [bottom])


def g_features(ctx, area, n, ratios, gap, rng, landscape):
    """Two big feature sections placed diagonally, each paired with a stack of smaller ones."""
    x0, y0, x1, y1 = area
    W, H = x1 - x0, y1 - y0
    if n < 4:
        return None
    k1 = (n - 2 + 1) // 2
    k2 = n - 2 - k1
    fw = rng.uniform(0.6, 0.68)
    flip = rng.random() < 0.5
    r1, r2 = ctx.split("v", x0, y0, W, H, [rng.uniform(0.9, 1.1), 1], gap)
    a1 = ctx.split("h", *r1, [1 - fw, fw] if flip else [fw, 1 - fw], gap)
    a2 = ctx.split("h", *r2, [fw, 1 - fw] if flip else [1 - fw, fw], gap)
    big1, side1 = (a1[1], a1[0]) if flip else (a1[0], a1[1])
    big2, side2 = (a2[0], a2[1]) if flip else (a2[1], a2[0])
    s1 = stack(ctx, side1, k1, gap, rng)
    s2 = stack(ctx, side2, k2, gap, rng)
    row1 = s1 + [big1] if flip else [big1] + s1
    row2 = [big2] + s2 if flip else s2 + [big2]
    return Plan(row1 + row2)


def g_mosaic(ctx, area, n, ratios, gap, rng, landscape):
    """Recursive guillotine cuts of varied proportions (Mondrian-like)."""
    x0, y0, x1, y1 = area
    if n < 2:
        return None

    def cut(box, k):
        if k == 1:
            return [box]
        x, y, w, h = box
        d = "h" if w * rng.uniform(0.8, 1.25) > h else "v"
        ka = max(1, min(k - 1, round(k * rng.uniform(0.3, 0.6))))
        wa = min(0.8, max(0.2, ka / k * rng.uniform(0.85, 1.2)))
        a, b = ctx.split(d, x, y, w, h, [wa, 1 - wa], gap)
        return cut(a, ka) + cut(b, k - ka)

    return Plan(cut((x0, y0, x1 - x0, y1 - y0), n))


GENERATORS = {
    "columns": g_columns,
    "columns_span": g_columns_span,
    "hero": g_hero,
    "bento": g_bento,
    "sidebar": g_sidebar,
    "flow": g_flow,
    "hero_bottom": g_hero_bottom,
    "spotlight": g_spotlight,
    "sandwich": g_sandwich,
    "features": g_features,
    "mosaic": g_mosaic,
}


def make_plan(style, area, n, ratios, gap, rng, landscape, sizes: dict | None, key_suffix: str, gap_extra=None):
    """Returns (style used, Plan, layout key). `sizes` maps layout key -> {split id: weights};
    `gap_extra` widens single gaps ({split id: {boundary: mm}}) to make room for flow arrows."""
    sizes = sizes if isinstance(sizes, dict) else {}
    if style not in GENERATORS:
        style = rng.choice(list(GENERATORS))
    key = f"{style}|{key_suffix}"
    ctx = Ctx(sizes.get(key), gap_extra)
    plan = GENERATORS[style](ctx, area, n, ratios, gap, rng, landscape)
    if plan is None:
        style, key = "columns", f"columns|{key_suffix}"
        ctx = Ctx(sizes.get(key), gap_extra)
        plan = g_columns(ctx, area, n, ratios, gap, rng, landscape)
    plan.splits = ctx.splits
    return style, plan, key
