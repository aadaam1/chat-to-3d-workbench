"""Shared parts of the timber blocks: the frame being built (members, joints,
bought items, assemblies), the numbers every block reads, and the arithmetic and
geometry helpers (millimetres, Z up; see tools/frame.py for the conventions).
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402

SCHEMA = 1
WALLS = ("front", "back", "left", "right")
KINDS = ("door", "window")
EPS = 0.05                 # mm; coordinates are rounded to 0.1
MIN_CRIPPLE = 50.0         # shorter gaps above a header or below a sill are left open
MIN_SHEET = 150.0          # no sheathing sheet is narrower than this
MIN_INFILL = 50.0          # shorter gaps above a side wall's top plate are left open


class SpecError(ValueError):
    """The spec can't be built. The message starts with the field name."""


# ------------------------------------------------------------------ geometry

def r1(v):
    v = round(float(v) + 0.0, 1)
    return 0.0 if v == 0 else v


def num(v):
    """JSON-friendly: 0.1 mm rounding, whole numbers as ints."""
    v = r1(v)
    return int(v) if v == int(v) else v


def unit(v):
    out = []
    for c in v:
        c = round(float(c) + 0.0, 6)
        c = 0.0 if c == 0 else c
        out.append(int(c) if c == int(c) else c)
    return out


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def layout(span, t, spacing):
    """Left faces of members t thick along a span: one flush at each end and
    the rest centred on multiples of `spacing` from the start, dropping any
    that would leave less than t between it and the last one."""
    last = span - t
    out = [0.0]
    k = 1
    while True:
        left = k * spacing - t / 2
        if left + t > last - t + EPS:
            break
        if left >= out[-1] + t - EPS:
            out.append(left)
        k += 1
    if last > 0:
        out.append(last)
    return [r1(v) for v in out]


def split(lo, hi, candidates, maxw, what, minw=MIN_SHEET):
    """Cut points from lo to hi, each on a candidate and at most maxw apart. The
    last piece is kept at least minw wide by moving the seam before it back."""
    pts = [lo]
    cand = sorted(set(r1(c) for c in candidates))
    while hi - pts[-1] > maxw + EPS:
        ok = [c for c in cand if pts[-1] + EPS < c <= pts[-1] + maxw + EPS]
        if not ok:
            raise SpecError(f"{what}: no framing member within {maxw:g} mm to land a sheet edge on; "
                            "use a smaller stud, joist or rafter spacing")
        pts.append(ok[-1])
    pts.append(hi)
    if len(pts) >= 3 and hi - pts[-2] < minw - EPS:
        ok = [c for c in cand if pts[-3] + minw - EPS <= c <= hi - minw + EPS
              and c - pts[-3] <= maxw + EPS]
        if ok:
            pts[-2] = ok[-1]
    return pts


def deck_rows(span, step):
    """Row boundaries of a deck: whole sheets and a last short row. A last row
    under 300 mm is shared with the one before it."""
    n = math.ceil(span / step - 1e-9)
    rows = [r1(min(i * step, span)) for i in range(n)] + [r1(span)]
    if n >= 2 and span - rows[-2] < 300:
        rows[-2] = r1((rows[-3] + span) / 2)
    return rows


def sheet_cuts(span, cand, long_, row, label, what):
    """Sheet boundaries along a row, each on a framing member; odd rows start
    with a part sheet so the joints between sheets stagger."""
    step = long_ if row % 2 == 0 else long_ / 2
    pts = [0.0]
    while span - pts[-1] > step + EPS:
        ok = [c for c in cand if pts[-1] + EPS < c <= pts[-1] + step + EPS]
        if not ok:
            raise SpecError(f"{label}: no framing member to land a sheet edge on in the {what}")
        pts.append(r1(ok[-1]))
        step = long_
    if len(pts) > 2 and span - pts[-1] < 300:       # avoid a sliver at the end
        back = [c for c in cand if pts[-2] + 300 <= c < pts[-1] and span - c <= long_ + EPS]
        if back:
            pts[-1] = r1(back[-1])
    pts.append(r1(span))
    return list(zip(pts, pts[1:]))


# ------------------------------------------------------------------ helpers

