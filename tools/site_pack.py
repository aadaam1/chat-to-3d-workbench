#!/usr/bin/env python3
"""A printable site pack for a timber structure: the shopping list and each side drawn on its own page.

    site_pack.py <project out dir> [--out <pdf>] [--html-only]

Reads <out>/frame.json, checks.json and bom.json (and the newest version in <out>/versions/), writes
<out>/site-pack.html (one self-contained file: inline SVG and CSS) and prints it to
<out>/<project>-site-pack-v<N>.pdf with headless Chrome (CHROME=/path/to/chrome if it is not found).
Without Chrome the HTML is still written, and the command stops with a plain message (exit 1);
with --html-only it exits 0.

The pages: a cover (size, verdict, the disclaimer, how it was planned), the shopping list, then
one page per part in site order (foundations, floor or deck, posts and beams, the four walls, the
roof) with a drawing and a table of its pieces, and a cut list. It is not an assembly guide.

The drawings are plain orthographic projections of the members in frame.json, painted far to near:
walls as seen from outside, floors and roofs from above, foundations from above with every footing
dimensioned from one corner. Each distinct piece (kind, section, length, cut angles) gets a letter
per part; the table says what each letter is and how many there are. Sheathing, cladding and deck
boards are not drawn (they would cover the frame) but are in the table. Same input, same files.
"""
import argparse, base64, html, io, json, math, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:                                         # the 3D views are rasterised with a z-buffer when these are there
    import numpy as np
    from PIL import Image
    HAVE_RASTER = True
except ImportError:                          # else they are drawn as sorted SVG polygons
    HAVE_RASTER = False
import bom as bomlib
import timberlib as tl
import versions as vers

# --------------------------------------------------------------------------- what to draw, as data
# A part of the structure is found by its assembly type, its group name or a prefix of it, the first
# rule that matches wins. A part nothing matches gets FALLBACK. "view" is the projection (plan = from
# above; front/back/left/right = looking at that side from outside; "outside" = the wall's own side).
# "auto" puts the spacing chain along the direction the joists or rafters are spread in;
# "hide" are the kinds left out of the drawing (they stay in the table).

HIDE = ["sheet", "board", "deckboard"]
PLAN_FLOOR = {"view": "plan", "title": "Plan, seen from above (front at the bottom)", "hide": HIDE,
              "auto": {"kinds": ["joist"], "mode": "gap"}, "overall": "wh"}
PLAN_POSTS = {"view": "plan", "title": "Plan, seen from above (front at the bottom)", "hide": HIDE,
              "hmarks": {"kinds": ["post"], "mode": "gap"}, "vmarks": {"kinds": ["post"], "mode": "gap"}, "overall": "wh"}
RULES = [
    {"types": ["foundations"], "groups": ["foundations"], "role": "foundations", "title": "Foundations", "order": 0,
     "views": [{"view": "plan", "title": "Footing centres, seen from above (front at the bottom)", "footings": True}]},
    {"types": ["platform"], "groups": ["floor", "deck"], "role": "floor", "order": 1, "title": "{G} frame", "views": [PLAN_FLOOR]},
    {"groups": ["frame"], "role": "posts", "order": 2, "title": "Posts and beams", "views": [
        PLAN_POSTS,
        {"view": "front", "title": "Front, seen from the front", "hide": HIDE, "hmarks": {"kinds": ["post"], "mode": "gap"},
         "overall": "wh", "ground": True, "ghost": ["deck", "floor"]},
        {"view": "left", "title": "Left side, seen from the left", "hide": HIDE, "hmarks": {"kinds": ["post"], "mode": "gap"},
         "overall": "wh", "ground": True, "ghost": ["deck", "floor"]}]},
    {"types": ["wall"], "prefixes": ["wall-"], "role": "wall", "order": 3, "title": "{G}", "views": [
        {"view": "outside", "title": "Seen from outside", "hide": HIDE, "hmarks": {"kinds": ["stud", "king", "jack"],
         "mode": "cum", "tall": 0.4}, "overall": "w", "heights": "ends", "openings": True}]},
    {"types": ["gable-roof", "mono-roof", "pergola-rafters", "slats"], "groups": ["roof"], "role": "roof", "order": 4,
     "title": "Roof", "views": [
        {"view": "plan", "title": "Plan, seen from above (front at the bottom)", "hide": HIDE + ["slat"],
         "auto": {"kinds": ["rafter"], "mode": "gap", "not_id": "flying"}, "overall": "wh"},
        {"view": "plan", "title": "Slats, seen from above", "only": ["slat"], "ghost_kinds": ["rafter"], "when": "slat",
         "auto": {"kinds": ["slat"], "mode": "gap"}, "overall": "wh"},
        {"view": "left", "title": "End, seen from the left", "hide": HIDE, "overall": "wh", "ghost": ["wall-", "floor"],
         "pitch": True}]},
]
FALLBACK = {"role": "other", "order": 5, "title": "{G}", "views": [
    {"view": "plan", "title": "Plan, seen from above (front at the bottom)", "hide": HIDE, "overall": "wh"},
    {"view": "front", "title": "Front, seen from the front", "hide": HIDE, "overall": "wh"}]}
WALL_ORDER = ["wall-front", "wall-back", "wall-left", "wall-right"]
WALL_VIEW = {"wall-front": "front", "wall-back": "back", "wall-left": "left", "wall-right": "right"}
# what lies at the left and right edge of each wall drawing, for the note under the title
WALL_SIDES = {"front": ("left wall", "right wall"), "back": ("right wall", "left wall"),
              "left": ("back wall", "front wall"), "right": ("front wall", "back wall")}

# projections: (looking direction, up). Screen right = direction x up. Farther = larger dot with direction.
VIEWS = {"plan": ((0, 0, -1), (0, 1, 0)), "front": ((0, 1, 0), (0, 0, 1)), "back": ((0, -1, 0), (0, 0, 1)),
         "left": ((1, 0, 0), (0, 0, 1)), "right": ((-1, 0, 0), (0, 0, 1))}

EXTRA_NAMES = {"ground-screw": "Ground screw", "pier": "Pier block", "footing": "Concrete footing", "post-base": "Post base",
               "deckboard": "Deck board", "board": "Cladding board"}
SHEET_NAMES = {"roof": "Roof sheet", "sheathing": "Wall sheathing", "floor": "Floor sheet", "walls": "Wall sheathing"}
TYPE_NAMES = {"pent-shed": "Pent shed (mono-pitch roof)", "gable-shed": "Gable shed", "terrace": "Terrace (raised deck)",
              "pergola": "Pergola", "summer-kitchen": "Summer kitchen"}
SIDE_WORDS = {"wall-front": "Front wall", "wall-back": "Back wall", "wall-left": "Left wall", "wall-right": "Right wall"}
PAGE_MM = {"eu": ("A4", 297.0, 210.0), "us": ("letter", 279.4, 215.9)}
SCALES = [1, 2, 2.5, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500]
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"           # no I or O: they look like 1 and 0
FONT = 2.8                                      # mm on paper, never smaller than 2.5
ACCENT = "#b45309"
SHORT_WARNING = "Guidance, not structural engineering. Check before you build."


# ------------------------------------------------------------------------------------------ geometry

def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def local_points(m):
    """The member's prism, as (outline polygon, thickness): box from the origin, L along x, W along y,
    T along z = x cross y (as memberGeom() in tools/viewer/viewer.html); an outline replaces the box
    end polygon, extruded T along z."""
    L, W, T = m["size"]
    poly = [tuple(p) for p in m["outline"]] if m.get("outline") else [(0, 0), (L, 0), (L, W), (0, W)]
    return poly, T


def world(m, u, v, t):
    x, y = m["x"], m["y"]
    z = cross(x, y)
    o = m["origin"]
    return tuple(o[i] + u * x[i] + v * y[i] + t * z[i] for i in range(3))


def prism(m):
    poly, T = local_points(m)
    return [world(m, u, v, t) for (u, v) in poly for t in (0, T)]


def is_convex(poly):
    sign = set()
    n = len(poly)
    for i in range(n):
        a, b, c = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cr) > 1e-6:
            sign.add(cr > 0)
    return len(sign) <= 1


def hull(pts):
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(pts), half(reversed(pts))
    return lo[:-1] + up[:-1]


class Proj:
    """One projection: forward direction f, up u, right = f x u."""

    def __init__(self, name):
        self.name = name
        self.f, self.u = VIEWS[name]
        self.r = cross(self.f, self.u)

    def pt(self, p):
        return (dot(p, self.r), dot(p, self.u), dot(p, self.f))

    def shapes(self, m):
        """The member's silhouette as a list of 2D polygons (model mm, screen right/up), and its depth."""
        poly, T = local_points(m)
        pts = [self.pt(p) for p in prism(m)]
        depth = sum(p[2] for p in pts) / len(pts)
        if not m.get("outline") or is_convex(poly):
            return [hull([(p[0], p[1]) for p in pts])], depth
        out = []                                              # a hollowed outline: each face on its own
        for t in (0, T):
            out.append([(q[0], q[1]) for q in (self.pt(world(m, u, v, t)) for (u, v) in poly)])
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            out.append([(q[0], q[1]) for q in (self.pt(world(m, u, v, t)) for (u, v, t) in
                                               ((a[0], a[1], 0), (b[0], b[1], 0), (b[0], b[1], T), (a[0], a[1], T)))])
        return out, depth


