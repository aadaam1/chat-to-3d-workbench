"""Pergola blocks: rafters across two beams (with an overhang past each beam),
slats across the rafters, and knee braces from the posts up to the beams.

Everything is built in a local frame, `u` along the beams, `v` across them, `z`
up, and mapped to the world by `Axes` (the beams run along X, or along Y).
Millimetres, Z up, the ground at Z 0.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
from timber.store import SpecError, layout, r1  # noqa: E402

C45 = math.sqrt(0.5)
MIN_BRACE_CLEAR = 700.0      # mm of beam past a post face before a brace is expected on that side
MIN_BRACE_LEG = 250.0        # mm, the shortest centreline run of a brace the generator draws
BRACE_CLEAR_SHARE = 0.45     # a brace's foot may use at most this share of the gap to the next post


def clip_half_plane(poly, f):
    """`poly` ((s, z) points) clipped to f(p) >= 0, f linear (Sutherland-Hodgman)."""
    out = []
    for i, p in enumerate(poly):
        q = poly[i - 1]
        fp, fq = f(p), f(q)
        if fp >= 0:
            if fq < 0:
                t = fq / (fq - fp)
                out.append((q[0] + (p[0] - q[0]) * t, q[1] + (p[1] - q[1]) * t))
            out.append(p)
        elif fq >= 0:
            t = fq / (fq - fp)
            out.append((q[0] + (p[0] - q[0]) * t, q[1] + (p[1] - q[1]) * t))
    return out


def sloped_brace(leg, w, u0, m):
    """A 45 degree brace under a sloping underside, in the plane (s horizontal out from a post
    face, z up): a band `w` wide whose centreline rises at 45 degrees from the foot and meets the
    underside z = u0 + m * s at s = leg, cut plumb against the post (s = 0) and along the
    underside at the head. Returns the quadrilateral's corners as (s, z)."""
    zc = u0 + m * leg - leg                       # centreline height at s = 0
    hw = w * C45                                  # half the band's height measured vertically
    big = 5000.0
    poly = [(-big, zc - big - hw), (big, zc + big - hw), (big, zc + big + hw), (-big, zc - big + hw)]
    poly = clip_half_plane(poly, lambda p: p[0])
    poly = clip_half_plane(poly, lambda p: u0 + m * p[0] - p[1])
    return poly


class Axes:
    """Maps the local frame (u along the beams, v across, z up) to the world."""

    def __init__(self, axis):
        self.axis, self.cross = axis, 1 - axis

    def pt(self, u, v, z=0.0):
        p = [0.0, 0.0, z]
        p[self.axis], p[self.cross] = u, v
        return p

    def vec(self, u, v, z):
        return self.pt(u, v, z)

    def box(self, fr, mid, kind, group, layer, item, lo, hi, laxis, waxis, **kw):
        """A box from local corners (u, v, z); laxis, waxis are local axes (0 u, 1 v, 2 z)."""
        a, b = self.pt(*lo), self.pt(*hi)
        lo_w = [min(a[i], b[i]) for i in range(3)]
        hi_w = [max(a[i], b[i]) for i in range(3)]
        world = lambda k: [self.axis, self.cross, 2][k]
        return fr.box(mid, kind, group, layer, item, lo_w, hi_w, world(laxis), world(waxis), **kw)


def brace_geometry(leg, w, zb):
    """The parallelogram of a 45 degree brace whose centreline runs `leg` out from
    a post face and `leg` up to a beam underside at height zb, `w` wide square to
    its axis, ends cut plumb against the post and square (level) against the beam.
    Returns (L, h, z, outline): the long edge, the centre's distance from the post
    face and its height, and the outline in the member's own (along, across) plane."""
    li, lo = leg - w * C45, leg + w * C45          # legs of the inner (corner) and outer edge
    L = 2.0 * lo * C45
    outline = [(0.0, 0.0), (L, 0.0), ((li + lo) * C45, w), (w, w)]
    h = C45 * (L - w) / 2.0
    z = C45 * (L + w) / 2.0 + (zb - lo)
    return L, h, z, outline


