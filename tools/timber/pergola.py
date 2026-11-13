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

    def build(self, L, Wd, z0, beam_plies, bearing, overhang, span):
        """`z0` the beams' tops; `beam_plies` the ids of every beam ply (to join to)."""
        self.us = layout(L, self.t, self.spacing)
        for i, u0 in enumerate(self.us, 1):
            rid = self.ax.box(self.fr, f"rafters/rafter-{i:02d}", "rafter", self.group, "roof", self.key,
                              (u0, 0.0, z0), (u0 + self.t, Wd, z0 + self.h), 1, 2, **self.kw)
            self.ids.append(rid)
            for pid in beam_plies:
                self.fr.joint("rafter-beam", rid, pid)
        self.top = z0 + self.h
        self.fr.assembly("rafters", "pergola-rafters", [
            {"role": "rafters", "kind": "rafter", "item": self.key, "spacing_mm": r1(self.spacing),
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

    def add(self, line, u_face, side, zb, leg, post_id, plies):
        """A brace on the post face at u_face; side +1 goes toward higher u, -1 toward lower."""
        L, h, z, outline = brace_geometry(leg, self.w, zb)
        n = len(self.records) + 1
        u = u_face + side * h
        c = C45
        x = self.ax.vec(side * c, 0.0, c)
        y = self.ax.vec(-side * c, 0.0, c)
        bid = self.fr.add(f"braces/brace-{n:02d}", "brace", self.group, "frame", self.key,
                          [L, self.w, self.t], self.ax.pt(u, line, z), x, y, cut=(45, 45), outline=outline, **self.kw)
        self.fr.joint("brace-post", bid, post_id)
        for pid in plies:
            self.fr.joint("brace-beam", bid, pid)
        self.records.append({"id": bid, "post": post_id, "side": side, "leg_mm": r1(leg), "line": r1(line)})
        return bid

    def assembly(self):
        if self.records:
            self.fr.assembly("braces", "braces", [
                {"role": "knee braces", "kind": "brace", "item": self.key, "count": len(self.records),
                 "angle_deg": 45, "leg_mm": max(r["leg_mm"] for r in self.records)}])