def bbox2(shapes):
    xs = [p[0] for s in shapes for p in s]
    ys = [p[1] for s in shapes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def aabb(m):
    pts = prism(m)
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


# --------------------------------------------------------------------------------------------- naming

def piece_name(m):
    k = m["kind"]
    if k == "sheet":
        return SHEET_NAMES.get(m.get("layer"), "Sheet")
    if k in EXTRA_NAMES:
        return EXTRA_NAMES[k]
    return bomlib.what_is(k, m["id"])


def fmt(mm, units, unit=False):
    """A length in the frame's units: whole millimetres, or feet-inches-sixteenths."""
    if units == "imperial":
        return tl.fmt_length(mm, "imperial")
    return f"{round(mm)}" + (" mm" if unit else "")


def item_name(lib, key):
    try:
        return tl.item(lib, key)["name"]
    except KeyError:
        return key


def cut_text(m):
    a, b = m.get("cut_deg") or [0, 0]
    if not a and not b:
        return ""
    f = lambda d: f"{d:g}°"
    return f"{f(a)} / {f(b)}"


def letter(i):
    n, s = len(LETTERS), ""
    i += 1
    while i:
        i, r = divmod(i - 1, n)
        s = LETTERS[r] + s
    return s


def piece_key(m):
    a, b = m.get("cut_deg") or [0, 0]
    return (piece_name(m), m["item"], round(m["size"][0]), round(a, 1), round(b, 1))


# ------------------------------------------------------------------------------------------- sections

def assembly_type(frame, group):
    for a in frame.get("assemblies", []):
        if a["id"] == group or a["id"].startswith(group + "/"):
            return a["type"]
    return None


def pick_rule(frame, group):
    t = assembly_type(frame, group)
    for r in RULES:
        if (t and t in r.get("types", [])) or group in r.get("groups", []) or any(group.startswith(p) for p in r.get("prefixes", [])):
            return r
    return FALLBACK


def group_sort(group, rule):
    wall = WALL_ORDER.index(group) if group in WALL_ORDER else len(WALL_ORDER)
    return (rule["order"], wall, group)


def make_sections(frame):
    groups = []
    for m in frame["members"]:
        if m["group"] not in groups:
            groups.append(m["group"])
    secs = []
    for g in groups:
        rule = pick_rule(frame, g)
        mem = [m for m in frame["members"] if m["group"] == g]
        title = rule["title"].format(G=SIDE_WORDS.get(g, g.replace("-", " ").capitalize()))
        if rule["role"] == "wall" and g not in WALL_VIEW:
            title = g.replace("-", " ").capitalize()
        views = []
        for v in rule["views"]:
            v = dict(v)
            if v.get("when") and not any(m["kind"] == v["when"] for m in mem):
                continue
            if v["view"] == "outside":
                v["view"] = WALL_VIEW.get(g, "front")
            views.append(v)
        secs.append({"group": g, "rule": rule, "role": rule["role"], "title": title, "members": mem, "views": views,
                     "sort": group_sort(g, rule)})
    secs.sort(key=lambda s: s["sort"])
    return secs


def structure_box(frame):
    """Corner of the structure: the box of everything above ground except the roof."""
    mem = [m for m in frame["members"] if m.get("layer") != "foundations" and m["group"] != "roof"] or frame["members"]
    boxes = [aabb(m) for m in mem]
    lo = [min(b[0][i] for b in boxes) for i in range(3)]
    hi = [max(b[1][i] for b in boxes) for i in range(3)]
    return lo, hi


# -------------------------------------------------------------------------------------------- drawing

def num(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def esc(s):
    return html.escape(str(s), quote=True)


def text_w(s, size=FONT, bold=False):
    return len(s) * size * (0.6 if bold else 0.56)


class Svg:
    """An SVG in paper millimetres. Everything drawn grows the bounding box, so the margins fit the dimensions."""

    def __init__(self):
        self.parts, self.bb = [], [1e9, 1e9, -1e9, -1e9]

    def ext(self, x0, y0, x1, y1):
        b = self.bb
        b[0], b[1], b[2], b[3] = min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)

    def poly(self, pts, cls):
        self.parts.append(f'<polygon class="{cls}" points="' + " ".join(f"{num(x)},{num(y)}" for x, y in pts) + '"/>')
        self.ext(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))

    def line(self, x0, y0, x1, y1, cls="dl"):
        self.parts.append(f'<line class="{cls}" x1="{num(x0)}" y1="{num(y0)}" x2="{num(x1)}" y2="{num(y1)}"/>')
        self.ext(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def text(self, x, y, s, anchor="middle", cls="dt", size=FONT, rot=0):
        w = text_w(s, size, "b" in cls.split())
        x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
        if rot:
            self.parts.append(f'<text class="{cls}" font-size="{num(size)}" text-anchor="{anchor}" '
                              f'transform="translate({num(x)},{num(y)}) rotate({rot})">{esc(s)}</text>')
            self.ext(x - size, y - w / 2, x + 0.3 * size, y + w / 2)
        else:
            self.parts.append(f'<text class="{cls}" font-size="{num(size)}" text-anchor="{anchor}" x="{num(x)}" y="{num(y)}">{esc(s)}</text>')
            self.ext(x0, y - size * 0.8, x0 + w, y + size * 0.25)

    def circle(self, x, y, r, cls="bub"):
        self.parts.append(f'<circle class="{cls}" cx="{num(x)}" cy="{num(y)}" r="{num(r)}"/>')
        self.ext(x - r, y - r, x + r, y + r)

    def tick(self, x, y):
        """A short 45-degree dimension tick."""
        self.parts.append(f'<line class="dl" x1="{num(x - 0.8)}" y1="{num(y + 0.8)}" x2="{num(x + 0.8)}" y2="{num(y - 0.8)}"/>')

    def render(self, pad=1.5):
        x0, y0, x1, y1 = self.bb
        w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        body = f'<g transform="translate({num(pad - x0)},{num(pad - y0)})">' + "".join(self.parts) + "</g>"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{num(w)}mm" height="{num(h)}mm" viewBox="0 0 {num(w)} {num(h)}">'
                + body + "</svg>"), w, h


def stagger(items, vertical=False):
    """Rows for dimension labels so none overlaps another label, and where it can, no leader crosses a label.
    items: [(centre, half_extent)] in paper mm, left to right. Returns a row number for each."""
    rows, placed = [], []                                  # placed: (row, lo, hi, centre)
    for c, h in items:
        lo, hi = c - h - 0.6, c + h + 0.6
        chosen = None
        for strict in (True, False):
            for r in range(8):
                ok = True
                for (r2, lo2, hi2, c2) in placed:
                    if r2 == r and not (hi < lo2 or lo > hi2):
                        ok = False
                    elif strict and r2 < r and lo2 <= c <= hi2:         # this leader crosses a nearer label
                        ok = False
                    elif strict and r2 > r and lo <= c2 <= hi:          # a farther leader crosses this label
                        ok = False
                    if not ok:
                        break
                if ok:
                    chosen = r
                    break
            if chosen is not None:
                break
        r = chosen if chosen is not None else 7
        rows.append(r)
        placed.append((r, lo, hi, c))
    return rows


def cluster(vals, tol=1.5):
    """Sorted values with those within tol of each other merged (their mean)."""
    out = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


