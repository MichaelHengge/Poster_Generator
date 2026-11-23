"""Editable layout trees.

A generated layout is a nest of splits (rows / columns). As soon as the user moves a section, the layout is
"frozen" into an explicit tree that is stored in the settings and edited from then on:

    split node: {"d": "h" | "v", "w": [weights], "c": [children], "g": gap factor, "a": True (flow arrows)}
    leaf:       {"s": section id}
    root also carries "style": the layout style it came from.

Weights are sizes in mm along the split direction (only their ratios matter), so a box moved into another
split keeps its own width / height relative to its new neighbours.
"""
import copy

from .structures import Plan


def _k(b):
    return tuple(round(v, 3) for v in b)


# ---------------------------------------------------------------- generated plan -> tree
def capture(plan: Plan, secs: list, gut: float, style: str) -> dict | None:
    """Rebuild the split nest of a generated layout. Returns None for layouts that aren't a pure nest
    (e.g. 'Columns + wide section', whose wide box crosses columns)."""
    if not plan.splits:
        return None
    first = {}
    for sp in plan.splits:
        if sp.rect is not None:
            first.setdefault(_k(sp.rect), sp)
    box_sec = {}
    for i, b in enumerate(plan.boxes):
        box_sec.setdefault(_k(b), i)
    used = []

    def node(sp):
        kids = []
        for b in sp.boxes:
            k = _k(b)
            sub = first.get(k)
            if sub is not None and sub.id > sp.id:
                child = node(sub)
            elif k in box_sec:
                i = box_sec[k]
                child = {"s": secs[i].get("id") or str(i)}
                used.append(i)
            else:
                raise ValueError("not a nest")
            if child is None:
                raise ValueError("not a nest")
            kids.append(child)
        weights = [b[2] if sp.dir == "h" else b[3] for b in sp.boxes]
        if len(kids) == 1:
            return kids[0]
        n = {"d": sp.dir, "w": [round(w, 2) for w in weights], "c": kids}
        if gut > 0 and abs(sp.gap - gut) > 0.01:
            n["g"] = round(sp.gap / gut, 3)
        if plan.arrows and sp.gap > gut * 1.5 and sp.dir == "h":
            n["a"] = True
        return n

    try:
        root = node(plan.splits[0])
    except ValueError:
        return None
    if sorted(used) != list(range(len(plan.boxes))):
        return None
    if "s" in root:                       # a single section
        root = {"d": "v", "w": [1.0], "c": [root]}
    root["style"] = style
    return root


# ---------------------------------------------------------------- tree -> plan
def leaves(n) -> list[str]:
    return [n["s"]] if "s" in n else [x for c in n["c"] for x in leaves(c)]


def _normalize(n):
    """Drop empty splits and replace one-child splits by their child (in place for children)."""
    if "s" in n:
        return n
    kids, weights = [], []
    for c, w in zip(n["c"], n["w"]):
        c = _normalize(c)
        if c is not None:
            kids.append(c)
            weights.append(w)
    if not kids:
        return None
    n["c"], n["w"] = kids, weights
    return n


def _collapse(n, root=True):
    if "s" in n:
        return n
    n["c"] = [_collapse(c, False) for c in n["c"]]
    if len(n["c"]) == 1 and not root:
        return n["c"][0]
    return n


def adapt(tree: dict, ids: list[str]) -> dict:
    """Make the tree hold exactly these sections: removed sections disappear, new ones are added next to the
    last section in reading order."""
    t = copy.deepcopy(tree)
    want = set(ids)

    def prune(n):
        if "s" in n:
            return n if n["s"] in want else None
        kids, ws = [], []
        for c, w in zip(n["c"], n["w"]):
            c = prune(c)
            if c is not None:
                kids.append(c)
                ws.append(w)
        if not kids:
            return None
        n["c"], n["w"] = kids, ws
        return n

    style = t.get("style")
    t = prune(t) or {"d": "v", "w": [], "c": []}
    present = set(leaves(t)) if t["c"] else set()
    missing = [i for i in ids if i not in present]
    if missing:
        # new sections join the last ordinary row / column: the parent of the last section (in reading order)
        # that sits below the top level - so they don't become an extra full-width band
        parents = []

        def collect(n, depth):
            if "s" in n:
                return
            for c in n["c"]:
                if "s" in c:
                    parents.append((depth, n))
                else:
                    collect(c, depth + 1)
        collect(t, 0)
        deep = [n for d, n in parents if d > 0]
        target = deep[-1] if deep else (parents[-1][1] if parents else t)
        avg = sum(target["w"]) / len(target["w"]) if target["w"] else 1.0
        for i in missing:
            target["c"].append({"s": i})
            target["w"].append(avg)
    t = _collapse(t)
    t["style"] = style
    return t