def _ov(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def _pairs(pts):
    return list(zip(pts, pts[1:]))


def aabb(m):
    """World bounding box (lo, hi) of a member, from its origin, axes and size."""
    x, y = m["x"], m["y"]
    z = cross(x, y)
    o = m["origin"]
    L, W, T = m["size"]
    cs = []
    for a in (0, L):
        for b in (0, W):
            for c in (0, T):
                cs.append([o[i] + a * x[i] + b * y[i] + c * z[i] for i in range(3)])
    return [min(c[i] for c in cs) for i in range(3)], [max(c[i] for c in cs) for i in range(3)]


def _clean(pts):
    """Drop repeated and collinear points from a closed polygon."""
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > EPS or abs(p[1] - out[-1][1]) > EPS:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= EPS and abs(out[0][1] - out[-1][1]) <= EPS:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) < 1e-6:
                del out[i]
                changed = True
                break
    return out


def _poly_clip(poly, u0, u1, z0, z1):
    """`poly` (s, z; counter-clockwise) clipped to a rectangle (Sutherland-Hodgman)."""
    def clip(pts, inside, inter):
        out = []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            if inside(p):
                if not inside(q):
                    out.append(inter(q, p))
                out.append(p)
            elif inside(q):
                out.append(inter(q, p))
        return out

    def ix(c):
        return lambda q, p: (c, q[1] + (p[1] - q[1]) * (c - q[0]) / (p[0] - q[0]))

    def iz(c):
        return lambda q, p: (q[0] + (p[0] - q[0]) * (c - q[1]) / (p[1] - q[1]), c)

    pts = list(poly)
    for inside, inter in ((lambda p: p[0] >= u0 - 1e-9, ix(u0)), (lambda p: p[0] <= u1 + 1e-9, ix(u1)),
                          (lambda p: p[1] >= z0 - 1e-9, iz(z0)), (lambda p: p[1] <= z1 + 1e-9, iz(z1))):
        if not pts:
            return []
        pts = clip(pts, inside, inter)
    pts = _clean([(r1(a), r1(b)) for a, b in pts]) if pts else []
    return pts if len(pts) >= 3 and _area(pts) > 1.0 else []


def _piece(poly, u0, u1, zlow, zhigh, notch):
    """The part of the wall polygon one sheet covers: between u0 and u1 and
    zlow and zhigh, less a notch (a, b, z_top) cut up from its bottom edge."""
    if notch:
        a, b, ztop = notch
        if u0 >= a - EPS and u1 <= b + EPS:           # wholly above the opening
            return _poly_clip(poly, u0, u1, ztop, zhigh)
        if b <= u0 + EPS or a >= u1 - EPS:
            notch = None
    p = _poly_clip(poly, u0, u1, zlow, zhigh)
    if not p or not notch:
        return p
    a, b, ztop = notch
    bot = None
    for i in range(len(p)):
        q, r = p[i], p[(i + 1) % len(p)]
        if abs(q[1] - zlow) < EPS and abs(r[1] - zlow) < EPS and r[0] > q[0]:
            bot = i
            break
    if bot is None:
        return p
    path = []
    a2, b2 = max(a, u0), min(b, u1)
    path += [(u0, zlow)] if a2 > u0 + EPS else []
    path += [(a2, zlow), (a2, ztop)] if a2 > u0 + EPS else [(u0, ztop)]
    path += [(b2, ztop), (b2, zlow)] if b2 < u1 - EPS else [(u1, ztop)]
    path += [(u1, zlow)] if b2 < u1 - EPS else []
    out = p[:bot] + path + p[bot + 2:]
    return _clean(out)


def _area(pts):
    return abs(sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))) / 2


def _is_rect(local, w, h):
    return len(local) == 4 and all(abs(p[0]) < EPS or abs(p[0] - w) < EPS for p in local) \
        and all(abs(p[1]) < EPS or abs(p[1] - h) < EPS for p in local)


def _poly_len(poly, p, q, z0, z1):
    """Length of a member's face centreline inside the sheet polygon (s, z): a
    vertical member along its centre line over the part of its face between
    p and q, a horizontal one along its own."""
    if (z1 - z0) >= (q - p):
        return _cross_len(poly, (p + q) / 2, True, z0, z1)
    return _cross_len(poly, (z0 + z1) / 2, False, p, q)


def _cross_len(poly, c, vertical, lo, hi):
    """Length inside `poly` of the line s = c (vertical) or z = c, between lo and hi.
    Averaged over a small nudge each way so a line along an edge counts once."""
    i0, i1 = (0, 1) if vertical else (1, 0)
    tot = 0.0
    for dc in (0.013, -0.013):
        xs = []
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            if (a[i0] - (c + dc)) * (b[i0] - (c + dc)) < 0:
                f = (c + dc - a[i0]) / (b[i0] - a[i0])
                xs.append(a[i1] + f * (b[i1] - a[i1]))
        xs.sort()
        tot += sum(max(0.0, min(b, hi) - max(a, lo)) for a, b in zip(xs[0::2], xs[1::2])) / 2
    return tot