class View:
    """A drawing of some members seen along one projection, at scale 1:N."""

    def __init__(self, frame, sec, vspec, letters, units, footings=None):
        self.frame, self.sec, self.spec, self.letters, self.units = frame, sec, vspec, letters, units
        self.pr = Proj(vspec["view"])
        self.footings = footings
        hide = set(vspec.get("hide", HIDE))
        only = set(vspec.get("only", []))
        ghost_kinds = set(vspec.get("ghost_kinds", []))
        self.drawn, self.ghost = [], []
        for m in sec["members"]:
            if only:
                (self.drawn if m["kind"] in only else self.ghost if m["kind"] in ghost_kinds else []).append(m)
            elif m["kind"] not in hide:
                self.drawn.append(m)
        for g in vspec.get("ghost", []):
            for m in frame["members"]:
                if (m["group"].startswith(g) or m["group"] == g) and m["kind"] not in HIDE and m["layer"] != "foundations":
                    self.ghost.append(m)
        self.shapes = []                                           # (member, polygons, depth)
        for m in self.drawn:
            s, d = self.pr.shapes(m)
            self.shapes.append((m, s, d))
        self.shapes.sort(key=lambda t: (-t[2], t[0]["id"]))        # far first
        self.gshapes = []
        for m in self.ghost:
            s, d = self.pr.shapes(m)
            self.gshapes.append((m, s, d))
        self.gshapes.sort(key=lambda t: (-t[2], t[0]["id"]))
        allp = [s for _, ss, _ in self.shapes for s in ss]
        self.box = bbox2(allp) if allp else (0, 0, 1, 1)
        if vspec.get("footings") and footings:
            lo, hi = structure_box(frame)
            r0 = self.pr.pt(lo)[0]
            self.outline = (r0, lo[1], hi[0], hi[1])             # plan: model x, y
            xs = [f[0] for f in footings] + [lo[0], hi[0]]
            ys = [f[1] for f in footings] + [lo[1], hi[1]]
            self.box = (min(xs) - 80, min(ys) - 80, max(xs) + 80, max(ys) + 80)
        else:
            self.outline = None
        self.openings = self.find_openings() if vspec.get("openings") else []

    # -- the pieces of information the drawing needs from the members

    def mbox(self, m):
        return bbox2(self.pr.shapes(m)[0])

    def find_openings(self):
        """Openings from the headers: width between the jack studs, height from the floor, sill height."""
        mem = [m for m in self.drawn]
        heads = {}
        for m in mem:
            if m["kind"] == "header":
                b = self.mbox(m)
                heads.setdefault((round(b[0]), round(b[2])), b)
        floor_z = min(self.mbox(m)[1] for m in mem) if mem else 0
        out = []
        for (r0, r1), hb in sorted(heads.items()):
            jacks = [self.mbox(m) for m in mem if m["kind"] in ("jack",) and self.mbox(m)[0] >= r0 - 1 and self.mbox(m)[2] <= r1 + 1]
            if len(jacks) < 2:
                jacks = [self.mbox(m) for m in mem if m["kind"] in ("king", "jack") and self.mbox(m)[0] >= r0 - 1 and self.mbox(m)[2] <= r1 + 1]
            mid = (r0 + r1) / 2
            left = [j[2] for j in jacks if (j[0] + j[2]) / 2 < mid]
            right = [j[0] for j in jacks if (j[0] + j[2]) / 2 > mid]
            cl, cr = (max(left) if left else r0), (min(right) if right else r1)
            sills = [self.mbox(m) for m in mem if m["kind"] == "sill" and self.mbox(m)[0] < cr - 1 and self.mbox(m)[2] > cl + 1
                     and self.mbox(m)[3] <= hb[1] + 1]
            bottom = max(s[3] for s in sills) if sills else floor_z
            out.append({"l": cl, "r": cr, "top": hb[1], "bottom": bottom, "window": bool(sills), "floor": floor_z})
        return out

    def marks(self, spec):
        """Centres along the screen-right axis (axis 0) or up axis (axis 1) for a marks spec."""
        res = {0: [], 1: []}
        ax = spec.get("axis")
        kinds = set(spec["kinds"])
        sel = []
        for m, ss, _ in self.shapes:
            if m["kind"] not in kinds or (spec.get("not_id") and spec["not_id"] in m["id"]):
                continue
            b = bbox2(ss)
            if spec.get("tall") and (b[3] - b[1]) < spec["tall"] * (self.box[3] - self.box[1]):
                continue
            sel.append(b)
        if not sel:
            return res
        if ax is None:                                       # joists and rafters: spread across their short side
            vertical = sum(1 for b in sel if (b[3] - b[1]) > (b[2] - b[0]))
            ax = 0 if vertical * 2 >= len(sel) else 1
        res[ax] = cluster([(b[0] + b[2]) / 2 if ax == 0 else (b[1] + b[3]) / 2 for b in sel])
        return res

    # -- drawing

    def draw(self, N):
        sv = Svg()
        r0, u0, r1, u1 = self.box
        X = lambda r: (r - r0) / N
        Y = lambda u: (u1 - u) / N
        W, H = (r1 - r0) / N, (u1 - u0) / N
        spec = self.spec
        units = self.units
        for m, ss, d in self.gshapes:
            for s in ss:
                sv.poly([(X(p[0]), Y(p[1])) for p in s], "gh")
        if spec.get("ground"):
            gy = Y(0)
            if 0 <= gy <= H + 5:
                sv.line(-3, gy, W + 3, gy, "gr")
                sv.text(W + 3.5, gy + 1, "ground", "start", "dt g")
        if self.outline:
            _, y0, _, y1 = self.outline
            x0 = self.outline[0]
            lo, hi = structure_box(self.frame)
            sv.poly([(X(lo[0]), Y(lo[1])), (X(hi[0]), Y(lo[1])), (X(hi[0]), Y(hi[1])), (X(lo[0]), Y(hi[1]))], "outl")
        placed, small = [], 0                                 # bubble centres
        n_small = sum(1 for m, ss, _ in self.shapes if self.letters.get(m["id"]) and
                      max((bbox2(ss)[2] - bbox2(ss)[0]), (bbox2(ss)[3] - bbox2(ss)[1])) / N < 7.5)
        for m, ss, d in self.shapes:
            for s in ss:
                pts = [(X(p[0]), Y(p[1])) for p in s]
                if len(pts) >= 3:
                    sv.poly(pts, "mem")
                elif len(pts) == 2:
                    sv.line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], "ml")
        for m, ss, d in self.shapes:                           # letters on top of all pieces
            lt = self.letters.get(m["id"])
            if not lt:
                continue
            b = bbox2(ss)
            bw, bh = (b[2] - b[0]) / N, (b[3] - b[1]) / N
            if max(bw, bh) < 7.5:                              # too small for a bubble on it: one beside it, on a leader
                if n_small > 12:                               # a crowd of small pieces: the table counts them
                    continue
                cx, cy = (X(b[0]) + X(b[2])) / 2, (Y(b[1]) + Y(b[3])) / 2
                for dx, dy in ((4.6, -4.6), (-4.6, -4.6), (4.6, 4.6), (-4.6, 4.6)):
                    if all((cx + dx - qx) ** 2 + (cy + dy - qy) ** 2 >= 4.7 ** 2 for qx, qy in placed):
                        placed.append((cx + dx, cy + dy))
                        small += 1
                        sv.line(cx, cy, cx + dx * 0.55, cy + dy * 0.55, "ld")
                        sv.circle(cx + dx, cy + dy, 2.1)
                        sv.text(cx + dx, cy + dy + 1.0, lt, "middle", "dt b")
                        break
                continue
            cx, cy = (X(b[0]) + X(b[2])) / 2, (Y(b[1]) + Y(b[3])) / 2
            along = [0] if bw >= bh else [1]
            spots = [(cx, cy)]
            reach = max(bw, bh) / 2 - 3.2
            for k in (1, -1, 2, -2):
                step = 4.6 * k
                if abs(step) <= reach:
                    spots.append((cx + step, cy) if along == [0] else (cx, cy + step))
            for (px, py) in spots:
                if all((px - qx) ** 2 + (py - qy) ** 2 >= 4.7 ** 2 for qx, qy in placed):
                    placed.append((px, py))
                    sv.circle(px, py, 2.1)
                    sv.text(px, py + 1.0, lt, "middle", "dt b")
                    break
        if self.footings:
            self.draw_footings(sv, X, Y)
        self.draw_openings(sv, X, Y)
        self.draw_dims(sv, X, Y, W, H, N)
        return sv

    def draw_footings(self, sv, X, Y):
        pts = [(X(fx), Y(fy)) for fx, fy, _ in self.footings]
        taken = []
        for i, (x, y) in enumerate(pts, 1):
            sv.line(x - 4, y, x + 4, y, "ct")
            sv.line(x, y - 4, x, y + 4, "ct")
            sv.circle(x, y, 1.0, "cdot")
        for i, (x, y) in enumerate(pts, 1):
            best = None
            for dx, dy in ((5, -5), (-5, -5), (5, 5), (-5, 5), (0, -7.5), (7.5, 0), (-7.5, 0), (0, 7.5)):
                bx, by = x + dx, y + dy
                clear = all((bx - qx) ** 2 + (by - qy) ** 2 >= 4.8 ** 2 for qx, qy in taken)
                clear = clear and all((bx - qx) ** 2 + (by - qy) ** 2 >= 3.6 ** 2 for qx, qy in pts)
                if clear:
                    best = (bx, by)
                    break
            bx, by = best or (x + 5, y - 5)
            taken.append((bx, by))
            sv.circle(bx, by, 2.3, "bub")
            sv.text(bx, by + 1.0, str(i), "middle", "dt b")

    def draw_openings(self, sv, X, Y):
        U = self.units
        for o in self.openings:
            x0, x1, yt, yb = X(o["l"]), X(o["r"]), Y(o["top"]), Y(o["bottom"])
            w = o["r"] - o["l"]
            h = o["top"] - o["bottom"]
            hh = o["top"] - o["floor"]
            # width line just under the header, height line at the left jack
            ym = yt + 3.0
            sv.line(x0, ym, x1, ym, "ac")
            sv.parts.append(f'<line class="ac" x1="{num(x0)}" y1="{num(ym - 1)}" x2="{num(x0)}" y2="{num(ym + 1)}"/>'
                            f'<line class="ac" x1="{num(x1)}" y1="{num(ym - 1)}" x2="{num(x1)}" y2="{num(ym + 1)}"/>')
            name = "Window" if o["window"] else "Door"
            lines = [f"{name} (clear opening)", f"{fmt(w, U)} wide", f"{fmt(h if o['window'] else hh, U)} high"]
            if o["window"]:
                lines.append(f"sill {fmt(o['bottom'] - o['floor'], U)} above the floor")
            cx = (x0 + x1) / 2
            avail = x1 - x0 - 1
            size = FONT
            if max(text_w(s, size) for s in lines) > avail:
                lines = [name, f"{fmt(w, U)} x {fmt(h if o['window'] else hh, U)}"] + ([f"sill {fmt(o['bottom'] - o['floor'], U)}"] if o["window"] else [])
            ty = ym + 5.0
            for i, s in enumerate(lines):
                sv.text(cx, ty + i * 3.5, s, "middle", "dt a" + (" b" if i == 0 else ""))

    def draw_dims(self, sv, X, Y, W, H, N):
        spec, U = self.spec, self.units
        r0, u0, r1, u1 = self.box
        ov = spec.get("overall", "")
        # --- chains along the bottom (axis 0) and the left (axis 1)
        mk = {0: [], 1: []}
        mode = {0: "gap", 1: "gap"}
        for key in ("hmarks", "vmarks", "auto"):
            s = spec.get(key)
            if not s:
                continue
            got = self.marks(dict(s, axis=0 if key == "hmarks" else 1 if key == "vmarks" else None))
            for a in (0, 1):
                if got[a]:
                    mk[a], mode[a] = got[a], s["mode"]
        if self.footings:
            mk[0] = cluster([f[0] for f in self.footings], 2)
            mk[1] = cluster([f[1] for f in self.footings], 2)
            mode[0] = mode[1] = "cum"
        ref0 = self.outline[0] if False else (structure_box(self.frame)[0][0] if self.footings else r0)
        ref1 = structure_box(self.frame)[0][1] if self.footings else u0
        y = H + 4.5
        if mk[0]:
            used = self.hchain(sv, X, mk[0], mode[0], r0, r1, ref0, y, N, W)
            y += used
        if "w" in ov:
            self.dim_h(sv, X(r0), X(r1), y + 3.5, fmt(r1 - r0, U))
        elif self.footings:
            pass
        x = -4.5
        if mk[1]:
            used = self.vchain(sv, Y, mk[1], mode[1], u0, u1, ref1, x, N, H)
            x -= used
        if "h" in ov:
            if self.spec["view"] == "plan":
                self.dim_v(sv, Y(u1), Y(u0), x - 3.5, fmt(u1 - u0, U))
            else:
                self.dim_v(sv, Y(u1), Y(u0), x - 3.5, fmt(u1 - u0, U))
        if spec.get("footings"):
            lo, hi = structure_box(self.frame)
            self.dim_h(sv, X(lo[0]), X(hi[0]), y + 3.5, fmt(hi[0] - lo[0], U))
            self.dim_v(sv, Y(hi[1]), Y(lo[1]), x - 3.5, fmt(hi[1] - lo[1], U))
        if spec.get("heights") == "ends":
            self.end_heights(sv, X, Y, W)
        if spec.get("pitch"):
            ang = self.pitch()
            if ang:
                sv.text(W / 2, -3.0, f"Roof pitch {ang:g}°", "middle", "dt b")

    def pitch(self):
        for m in self.sec["members"]:
            if m["kind"] == "rafter" and "flying" not in m["id"]:
                a = math.degrees(math.asin(min(1.0, abs(m["x"][2]))))
                return round(a, 1) if a > 0.5 else 0
        return 0

    def end_heights(self, sv, X, Y, W):
        r0, u0, r1, u1 = self.box
        left = [self.mbox(m) for m in self.drawn]
        lh = max(b[3] for b in left if b[0] <= r0 + 1)
        rh = max(b[3] for b in left if b[2] >= r1 - 1)
        lo = u0
        self.dim_v(sv, Y(lh), Y(lo), -4.5, fmt(lh - lo, self.units))
        if abs(lh - rh) > 1:
            self.dim_v(sv, Y(rh), Y(lo), X(r1) + 4.5, fmt(rh - lo, self.units), right=True)
        else:
            pass

    def hchain(self, sv, X, marks, mode, r0, r1, ref, y, N, W):
        U = self.units
        pos, labels = [], []
        if mode == "cum":
            pts = [(X(m), fmt(m - ref, U)) for m in marks]
            pos = [X(r0)] + [p for p, _ in pts]
            labels = [(p, s) for p, s in pts]
        else:
            edges = [r0] + list(marks) + [r1]
            pos = [X(e) for e in edges]
            labels = [(X(c), t) for c, t in runs(edges, U)]
        sv.line(pos[0], y, pos[-1], y, "dl")
        for p in pos:
            sv.line(p, y - 1.2, p, y + 1.2, "dl")
            sv.tick(p, y)
        rows = stagger([(c, text_w(s) / 2) for c, s in labels])
        rh = 3.5
        for (c, s), r in zip(labels, rows):
            ty = y + 3.2 + r * rh
            if r:
                sv.line(c, y, c, ty - 2.6, "ld")
            sv.text(c, ty, s, "middle", "dt")
        return 3.4 + (max(rows) + 1) * rh + 1.0

    def vchain(self, sv, Y, marks, mode, u0, u1, ref, x, N, H):
        U = self.units
        if mode == "cum":
            pts = [(Y(m), fmt(m - ref, U)) for m in marks]
            pos = [Y(u0)] + [p for p, _ in pts]
            labels = pts
        else:
            edges = [u0] + list(marks) + [u1]
            pos = [Y(e) for e in edges]
            labels = [(Y(c), t) for c, t in runs(edges, U)]
        sv.line(x, min(pos), x, max(pos), "dl")
        for p in pos:
            sv.line(x - 1.2, p, x + 1.2, p, "dl")
            sv.tick(x, p)
        order = sorted(range(len(labels)), key=lambda i: labels[i][0])
        rows_sorted = stagger([(labels[i][0], FONT * 0.55) for i in order])
        rows = {i: r for i, r in zip(order, rows_sorted)}
        colw = max(text_w(s) for _, s in labels) + 1.6
        for i, (c, s) in enumerate(labels):
            r = rows[i]
            tx = x - 1.8 - r * colw
            if r:
                sv.line(x, c, tx + 0.4, c, "ld")
            sv.text(tx, c + 1.0, s, "end", "dt")
        return 2.0 + (max(rows.values()) + 1) * colw

    def dim_h(self, sv, xa, xb, y, s):
        sv.line(xa, y, xb, y, "dl")
        for x in (xa, xb):
            sv.line(x, y - 1.5, x, y + 1.5, "dl")
            sv.tick(x, y)
        sv.text((xa + xb) / 2, y - 0.9, s, "middle", "dt b")

    def dim_v(self, sv, ya, yb, x, s, right=False):
        sv.line(x, ya, x, yb, "dl")
        for y in (ya, yb):
            sv.line(x - 1.5, y, x + 1.5, y, "dl")
            sv.tick(x, y)
        sv.text(x - 1.0 if not right else x + 3.2, (ya + yb) / 2, s, "middle", "dt b", rot=-90)