class Rafters:
    """Rafters across the beams, on top of them, at a spacing along the beams,
    one flush at each end, reaching `overhang` past the outer face of each beam."""

    def __init__(self, frame, lib, ax, item_key, spacing, group="roof", treated=True):
        self.fr, self.ax, self.key, self.spacing, self.group = frame, ax, item_key, spacing, group
        it = tl.item(lib, item_key)
        self.t, self.h = it["thickness_mm"], it["width_mm"]      # thickness across, depth up
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")
        self.ids, self.us = [], []

    def positions(self, L, over):
        """Left faces of the rafters: one flush at each end, one centred on every
        post line `over` (u of each post), and more between them so that no two
        are further apart (centre to centre) than the spacing."""
        t, hs = self.t, self.t / 2.0
        fixed = sorted({r1(min(max(u, hs), L - hs)) for u in over} | {r1(hs), r1(L - hs)})
        keep = []
        for c in fixed:                       # two rafters closer than their thickness are one
            if keep and c - keep[-1] < t + 1.0:
                if c in (r1(L - hs),):
                    keep[-1] = c
                continue
            keep.append(c)
        cs = [keep[0]]
        for a, b in zip(keep, keep[1:]):
            n = max(1, math.ceil((b - a) / self.spacing - 1e-9))
            cs += [r1(a + (b - a) * i / n) for i in range(1, n + 1)]
        return [r1(c - hs) for c in cs]

    def build(self, L, Wd, z0, beam_plies, bearing, overhang, span, over=()):
        """`z0` the beams' tops; `beam_plies` the ids of every beam ply (to join to);
        `over` the u of each post, where a rafter is centred."""
        self.us = self.positions(L, over)
        gap = max((b - a for a, b in zip(self.us, self.us[1:])), default=self.spacing)
        for i, u0 in enumerate(self.us, 1):
            rid = self.ax.box(self.fr, f"rafters/rafter-{i:02d}", "rafter", self.group, "roof", self.key,
                              (u0, 0.0, z0), (u0 + self.t, Wd, z0 + self.h), 1, 2, **self.kw)
            self.ids.append(rid)
            for pid in beam_plies:
                self.fr.joint("rafter-beam", rid, pid)
        self.top = z0 + self.h
        self.fr.assembly("rafters", "pergola-rafters", [
            {"role": "rafters", "kind": "rafter", "item": self.key, "spacing_mm": r1(min(self.spacing, gap)),
             "span_mm": r1(span), "overhang_mm": r1(overhang), "supports": [r1(b) for b in bearing]}])
        return self


class Slats:
    """Slats lying flat across the rafters (along the beams), evenly spaced, one flush at each edge."""

    def __init__(self, frame, lib, ax, item_key, spacing, group="roof", treated=True):
        self.fr, self.ax, self.key, self.spacing, self.group = frame, ax, item_key, spacing, group
        it = tl.item(lib, item_key)
        self.t, self.w = it["thickness_mm"], it["width_mm"]       # thickness up, width across
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")
        self.ids = []

    def build(self, L, Wd, z0, rafter_ids):
        vs = layout(Wd, self.w, self.spacing)
        for i, v0 in enumerate(vs, 1):
            sid = self.ax.box(self.fr, f"slats/slat-{i:02d}", "slat", self.group, "roof", self.key,
                              (0.0, v0, z0), (L, v0 + self.w, z0 + self.t), 0, 1, **self.kw)
            self.ids.append(sid)
            for rid in rafter_ids:
                self.fr.joint("slat-rafter", sid, rid, crossings=1)
        self.top = z0 + self.t
        self.fr.assembly("slats", "slats", [
            {"role": "slats", "kind": "slat", "item": self.key, "spacing_mm": r1(self.spacing), "count": len(self.ids)}])
        return self


