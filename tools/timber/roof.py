"""A mono-pitch roof: rafters on two bearing plates (the higher front wall and
the lower back wall), a flying rafter and outriggers for the side overhang,
blocking, fascia, bargeboards, a deck of sheets and the roofing bought to cover
it. Rafter tops are flush; the roof's line (RoofLine) is known before any wall
is built, so the walls can fill up to it."""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import timberlib as tl  # noqa: E402
import framing as fr_rules  # noqa: E402
from timber.store import EPS, _norm, _ov, layout, r1, sheet_cuts, deck_rows  # noqa: E402

fr = fr_rules


class RoofLine:
    """The roof's line, worked out before anything is built: slope from the
    front wall's top plate down to the back wall's, as a pure function of Y."""

    def __init__(self, lay):
        self.hf, self.w = lay.hf, lay.w
        self.k = (lay.hf - lay.hb) / (lay.D - lay.w)        # roof slope, rise over run
        self.ang = math.atan(self.k)
        self.sin, self.cos = math.sin(self.ang), math.cos(self.ang)

    def underside(self, y):
        """Height of the rafter underside above world Y."""
        return self.hf - (y - self.w) * self.k

    gable = False

    def top_over(self, a, b):
        """Height of the underside over a stud between Y a and b: the side
        walls' infill is cut to the long point, at the front face (a)."""
        return self.underside(a)

    def cut_deg(self, a, b):
        return round(math.degrees(self.ang), 1)

class SlopeRoof:
    """What a sloping roof's members share: a member along the slope, plumb cut
    at both ends with its top flush with the rafter tops, and a block of the
    rafter section square to the slope. The slope is described by `d` (down the
    slope), `nrm` (up from the underside) and `p0` (the underside point at the
    plumb line the lengths along the slope are measured from), set by the roof
    before it builds."""

    def __init__(self, frame, lay, line):
        self.fr, self.line = frame, line
        self.s, self.lib, self.W, self.D, self.w = lay.s, lay.lib, lay.W, lay.D, lay.w
        self.tr, self.wr, self.rdeck = lay.tr, lay.wr, lay.rdeck
        self.sin, self.cos, self.ang = line.sin, line.cos, line.ang
        self.add, self.box, self.joint, self.bought = frame.add, frame.box, frame.joint, frame.bought

    def slope_underside(self, y):
        """Height of the rafter underside's line (extended) above Y."""
        return self.line.underside(y)

    def slope_member(self, mid, kind, item, x0, t, width, y0=None, y1=None, **kw):
        """A member along the slope from the plumb line at Y y0 (the high end;
        default the front eave) to the one at y1 (default the back eave), plumb
        cut at both ends, its top flush with the rafter tops, `width` deep square
        to the slope and `t` thick from x0 along X."""
        oh, D, sn, cs = self.s["overhang"], self.D, self.sin, self.cos
        d, nrm = self.d, self.nrm
        if y0 is None:
            y0 = -oh
        if y1 is None:
            y1 = D + oh
        top_f = self.slope_underside(y0) + self.wr / cs
        oy, oz = y0 - width * sn, top_f - width * cs
        L = (y1 - oy) / cs
        tw = width * sn / cs
        outline = [(tw, 0.0), (L, 0.0), (L - tw, width), (0.0, width)]
        c = [x0 + t / 2, oy + L / 2 * d[1] + width / 2 * nrm[1], oz + L / 2 * d[2] + width / 2 * nrm[2]]
        cut = round(math.degrees(self.ang), 1)
        return self.add(mid, kind, "roof", "roof", item, [L, width, t], c, d, nrm,
                        cut=(cut, cut), outline=outline, **kw)

    def slope_block(self, mid, kind, x0, x1, u):
        """A block of the rafter section square to the slope between x0 and x1,
        flush with the rafters top and bottom, centred at u along the underside
        (u = 0 at the plumb line of `p0`)."""
        p0, d, nrm, wr = self.p0, self.d, self.nrm, self.wr
        c = [(x0 + x1) / 2, p0[1] + u * d[1] + wr / 2 * nrm[1], p0[2] + u * d[2] + wr / 2 * nrm[2]]
        return self.add(mid, kind, "roof", "roof", self.s["rafter_item"], [x1 - x0, wr, self.tr],
                        c, (1, 0, 0), nrm)