def runs(edges, units):
    """Labels (centre in model mm, text) for the gaps between edges; four or more equal gaps in a row become one '7 x 567'."""
    gaps = [(a, b) for a, b in zip(edges, edges[1:])]
    out, i = [], 0
    while i < len(gaps):
        j = i
        while j + 1 < len(gaps) and abs((gaps[j + 1][1] - gaps[j + 1][0]) - (gaps[i][1] - gaps[i][0])) < 1.5:
            j += 1
        n = j - i + 1
        if n >= 4:
            out.append(((gaps[i][0] + gaps[j][1]) / 2, f"{n} x {fmt(gaps[i][1] - gaps[i][0], units)}"))
        else:
            out += [((a + b) / 2, fmt(b - a, units)) for a, b in gaps[i:j + 1]]
        i = j + 1
    return out


def fit(make, max_w, max_h):
    """Draw at the largest tidy scale that fits the panel. Returns (svg, N, w, h)."""
    last = None
    for N in SCALES:
        sv = make(N)
        svg, w, h = sv.render()
        last = (svg, N, w, h)
        if w <= max_w and h <= max_h:
            return last
    return last


# --------------------------------------------------------------------------------------------- tables

def footings_of(frame):
    """(x, y, name) of every footing: ground screws, piers, concrete footings (else the post bases)."""
    mem = [m for m in frame["members"] if m["kind"] in ("ground-screw", "pier", "footing")]
    if not mem:
        mem = [m for m in frame["members"] if m["kind"] == "post-base"]
    out = []
    for m in mem:
        lo, hi = aabb(m)
        out.append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, piece_name(m)))
    ys = cluster([f[1] for f in out], 2)
    def row(f):
        return min(range(len(ys)), key=lambda i: abs(ys[i] - f[1]))
    out.sort(key=lambda f: (row(f), f[0]))
    return out


def section_letters(sec, drawn_ids):
    """Letters for the drawn pieces of a section: same kind, section, length and cut angles, same letter."""
    keys = {}
    for m in sec["members"]:
        if m["id"] in drawn_ids:
            keys.setdefault(piece_key(m), []).append(m)
    order = bomlib.KIND_NAMES
    names = [v[0] for v in order.values()]
    def sk(k):
        return (names.index(k[0]) if k[0] in names else len(names), k[0], k[1], -k[2], k[3], k[4])
    keyed = sorted(keys, key=sk)
    letters, rows = {}, []
    for i, k in enumerate(keyed):
        lt = letter(i)
        for m in keys[k]:
            letters[m["id"]] = lt
        rows.append((lt, keys[k]))
    return letters, rows


def piece_rows(frame, sec, letters, lib, units):
    """Table rows (letter, name, section, length, cuts, qty) for every member of the section, drawn or not."""
    drawn = {}
    for m in sec["members"]:
        if m["id"] in letters:
            drawn.setdefault(letters[m["id"]], []).append(m)
    rows = []
    for lt in sorted(drawn, key=lambda s: (len(s), [LETTERS.index(c) for c in s])):
        ms = drawn[lt]
        m = ms[0]
        rows.append({"letter": lt, "name": piece_name(m), "item": item_name(lib, m["item"]),
                     "length": fmt(m["size"][0], units, True), "cuts": cut_text(m), "qty": len(ms), "drawn": True})
    other = {}
    for m in sec["members"]:
        if m["id"] not in letters:
            sheet = m["kind"] in ("sheet",)
            size = f"{fmt(m['size'][0], units, True)} x {fmt(m['size'][1], units, True)}" if sheet else fmt(m["size"][0], units, True)
            k = (piece_name(m), item_name(lib, m["item"]), size, cut_text(m))
            other.setdefault(k, []).append(m)
    byname = {}
    for k in sorted(other):
        byname.setdefault((k[0], k[1]), []).append(k)
    for (nm, it), ks in byname.items():
        qty = sum(len(other[k]) for k in ks)
        if len(ks) > 3:
            ls = sorted(m["size"][0] for k in ks for m in other[k])
            rows.append({"letter": "", "name": nm, "item": it, "cuts": "", "qty": qty, "drawn": False,
                         "length": f"{fmt(ls[0], units, True)} to {fmt(ls[-1], units, True)}"})
        else:
            for k in ks:
                rows.append({"letter": "", "name": k[0], "item": k[1], "length": k[2], "cuts": k[3], "qty": len(other[k]), "drawn": False})
    return rows


# ------------------------------------------------------------------------------------------ 3D views
# An axonometric view (an orthographic projection from a raised front-left corner) drawn from real faces:
# each member's six faces (or its outline prism's), back faces dropped, painted far to near, shaded by the
# way each face points. Colours are CSS classes: material or part (cat) + brightness (lvl), so the
# file stays small and prints in greyscale.

ISO_AZ, ISO_EL = 34.0, 26.0            # degrees: round from the front towards the right, and down from the horizon
LIGHT = (-0.5, -0.35, 0.8)             # towards the light: from the left, front and above
MIN_FACE_MM2 = 1.0                     # faces smaller than this on paper are left out
# (cat: base colour). Materials for "how it looks", tones for the parts of "the frame, by page".
CATS = {"tim": (232, 214, 184), "cla": (205, 172, 124), "shs": (226, 214, 188), "rof": (128, 134, 140),
        "dck": (200, 164, 118), "fnd": (176, 176, 176), "fa": (236, 236, 236), "hi": (176, 84, 14),
        "p0": (208, 224, 242), "p1": (242, 220, 190), "p2": (206, 236, 208), "p3": (242, 208, 208),
        "p4": (228, 214, 244), "p5": (246, 238, 184), "p6": (200, 232, 232), "p7": (222, 222, 222)}
PART_TONES = 8