class KneeBraces:
    """Knee braces at 45 degrees from a post face up to the underside of the beam
    that sits on it, in the plane of the beam. `build` puts one on each side of
    each post where the beam goes on far enough (see MIN_BRACE_CLEAR)."""

    def __init__(self, frame, lib, ax, item_key, leg, group="frame", treated=True):
        self.fr, self.ax, self.key, self.leg, self.group = frame, ax, item_key, leg, group
        it = tl.item(lib, item_key)
        self.w, self.t = it["width_mm"], it["thickness_mm"]       # width in the plane, thickness across
        self.kw = dict(treated=treated, variant="impregnated" if treated else "sawn")
        self.records = []

    def leg_for(self, clear):
        """Centreline run of a brace for `clear` mm of free beam between a post face and what is next."""
        return min(self.leg, BRACE_CLEAR_SHARE * clear - self.w * C45)

    def lowest(self, leg):
        """How far below the beam underside the foot of a brace of this centreline run reaches."""
        return leg + self.w * C45

    def add(self, line, u_face, side, zb, leg, post_id, plies, across=False, thick=None):
        """A brace on a post face. Along the beams (default): in the beam's plane at v = line,
        its foot on the post face at u_face, side +1 toward higher u, -1 toward lower, its head
        under the beam at height zb. Across the beams (`across`): in the plane at u = `line`, its
        foot on the post face at v = u_face, side +1 toward higher v, its head under the rafter
        (`plies` is then the rafter to join) at height zb. `thick` rips the brace thinner."""
        L, h, z, outline = brace_geometry(leg, self.w, zb)
        n = 1 + sum(1 for r in self.records if r["across"] == across)
        c = C45
        T = self.t if thick is None else min(self.t, thick)
        if across:
            pos, x, y = self.ax.pt(line, u_face + side * h, z), self.ax.vec(0.0, side * c, c), self.ax.vec(0.0, -side * c, c)
        else:
            pos, x, y = self.ax.pt(u_face + side * h, line, z), self.ax.vec(side * c, 0.0, c), self.ax.vec(-side * c, 0.0, c)
        bid = self.fr.add(f"braces/{'cross' if across else 'brace'}-{n:02d}", "brace", self.group, "frame", self.key,
                          [L, self.w, T], pos, x, y, cut=(45, 45), outline=outline, **self.kw)
        self.fr.joint("brace-post", bid, post_id)
        for pid in plies:
            self.fr.joint("brace-rafter" if across else "brace-beam", bid, pid)
        self.records.append({"id": bid, "post": post_id, "side": side, "leg_mm": r1(leg), "line": r1(line),
                             "across": across})
        return bid

    def add_sloped(self, u, v_face, side, leg, under, post_id, head_id, thick):
        """A brace across the beams, in the plane at `u`, its foot on a post face at v = v_face (side
        +1 toward higher v), its head under a sloping member (`head_id`, a rafter) whose underside
        height is `under(v)`, a straight line over the brace. Cut plumb at the foot and along the
        underside at the head. `thick` rips it to the rafter's thickness. Returns (id, lowest z)."""
        u0 = under(v_face)
        m = (under(v_face + side * 100.0) - u0) / 100.0
        poly = sloped_brace(leg, self.w, u0, m)
        c = C45
        a = [((s_ + z_) * c, (-s_ + z_) * c) for s_, z_ in poly]      # (along, across) of each corner
        a0, a1 = min(p[0] for p in a), max(p[0] for p in a)
        b0, b1 = min(p[1] for p in a), max(p[1] for p in a)
        La, wb = a1 - a0, b1 - b0
        am, bm = (a0 + a1) / 2.0, (b0 + b1) / 2.0
        sc, zc = (am - bm) * c, (am + bm) * c
        T = self.t if thick is None else min(self.t, thick)
        n = 1 + sum(1 for r in self.records if r["across"])
        bid = self.fr.add(f"braces/cross-{n:02d}", "brace", self.group, "frame", self.key, [La, wb, T],
                          self.ax.pt(u, v_face + side * sc, zc), self.ax.vec(0.0, side * c, c),
                          self.ax.vec(0.0, -side * c, c), cut=(45, 45),
                          outline=[(p[0] - a0, p[1] - b0) for p in a], **self.kw)
        self.fr.joint("brace-post", bid, post_id)
        self.fr.joint("brace-rafter", bid, head_id)
        self.records.append({"id": bid, "post": post_id, "side": side, "leg_mm": r1(leg), "line": r1(u), "across": True})
        return bid, min(p[1] for p in poly)

    def assembly(self):
        if self.records:
            self.fr.assembly("braces", "braces", [
                {"role": "knee braces", "kind": "brace", "item": self.key, "count": len(self.records), "across_count": sum(1 for r in self.records if r["across"]),
                 "angle_deg": 45, "leg_mm": max(r["leg_mm"] for r in self.records)}])