class MonoRoof(SlopeRoof):
    """The roof. It is given the line, the ids of the two plates the rafters bear
    on and the ids of each side wall's infill studs. Exposes `underside(y)` (height
    of the rafter underside above world Y), `rafters` (ids), `rafter_x`, `flying`,
    `barges`, `roof_blocks`, `roof_sheets` and `deck_len`; `buy()` adds the roofing."""

    def __init__(self, frame, lay, line, front_bear, back_bear, infill):
        super().__init__(frame, lay, line)
        self.front_bear, self.back_bear, self.infill = front_bear, back_bear, infill

    def underside(self, y):
        return self.line.underside(y)

    def build(self):
        self.roof()
        self.fr.assembly("roof", "mono-roof", [
            {"role": "rafters", "kind": "rafter", "spacing_mm": _norm(self.s["rafter_spacing"]),
             "deck": self.s["roof_deck"], "deck_role": "roof", "deck_group": "roof"}])
        return self

    def roof(self):
        s, W, D, w, tr, wr = self.s, self.W, self.D, self.w, self.tr, self.wr
        oh, os_, sn, cs = s["overhang"], s["overhang_side"], self.sin, self.cos
        self.d = d = (0, cs, -sn)              # down the slope
        self.nrm = nrm = (0, sn, cs)           # up from the underside
        self.lu = lu = (D + 2 * oh) / cs       # underside length, plumb line to plumb line
        tan_a = sn / cs
        self.p0 = p0 = (0.0, -oh, self.line.underside(-oh))
        ri = s["rafter_item"]
        xs = layout(W, tr, s["rafter_spacing"])
        self.rafter_x, self.rafters = xs, []
        top_f, top_b = self.front_bear, self.back_bear
        for i, x0 in enumerate(xs, 1):
            rid = self.slope_member(f"roof/rafter-{i:02d}", "rafter", ri, x0, tr, wr)
            self.rafters.append(rid)
            self.joint("rafter-plate", rid, top_f)
            self.joint("rafter-plate", rid, top_b)
        for nm, rid in (("left", self.rafters[0]), ("right", self.rafters[-1])):
            for iid in self.infill[nm]:
                self.joint("stud-plate", iid, rid)
        # the side overhang: a flying rafter each side, carried on outriggers
        self.flying = []
        if os_ > 0:
            for nm, x0 in (("left", -os_), ("right", W + os_ - tr)):
                self.flying.append(self.slope_member(f"roof/flying-rafter-{nm}", "rafter", ri, x0, tr, wr))
        # the fascia and bargeboards' section: the deck runs out over them
        fi = s["fascia_item"]
        fit = tl.item(self.lib, fi)
        tf, wf = fit["thickness_mm"], fit["width_mm"]
        ext = tf / cs                          # the fascia's thickness, measured down the slope
        # deck rows down the slope, from the front fascia's outer face to the back
        # one's; blocking under the seams between the rafters
        short, long_ = self.rdeck["size_mm"]
        rows = deck_rows(lu + 2 * ext, short)
        u_off = -wr * tan_a - ext              # the rafters' top front corner, less the fascia
        self.deck_len = lu + 2 * ext
        seams = [u_off + u for u in rows[1:-1]]
        # blocking over the walls: outer face on the frame's outer face, front and back
        eaves = [oh / cs + tr / 2, (D + oh - wr * sn) / cs - tr / 2]
        eaves = [u for u in eaves if all(abs(u - v) >= tr for v in seams)]
        self.roof_blocks = []
        bl = 0
        for k, u in enumerate(sorted(eaves + seams)):
            seam = u in seams
            for xa, xb in zip(xs, xs[1:]):
                x0, x1 = xa + tr, xb
                if x1 - x0 < EPS:
                    continue
                if seam:
                    bl += 1
                    bid = self.slope_block(f"roof/blocking-{bl:02d}", "blocking", x0, x1, u)
                    self.roof_blocks.append((bid, x0, x1, u - u_off))
                else:
                    side = "front" if u < lu / 2 else "back"
                    n = sum(1 for m in self.fr.ids if m.startswith(f"roof/eave-{side}-")) + 1
                    bid = self.slope_block(f"roof/eave-{side}-{n:02d}", "blocking", x0, x1, u)
                    self.roof_blocks.append((bid, x0, x1, u - u_off))
                self.joint("blocking-rafter", bid, self.rafters[xs.index(xa)])
                self.joint("blocking-rafter", bid, self.rafters[xs.index(xb)])
        # the ladders: outriggers from the end rafter to the flying rafter
        if self.flying:
            ends = (tr / 2, lu - wr * tan_a - tr / 2)
            at = fr.ladder(ends[0], ends[1], eaves + seams, s["rafter_spacing"], tr)
            for nm, fly, rid, (x0, x1) in (("left", self.flying[0], self.rafters[0], (-os_ + tr, 0.0)),
                                           ("right", self.flying[1], self.rafters[-1], (W, W + os_ - tr))):
                for i, u in enumerate(at, 1):
                    oid = self.slope_block(f"roof/outrigger-{nm}-{i:02d}", "outrigger", x0, x1, u)
                    self.roof_blocks.append((oid, x0, x1, u - u_off))
                    self.joint("blocking-rafter", oid, rid)
                    self.joint("blocking-rafter", oid, fly)
        # fascia on the rafter ends (the back one's top dropped to clear the
        # deck running down over it), bargeboards on the outer rafters
        self.barges = []
        outer = self.flying or [self.rafters[0], self.rafters[-1]]
        ends = self.rafters + self.flying
        for nm, y, ztop in (("front", -oh - tf, self.line.underside(-oh) + wr / cs),
                            ("back", D + oh, self.line.underside(D + oh) + wr / cs - tf * tan_a)):
            fid = self.box(f"roof/fascia-{nm}", "fascia", "roof", "roof", fi,
                           (-os_ - tf, y, ztop - wf), (W + os_ + tf, y + tf, ztop), 0, 2)
            for rid in ends:
                self.joint("fascia-rafter", fid, rid)
        for nm, x0, rid in (("left", -os_ - tf, outer[0]), ("right", W + os_, outer[1])):
            bid = self.slope_member(f"roof/bargeboard-{nm}", "bargeboard", fi, x0, tf, wf)
            self.joint("barge-rafter", bid, rid, edge_mm=lu)
            self.barges.append((bid, x0))
        # the deck, edge to edge over the bargeboards, each sheet edge on a rafter
        allx = sorted(self.rafter_x + ([-os_, W + os_ - tr] if self.flying else []))
        cand = [x0 + tr / 2 + os_ + tf for x0 in allx]
        td = self.rdeck["thickness_mm"]
        n = 0
        self.roof_sheets = []
        for r, (u0, u1) in enumerate(zip(rows, rows[1:])):
            for a, b in sheet_cuts(W + 2 * (os_ + tf), cand, long_, r, "width", "roof deck"):
                x0, x1 = r1(a - os_ - tf), r1(b - os_ - tf)
                n += 1
                uc = u_off + (u0 + u1) / 2
                ctr = [(x0 + x1) / 2,
                       p0[1] + uc * d[1] + (wr + td / 2) * nrm[1],
                       p0[2] + uc * d[2] + (wr + td / 2) * nrm[2]]
                sid = self.add(f"roof/deck-{n:02d}", "sheet", "roof", "roof", s["roof_deck"],
                               [x1 - x0, u1 - u0, td], ctr, (1, 0, 0), d)
                self.roof_sheets.append((sid, x0, x1, u0, u1))
        rafters = list(zip(self.rafters, self.rafter_x))
        if self.flying:
            rafters += [(self.flying[0], -os_), (self.flying[1], W + os_ - tr)]
        for sid, x0, x1, u0, u1 in self.roof_sheets:
            for rid, rx in rafters:
                ox = _ov(x0, x1, rx, rx + tr)
                if ox > EPS:
                    self.joint("sheet-frame", sid, rid, edge_mm=u1 - u0)
            for bid, bx in self.barges:
                if _ov(x0, x1, bx, bx + tf) > EPS:
                    self.joint("sheet-frame", sid, bid, edge_mm=u1 - u0)
            for nm, at in (("front", 0.0), ("back", self.deck_len)):
                if abs(u0 - at) <= EPS or abs(u1 - at) <= EPS:
                    self.joint("sheet-frame", sid, f"roof/fascia-{nm}", edge_mm=x1 - x0)
            for bid, b0, b1, bu in self.roof_blocks:
                if u0 - EPS <= bu <= u1 + EPS and _ov(x0, x1, b0, b1) > EPS:
                    self.joint("sheet-frame", sid, bid, edge_mm=_ov(x0, x1, b0, b1))

    def buy(self):
        """The roofing it covers the deck with, as a bought item (by area)."""
        tf = tl.item(self.lib, self.s["fascia_item"])["thickness_mm"]
        wide = self.W + 2 * (self.s["overhang_side"] + tf)
        area = (wide / 1000) * (self.deck_len / 1000)
        note = f"roof area ({wide / 1000:g} x {self.deck_len / 1000:.3f} m on the slope) plus 10% overlap"
        self.bought.append({"item": self.s["roofing"], "qty": round(area * 1.1, 2), "unit": "m2",
                            "note": note})