def unit(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def area2(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def in_poly(p, poly):
    """Point in a polygon (even-odd)."""
    x, y, c = p[0], p[1], False
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
    return c


def mat_cat(m):
    """The material class of a member for the "how it looks" view."""
    k = m["kind"]
    if k == "sheet":
        return "rof" if m.get("layer") == "roof" else "shs"
    if k == "board":
        return "cla"
    if k == "deckboard":
        return "dck"
    if m.get("layer") == "foundations":
        return "fnd"
    return "tim"


def iso_css():
    rules = ["svg .iso polygon{stroke:#3a3a3a;stroke-width:.09;stroke-linejoin:round}",
             "svg .lite polygon{stroke:#c4c4c4;stroke-width:.07}",
             "svg .gd{fill:#f6f6f3;stroke:#c8c8c8;stroke-width:.2;stroke-dasharray:1.6 1}",
             "svg .ar{fill:var(--accent);stroke:var(--accent);stroke-width:.5;stroke-linejoin:round}"]
    for cat, c in CATS.items():
        for lv in range(10, 21):
            f = lv / 20.0
            rules.append(f"svg .{cat}{lv}{{fill:#{''.join('%02x' % min(255, round(v * f)) for v in c)}}}")
    return "\n".join(rules)


def triangulate(p3):
    """A face (3 or more (x, y, depth) points, convex or not) as triangles: ear clipping on the screen points."""
    n = len(p3)
    if n == 3:
        return [tuple(p3)]
    area = sum(p3[i][0] * p3[(i + 1) % n][1] - p3[(i + 1) % n][0] * p3[i][1] for i in range(n))
    if abs(area) < 1e-9:
        return []
    idx = list(range(n))
    if area < 0:
        idx.reverse()
    cr = lambda a, b, c: (p3[b][0] - p3[a][0]) * (p3[c][1] - p3[a][1]) - (p3[b][1] - p3[a][1]) * (p3[c][0] - p3[a][0])
    out, guard = [], 0
    while len(idx) > 3 and guard < 4 * n * n:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cr(a, b, c) <= 1e-9:
                continue
            if any(j not in (a, b, c) and cr(a, b, j) >= 0 and cr(b, c, j) >= 0 and cr(c, a, j) >= 0 for j in idx):
                continue
            out.append((p3[a], p3[b], p3[c]))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        out.append(tuple(p3[i] for i in idx))
    return out


def raster_tri(t, zfixed, face, zbuf, fid, ground):
    """One triangle (three (px, py, depth)) into the depth and face buffers; the nearer depth wins."""
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = t
    if zfixed is not None:
        z0 = z1 = z2 = zfixed
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(d) < 1e-9:
        return
    H, W = zbuf.shape
    xa, xb = max(0, int(math.floor(min(x0, x1, x2)))), min(W - 1, int(math.ceil(max(x0, x1, x2))))
    ya, yb = max(0, int(math.floor(min(y0, y1, y2)))), min(H - 1, int(math.ceil(max(y0, y1, y2))))
    if xa > xb or ya > yb:
        return
    xs = np.arange(xa, xb + 1, dtype=np.float64) + 0.5
    ys = (np.arange(ya, yb + 1, dtype=np.float64) + 0.5)[:, None]
    l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
    l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
    l2 = 1.0 - l0 - l1
    eps = -1e-7
    inside = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
    z = (l0 * z0 + l1 * z1 + l2 * z2).astype(np.float32)
    zs = zbuf[ya:yb + 1, xa:xb + 1]
    win = inside & (z < zs)
    zs[win] = z[win]
    fid[ya:yb + 1, xa:xb + 1][win] = face


def bubbles_svg(spots, r=2.5):
    """Numbered bubbles at (x, y) paper mm; those that would overlap are pushed apart and joined to their spot."""
    pos = [list(p) for _, p in spots]
    home = [list(p) for p in pos]
    for _ in range(60):
        moved = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                d = math.hypot(dx, dy)
                if d < 2 * r + 0.8:
                    if d < 1e-6:
                        dx, dy, d = 0.0, 1.0, 1.0
                    k = (2 * r + 0.8 - d) / 2 / d
                    pos[i][0] -= dx * k; pos[i][1] -= dy * k
                    pos[j][0] += dx * k; pos[j][1] += dy * k
                    moved = True
        if not moved:
            break
    out = []
    for p, h0 in zip(pos, home):
        if math.hypot(p[0] - h0[0], p[1] - h0[1]) > 1.0:
            out.append(f'<line class="dl" x1="{h0[0]:.1f}" y1="{h0[1]:.1f}" x2="{p[0]:.1f}" y2="{p[1]:.1f}"/>')
        out.append(f'<circle class="cdot" cx="{h0[0]:.1f}" cy="{h0[1]:.1f}" r="0.7"/>')
    for (lab, _), p in zip(spots, pos):
        out.append(f'<circle class="bub" cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="{r}"/>'
                   f'<text class="dt n" font-size="3" text-anchor="middle" x="{p[0]:.1f}" y="{p[1] + 1.05:.1f}">{esc(lab)}</text>')
    return "".join(out)


class Iso:
    """The camera and every member's visible faces, worked out once."""

    def __init__(self, frame):
        az, el = math.radians(ISO_AZ), math.radians(ISO_EL)
        self.f = (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), -math.sin(el))
        self.r = unit(cross(self.f, (0, 0, 1)))
        self.u = cross(self.r, self.f)
        self.light = unit(LIGHT)
        self.members = [self.build(m) for m in frame["members"]]
        allp = [p for m in frame["members"] for p in prism(m)]
        self.ground = [(min(p[0] for p in allp) - 150, min(p[1] for p in allp) - 150),
                       (max(p[0] for p in allp) + 150, max(p[1] for p in allp) + 150)]

    def pt(self, p):
        return (dot(p, self.r), dot(p, self.u), dot(p, self.f))

    def build(self, m):
        poly, T = local_points(m)
        x, y = unit(tuple(m["x"])), unit(tuple(m["y"]))
        z = cross(x, y)
        base = [world(m, u, v, 0) for u, v in poly]
        top = [world(m, u, v, T) for u, v in poly]
        n = len(poly)
        sgn = 1 if sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n)) > 0 else -1
        faces = [(base, (-z[0], -z[1], -z[2])), (top, z)]
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            du, dv = b[0] - a[0], b[1] - a[1]
            if abs(du) + abs(dv) < 1e-9:
                continue
            nu, nv = sgn * dv, -sgn * du
            nrm = unit(tuple(nu * x[k] + nv * y[k] for k in range(3)))
            faces.append(([base[i], base[(i + 1) % n], top[(i + 1) % n], top[i]], nrm))
        out = []
        for pts, nrm in faces:
            if dot(nrm, self.f) >= -1e-6:
                continue
            p3 = [self.pt(p) for p in pts]
            lit = max(0.0, dot(nrm, self.light))
            lv = max(10, min(20, round((0.5 + 0.62 * lit) * 20)))
            out.append((p3, lv, sum(q[2] for q in p3) / len(p3)))
        out.sort(key=lambda t: -t[2])
        near = min(self.pt(p)[2] for p in base + top)
        return {"id": m["id"], "group": m["group"], "kind": m["kind"], "faces": out, "key": near, "m": m}

    def scene(self, picks):
        """picks: [(member index, cat, layer, tag)] -> faces in paint order [(polygon, cat+level, tag)]."""
        order = sorted(picks, key=lambda p: (p[2], -self.members[p[0]]["key"], self.members[p[0]]["id"]))
        items = []
        for mi, cat, layer, tag in order:
            for p3, lv, _ in self.members[mi]["faces"]:
                items.append(([(q[0], q[1]) for q in p3], f"{cat}{lv}", tag))
        return items

    def anchors(self, items):
        """For each tag, a spot on a face of that part that nothing painted later covers."""
        boxes = [bbox2([it[0]]) for it in items]
        by = {}
        for i, it in enumerate(items):
            if it[2] is not None:
                by.setdefault(it[2], []).append(i)
        res = {}
        for tag in sorted(by):
            cands = sorted(by[tag], key=lambda i: -area2(items[i][0]))[:40]
            vis = []
            for i in cands:
                poly = items[i][0]
                c = (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
                hidden = any(b[0] <= c[0] <= b[2] and b[1] <= c[1] <= b[3] and in_poly(c, items[j][0])
                             for j, b in ((j, boxes[j]) for j in range(i + 1, len(items))))
                if not hidden:
                    vis.append((area2(poly), c))
            if not vis:
                poly = items[cands[0]][0]
                vis = [(1.0, (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)))]
            tw = sum(a for a, _ in vis)
            wc = (sum(a * c[0] for a, c in vis) / tw, sum(a * c[1] for a, c in vis) / tw)
            res[tag] = min((c for _, c in vis), key=lambda c: (c[0] - wc[0]) ** 2 + (c[1] - wc[1]) ** 2)
        return res

    def draw_items(self, items, max_w, max_h, lite=None, top=None, bubbles=None, arrow=None, ground=True):
        """The scene as an SVG (paper mm). lite: items painted as a faint layer first (indexes < lite);
        bubbles: [(label, (x, y) in model screen units)]; arrow: (from, to) in model 3D."""
        g0, g1 = self.ground
        gpoly = [self.pt((x, y, 0))[:2] for x, y in ((g0[0], g0[1]), (g1[0], g0[1]), (g1[0], g1[1]), (g0[0], g1[1]))] if ground else []
        shapes = [it[0] for it in items] + ([gpoly] if gpoly else [])
        ar = [self.pt(p)[:2] for p in arrow] if arrow else []
        x0, y0, x1, y1 = bbox2(shapes + ([ar] if ar else []))
        s = min(max_w / (x1 - x0), max_h / (y1 - y0))
        if s * 1.0 > 0.2:
            s = 0.2
        X = lambda v: (v - x0) * s
        Y = lambda v: (y1 - v) * s
        P = lambda poly: " ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in poly)
        parts = []
        if gpoly:
            parts.append(f'<polygon class="gd" points="{P(gpoly)}"/>')
        cur = None
        for poly, cls, tag in items:
            if area2(poly) * s * s < MIN_FACE_MM2:
                continue
            g = "iso lite" if (lite and tag == "lite") else "iso"
            if g != cur:
                parts.append(("</g>" if cur else "") + f'<g class="{g}">')
                cur = g
            parts.append(f'<polygon class="{cls}" points="{P(poly)}"/>')
        if cur:
            parts.append("</g>")
        w, h = (x1 - x0) * s, (y1 - y0) * s
        if ar:
            (ax, ay), (bx, by) = ((X(ar[0][0]), Y(ar[0][1])), (X(ar[1][0]), Y(ar[1][1])))
            L = math.hypot(bx - ax, by - ay) or 1
            dx, dy = (bx - ax) / L, (by - ay) / L
            parts.append(f'<line class="ar" x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx - dx * 2:.1f}" y2="{by - dy * 2:.1f}"/>'
                         f'<polygon class="ar" points="{bx:.1f},{by:.1f} {bx - dx * 3 - dy * 1.4:.1f},{by - dy * 3 + dx * 1.4:.1f} '
                         f'{bx - dx * 3 + dy * 1.4:.1f},{by - dy * 3 - dx * 1.4:.1f}"/>')
        if bubbles:
            r = 2.5
            pos = [[X(a[0]), Y(a[1])] for _, a in bubbles]
            home = [list(p) for p in pos]
            for _ in range(60):
                moved = False
                for i in range(len(pos)):
                    for j in range(i + 1, len(pos)):
                        dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                        d = math.hypot(dx, dy)
                        if d < 2 * r + 0.8:
                            if d < 1e-6:
                                dx, dy, d = 0.0, 1.0, 1.0
                            k = (2 * r + 0.8 - d) / 2 / d
                            pos[i][0] -= dx * k; pos[i][1] -= dy * k
                            pos[j][0] += dx * k; pos[j][1] += dy * k
                            moved = True
                if not moved:
                    break
            for (lab, _), p, h0 in zip(bubbles, pos, home):
                if math.hypot(p[0] - h0[0], p[1] - h0[1]) > 1.0:
                    parts.append(f'<line class="dl" x1="{h0[0]:.1f}" y1="{h0[1]:.1f}" x2="{p[0]:.1f}" y2="{p[1]:.1f}"/>')
                parts.append(f'<circle class="cdot" cx="{h0[0]:.1f}" cy="{h0[1]:.1f}" r="0.7"/>')
            for (lab, _), p in zip(bubbles, pos):
                parts.append(f'<circle class="bub" cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="{r}"/>'
                             f'<text class="dt n" font-size="3" text-anchor="middle" x="{p[0]:.1f}" y="{p[1] + 1.05:.1f}">{esc(lab)}</text>')
        pad = 3.0
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad:.1f}mm" height="{h + 2 * pad:.1f}mm" '
               f'viewBox="{-pad} {-pad} {w + 2 * pad:.1f} {h + 2 * pad:.1f}">' + "".join(parts) + "</svg>")
        return svg


    # -- the z-buffer path: every face is rasterised with a per-pixel depth, so no sort can go wrong

    def triangles(self, mi):
        """Each visible face of member mi as triangles of (x, y, depth) points, with a face number."""
        out = []
        for fi, (p3, lv, _) in enumerate(self.members[mi]["faces"]):
            for t in triangulate(p3):
                out.append((fi, t))
        return out

    def draw(self, picks, max_w, max_h, bubbles=False, arrow=None, ground=True, ppm=8.0):
        """picks: [(member index, cat, layer, tag)]. Layer 1 is drawn over layer 0 whatever the depth.
        bubbles: number the tagged parts. arrow: (from, to) in model 3D. Returns an SVG in paper mm."""
        if not HAVE_RASTER:
            items = self.scene(picks)
            return self.draw_items(items, max_w, max_h, lite=any(p[1] == "fa" for p in picks),
                                   bubbles=[(str(t + 1), a) for t, a in sorted(self.anchors(items).items())] if bubbles else None,
                                   arrow=arrow, ground=ground)
        g0, g1 = self.ground
        gq = [self.pt((x, y, 0)) for x, y in ((g0[0], g0[1]), (g1[0], g0[1]), (g1[0], g1[1]), (g0[0], g1[1]))] if ground else []
        pts = [q[:2] for q in gq]
        for mi, *_ in picks:
            for p3, _, _ in self.members[mi]["faces"]:
                pts += [(q[0], q[1]) for q in p3]
        ar = [self.pt(p)[:2] for p in arrow] if arrow else []
        x0, y0, x1, y1 = bbox2([pts + ar])
        s = min(max_w / (x1 - x0), max_h / (y1 - y0), 0.2)                # paper mm per model mm
        pad = 3.0
        W, H = int(math.ceil((x1 - x0) * s * ppm + 2 * pad * ppm)), int(math.ceil((y1 - y0) * s * ppm + 2 * pad * ppm))
        k = s * ppm
        to_px = lambda q: ((q[0] - x0) * k + pad * ppm, (y1 - q[1]) * k + pad * ppm, q[2])
        zbuf = np.full((H, W), np.inf, dtype=np.float32)
        fid = np.zeros((H, W), dtype=np.int32)
        face_rgb, face_line, face_tag = [(255, 255, 255)], [(255, 255, 255)], [-1]
        if gq:
            face_rgb.append((246, 246, 243)); face_line.append((200, 200, 200)); face_tag.append(-1)
            for t in triangulate(gq):
                raster_tri([to_px(q) for q in t], 1e12, len(face_rgb) - 1, zbuf, fid, True)
        for layer in sorted(set(p[2] for p in picks)):
            if layer:
                zbuf[:] = np.inf
            for mi, cat, ly, tag in sorted((p for p in picks if p[2] == layer), key=lambda p: self.members[p[0]]["id"]):
                for p3, lv, _ in self.members[mi]["faces"]:
                    c = CATS[cat]
                    face_rgb.append(tuple(min(255, round(v * lv / 20.0)) for v in c))
                    face_line.append((196, 196, 196) if cat == "fa" else (58, 58, 58))
                    face_tag.append(-1 if tag is None or tag == "lite" else tag)
                    for t in triangulate(p3):
                        raster_tri([to_px(q) for q in t], None, len(face_rgb) - 1, zbuf, fid, False)
        rgb = np.array(face_rgb, dtype=np.uint8)[fid]
        # outlines: where the face changes between neighbouring pixels, the nearer pixel gets the line colour
        z = np.where(fid > 0, zbuf, np.inf)
        edge = np.zeros((H, W), dtype=bool)
        for sl_a, sl_b in (((slice(None), slice(0, -1)), (slice(None), slice(1, None))),
                           ((slice(0, -1), slice(None)), (slice(1, None), slice(None)))):
            diff = fid[sl_a] != fid[sl_b]
            first = (z[sl_a] <= z[sl_b]) & diff
            second = (z[sl_b] < z[sl_a]) & diff
            edge[sl_a] |= first
            edge[sl_b] |= second
        lines = np.array(face_line, dtype=np.uint8)[fid]
        rgb = np.where(edge[:, :, None] & (fid[:, :, None] > 1), lines, rgb)
        rgb = np.where(edge[:, :, None] & (fid[:, :, None] == 1), lines, rgb)
        buf = io.BytesIO()
        Image.fromarray(rgb, "RGB").save(buf, format="PNG", compress_level=9, optimize=False)
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        parts = [f'<image x="0" y="0" width="{W / ppm:.2f}" height="{H / ppm:.2f}" href="data:image/png;base64,{data}"/>']
        mm = lambda v: v / ppm
        if ar:
            (ax, ay), (bx, by) = [(mm(to_px(p + (0,))[0]), mm(to_px(p + (0,))[1])) for p in ar]
            L = math.hypot(bx - ax, by - ay) or 1
            dx, dy = (bx - ax) / L, (by - ay) / L
            parts.append(f'<line class="ar" x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx - dx * 2:.1f}" y2="{by - dy * 2:.1f}"/>'
                         f'<polygon class="ar" points="{bx:.1f},{by:.1f} {bx - dx * 3 - dy * 1.4:.1f},{by - dy * 3 + dx * 1.4:.1f} '
                         f'{bx - dx * 3 + dy * 1.4:.1f},{by - dy * 3 - dx * 1.4:.1f}"/>')
        if bubbles:
            tags = np.array(face_tag)[fid]
            spots = []
            for tag in sorted(set(int(t) for t in np.unique(tags)) - {-1}):
                ys, xs = np.nonzero(tags == tag)
                cx, cy = xs.mean(), ys.mean()
                j = int(np.argmin((xs - cx) ** 2 + (ys - cy) ** 2))
                spots.append((str(tag + 1), (mm(xs[j] + 0.5), mm(ys[j] + 0.5))))
            parts.append(bubbles_svg(spots))
        w, h = W / ppm, H / ppm
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" viewBox="0 0 {w:.2f} {h:.2f}">'
                + "".join(parts) + "</svg>")