def _norm(d):
    """The spec as stored: whole numbers as ints, other floats to 6 places."""
    if isinstance(d, dict):
        return {k: _norm(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_norm(v) for v in d]
    if isinstance(d, float):
        d = round(d, 6)
        return int(d) if d == int(d) else d
    return d


# ------------------------------------------------------------------ the frame

class Frame:
    """What is being built: members, joints, bought items and the assemblies
    that made them. Every block adds to one Frame."""

    def __init__(self):
        self.members, self.joints, self.bought = [], [], []
        self.ids = set()
        self.assemblies = []

    def add(self, mid, kind, group, layer, item, size, centre, x, y, cut=(0, 0), outline=None,
            treated=False, variant="sawn"):
        if mid in self.ids:
            raise AssertionError(f"duplicate id {mid}")
        self.ids.add(mid)
        z = cross(x, y)
        origin = [centre[i] - size[0] / 2 * x[i] - size[1] / 2 * y[i] - size[2] / 2 * z[i]
                  for i in range(3)]
        self.members.append({
            "id": mid, "kind": kind, "group": group, "layer": layer, "item": item,
            "variant": variant, "treated": treated,
            "size": [num(v) for v in size], "origin": [num(v) for v in origin],
            "x": unit(x), "y": unit(y), "cut_deg": [num(cut[0]), num(cut[1])],
            "outline": None if outline is None else [[num(a), num(b)] for a, b in outline]})
        return mid

    def box(self, mid, kind, group, layer, item, lo, hi, laxis, waxis, **kw):
        """An axis-aligned member from its corners; laxis and waxis are world axis
        numbers (0 X, 1 Y, 2 Z); the thickness runs along the third."""
        size3 = [hi[i] - lo[i] for i in range(3)]
        taxis = 3 - laxis - waxis
        e = lambda i: [1 if j == i else 0 for j in range(3)]
        return self.add(mid, kind, group, layer, item,
                        [size3[laxis], size3[waxis], size3[taxis]],
                        [(lo[i] + hi[i]) / 2 for i in range(3)], e(laxis), e(waxis), **kw)

    def joint(self, typ, a, b, **extra):
        j = {"type": typ, "a": a, "b": b}
        j.update({k: num(v) if isinstance(v, float) else v for k, v in extra.items()})
        self.joints.append(j)

    def member(self, mid):
        return next(m for m in self.members if m["id"] == mid)

    def assembly(self, aid, typ, spans):
        """Record an assembly: its id, type and the spans the checks read
        (each {"role", "kind", "spacing_mm", ...})."""
        self.assemblies.append({"id": aid, "type": typ, "spans": spans})


class Layout:
    """The numbers the blocks share, worked out before anything is built: the
    library items, section sizes, the floor top and the heights."""

    def __init__(self, spec, lib):
        self.s, self.lib = spec, lib
        s = self.s
        self.W, self.D = s["width"], s["depth"]
        self.frame = tl.item(lib, s["frame_item"])
        self.t, self.w = self.frame["thickness_mm"], self.frame["width_mm"]
        fl = tl.item(lib, s["floor_item"])
        self.tj, self.hj = fl["thickness_mm"], fl["width_mm"]
        self.raf = tl.item(lib, s["rafter_item"])
        self.tr, self.wr = self.raf["thickness_mm"], self.raf["width_mm"]
        self.fdeck = tl.item(lib, s["floor_deck"])
        self.rdeck = tl.item(lib, s["roof_deck"])
        self.sheath = tl.item(lib, s["sheathing"])
        self.clad = tl.item(lib, s["cladding"])
        self.ts, self.tc = self.sheath["thickness_mm"], self.clad["thickness_mm"]
        self.zd = self.hj + self.fdeck["thickness_mm"]          # top of the floor deck
        self.gable = s["type"] == "gable-shed"
        if self.gable:            # both eave walls the same height; the gable walls' top plates are level too
            self.hf = self.hb = s["height_eaves"]
        else:
            self.hf, self.hb = s["height_front"], s["height_back"]
        self.courses = 2 if s["top_plate"] == "double" else 1     # top plate courses
        hd = tl.item(lib, s["header_item"])
        self.th, self.hh = hd["thickness_mm"], hd["width_mm"]     # one header ply: thickness, depth
        self.plies = 2 if 2 * self.th <= self.w + EPS else 1

    def height_field(self, wall):
        """The description field that sets a wall's height, for error messages."""
        if self.gable:
            return "height_eaves"
        return "height_front" if wall == "front" else "height_back"