def plan_from_tree(tree: dict, secs: list, area, gut: float, ctx) -> Plan:
    ids = [sec.get("id") or str(i) for i, sec in enumerate(secs)]
    t = adapt(tree, ids)
    x0, y0, x1, y1 = area
    boxes, arrows = {}, []

    def walk(n, rect):
        if "s" in n:
            boxes[n["s"]] = rect
            return
        g = gut * n.get("g", 1.0)
        outs = ctx.split(n["d"], *rect, n["w"], g)
        if n.get("a") and n["d"] == "h":
            for b1, b2 in zip(outs, outs[1:]):
                gap = b2[0] - (b1[0] + b1[2])
                arrows.append(((b1[0] + b1[2] + b2[0]) / 2, b1[1] + b1[3] / 2, gap * 0.55, min(gap * 0.9, b1[3] * 0.3)))
        for c, r in zip(n["c"], outs):
            walk(c, r)

    walk(t, (x0, y0, x1 - x0, y1 - y0))
    return Plan([boxes[i] for i in ids], arrows=arrows)


def bake(tree: dict, secs: list, area, gut: float, ctx) -> dict:
    """Copy of the (adapted) tree whose weights are the sizes currently on screen (incl. dragged sizes)."""
    ids = [sec.get("id") or str(i) for i, sec in enumerate(secs)]
    t = adapt(tree, ids)
    x0, y0, x1, y1 = area

    def walk(n, rect):
        if "s" in n:
            return
        outs = ctx.split(n["d"], *rect, n["w"], gut * n.get("g", 1.0))
        n["w"] = [round(b[2] if n["d"] == "h" else b[3], 2) for b in outs]
        for c, r in zip(n["c"], outs):
            walk(c, r)

    walk(t, (x0, y0, x1 - x0, y1 - y0))
    return t


# ---------------------------------------------------------------- moving a section
def _path(n, sid, acc=()):
    """[(node, child index), ...] from the root down to the leaf with this section id."""
    if "s" in n:
        return list(acc) if n["s"] == sid else None
    for i, c in enumerate(n["c"]):
        p = _path(c, sid, acc + ((n, i),))
        if p is not None:
            return p
    return None


def move(tree: dict, a: str, b: str, size_along) -> dict:
    """Move section a onto section b's place.
    - If a is the only section in its branch below the common parent (e.g. a full-width hero row), that whole
      branch moves within the common parent: the hero row can go to the bottom.
    - Otherwise a leaves its own row / column and is put next to b in b's row / column, keeping its size.
    size_along(section id, "h" | "v") gives a's current width / height."""
    t = copy.deepcopy(tree)
    pa, pb = _path(t, a), _path(t, b)
    if not pa or not pb or a == b:
        return t
    d = 0
    while d < min(len(pa), len(pb)) and pa[d][0] is pb[d][0] and pa[d][1] == pb[d][1]:
        d += 1
    lca, ia = pa[d]
    ib = pb[d][1]
    branch = lca["c"][ia]
    if leaves(branch) == [a]:
        c, w = lca["c"].pop(ia), lca["w"].pop(ia)
        lca["c"].insert(ib, c)
        lca["w"].insert(ib, w)
    else:
        order = leaves(t)
        after = order.index(a) < order.index(b)
        parent_b, jb = pb[-1]
        parent_a, ja = pa[-1]
        leaf = parent_a["c"][ja]
        parent_b["c"].insert(jb + (1 if after else 0), leaf)
        parent_b["w"].insert(jb + (1 if after else 0), size_along(a, parent_b["d"]))
        k = next(i for i, c in enumerate(parent_a["c"]) if c is leaf and not (parent_a is parent_b and i == jb + (1 if after else 0)))
        parent_a["c"].pop(k)
        parent_a["w"].pop(k)
    style = t.get("style")
    t = _collapse(_normalize(t))
    t["style"] = style
    return t