def looks_svg(iso, frame, max_w, max_h):
    picks = [(i, mat_cat(m), 0, None) for i, m in enumerate(frame["members"])]
    return iso.draw(picks, max_w, max_h)


def frame_svg(iso, frame, secs, max_w, max_h):
    part_of = {s["group"]: i for i, s in enumerate(secs)}
    picks = [(i, f"p{part_of[m['group']] % PART_TONES}", 0, part_of[m["group"]])
             for i, m in enumerate(frame["members"]) if m["kind"] not in HIDE]
    return iso.draw(picks, max_w, max_h, bubbles=True)


def key_picks(frame, sec):
    """The frame in very light grey (layer 0) with this part dark and drawn over it (layer 1)."""
    picks = []
    for i, m in enumerate(frame["members"]):
        if m["kind"] in HIDE:
            continue
        mine = m["group"] == sec["group"]
        picks.append((i, "hi" if mine else "fa", 1 if mine else 0, None if mine else "lite"))
    return picks


def key_svg(iso, frame, secs, sec, max_w, max_h):
    """The key view: the frame with this part dark, and an arrow for where its main drawing is seen from."""
    picks = key_picks(frame, sec)
    mem = [m for m in sec["members"] if m["kind"] not in HIDE] or sec["members"]
    boxes = [aabb(m) for m in mem]
    lo = [min(b[0][k] for b in boxes) for k in range(3)]
    hi = [max(b[1][k] for b in boxes) for k in range(3)]
    mid = [(lo[k] + hi[k]) / 2 for k in range(3)]
    v = sec["views"][0]["view"] if sec["views"] else "plan"
    span = max(hi[k] - lo[k] for k in range(3))
    L = max(450.0, min(900.0, span * 0.35))
    if v == "plan":
        arrow = ((mid[0], mid[1], hi[2] + L), (mid[0], mid[1], hi[2] + 40))
    else:
        d = {"front": (0, 1, 0), "back": (0, -1, 0), "left": (1, 0, 0), "right": (-1, 0, 0)}[v]
        end = list(mid)
        k = 0 if d[0] else 1
        end[k] = (lo[k] - 40) if d[k] > 0 else (hi[k] + 40)
        arrow = (tuple(end[j] - d[j] * L for j in range(3)), tuple(end))
    return iso.draw(picks, max_w, max_h, arrow=arrow, ppm=6.0)


# ------------------------------------------------------------------------------------------ html page

CSS = """
:root{--ink:#1a1a1a;--grey:#666;--line:#bbb;--accent:%(accent)s}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#fff;color:var(--ink);font:9.5pt/1.35 system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif}
%(pages)s
h1{font-size:26pt;margin:0 0 2mm;line-height:1.1}
h2{font-size:15pt;margin:0 0 3mm}
h3{font-size:11pt;margin:5mm 0 1.5mm;break-after:avoid}
p{margin:0 0 2mm}
.sub{color:var(--grey);margin:0 0 5mm}
.page{break-before:page}
.page:first-of-type{break-before:auto}
.draw{page:drawing}
.facts{border-collapse:collapse;margin:0 0 5mm}
.facts td{padding:1mm 6mm 1mm 0;vertical-align:top}
.facts td:first-child{color:var(--grey)}
.verdict{border-left:2mm solid var(--ink);padding:2mm 4mm;margin:0 0 5mm;background:#f3f3f1}
.verdict b{font-size:12pt}
.verdict ul{margin:1.5mm 0 0;padding-left:5mm}
.warn{border:0.6mm solid var(--ink);padding:3mm 4mm;margin:0 0 5mm}
.warn b{display:block;font-size:11pt;margin-bottom:1mm}
.small{font-size:8.5pt;color:var(--grey)}
ul.dec{margin:0 0 4mm;padding-left:5mm}
ul.dec li{margin-bottom:1mm}
table{border-collapse:collapse;width:100%%}
th,td{text-align:left;padding:1mm 2mm;border-bottom:0.2mm solid var(--line);vertical-align:top}
th{font-size:8.5pt;color:var(--grey);font-weight:600;border-bottom:0.4mm solid var(--ink)}
td.n,th.n{text-align:right;white-space:nowrap}
td.nw{white-space:nowrap}
tr{break-inside:avoid}
.tot{font-weight:700;border-top:0.4mm solid var(--ink)}
.lt{display:inline-block;min-width:5.5mm;text-align:center;border:0.3mm solid var(--ink);border-radius:50%%;font-weight:700;font-size:8.5pt;line-height:4.6mm}
.drawing{display:grid;grid-template-columns:1fr %(tw)smm;gap:6mm;align-items:start}
.drawing.full{grid-template-columns:1fr}
.panel{display:flex;flex-direction:column;align-items:center;justify-content:flex-start}
.panel .cap{font-size:9pt;color:var(--grey);margin:0 0 1mm;align-self:flex-start}
.cols{display:flex;gap:6mm}
.cols .panel{flex:1}
.head{display:flex;justify-content:flex-start;align-items:baseline;border-bottom:0.4mm solid var(--ink);margin:0 0 3mm}
.head h2{margin:0}
.head .sc{color:var(--grey);font-size:9pt;margin-left:auto}
.pieces{font-size:8.5pt}
.pieces td,.pieces th{padding:0.55mm 1.5mm}
.note{font-size:8.5pt;color:var(--grey);margin:2mm 0 0}
.nd{color:var(--grey)}
svg{display:block;max-width:100%%}
svg text{font-family:system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;fill:#1a1a1a}
svg .mem{fill:#f1efe9;stroke:#1a1a1a;stroke-width:.25;stroke-linejoin:round}
svg .ml{stroke:#1a1a1a;stroke-width:.4}
svg .gh{fill:none;stroke:#b5b5b5;stroke-width:.2}
svg .outl{fill:none;stroke:#888;stroke-width:.25;stroke-dasharray:1.6 1}
svg .gr{stroke:#555;stroke-width:.5}
svg .dl{stroke:var(--accent);stroke-width:.2;fill:none}
svg .ld{stroke:var(--accent);stroke-width:.12;fill:none}
svg .ac{stroke:var(--accent);stroke-width:.25;fill:none}
svg .ct{stroke:var(--accent);stroke-width:.3}
svg .cdot{fill:var(--accent);stroke:none}
svg .bub{fill:#fff;stroke:#1a1a1a;stroke-width:.3}
svg .dt{fill:var(--accent);paint-order:stroke;stroke:#fff;stroke-width:.7;stroke-linejoin:round}
svg .dt.a{fill:var(--accent)}
svg .dt.g{fill:#666}
svg .dt.b{font-weight:700}
svg .bub+text.dt{fill:#1a1a1a;stroke:none}
svg text.n{font-weight:700;fill:#1a1a1a;stroke:none}
.views{display:flex;gap:6mm;margin:0 0 4mm;align-items:flex-start}
.views>div{flex:1;min-width:0}
.views .cap{font-size:9pt;font-weight:600;margin:0 0 1mm}
.leg{list-style:none;margin:1mm 0 0;padding:0;columns:2;font-size:8.5pt}
.leg li{break-inside:avoid;margin:0 0 .8mm}
.key{margin:0 0 1.5mm}
.key .cap{font-size:8.5pt;color:var(--grey);margin:0 0 .5mm}
.head .pno{order:-1;margin-right:2mm;align-self:center}
"""


def page_css(region, footer_left, panel_h, tw):
    name, w, h = PAGE_MM[region]
    size = "A4" if name == "A4" else "letter"
    foot = (f'@bottom-left{{content:"{footer_left}";font:8pt system-ui,Arial,sans-serif;color:#666;vertical-align:top;padding-top:3mm}}'
            f'@bottom-right{{content:"Page " counter(page);font:8pt system-ui,Arial,sans-serif;color:#666;vertical-align:top;padding-top:3mm}}'
            f'@bottom-center{{content:"{SHORT_WARNING}";font:8pt system-ui,Arial,sans-serif;color:#666;vertical-align:top;padding-top:3mm}}')
    pages = (f"@page{{size:{size};margin:14mm 14mm 16mm 14mm;{foot}}}\n"
             f"@page drawing{{size:{size} landscape;margin:10mm 10mm 14mm 10mm;{foot}}}")
    return CSS % {"accent": ACCENT, "pages": pages, "tw": num(tw), "panel_h": num(panel_h)} + iso_css()


def pretty_name(frame):
    n = frame.get("name") or "structure"
    return n.replace("-", " ").replace("_", " ").strip().capitalize()


def first_sentence(text, limit=260):
    t = " ".join(text.split())
    cut = t.find(". ")
    t = t[:cut + 1] if 0 < cut < limit else t
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "..."


def cover_html(frame, checks, name, version, date, units, structure_size, bom, views=""):
    spec = frame.get("spec", {})
    typ = TYPE_NAMES.get(spec.get("type"), (spec.get("type") or "Timber structure").replace("-", " ").capitalize())
    w, d, h = structure_size
    open_f = [f for f in checks.get("findings", []) if f["level"] in ("fix", "check")]
    ver = f"v{version}" if version else "no saved version"
    rows = [("Type", typ), ("Overall size", f"{fmt(w, units, True)} wide x {fmt(d, units, True)} deep x {fmt(h, units, True)} high"
                                              + " (including the roof overhang)"),
            ("Version", ver + (f", {date}" if date else "")),
            ("Region", ("Europe" if frame["region"] == "eu" else "United States") + (", metric (mm)" if units == "metric" else ", feet and inches"))]
    facts = "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in rows)
    if open_f:
        items = "".join(f"<li><b>{'Fix' if f['level'] == 'fix' else 'Check'}:</b> {esc(f['title'])}. {esc(first_sentence(f['text']))}</li>"
                        for f in open_f)
        verdict = (f'<div class="verdict"><b>{len(open_f)} thing{"s" if len(open_f) != 1 else ""} to settle before you build</b>'
                   f"<ul>{items}</ul></div>")
    else:
        verdict = ('<div class="verdict"><b>Looks good</b><br>The workbench\'s own checks found nothing to fix or to decide. '
                   "That is not an approval: see the notice below.</div>")
    warn = bomlib.SAFETY_NOTE.lstrip("> ").strip()
    warn = (f'<div class="warn"><b>Read this before you build</b>'
            f"<p>{esc(warn)}</p>"
            "<p>Check local rules on size, height and distance from the boundary before you buy anything. "
            "Footings are bought items: their load capacity is not checked. Wind and uplift are not covered for open structures.</p></div>")
    dec = ""
    decisions = frame.get("decisions") or bom.get("decisions")
    if decisions:
        dec = ("<h3>How it was planned</h3><p class=\"small\">What the description left open, and what the planner chose.</p><ul class=\"dec\">"
               + "".join(f"<li><b>{esc(x['what'])}:</b> {esc(x['chose'])}. {esc(x['why'][:1].upper() + x['why'][1:])}.</li>" for x in decisions)
               + "</ul>")
    how = ('<h3>How to read the drawings</h3><p class="small">The two 3D views are seen from the front-left, from above: the numbers on the right-hand one are the part numbers at the top of each drawing page. '
           "Each side is drawn on its own page. Walls are seen from outside. "
           "Floors and roofs are seen from above, with the front at the bottom of the page. Left and right are as you face the front "
           "wall from outside. Letters match the table next to the drawing. Sheathing, cladding and deck boards are not drawn "
           "(they would hide the frame) but are in the table. Print at 100% (not &quot;fit to page&quot;) for the scale shown.</p>")
    return (f'<section class="page cover"><h1>{esc(name)}</h1><p class="sub">Site pack: shopping list and drawings</p>'
            f'<table class="facts">{facts}</table>{views}{verdict}{warn}{dec}{how}</section>')


def shopping_html(bom, units):
    L = lambda mm: tl.fmt_length(mm, units)
    snap = bom.get("snapshot")
    cur = (snap or {}).get("currency")
    money = lambda x: tl.money(x, cur)
    ms = bool(snap)       # a Supplier column when priced: the supplier and, small, the product it was priced as
    sh = "<th>Supplier and product</th>" if ms else ""

    def sc(line, piece=None):
        text = bomlib.priced_as(line, piece)
        who, _, what = text.partition(": ")
        return (f"<td>{esc(who)}" + (f"<br><span class=nd>{esc(what)}</span>" if what else "") + "</td>") if ms else ""

    def prices(unit, total):
        return ("no price", "no price") if total is None else (money(unit), money(total))

    def total_cell(line):
        return esc(money(line["total"])) if line.get("priced") else "no price"
    out = ['<section class="page"><h2>Shopping list</h2>']
    if snap:
        t = bom["totals"]
        out.append(f'<p class="sub">Prices: {esc(bomlib.suppliers_text(snap))} ({esc(bomlib.price_basis(snap))}). '
                   f'A dated snapshot: the supplier\'s current price wins. '
                   f'<b>Total {esc(money(t["amount"]))}</b> for {t["priced_lines"]} of {t["lines"]} lines'
                   + (" (partial: lines marked no price are not in it)" if t["partial"] else "") + ".</p>")
    else:
        out.append('<p class="sub">No price snapshot was used, so there are no prices.</p>')
    out.append(f'<p class="small">Spare: {bom["waste_pct"]:g}% of the timber and fastener counts, rounded up. Lengths are in {esc(units)} units.</p>')
    if bom.get("problems"):
        out.append("<h3>Problems</h3><ul>" + "".join(f"<li>{esc(p)}</li>" for p in bom["problems"]) + "</ul>")
    out.append(f"<h3>Timber and cladding</h3><table><tr><th>Item</th><th>Variant</th><th>Buy</th><th class=n>Price each</th><th class=n>Line total</th>{sh}</tr>")
    for ln in bom["timber"]:
        for i, r in enumerate(ln["pieces"]):
            qty = f"{r['total_qty']} x {L(r['length_mm'])}" + (f" (incl. {r['spare']} spare)" if r["spare"] else "")
            each, tot = prices(r["unit_price"], r["line_total"])
            out.append(f"<tr><td>{esc(ln['name']) if i == 0 else ''}</td><td>{esc(ln['variant']) if i == 0 else ''}</td>"
                       f"<td>{esc(qty)}</td><td class=n>{esc(each)}</td><td class=n>{esc(tot)}</td>{sc(ln, r)}</tr>")
    out.append("</table>")
    if bom["sheets"]:
        out.append(f"<h3>Sheets</h3><table><tr><th>Item</th><th>Sheet</th><th>Buy</th><th class=n>Price each</th><th class=n>Line total</th>{sh}</tr>")
        for ln in bom["sheets"]:
            a, b = ln["sheet_size_mm"]
            qty = f"{ln['sheets_to_buy']}" + (f" (incl. {ln['spare_sheets']} spare)" if ln["spare_sheets"] else "")
            each, tot = prices(ln["unit_price"], ln["total"])
            out.append(f"<tr><td>{esc(ln['name'])}</td><td>{esc(L(a))} x {esc(L(b))}</td><td>{esc(qty)}</td>"
                       f"<td class=n>{esc(each)}</td><td class=n>{esc(tot)}</td>{sc(ln)}</tr>")
        out.append("</table>")
    nails = [f for f in bom["fasteners"] if f["kind"] == "nail"]
    screws = [f for f in bom["fasteners"] if f["kind"] != "nail"]
    if nails:
        out.append("<h3>Nails</h3><p class=small>Sold by weight: the count, with the spare, is turned into a weight and rounded up to box sizes.</p>"
                   f"<table><tr><th>Nail</th><th>Buy</th><th class=n>About</th><th class=n>Price</th>{sh}</tr>")
        for f in nails:
            u = f["weight_unit"]
            packs = bomlib.nail_packs_text(f)
            out.append(f"<tr><td>{esc(f['name'])}</td><td>{esc(packs)}</td><td class=n>{f['weight']:g} {esc(u)}</td>"
                       f"<td class=n>{total_cell(f)}</td>{sc(f)}</tr>")
        out.append("</table>")
    if screws:
        out.append(f"<h3>Structural screws and bolts</h3><table><tr><th>Item</th><th>Buy</th><th class=n>Count</th><th class=n>Price</th>{sh}</tr>")
        for f in screws:
            packs = ", ".join(f"{p['qty']} x {p['size']:g}" for p in f["packs"])
            out.append(f"<tr><td>{esc(f['name'])}</td><td>{esc(packs)}</td><td class=n>{f['to_buy']}</td>"
                       f"<td class=n>{total_cell(f)}</td>{sc(f)}</tr>")
        out.append("</table>")
    if bom["bought"]:
        out.append(f"<h3>Bought items</h3><table><tr><th>Item</th><th class=n>Quantity</th><th>Note</th><th class=n>Price</th>{sh}</tr>")
        for b in bom["bought"]:
            out.append(f"<tr><td>{esc(b['name'])}</td><td class=n>{b['qty']:g} {esc(b['unit'])}</td><td>{esc(bomlib.bought_note(b))}</td>"
                       f"<td class=n>{total_cell(b)}</td>{sc(b)}</tr>")
        out.append("</table>")
    out.append("<h3>Not on this list</h3><ul class=dec>"
               "<li>Fixings for the base: what holds the bottom plates or the frame to the floor, the ground or the footings.</li>"
               "<li>Doors and windows themselves, beyond the line item above (frames, hinges, locks, glass).</li>"
               "<li>Roofing beyond the felt area above: ridge flashing, edge trims, gutters, shingles or metal sheet.</li>"
               "<li>Paint, stain, preservative, sealant, membranes and anything for the inside.</li>"
               "<li>Tools, scaffolding, and the fixings of bought items such as ground screws and post bases.</li></ul>")
    notes = bom.get("notes") or []
    if notes:
        out.append("<p class=small>" + " ".join(esc(n) for n in notes) + "</p>")
    out.append("</section>")
    return "".join(out)


def appendix_html(bom, units, group_titles):
    L = lambda mm: tl.fmt_length(mm, units)
    out = ['<section class="page"><h2>Cut list</h2><p class="sub">For each length of timber you buy, the pieces to cut from it. '
           "Cut the long pieces first. The saw kerf is allowed for.</p>"]
    for ln in bom["timber"]:
        who = f" <span class=nd>(from {esc(ln['supplier'])})</span>" if ln.get("supplier") else ""
        out.append(f"<h3>{esc(ln['name'])}, {esc(ln['variant'])}: {ln['cuts']} cuts from {len(ln['layouts'])} pieces{who}</h3>"
                   "<table><tr><th>Piece</th><th>Length</th><th>Cuts</th><th class=n>Offcut</th></tr>")
        for p in ln["layouts"]:
            g = {}
            for c in p["cuts"]:
                k = (c["what"], round(c["length_mm"]), tuple(c["cut_deg"]), group_titles.get(c["group"], c["group"]))
                g[k] = g.get(k, 0) + 1
            cuts = "; ".join(f"{n} x {w} {L(l)}" + (f" ({a:g}/{b:g} deg)" if a or b else "") + f" <span class=nd>{esc(gt)}</span>"
                             for (w, l, (a, b), gt), n in g.items())
            out.append(f"<tr><td class=nw>{esc(p['piece'])}</td><td class=nw>{esc(L(p['stock_mm']))}</td><td>{cuts}</td><td class=n>{esc(L(p['offcut_mm']))}</td></tr>")
        out.append("</table>")
    for ln in bom["sheets"]:
        a, b = ln["sheet_size_mm"]
        out.append(f"<h3>{esc(ln['name'])}: {ln['parts']} parts from {ln['sheets_packed']} sheets ({esc(L(a))} x {esc(L(b))})</h3>"
                   "<table><tr><th>Sheet</th><th>Parts (position from the sheet corner, size)</th><th class=n>Used</th></tr>")
        for s in ln["layouts"]:
            parts = "; ".join(f"{esc(group_titles.get(p['id'].split('/')[0], p['id'].split('/')[0]))} {esc(p['id'].split('/')[-1])}: "
                              f"at {esc(L(p['x']))}, {esc(L(p['y']))}, {esc(L(p['w']))} x {esc(L(p['h']))}" + (" turned" if p["rotated"] else "")
                              for p in s["parts"])
            out.append(f"<tr><td>{s['sheet']}</td><td>{parts}</td><td class=n>{s['used_pct']:g}%</td></tr>")
        out.append("</table>")
    out.append("</section>")
    return "".join(out)


def build_pages(frame, checks, bom, version, date):
    units = frame["units"]
    region = frame["region"]
    lib = tl.load(region)
    name = pretty_name(frame)
    _, pw, ph = PAGE_MM[region]
    footer = f"{name}, version {version}" if version else name
    tw = 92.0
    panel_w, panel_h = pw - 20.0, ph - 24.0 - 10.0
    left_w = panel_w - tw - 6.0
    footings = footings_of(frame)
    lo, hi = structure_box(frame)
    allbox = [aabb(m) for m in frame["members"] if m.get("layer") != "foundations"] or [aabb(m) for m in frame["members"]]
    size = (max(b[1][0] for b in allbox) - min(b[0][0] for b in allbox), max(b[1][1] for b in allbox) - min(b[0][1] for b in allbox),
            max(b[1][2] for b in allbox) - max(0, min(b[0][2] for b in allbox) if False else 0))
    secs = make_sections(frame)
    group_titles = {s["group"]: s["title"] for s in secs}
    iso = Iso(frame)
    vw = (ph - 28.0 - 6.0) / 2
    secs_ = secs
    legend = "".join(f'<li><span class="lt">{i + 1}</span> {esc(sc["title"])}</li>' for i, sc in enumerate(secs_))
    views = ('<div class="views"><div><p class="cap">How it looks</p>' + looks_svg(iso, frame, vw, 72.0) + '</div>'
             '<div><p class="cap">The frame, by part</p>' + frame_svg(iso, frame, secs_, vw, 72.0) + '</div></div>'
             f'<ul class="leg">{legend}</ul>')
    body = [cover_html(frame, checks, name, version, date, units, size, bom, views), shopping_html(bom, units)]
    summary = []
    for sec in secs:
        # which members are drawn in any view: their letters
        probe = [View(frame, sec, v, {}, units, footings if v.get("footings") else None) for v in sec["views"]]
        drawn_ids = set(m["id"] for v in probe for m, _, _ in v.shapes)
        letters, _ = section_letters(sec, drawn_ids)
        if sec["role"] == "foundations":
            letters = {}
        rows = piece_rows(frame, sec, letters, lib, units)
        sec["letters"], sec["rows"] = letters, rows
        views = [View(frame, sec, v, letters, units, footings if v.get("footings") else None) for v in sec["views"]]
        pages = []
        for i, v in enumerate(views):
            pages.append(v)
        body.append(section_html(frame, sec, views, rows, units, left_w, panel_w, panel_h, tw, footings, lo, hi,
                                 key=key_svg(iso, frame, secs, sec, 46.0, 30.0), no=secs.index(sec) + 1))
    body.append(appendix_html(bom, units, group_titles))
    css = page_css(region, f"{esc(name)}, {'version ' + str(version) if version else 'no saved version'}".replace('"', "'"), panel_h, tw)
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(name)}: site pack</title>'
           f"<style>{css}</style></head><body>" + "\n".join(body) + "</body></html>\n")
    return doc


def pieces_table(sec, rows, units, footings):
    if sec["role"] == "foundations":
        t = ['<table class="pieces"><tr><th>No.</th><th class=n>x (from the left)</th><th class=n>y (from the front)</th></tr>']
        lo, _ = structure_box(sec["frame"])
        for i, (fx, fy, _) in enumerate(footings, 1):
            t.append(f"<tr><td><span class=lt>{i}</span></td><td class=n>{esc(fmt(fx - lo[0], units, True))}</td><td class=n>{esc(fmt(fy - lo[1], units, True))}</td></tr>")
        t.append("</table>")
        names = {}
        for _, _, n in footings:
            names[n] = names.get(n, 0) + 1
        t.append(f'<p class="note">{esc(", ".join(f"{n} x {k.lower()}" for k, n in names.items()))}. All measured from the front-left corner '
                 "of the structure to the centre of each footing. Check the diagonals between opposite footings: equal means square.</p>")
        xs = [f[0] for f in footings]
        ys = [f[1] for f in footings]
        if len(footings) > 3:
            d = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            t.append(f'<p class="note">Diagonal between the outer footings: {esc(fmt(d, units, True))}.</p>')
        return "".join(t)
    t = ['<table class="pieces"><tr><th></th><th>Piece</th><th>Section</th><th class=n>Length</th><th class=n>Qty</th></tr>']
    for r in rows:
        lt = f'<span class=lt>{esc(r["letter"])}</span>' if r["letter"] else '<span class=nd>-</span>'
        cut = f'<br><span class=nd>cut {esc(r["cuts"])}</span>' if r["cuts"] else ""
        t.append(f"<tr><td>{lt}</td><td>{esc(r['name'])}" + ("" if r["drawn"] else " <span class=nd>(not drawn)</span>") +
                 f"</td><td>{esc(r['item'])}</td><td class=n>{esc(r['length'])}{cut}</td><td class=n>{r['qty']}</td></tr>")
    t.append("</table>")
    return "".join(t)


def section_html(frame, sec, views, rows, units, left_w, panel_w, panel_h, tw, footings, lo, hi, key="", no=None):
    sec["frame"] = frame
    title = sec["title"]
    out = []
    first = views[0]
    sub = ""
    if sec["role"] == "wall":
        a, b = WALL_SIDES.get(first.spec["view"], ("", ""))
        sub = f"At the left of the drawing: the {a}. At the right: the {b}. Dimensions run from the left end of the bottom plate."
    elif first.spec["view"] == "plan":
        sub = "The left wall is at the left."
    pn = f'<span class="lt pno">{no}</span>' if no else ""
    heads = lambda t, N: f'<div class="head"><h2>{esc(t)}</h2>{pn}<span class="sc">scale 1:{num(N)} at 100%</span></div>'
    def draw_one(v, w, h):
        svg, N, sw, sh = fit(lambda n: v.draw(n), w, h)
        return svg, N
    # page 1: the first view and the table
    avail_h = panel_h - 36.0
    svg, N = draw_one(first, left_w, avail_h)
    out.append('<section class="page draw">' + heads(title, N) + f'<p class="note" style="margin:-1mm 0 2mm">{esc(sub)}</p>'
               f'<div class="drawing"><div class="panel"><p class="cap">{esc(first.spec["title"])}</p>{svg}</div>'
               f'<div><div class="key"><p class="cap">Where this part is; arrow: viewing direction</p>{key}</div>{pieces_table(sec, rows, units, footings)}</div></div></section>')
    rest = views[1:]
    if rest:
        n = len(rest)
        w = (panel_w - 6.0 * (n - 1)) / n
        panels = []
        scales = []
        for v in rest:
            s, N2 = draw_one(v, w, avail_h)
            scales.append(N2)
            panels.append(f'<div class="panel"><p class="cap">{esc(v.spec["title"])} (1:{num(N2)})</p>{s}</div>')
        out.append('<section class="page draw">' + heads(title + " (continued)", max(scales)) +
                   f'<p class="note" style="margin:-1mm 0 2mm">Letters are the same as in the table on the previous page.</p>'
                   f'<div class="cols">{"".join(panels)}</div></section>')
    return "".join(out)


# --------------------------------------------------------------------------------------------- main

def newest_version(out_dir):
    ns = vers.numbers(os.path.join(out_dir, "versions"))
    if not ns:
        return None, ""
    n = ns[-1]
    date = ""
    try:
        with open(os.path.join(out_dir, "versions", f"v{n}", "meta.json"), encoding="utf-8") as f:
            date = json.load(f).get("created", "")[:10]
    except (OSError, ValueError):
        pass
    return n, date


def load(out_dir, name):
    with open(os.path.join(out_dir, name), encoding="utf-8") as f:
        return json.load(f)


def make_html(out_dir):
    frame, checks, bom = load(out_dir, "frame.json"), load(out_dir, "checks.json"), load(out_dir, "bom.json")
    version, date = newest_version(out_dir)
    return build_pages(frame, checks, bom, version, date), frame, version


def chrome_path():
    try:
        import viewer_gif
        return viewer_gif.find_chrome()
    except SystemExit:
        return None


def print_pdf(chrome, html_path, pdf_path):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", "file://" + os.path.abspath(html_path)]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    return r.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0, r.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out_dir", help="the project's out/ folder (frame.json, checks.json, bom.json)")
    ap.add_argument("--out", help="the PDF to write (default: <out>/<project>-site-pack-v<N>.pdf)")
    ap.add_argument("--html-only", action="store_true", help="write the HTML and stop: no PDF, no need for Chrome")
    a = ap.parse_args()
    out_dir = a.out_dir
    for n in ("frame.json", "checks.json", "bom.json"):
        if not os.path.exists(os.path.join(out_dir, n)):
            sys.exit(f"site_pack: {os.path.join(out_dir, n)} is missing: build the structure first (tools/build_frame.sh)")
    doc, frame, version = make_html(out_dir)
    html_path = os.path.join(out_dir, "site-pack.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"site pack page: {html_path}")
    if a.html_only:
        return 0
    chrome = chrome_path()
    if not chrome:
        print("site_pack: the PDF needs Google Chrome (or Chromium), and it was not found. Install it, or set "
              "CHROME=/path/to/chrome and run this again. The page was written; open it in a browser and print it to PDF.",
              file=sys.stderr)
        return 1
    project = frame.get("name") or "structure"
    pdf = a.out or os.path.join(out_dir, f"{project}-site-pack" + (f"-v{version}" if version else "") + ".pdf")
    ok, err = print_pdf(chrome, html_path, pdf)
    if not ok:
        print("site_pack: Chrome did not make the PDF.\n" + err[-600:], file=sys.stderr)
        return 1
    print(f"site pack: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
